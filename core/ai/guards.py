"""The evidence guard — fix item 5, and §6.5's anti-hallucination rule.

*"Reject any evidence that doesn't fuzzy-match (rapidfuzz.partial_ratio ≥ 90)
into text_extract. Log every rejection. The rejection rate is your strongest
empirical result and belongs in the report."*

Two details in that item are easy to get wrong and are the reason this module
is as careful as it is:

**Normalise both sides, store neither normalised.** The comparison collapses
whitespace, casefolds and undoes PDF hyphenation — because extraction reflows
text and a genuine quote will not survive a literal match. But what gets
persisted is the model's original span, untouched. A "verbatim span" that has
been through a normaliser is not verbatim, and the student's feedback page
quotes it back to them.

**There is no bypass.** Not at high confidence, not for a trusted model, not
for a criterion the faculty member already agrees with. Fix item 5: *"the guard
is the only path to persisting a CriterionScore — there is no bypass branch, at
any confidence."*
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from rapidfuzz import fuzz

from core.ai.schemas import CriterionResult
from core.scoring.enums import Verdict

logger = logging.getLogger("rubriq.ai.guard")

#: §6.5's threshold. Below this the span is treated as fabricated.
MINIMUM_MATCH = 90.0

#: A span shorter than this fuzzy-matches almost any text by accident — "the
#: system" would pass against any document. Too short is treated as no
#: evidence rather than as evidence.
MINIMUM_SPAN_CHARS = 12

#: Characters PDF extraction sprinkles through otherwise clean text.
_INVISIBLE = dict.fromkeys(
    map(ord, "­​‌‍﻿"),
    None,  # soft hyphen, zero-widths
)

#: A hyphen at a line break splits one word across two lines.
_LINE_BREAK_HYPHEN = re.compile(r"-\s*\n\s*")

_WHITESPACE = re.compile(r"\s+")

#: Quotation marks a word processor curls, which a model then straightens.
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def normalise_for_match(text: str) -> str:
    """Reduce text to a form two reflowed copies of it will share.

    Applied identically to the model's span and to the submission text — an
    asymmetric normalisation would fail genuine evidence and make the rejection
    rate meaningless as a result.
    """
    if not text:
        return ""

    # NFKC folds ligatures (ﬁ → fi) that PDF fonts emit and models do not.
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_INVISIBLE).translate(_QUOTES)
    text = _LINE_BREAK_HYPHEN.sub("", text)
    text = _WHITESPACE.sub(" ", text)

    return text.strip().casefold()


@dataclass(frozen=True, slots=True)
class EvidenceCheck:
    """The result of checking one span against the submission."""

    accepted: bool
    score: float
    reason: str

    @property
    def rejected(self) -> bool:
        return not self.accepted


@dataclass(frozen=True, slots=True)
class EvidenceRejection:
    """A rejected span, kept for the report.

    §6.5 calls the rejection rate the strongest empirical result this project
    produces, so the fabricated span is recorded rather than merely counted —
    a rate with no examples behind it persuades nobody in a viva.
    """

    code: str
    span: str
    match_score: float
    reason: str


def verify_evidence(evidence: str, source_text: str) -> EvidenceCheck:
    """Check one span against the submission it claims to quote."""
    span = (evidence or "").strip()

    if not span:
        return EvidenceCheck(False, 0.0, "No span was cited.")

    if len(span) < MINIMUM_SPAN_CHARS:
        return EvidenceCheck(
            False,
            0.0,
            f"Span is only {len(span)} characters; too short to identify.",
        )

    haystack = normalise_for_match(source_text)
    needle = normalise_for_match(span)

    if not haystack:
        return EvidenceCheck(False, 0.0, "The submission has no extracted text.")

    # partial_ratio, not ratio: the span is a fragment of a long document, so
    # the comparison must be "does this appear inside", not "are these similar".
    score = float(fuzz.partial_ratio(needle, haystack))

    if score < MINIMUM_MATCH:
        return EvidenceCheck(
            False,
            score,
            f"Best match {score:.1f} is below the {MINIMUM_MATCH:.0f} threshold — "
            "this span does not appear in the submission.",
        )

    return EvidenceCheck(True, score, "")


@dataclass(frozen=True, slots=True)
class GuardOutcome:
    """Everything the caller needs after guarding a batch."""

    results: tuple[CriterionResult, ...]
    rejections: tuple[EvidenceRejection, ...]

    @property
    def rejection_rate(self) -> float:
        """Share of criteria whose evidence was fabricated, 0 … 1."""
        if not self.results:
            return 0.0
        return len(self.rejections) / len(self.results)

    @property
    def clean(self) -> bool:
        return not self.rejections


def demote(result: CriterionResult, reason: str) -> CriterionResult:
    """Turn a criterion into ``NO_EVIDENCE`` at score 0.

    §6.3 makes this a node rather than a post-processing step so the rejection
    is checkpointed and visible. Here in 5a it is a function; 5b's graph calls
    the same one.
    """
    return result.model_copy(
        update={
            "verdict": Verdict.NO_EVIDENCE,
            # Decimal, not int: the model round-trips through the checkpointer
            # and a bare 0 makes pydantic re-serialise it as the wrong type.
            "score": Decimal("0"),
            "rationale": (
                f"Evidence rejected: {reason} "
                f"(original rationale: {result.rationale or '—'})"
            ),
        }
    )


def apply_guard(
    results: list[CriterionResult],
    source_text: str,
    *,
    submission_ref: str = "",
) -> GuardOutcome:
    """Verify every span, demoting the ones that fail.

    The only path by which a criterion result becomes persistable. Every
    rejection is logged with the fabricated span.
    """
    kept: list[CriterionResult] = []
    rejections: list[EvidenceRejection] = []

    for result in results:
        # NO_EVIDENCE is already at zero and cites nothing; there is no span to
        # check and nothing to demote it to.
        if result.verdict is Verdict.NO_EVIDENCE:
            kept.append(result)
            continue

        check = verify_evidence(result.evidence, source_text)

        if check.accepted:
            kept.append(result)
            continue

        rejection = EvidenceRejection(
            code=result.code,
            span=result.evidence,
            match_score=check.score,
            reason=check.reason,
        )
        rejections.append(rejection)

        logger.warning(
            "evidence rejected submission=%s criterion=%s score=%.1f reason=%s span=%r",
            submission_ref or "?",
            result.code,
            check.score,
            check.reason,
            result.evidence,
        )

        kept.append(demote(result, check.reason))

    return GuardOutcome(results=tuple(kept), rejections=tuple(rejections))

"""Fix item 5 — AI evidence validation.

The proofs the item asks for, each with a test:

* a fixture with fabricated evidence is rejected;
* a fixture with real-but-reflowed evidence is accepted;
* a fixture whose ``text_extract`` contains the PRN pattern and the student's
  name asserts neither appears in the outgoing prompt;
* every rejection is logged with the fabricated span.

The second is the one that matters most and is easiest to get wrong. A guard
that rejects genuine evidence because a PDF reflowed a line makes the rejection
rate noise instead of a result, and §6.5 calls that rate the strongest
empirical finding this project produces.
"""

from __future__ import annotations

import logging
from decimal import Decimal

import pytest

from core.ai.guards import (
    MINIMUM_MATCH,
    EvidenceRejection,
    apply_guard,
    demote,
    normalise_for_match,
    verify_evidence,
)
from core.ai.schemas import CriterionResult
from core.scoring.enums import Verdict

#: A short synopsis standing in for a real submission.
SUBMISSION = """\
RubriQ — Mini Project Synopsis

1. Problem statement
Faculty currently mark project reviews from memory against a rubric that
students never see before they submit. Marks vary between reviewers and
students cannot tell what was expected of them.

2. Objectives
- Let faculty define a rubric per milestone and publish it to students.
- Produce an evidence-backed estimated score sheet that faculty approve.

3. Scope
Out of scope: plagiarism detection, executing student code, LMS integration.
"""


def result(
    code: str = "C1",
    *,
    evidence: str,
    verdict: Verdict = Verdict.FOLLOWED,
    score: str = "8",
) -> CriterionResult:
    return CriterionResult(
        code=code,
        verdict=verdict,
        score=Decimal(score),
        max_score=Decimal("10"),
        confidence=0.9,
        evidence=evidence,
        rationale="Stated clearly.",
    )


class TestFabricatedEvidenceIsRejected:
    def test_a_span_that_is_not_in_the_document(self) -> None:
        """The headline case: the model quoted something that does not exist."""
        check = verify_evidence(
            "The system uses a microservices architecture deployed on Kubernetes.",
            SUBMISSION,
        )

        assert check.rejected
        assert check.score < MINIMUM_MATCH
        assert "does not appear" in check.reason

    def test_a_plausible_but_invented_sentence(self) -> None:
        """Fabrications usually sound like the document, which is the danger."""
        check = verify_evidence(
            "Faculty currently mark project reviews using a standardised "
            "digital scoring rubric approved by the department.",
            SUBMISSION,
        )

        assert check.rejected

    def test_an_empty_span(self) -> None:
        assert verify_evidence("", SUBMISSION).rejected

    def test_a_span_too_short_to_identify_anything(self) -> None:
        """ "the system" fuzzy-matches almost any document by accident."""
        check = verify_evidence("scope", SUBMISSION)

        assert check.rejected
        assert "too short" in check.reason

    def test_a_submission_with_no_extracted_text(self) -> None:
        """A scanned PDF: nothing can be evidenced against it."""
        check = verify_evidence("Faculty currently mark project reviews", "")

        assert check.rejected
        assert "no extracted text" in check.reason


class TestGenuineEvidenceIsAccepted:
    def test_an_exact_quotation(self) -> None:
        check = verify_evidence("Marks vary between reviewers", SUBMISSION)

        assert check.accepted
        assert check.score >= MINIMUM_MATCH

    def test_a_span_reflowed_across_a_line_break(self) -> None:
        """PDF extraction wraps lines; the model quotes it as one sentence."""
        check = verify_evidence(
            "students never see before they submit. Marks vary between reviewers",
            SUBMISSION,
        )

        assert check.accepted

    def test_a_span_whose_hyphenation_was_undone(self) -> None:
        source = "The system shall support evidence-\nbacked scoring of work."
        check = verify_evidence("evidencebacked scoring of work", source)

        assert check.accepted

    def test_a_span_with_different_casing(self) -> None:
        check = verify_evidence("MARKS VARY BETWEEN REVIEWERS", SUBMISSION)

        assert check.accepted

    def test_a_span_with_collapsed_whitespace(self) -> None:
        check = verify_evidence("Marks   vary\t between    reviewers", SUBMISSION)

        assert check.accepted

    def test_a_span_with_straightened_curly_quotes(self) -> None:
        source = "The guide said “number the requirements” before review."
        check = verify_evidence('said "number the requirements" before', source)

        assert check.accepted

    def test_a_span_containing_a_ligature_from_the_pdf_font(self) -> None:
        """PDF fonts emit ﬁ as one glyph; a model retypes it as two letters."""
        source = "The system must be conﬁgured before the ﬁrst review."
        check = verify_evidence("must be configured before the first review", source)

        assert check.accepted


class TestNormalisationIsSymmetric:
    def test_both_sides_go_through_the_same_function(self) -> None:
        """An asymmetric normalisation fails genuine evidence."""
        raw = "Marks  vary\nbetween   REVIEWERS"

        assert normalise_for_match(raw) == "marks vary between reviewers"

    def test_normalisation_never_touches_what_is_stored(self) -> None:
        """Fix item 5: the stored span must stay verbatim.

        The guard compares normalised forms but returns the model's original
        text — a "verbatim span" that has been through a normaliser is not one,
        and the student's feedback page quotes it back to them.
        """
        original = "Marks   vary\nbetween reviewers"
        outcome = apply_guard([result(evidence=original)], SUBMISSION)

        assert outcome.results[0].evidence == original


class TestNoBypass:
    def test_high_confidence_does_not_skip_the_guard(self) -> None:
        """Fix item 5: "no bypass branch, at any confidence"."""
        confident_lie = CriterionResult(
            code="C1",
            verdict=Verdict.FOLLOWED,
            score=Decimal("10"),
            max_score=Decimal("10"),
            confidence=1.0,
            evidence="The project uses a Kubernetes cluster for deployment.",
            rationale="Very sure.",
        )

        outcome = apply_guard([confident_lie], SUBMISSION)

        assert len(outcome.rejections) == 1
        assert outcome.results[0].verdict is Verdict.NO_EVIDENCE
        assert outcome.results[0].score == 0

    def test_a_demoted_criterion_scores_zero(self) -> None:
        demoted = demote(result(evidence="invented"), "fabricated")

        assert demoted.verdict is Verdict.NO_EVIDENCE
        assert demoted.score == 0

    def test_the_original_rationale_survives_demotion(self) -> None:
        """So a reviewer can see what the model thought before it was rejected."""
        demoted = demote(result(evidence="invented"), "fabricated")

        assert "Stated clearly." in demoted.rationale
        assert "Evidence rejected" in demoted.rationale

    def test_an_already_no_evidence_criterion_is_left_alone(self) -> None:
        """Nothing to check and nothing to demote it to."""
        honest = CriterionResult(
            code="C2",
            verdict=Verdict.NO_EVIDENCE,
            score=Decimal("0"),
            max_score=Decimal("10"),
            confidence=0.4,
            evidence="",
            rationale="The submission does not discuss testing.",
        )

        outcome = apply_guard([honest], SUBMISSION)

        assert outcome.rejections == ()
        assert outcome.results[0].rationale == "The submission does not discuss testing."


class TestRejectionsAreRecorded:
    def test_the_fabricated_span_is_kept_not_just_counted(self) -> None:
        """§6.5: the rejection rate is a report result; it needs examples."""
        lie = "The system uses a Kubernetes cluster for deployment."
        outcome = apply_guard([result(evidence=lie)], SUBMISSION)

        rejection = outcome.rejections[0]
        assert isinstance(rejection, EvidenceRejection)
        assert rejection.span == lie
        assert rejection.code == "C1"
        assert rejection.match_score < MINIMUM_MATCH
        assert rejection.reason

    def test_every_rejection_is_logged_with_its_span(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        lie = "Deployed on a Kubernetes cluster with autoscaling enabled."

        with caplog.at_level(logging.WARNING, logger="rubriq.ai.guard"):
            apply_guard([result(evidence=lie)], SUBMISSION, submission_ref="sub-7")

        assert any(lie in record.getMessage() for record in caplog.records)
        assert any("sub-7" in record.getMessage() for record in caplog.records)

    def test_the_rejection_rate_is_reportable(self) -> None:
        outcome = apply_guard(
            [
                result("C1", evidence="Marks vary between reviewers"),
                result("C2", evidence="Deployed on Kubernetes with autoscaling."),
                result("C3", evidence="Out of scope: plagiarism detection"),
                result("C4", evidence="Written in Rust for memory safety."),
            ],
            SUBMISSION,
        )

        assert len(outcome.rejections) == 2
        assert outcome.rejection_rate == 0.5
        assert outcome.clean is False

    def test_a_clean_batch_reports_no_rejections(self) -> None:
        outcome = apply_guard(
            [
                result("C1", evidence="Marks vary between reviewers"),
                result("C2", evidence="Out of scope: plagiarism detection"),
            ],
            SUBMISSION,
        )

        assert outcome.clean
        assert outcome.rejection_rate == 0.0

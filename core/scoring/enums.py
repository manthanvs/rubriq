"""Enums shared by evaluations and score sheets.

Separate from the models so ``core/db/models.py`` can import them without a
cycle, the same arrangement ``SubmissionStatus`` already uses.
"""

from __future__ import annotations

from enum import StrEnum


class EvaluationEngine(StrEnum):
    """Who produced the scores.

    Fix item 8 wants a provenance chip per row so a hand-corrected mark is
    never mistaken for a model output. This column is what it reads.
    """

    MANUAL = "MANUAL"
    AI = "AI"


class EvaluationStatus(StrEnum):
    """Where an evaluation is in its lifecycle.

    Manual scoring goes straight to ``COMPLETE``. The other three exist for
    Phase 5's AI runs, and approval is blocked on anything but ``COMPLETE``
    (fix item 4) — which is why they are defined here rather than later.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class Verdict(StrEnum):
    """What the student did or did not do for one criterion.

    §4 is explicit that this is a first-class column, not something derived
    from the score at render time: it powers the "has followed / has not
    followed" view the requirement asks for, and a score of 0 could mean
    either "attempted badly" or "absent from the document entirely".
    """

    FOLLOWED = "FOLLOWED"
    PARTIAL = "PARTIAL"
    NOT_FOLLOWED = "NOT_FOLLOWED"

    #: No verbatim span could be found. Invariant #3 forces score 0 here, and
    #: fix item 4 blocks approval while a *mandatory* criterion sits at this.
    NO_EVIDENCE = "NO_EVIDENCE"

    @property
    def glyph(self) -> str:
        """The compact grid symbol from §7 / fix item 12."""
        return {
            Verdict.FOLLOWED: "✓",
            Verdict.PARTIAL: "~",
            Verdict.NOT_FOLLOWED: "✗",
            Verdict.NO_EVIDENCE: "?",
        }[self]

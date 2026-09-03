"""Plain values returned by the scoring services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from core.scoring.enums import EvaluationEngine, EvaluationStatus, Verdict
from core.scoring.policy import AttendanceStatus


@dataclass(frozen=True, slots=True)
class CriterionScoreDTO:
    criterion_id: int
    code: str
    title: str
    weight: Decimal
    max_score: Decimal
    is_mandatory: bool
    score: Decimal
    verdict: Verdict
    confidence: Decimal | None
    evidence_span: str | None
    rationale: str | None

    @property
    def is_unresolved(self) -> bool:
        """Mandatory and unevidenced — the thing that blocks approval."""
        return self.is_mandatory and self.verdict is Verdict.NO_EVIDENCE


@dataclass(frozen=True, slots=True)
class ScoreSheetDTO:
    """A computed sheet, its provenance, and its approval state."""

    id: int
    evaluation_id: int
    submission_id: int
    engine: EvaluationEngine
    evaluation_status: EvaluationStatus
    submission_version: int
    rubric_version: int

    max_marks: Decimal
    weighted_percent: Decimal
    base_total: Decimal
    penalty: Decimal
    final_total: Decimal
    days_late: int
    attendance_status: AttendanceStatus
    reinstated: bool
    reinstate_reason: str | None

    approved_by: str | None
    approved_at: datetime | None
    faculty_note: str | None

    criteria: tuple[CriterionScoreDTO, ...]
    override_count: int = 0

    @property
    def is_approved(self) -> bool:
        return self.approved_at is not None

    @property
    def is_absent(self) -> bool:
        return self.attendance_status is AttendanceStatus.ABSENT

    @property
    def display_total(self) -> str:
        """One renderer for the total, used by the grid and both exporters.

        Fix item 10: ``ABSENT`` never renders as a number anywhere, Excel
        included. Deriving it here rather than per page is what stops the two
        from disagreeing.
        """
        return "ABSENT" if self.is_absent else f"{self.final_total}"

    @property
    def provenance(self) -> str:
        """``AI`` / ``MANUAL`` / ``OVERRIDDEN`` — fix item 8's chip.

        A hand-corrected mark must never be mistaken for a model output.
        """
        if self.override_count:
            return "OVERRIDDEN"
        return str(self.engine)

    @property
    def unresolved_mandatory(self) -> tuple[str, ...]:
        return tuple(c.code for c in self.criteria if c.is_unresolved)


@dataclass(frozen=True, slots=True)
class GridRow:
    """One student's row in the review grid (§7).

    Carries the sheet when there is one, and enough identity to render a row
    for a student who has not submitted at all — a grid that silently omits
    non-submitters is how someone gets missed.
    """

    student_email: str
    student_name: str
    prn: str | None
    submission_id: int | None
    submission_version: int | None
    submitted_at: datetime | None
    has_newer_version: bool
    sheet: ScoreSheetDTO | None

    @property
    def has_submitted(self) -> bool:
        return self.submission_id is not None

    @property
    def needs_attention(self) -> bool:
        """Fix item 8's single predicate.

        Used by the grid filter *and* the dashboard count, so the two cannot
        drift — they are the same function, not the same idea implemented
        twice.
        """
        if not self.has_submitted:
            return True
        if self.sheet is None:
            return True
        if self.sheet.evaluation_status is not EvaluationStatus.COMPLETE:
            return True
        if self.sheet.unresolved_mandatory:
            return True
        if self.has_newer_version:
            return True
        return not self.sheet.is_approved

    @property
    def status_label(self) -> str:
        """The one shared status renderer fix item 10 asks for."""
        if not self.has_submitted:
            return "No submission"
        if self.sheet is None:
            return "Not scored"
        if self.sheet.is_absent:
            return "Absent"
        if self.sheet.reinstated:
            return "Reinstated"
        if self.sheet.is_approved:
            return "Approved"
        return "Estimate"

"""The single source of export rows — fix item 11.

The named failure: *"the TSV and the XLSX disagree because each formats its own
numbers."* So both exporters consume :func:`build_export_rows` and neither is
allowed to compute or reformat anything. Formatting may differ between the two;
**numbers never do**, and ``tests/core/exports/test_parity.py`` asserts it cell
for cell.

Two further rules from the same item:

* Rows come from the persisted ``ScoreSheet``, never from grid widget state, so
  an uncommitted edit cannot ship.
* An unapproved row carries ``ESTIMATE — NOT APPROVED`` in its status column.
  Invariant #1 says the AI never publishes a final mark; exporting an estimate
  that looks final would break that at the very last step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.academics.access import require_faculty
from core.academics.milestones import get_milestone
from core.auth.actor import Actor
from core.clock import to_ist
from core.db.models import ProjectCycle, ReviewMilestone, Subject
from core.scoring.grid import list_grid_rows

#: Stamped into the status column of any row that nobody has approved.
ESTIMATE_MARKER = "ESTIMATE — NOT APPROVED"


@dataclass(frozen=True, slots=True)
class ExportRow:
    """One student's row, already rendered to strings.

    Values are strings because that is what both exporters write, and because
    it removes the last opportunity for one of them to format a number
    differently from the other.
    """

    prn: str
    name: str
    email: str
    submitted_at: str
    days_late: str
    status: str
    criteria: dict[str, str]
    base_total: str
    penalty: str
    final_total: str
    provenance: str
    approved_by: str
    approved_at: str
    note: str


@dataclass(frozen=True, slots=True)
class ExportBundle:
    """Everything an exporter needs, including the filename §7 specifies."""

    subject_code: str
    subject_name: str
    milestone_index: int
    milestone_title: str
    max_marks: str
    criterion_codes: tuple[str, ...]
    rows: tuple[ExportRow, ...]
    generated_at: datetime
    evidence: tuple[dict[str, str], ...] = field(default_factory=tuple)

    @property
    def filename_stem(self) -> str:
        """``RubriQ_<SubjectCode>_Review<N>_<YYYYMMDD>`` — §7, exactly."""
        stamp = to_ist(self.generated_at).strftime("%Y%m%d")
        return f"RubriQ_{self.subject_code}_Review{self.milestone_index}_{stamp}"

    @property
    def headers(self) -> tuple[str, ...]:
        return (
            "PRN",
            "Name",
            "Email",
            "Submitted (IST)",
            "Days Late",
            "Status",
            *self.criterion_codes,
            "Base",
            "Penalty",
            "Final",
            "Provenance",
            "Approved By",
            "Approved At",
            "Note",
        )

    def cells(self) -> list[list[str]]:
        """The full grid, header row first. Both exporters write exactly this."""
        grid = [list(self.headers)]
        for row in self.rows:
            grid.append(
                [
                    row.prn,
                    row.name,
                    row.email,
                    row.submitted_at,
                    row.days_late,
                    row.status,
                    *[row.criteria.get(code, "") for code in self.criterion_codes],
                    row.base_total,
                    row.penalty,
                    row.final_total,
                    row.provenance,
                    row.approved_by,
                    row.approved_at,
                    row.note,
                ]
            )
        return grid


def build_export_rows(
    actor: Actor, session: Session, *, milestone_id: int, generated_at: datetime
) -> ExportBundle:
    """Build the export from persisted rows, for one milestone."""
    require_faculty(actor, "export score sheets")
    milestone_dto = get_milestone(actor, session, milestone_id)

    milestone = session.get(ReviewMilestone, milestone_id)
    subject_id = session.execute(
        select(ProjectCycle.subject_id).where(ProjectCycle.id == milestone.cycle_id)
    ).scalar_one()
    subject = session.get(Subject, subject_id)

    grid_rows = list_grid_rows(actor, session, milestone_id=milestone_id)

    codes: list[str] = []
    for row in grid_rows:
        if row.sheet is None:
            continue
        for criterion in row.sheet.criteria:
            if criterion.code not in codes:
                codes.append(criterion.code)
    codes.sort()

    rows: list[ExportRow] = []
    evidence: list[dict[str, str]] = []

    for row in grid_rows:
        sheet = row.sheet

        if sheet is None:
            rows.append(
                ExportRow(
                    prn=row.prn or "",
                    name=row.student_name,
                    email=row.student_email,
                    submitted_at=(
                        to_ist(row.submitted_at).strftime("%Y-%m-%d %H:%M")
                        if row.submitted_at
                        else ""
                    ),
                    days_late="",
                    status=row.status_label,
                    criteria={},
                    base_total="",
                    penalty="",
                    final_total="",
                    provenance="",
                    approved_by="",
                    approved_at="",
                    note="",
                )
            )
            continue

        status = row.status_label
        if not sheet.is_approved:
            status = f"{status} · {ESTIMATE_MARKER}"

        rows.append(
            ExportRow(
                prn=row.prn or "",
                name=row.student_name,
                email=row.student_email,
                submitted_at=(
                    to_ist(row.submitted_at).strftime("%Y-%m-%d %H:%M")
                    if row.submitted_at
                    else ""
                ),
                days_late=str(sheet.days_late),
                status=status,
                criteria={c.code: f"{c.score}" for c in sheet.criteria},
                base_total=f"{sheet.base_total}",
                penalty=f"{sheet.penalty}",
                # display_total, so an absent student is never a number here
                # any more than on screen (fix item 10).
                final_total=sheet.display_total,
                provenance=sheet.provenance,
                approved_by=sheet.approved_by or "",
                approved_at=(
                    to_ist(sheet.approved_at).strftime("%Y-%m-%d %H:%M")
                    if sheet.approved_at
                    else ""
                ),
                note=sheet.faculty_note or "",
            )
        )

        for criterion in sheet.criteria:
            evidence.append(
                {
                    "PRN": row.prn or "",
                    "Name": row.student_name,
                    "Criterion": criterion.code,
                    "Verdict": str(criterion.verdict),
                    "Score": f"{criterion.score}",
                    "Evidence": criterion.evidence_span or "",
                    "Rationale": criterion.rationale or "",
                }
            )

    return ExportBundle(
        subject_code=subject.code,
        subject_name=subject.name,
        milestone_index=milestone_dto.index,
        milestone_title=milestone_dto.title,
        max_marks=f"{milestone.max_marks}",
        criterion_codes=tuple(codes),
        rows=tuple(rows),
        generated_at=generated_at,
        evidence=tuple(evidence),
    )

"""The department's assessment sheet, as data.

PCCoE assesses a review on a printed form: the institute's header, a grey
title band, a block of particulars, then one table — Sr. No., PRN, Name of the
Student, Project Title, one column per criterion, and the Total — with a
Marks row stating what each column is out of, and three signatures beneath.

This module builds that form **once**, from saved score sheets, and every
place a mark is shown renders the same object: the Excel export, the copied
table, the score drawer for one student, and the student's own feedback. Fix
item 11 asked that two exports never disagree; the stronger version of that
is that there is only one thing to disagree with.

Nothing here does mark arithmetic. Scores and totals arrive already computed
by ``core/scoring``; this only decides how each is written on the form.

Four states a row can be in, each written the way a guide would write it:

* approved — the scores and the total;
* scored but not yet approved — the same, with ``*`` on the total and a
  footnote, because an estimate must never look final (invariant #1);
* absent — ``AB`` for the total, criteria blank. Absence is a status, never a
  number (§5.1, fix item 10);
* no submission — ``NS``, which is not the same thing as absent and is not
  written as if it were.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.academics.access import require_faculty
from core.academics.enrollment import project_title_for
from core.academics.milestones import get_milestone
from core.auth.actor import Actor
from core.clock import to_ist
from core.db.models import ProjectCycle, ReviewMilestone, Subject, User
from core.errors import NotAuthorized, ValidationError
from core.rubrics.service import published_rubric_for
from core.scoring.dto import GridRow
from core.scoring.grid import list_grid_rows
from core.scoring.sheets import member_totals, sheet_for_submission
from core.submissions.service import latest_submission

#: The institute block at the top of every form, line by line, as printed.
INSTITUTE_LINES: tuple[str, ...] = (
    "Pimpri Chinchwad Education Trust's",
    "Pimpri Chinchwad College of Engineering (PCCoE)",
    "(An Autonomous Institute)",
    "Affiliated to Savitribai Phule Pune University(SPPU)",
    "ISO 21001:2018 Certified by TUV SUD",
)

DEPARTMENT = "MCA"

#: Who signs, left to right.
SIGNATORIES: tuple[str, ...] = (
    "Project Guide",
    "Project Coordinator",
    "Head of the Department",
)

ABSENT = "AB"
NO_SUBMISSION = "NS"
PENDING = "—"
ESTIMATE_MARK = "*"
#: The form has no penalty column, so a total that is not the sum of its
#: criteria — a late deduction, or a group member marked apart — would read as
#: an arithmetic error. The mark says it is deliberate; the legend says why.
ADJUSTED_MARK = "†"

#: Printed beneath the table whenever a code below appears in it.
LEGEND: dict[str, str] = {
    ABSENT: "AB — absent: submitted more than three days late, so not scored "
    "until the guide reinstates it.",
    NO_SUBMISSION: "NS — no submission received for this review.",
    PENDING: "— — submitted, not yet scored.",
    ESTIMATE_MARK: "* — a suggested mark not yet approved by the guide. It is not final.",
    ADJUSTED_MARK: "† — the total includes a late-submission penalty or an "
    "individual adjustment within a group.",
}

FIXED_COLUMNS: tuple[str, ...] = (
    "Sr. No.",
    "PRN",
    "Name of the Student",
    "Project Title",
)

_ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI"}


def roman(number: int) -> str:
    return _ROMAN.get(number, str(number))


def format_mark(value: Decimal) -> str:
    """``5.00`` → ``5``, ``4.50`` → ``4.5``, ``21.63`` → ``21.63``.

    A form reads "5", not "5.00". Never scientific notation, which is what a
    bare ``normalize()`` produces for round tens.
    """
    text = f"{value.quantize(Decimal('0.01')):f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def year_label(semester: int) -> str:
    """MCA is two years: semesters 1–2 are FYMCA, 3–4 are SYMCA."""
    return "FYMCA" if semester <= 2 else "SYMCA"


def semester_in_year(semester: int) -> str:
    """The form numbers the semester within its year: I or II."""
    return "I" if semester % 2 == 1 else "II"


def academic_year(text: str) -> str:
    """``2026-27`` → ``2026-2027``, as the form writes it."""
    head, sep, tail = (text or "").partition("-")
    if sep and len(head) == 4 and len(tail) == 2 and head.isdigit() and tail.isdigit():
        return f"{head}-{head[:2]}{tail}"
    return text


@dataclass(frozen=True, slots=True)
class AssessmentHeader:
    """Everything above the table."""

    title: str
    department: str
    academic_year: str
    semester: str
    year: str
    subject: str
    date: str
    guide: str
    review: str

    @property
    def particulars(self) -> tuple[tuple[tuple[str, str], ...], ...]:
        """The three-by-three block of particulars, row by row, as printed."""
        return (
            (
                ("Department", self.department),
                ("Academic Year", self.academic_year),
                ("Semester", self.semester),
            ),
            (
                ("Year", self.year),
                ("Subject", self.subject),
                ("Date", self.date),
            ),
            (
                ("Name of Project Guide", self.guide),
                ("Review", self.review),
                ("", ""),
            ),
        )


@dataclass(frozen=True, slots=True)
class AssessmentRow:
    sr_no: int
    prn: str
    name: str
    project_title: str
    scores: tuple[str, ...]
    total: str
    is_estimate: bool
    student_email: str
    is_adjusted: bool = False

    def cells(self) -> list[str]:
        return [
            str(self.sr_no),
            self.prn,
            self.name,
            self.project_title,
            *self.scores,
            self.total,
        ]


@dataclass(frozen=True, slots=True)
class AssessmentSheet:
    header: AssessmentHeader
    criteria: tuple[str, ...]
    criterion_max: tuple[str, ...]
    max_total: str
    rows: tuple[AssessmentRow, ...]
    subject_code: str
    review_index: int
    generated_at: datetime

    @property
    def column_headers(self) -> tuple[str, ...]:
        return (*FIXED_COLUMNS, *self.criteria, "Total")

    @property
    def marks_row(self) -> list[str]:
        """The row stating what each column is out of."""
        return ["", "", "", "Marks", *self.criterion_max, self.max_total]

    def table(self) -> list[list[str]]:
        """The table as printed: headings, the Marks row, then each student.

        Every renderer — the spreadsheet, the copied table, the page — draws
        exactly this, so none of them can disagree with another.
        """
        return [
            list(self.column_headers),
            self.marks_row,
            *[row.cells() for row in self.rows],
        ]

    @property
    def legend(self) -> tuple[str, ...]:
        """Only the notes that apply to something actually on the sheet."""
        used = {row.total for row in self.rows}
        lines = [
            LEGEND[code] for code in (ABSENT, NO_SUBMISSION, PENDING) if code in used
        ]
        if any(row.is_adjusted for row in self.rows):
            lines.append(LEGEND[ADJUSTED_MARK])
        if any(row.is_estimate for row in self.rows):
            lines.append(LEGEND[ESTIMATE_MARK])
        return tuple(lines)

    @property
    def filename_stem(self) -> str:
        """``RubriQ_<Subject>_Review<N>_<YYYYMMDD>`` — §7."""
        stamp = to_ist(self.generated_at).strftime("%Y%m%d")
        return f"RubriQ_{self.subject_code}_Review{self.review_index}_{stamp}"

    def only(self, student_email: str) -> AssessmentSheet:
        """The same form with one student's row — for the score drawer.

        The row keeps its class Sr. No., so it can be found on the full sheet.
        """
        rows = tuple(r for r in self.rows if r.student_email == student_email)
        if not rows:
            raise ValidationError("That student is not on this sheet.")
        return AssessmentSheet(
            header=self.header,
            criteria=self.criteria,
            criterion_max=self.criterion_max,
            max_total=self.max_total,
            rows=rows,
            subject_code=self.subject_code,
            review_index=self.review_index,
            generated_at=self.generated_at,
        )


def _row(position: int, row: GridRow, codes: tuple[str, ...]) -> AssessmentRow:
    """Write one grid row the way a guide writes it on the form."""
    blank = tuple("" for _ in codes)
    sheet = row.sheet

    adjusted = False
    if row.submission_id is None:
        scores, total, estimate = blank, NO_SUBMISSION, False
    elif sheet is None:
        scores, total, estimate = blank, PENDING, False
    elif sheet.is_absent:
        scores, total, estimate = blank, ABSENT, False
    else:
        by_code = {c.code: c for c in sheet.criteria}
        scores = tuple(
            format_mark(by_code[code].score) if code in by_code else "" for code in codes
        )
        estimate = not sheet.is_approved
        # Whether the total is something other than the base the criteria
        # produce. Compared against base_total, not a fresh sum, because
        # computing a mark here is exactly what this module must not do.
        adjusted = row.member_mark != sheet.base_total
        total = (
            format_mark(row.member_mark)
            + (ADJUSTED_MARK if adjusted else "")
            + (ESTIMATE_MARK if estimate else "")
        )

    return AssessmentRow(
        sr_no=position,
        prn=row.prn or "",
        name=row.student_name or row.student_email,
        project_title=row.project_title,
        scores=scores,
        total=total,
        is_estimate=estimate,
        student_email=row.student_email,
        is_adjusted=adjusted,
    )


def build_assessment(
    actor: Actor,
    session: Session,
    *,
    milestone_id: int,
    generated_at: datetime,
) -> AssessmentSheet:
    """The assessment sheet for one review, from saved score sheets."""
    require_faculty(actor, "build an assessment sheet")
    get_milestone(actor, session, milestone_id)

    # Roll order, as the department's form lists a class — not the grid's
    # "needs attention first", which is a working order rather than a record.
    ordered = sorted(
        list_grid_rows(actor, session, milestone_id=milestone_id),
        key=lambda r: (r.prn or "~", r.student_name.casefold()),
    )
    return _sheet(actor, session, milestone_id, ordered, generated_at)


def build_own_assessment(
    actor: Actor,
    session: Session,
    *,
    milestone_id: int,
    generated_at: datetime,
) -> AssessmentSheet | None:
    """A student's own row on the form — and only once it is approved.

    ``None`` until then: an unapproved estimate shown to a student is
    published in the only sense that matters (invariant #1).
    """
    if not actor.is_student:
        raise NotAuthorized("This is the student's view of their own sheet.")

    submission = latest_submission(
        actor, session, milestone_id=milestone_id, student_email=actor.email
    )
    if submission is None:
        return None
    sheet = sheet_for_submission(actor, session, submission.id)
    if sheet is None or not sheet.is_approved:
        return None

    me = session.get(User, actor.email)
    subject_id = get_milestone(actor, session, milestone_id).subject_id
    row = GridRow(
        student_email=actor.email,
        student_name=me.name if me else actor.email,
        prn=me.prn if me else None,
        submission_id=submission.id,
        submission_version=submission.version,
        submitted_at=submission.submitted_at,
        has_newer_version=False,
        sheet=sheet,
        member_total=member_totals(actor, session, score_sheet_id=sheet.id).get(
            actor.email
        ),
        project_title=project_title_for(
            actor, session, subject_id=subject_id, student_email=actor.email
        ),
    )
    return _sheet(actor, session, milestone_id, [row], generated_at)


def _sheet(
    actor: Actor,
    session: Session,
    milestone_id: int,
    grid_rows: list[GridRow],
    generated_at: datetime,
) -> AssessmentSheet:
    milestone_dto = get_milestone(actor, session, milestone_id)
    milestone = session.get(ReviewMilestone, milestone_id)
    cycle = session.get(ProjectCycle, milestone.cycle_id)
    subject = session.get(Subject, cycle.subject_id)
    guide = session.scalar(select(User.name).where(User.email == subject.owner_email))

    rubric = published_rubric_for(actor, session, milestone_id)
    criteria = tuple(rubric.criteria) if rubric else ()
    codes = tuple(c.code for c in criteria)
    rows = tuple(_row(position, row, codes) for position, row in enumerate(grid_rows, 1))

    return AssessmentSheet(
        header=AssessmentHeader(
            title=(
                f"{subject.name}: Review {roman(milestone_dto.index)}- Assessment Sheet"
            ),
            department=DEPARTMENT,
            academic_year=academic_year(cycle.academic_year),
            semester=semester_in_year(subject.semester),
            year=year_label(subject.semester),
            subject=subject.name,
            date=to_ist(generated_at).strftime("%d/%m/%Y"),
            guide=guide or subject.owner_email,
            review=f"{milestone_dto.index}   {milestone_dto.title}",
        ),
        criteria=tuple(c.title for c in criteria),
        criterion_max=tuple(format_mark(c.max_score) for c in criteria),
        max_total=format_mark(milestone.max_marks),
        rows=rows,
        subject_code=subject.code,
        review_index=milestone_dto.index,
        generated_at=generated_at,
    )

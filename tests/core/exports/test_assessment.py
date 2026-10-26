"""The department's assessment sheet — what each row says, and who may see it.

The form is the one object every output renders, so what it writes for each
state of a row is the whole contract: a number only when there is a mark, a
star on anything nobody approved, and AB / NS / — never written as zero.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from core.academics.enrollment import project_title_for, set_project_title
from core.clock import IST
from core.db.engine import session_scope
from core.errors import NotAuthorized, ValidationError
from core.exports.assessment import (
    ABSENT,
    ADJUSTED_MARK,
    ESTIMATE_MARK,
    LEGEND,
    NO_SUBMISSION,
    PENDING,
    academic_year,
    build_assessment,
    build_own_assessment,
    format_mark,
    roman,
    semester_in_year,
    year_label,
)
from core.scoring.enums import Verdict
from core.scoring.sheets import approve_sheet, save_manual_scores

WHEN = datetime(2026, 9, 3, 10, 30, tzinfo=IST)
FULL = {"C1": (10, Verdict.FOLLOWED), "C2": (8, Verdict.PARTIAL)}


def _form(db_factory, world, milestone_id):
    with session_scope(db_factory) as session:
        return build_assessment(
            world.faculty_a, session, milestone_id=milestone_id, generated_at=WHEN
        )


def _mine(form, world):
    return next(r for r in form.rows if r.student_email == world.student_1.email)


def _score(db_factory, world, graded, *, approve: bool):
    with session_scope(db_factory) as session:
        sheet = save_manual_scores(
            world.faculty_a, session, submission_id=graded.submission_id, scores=FULL
        )
    if approve:
        with session_scope(db_factory) as session:
            approve_sheet(world.faculty_a, session, score_sheet_id=sheet.id)
    return sheet


class TestFormatting:
    @pytest.mark.parametrize(
        ("value", "text"),
        [("5.00", "5"), ("4.50", "4.5"), ("21.63", "21.63"), ("20", "20"), ("0", "0")],
    )
    def test_marks_are_written_as_a_guide_writes_them(self, value, text) -> None:
        assert format_mark(Decimal(value)) == text

    def test_the_year_and_semester_follow_mca_numbering(self) -> None:
        assert (year_label(1), semester_in_year(1)) == ("FYMCA", "I")
        assert (year_label(2), semester_in_year(2)) == ("FYMCA", "II")
        assert (year_label(3), semester_in_year(3)) == ("SYMCA", "I")

    def test_the_academic_year_is_spelt_out(self) -> None:
        assert academic_year("2026-27") == "2026-2027"
        assert academic_year("2026-2027") == "2026-2027"

    def test_reviews_are_numbered_in_roman(self) -> None:
        assert [roman(n) for n in (1, 2, 3)] == ["I", "II", "III"]


class TestHeader:
    def test_it_reads_like_the_printed_form(self, db_factory, world, graded) -> None:
        form = _form(db_factory, world, graded.milestone_id)

        assert form.header.title == "Mini Project: Review I- Assessment Sheet"
        assert form.header.academic_year == "2026-2027"
        assert form.header.year == "SYMCA"
        assert form.header.guide == "Anjana"
        assert form.header.date == "03/09/2026"

    def test_criteria_are_headed_by_title_not_code(
        self, db_factory, world, graded
    ) -> None:
        form = _form(db_factory, world, graded.milestone_id)

        assert form.column_headers == (
            "Sr. No.",
            "PRN",
            "Name of the Student",
            "Project Title",
            "Problem statement",
            "SRS completeness",
            "Total",
        )
        assert form.marks_row == ["", "", "", "Marks", "10", "10", "25"]


class TestRows:
    def test_submitted_but_unscored_is_a_dash(self, db_factory, world, graded) -> None:
        row = _mine(_form(db_factory, world, graded.milestone_id), world)

        assert row.total == PENDING
        assert not any(row.scores)

    def test_an_unapproved_mark_is_starred(self, db_factory, world, graded) -> None:
        """Invariant #1 on paper: an estimate never looks final."""
        _score(db_factory, world, graded, approve=False)
        form = _form(db_factory, world, graded.milestone_id)
        row = _mine(form, world)

        assert row.scores == ("10", "8")
        assert row.total == "23" + ESTIMATE_MARK
        assert row.is_estimate
        assert LEGEND[ESTIMATE_MARK] in form.legend

    def test_an_approved_mark_is_plain(self, db_factory, world, graded) -> None:
        _score(db_factory, world, graded, approve=True)
        form = _form(db_factory, world, graded.milestone_id)
        row = _mine(form, world)

        assert row.total == "23"
        assert not row.is_estimate
        assert form.legend == ()

    def test_absent_is_ab_with_the_criteria_blank(
        self, db_factory, world, graded
    ) -> None:
        from core.db.models import ReviewMilestone, Submission

        with session_scope(db_factory) as session:
            submission = session.get(Submission, graded.submission_id)
            milestone = session.get(ReviewMilestone, graded.milestone_id)
            submission.submitted_at = milestone.due_at + timedelta(days=6)

        _score(db_factory, world, graded, approve=False)
        form = _form(db_factory, world, graded.milestone_id)
        row = _mine(form, world)

        assert row.total == ABSENT
        assert row.scores == ("", "")
        assert LEGEND[ABSENT] in form.legend

    def test_a_late_total_is_marked_as_adjusted(self, db_factory, world, graded) -> None:
        """The form has no penalty column, so the total says it was reduced."""
        from core.db.models import ReviewMilestone, Submission

        with session_scope(db_factory) as session:
            submission = session.get(Submission, graded.submission_id)
            milestone = session.get(ReviewMilestone, graded.milestone_id)
            submission.submitted_at = milestone.due_at + timedelta(days=2)

        _score(db_factory, world, graded, approve=True)
        row = _mine(_form(db_factory, world, graded.milestone_id), world)

        assert row.total.endswith(ADJUSTED_MARK)
        assert row.is_adjusted

    def test_no_submission_is_ns(self, db_factory, world) -> None:
        form = _form(db_factory, world, world.milestone_visible)

        assert _mine(form, world).total == NO_SUBMISSION

    def test_only_keeps_the_class_serial_number(self, db_factory, world, graded) -> None:
        form = _form(db_factory, world, graded.milestone_id)
        one = form.only(world.student_1.email)

        assert one.rows == (_mine(form, world),)
        with pytest.raises(ValidationError):
            form.only("nobody@pccoepune.org")


class TestProjectTitle:
    def test_it_reaches_the_form(self, db_factory, world, graded) -> None:
        with session_scope(db_factory) as session:
            set_project_title(
                world.student_1,
                session,
                subject_id=world.subject_a,
                student_email=world.student_1.email,
                title="  RubriQ   review system ",
            )

        row = _mine(_form(db_factory, world, graded.milestone_id), world)
        assert row.project_title == "RubriQ review system"

    def test_a_student_cannot_title_someone_else(self, db_factory, world) -> None:
        with session_scope(db_factory) as session, pytest.raises(NotAuthorized):
            set_project_title(
                world.student_2,
                session,
                subject_id=world.subject_a,
                student_email=world.student_1.email,
                title="Not mine",
            )

    def test_faculty_of_another_subject_cannot_read_it(self, db_factory, world) -> None:
        with session_scope(db_factory) as session, pytest.raises(NotAuthorized):
            project_title_for(
                world.faculty_b,
                session,
                subject_id=world.subject_a,
                student_email=world.student_1.email,
            )

    def test_an_overlong_title_is_refused(self, db_factory, world) -> None:
        with session_scope(db_factory) as session, pytest.raises(ValidationError):
            set_project_title(
                world.faculty_a,
                session,
                subject_id=world.subject_a,
                student_email=world.student_1.email,
                title="x" * 201,
            )


class TestStudentView:
    def _own(self, db_factory, world, milestone_id):
        with session_scope(db_factory) as session:
            return build_own_assessment(
                world.student_1, session, milestone_id=milestone_id, generated_at=WHEN
            )

    def test_nothing_before_approval(self, db_factory, world, graded) -> None:
        _score(db_factory, world, graded, approve=False)

        assert self._own(db_factory, world, graded.milestone_id) is None

    def test_their_own_row_once_approved(self, db_factory, world, graded) -> None:
        _score(db_factory, world, graded, approve=True)
        form = self._own(db_factory, world, graded.milestone_id)

        assert [r.student_email for r in form.rows] == [world.student_1.email]
        assert form.rows[0].total == "23"

    def test_faculty_use_the_class_sheet_instead(self, db_factory, world, graded) -> None:
        with session_scope(db_factory) as session, pytest.raises(NotAuthorized):
            build_own_assessment(
                world.faculty_a,
                session,
                milestone_id=graded.milestone_id,
                generated_at=WHEN,
            )

    def test_a_student_cannot_build_the_class_sheet(
        self, db_factory, world, graded
    ) -> None:
        with session_scope(db_factory) as session, pytest.raises(NotAuthorized):
            build_assessment(
                world.student_1,
                session,
                milestone_id=graded.milestone_id,
                generated_at=WHEN,
            )

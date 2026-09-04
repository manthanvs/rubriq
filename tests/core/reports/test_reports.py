"""Reporting aggregates.

The property worth guarding here is §5.1's: **an absence is not a zero.** An
average that folds absences in drags a cohort's mean down and makes the
distinction the whole late policy exists to preserve invisible at exactly the
moment someone is looking at a chart of it.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from core.db.engine import session_scope
from core.db.models import ReviewMilestone, Submission
from core.errors import NotAuthorized
from core.reports.service import attendance_mix, build_report
from core.scoring.enums import Verdict
from core.scoring.sheets import approve_sheet, save_manual_scores

FULL = {"C1": (10, Verdict.FOLLOWED), "C2": (10, Verdict.FOLLOWED)}
HALF = {"C1": (5, Verdict.PARTIAL), "C2": (5, Verdict.PARTIAL)}


def _score(db_factory, world, graded, scores):
    with session_scope(db_factory) as session:
        return save_manual_scores(
            world.faculty_a, session, submission_id=graded.submission_id, scores=scores
        )


def _make_absent(db_factory, graded):
    """Push the submission past the four-day ABSENT threshold."""
    with session_scope(db_factory) as session:
        submission = session.get(Submission, graded.submission_id)
        milestone = session.get(ReviewMilestone, graded.milestone_id)
        submission.submitted_at = milestone.due_at + timedelta(days=5)


class TestAbsenceIsNotAZero:
    def test_an_absent_student_is_excluded_from_the_mean(
        self, db_factory, world, graded
    ) -> None:
        _make_absent(db_factory, graded)
        _score(db_factory, world, graded, FULL)

        with session_scope(db_factory) as session:
            report = build_report(
                world.faculty_a, session, milestone_id=graded.milestone_id
            )

        assert report.absent == 1
        assert report.scored == 1
        assert report.mean is None, "the only sheet was absent; there is no mean"

    def test_an_absent_student_is_counted_separately(
        self, db_factory, world, graded
    ) -> None:
        _make_absent(db_factory, graded)
        _score(db_factory, world, graded, FULL)

        with session_scope(db_factory) as session:
            mix = attendance_mix(
                world.faculty_a, session, milestone_id=graded.milestone_id
            )

        assert mix.get("ABSENT") == 1
        assert "PRESENT" not in mix

    def test_a_genuine_zero_still_counts_toward_the_mean(
        self, db_factory, world, graded
    ) -> None:
        """Attempted and scored zero is a real data point; absent is not."""
        _score(
            db_factory,
            world,
            graded,
            {"C1": (0, Verdict.NOT_FOLLOWED), "C2": (0, Verdict.NOT_FOLLOWED)},
        )

        with session_scope(db_factory) as session:
            report = build_report(
                world.faculty_a, session, milestone_id=graded.milestone_id
            )

        assert report.absent == 0
        assert report.mean == Decimal("0.00")

    def test_absent_criteria_do_not_skew_the_weak_spot_chart(
        self, db_factory, world, graded
    ) -> None:
        _make_absent(db_factory, graded)
        _score(db_factory, world, graded, FULL)

        with session_scope(db_factory) as session:
            report = build_report(
                world.faculty_a, session, milestone_id=graded.milestone_id
            )

        assert report.criteria == (), "an absent sheet contributes no criterion stats"


class TestCohortShape:
    def test_students_who_never_submitted_are_counted(
        self, db_factory, world, graded
    ) -> None:
        """A report that omits non-submitters flatters the cohort."""
        _score(db_factory, world, graded, FULL)

        with session_scope(db_factory) as session:
            report = build_report(
                world.faculty_a, session, milestone_id=graded.milestone_id
            )

        assert report.enrolled == 1
        assert report.submitted == 1
        assert report.not_submitted == 0

    def test_approval_is_counted_separately_from_scoring(
        self, db_factory, world, graded
    ) -> None:
        sheet = _score(db_factory, world, graded, FULL)

        with session_scope(db_factory) as session:
            report = build_report(
                world.faculty_a, session, milestone_id=graded.milestone_id
            )
        assert (report.scored, report.approved) == (1, 0)

        with session_scope(db_factory) as session:
            approve_sheet(world.faculty_a, session, score_sheet_id=sheet.id)

        with session_scope(db_factory) as session:
            report = build_report(
                world.faculty_a, session, milestone_id=graded.milestone_id
            )
        assert (report.scored, report.approved) == (1, 1)

    def test_an_unscored_milestone_reports_nothing_rather_than_zeroes(
        self, db_factory, world, graded
    ) -> None:
        """Fix item 13: an empty state, not a chart of nothing."""
        with session_scope(db_factory) as session:
            report = build_report(
                world.faculty_a, session, milestone_id=graded.milestone_id
            )

        assert not report.has_marks
        assert report.bands == ()
        assert report.mean is None
        assert report.weakest is None


class TestWeakSpot:
    def test_the_weakest_criterion_is_identified(self, db_factory, world, graded) -> None:
        _score(
            db_factory,
            world,
            graded,
            {"C1": (3, Verdict.PARTIAL), "C2": (9, Verdict.FOLLOWED)},
        )

        with session_scope(db_factory) as session:
            report = build_report(
                world.faculty_a, session, milestone_id=graded.milestone_id
            )

        assert report.weakest.code == "C1"
        assert report.weakest.mean_percent == Decimal("30.0")

    def test_unevidenced_criteria_are_surfaced(self, db_factory, world, graded) -> None:
        _score(
            db_factory,
            world,
            graded,
            {"C1": (0, Verdict.NO_EVIDENCE), "C2": (8, Verdict.FOLLOWED)},
        )

        with session_scope(db_factory) as session:
            report = build_report(
                world.faculty_a, session, milestone_id=graded.milestone_id
            )

        weakest = report.weakest
        assert weakest.code == "C1"
        assert weakest.unevidenced == 1

    def test_the_bands_cover_full_marks(self, db_factory, world, graded) -> None:
        """Full marks must land in a band rather than falling off the top."""
        _score(db_factory, world, graded, FULL)

        with session_scope(db_factory) as session:
            report = build_report(
                world.faculty_a, session, milestone_id=graded.milestone_id
            )

        assert sum(band.count for band in report.bands) == 1
        assert report.bands[-1].count == 1


class TestScoping:
    def test_a_student_cannot_read_reports(self, db_factory, world, graded) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                build_report(world.student_1, session, milestone_id=graded.milestone_id)

    def test_another_faculty_cannot_read_your_cohort(
        self, db_factory, world, graded
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                build_report(world.faculty_b, session, milestone_id=graded.milestone_id)


class TestGroupMemberMarks:
    """The class average must agree with the grid and the spreadsheet.

    Found during the demo rehearsal: the Reports page averaged the *group's*
    total for every member, so a member marked apart from their group counted
    at the wrong figure and the mean disagreed with the exported file. Fix item
    11's rule — one set of numbers wherever they are shown — applies to a chart
    as much as to a column.
    """

    def test_the_mean_uses_the_members_own_mark(
        self, db_factory, world, graded
    ) -> None:
        from decimal import Decimal

        from core.db.models import Enrollment
        from core.groups.service import create_group
        from core.scoring.sheets import adjust_member
        from core.submissions.service import submit

        mate = "someone.else@pccoepune.org"

        with session_scope(db_factory) as session:
            session.add(Enrollment(student_email=mate, subject_id=world.subject_a))

        with session_scope(db_factory) as session:
            create_group(
                world.faculty_a,
                session,
                subject_id=world.subject_a,
                name="Team Alpha",
                member_emails=[world.student_1.email, mate],
            )

        import tempfile
        from pathlib import Path

        uploads = Path(tempfile.mkdtemp())
        with session_scope(db_factory) as session:
            made = submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files={"a.txt": b"Our work."},
                uploads_root=uploads,
            )
            submission_id = made.id

        with session_scope(db_factory) as session:
            sheet = save_manual_scores(
                world.faculty_a, session, submission_id=submission_id, scores=FULL
            )
            sheet_id, group_total = sheet.id, sheet.final_total

        with session_scope(db_factory) as session:
            adjust_member(
                world.faculty_a,
                session,
                score_sheet_id=sheet_id,
                student_email=mate,
                delta="-4.00",
                reason="Documentation only.",
            )

        with session_scope(db_factory) as session:
            report = build_report(
                world.faculty_a, session, milestone_id=world.milestone_visible
            )

        expected = (
            (group_total + (group_total - Decimal("4.00"))) / 2
        ).quantize(Decimal("0.01"))

        assert report.mean == expected, (
            "the mean counted the group's total for the adjusted member"
        )
        assert report.lowest == group_total - Decimal("4.00")

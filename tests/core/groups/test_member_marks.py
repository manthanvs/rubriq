"""Phase 9 — marking one member of a granted group apart from the rest.

This is the first thing in the project that lets two students who submitted the
same work receive different marks, so the tests lead with the guards rather
than the happy path: a reason is compulsory, the adjustment is refused entirely
on individual work, approval is cleared when a published mark moves, and an
absent group does not become a number just because someone was adjusted.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.auth.actor import Actor
from core.db.engine import session_scope
from core.db.models import (
    Enrollment,
    MemberAdjustment,
    ReviewMilestone,
    Submission,
    User,
)
from core.errors import NotAuthorized, ValidationError
from core.groups.service import create_group
from core.scoring.enums import Verdict
from core.scoring.grid import list_grid_rows
from core.scoring.sheets import (
    adjust_member,
    approve_sheet,
    member_adjustment_history,
    member_totals,
    save_manual_scores,
)
from core.submissions.service import submit

MATE = "someone.else@pccoepune.org"

#: Enrolled in the same subject, but not in the group — the outsider worth
#: testing. (``world.student_2`` is *this same email*, so it cannot play the
#: outsider here; cross-subject isolation is covered in test_isolation.py.)
OUTSIDER = "outsider@pccoepune.org"

FULL = {"C1": (10, Verdict.FOLLOWED), "C2": (10, Verdict.FOLLOWED)}


@pytest.fixture
def mate(db_factory, world):
    with session_scope(db_factory) as session:
        session.add(Enrollment(student_email=MATE, subject_id=world.subject_a))
        session.add(User(email=OUTSIDER, role=world.student_1.role, name="Outsider"))
        session.flush()
        session.add(Enrollment(student_email=OUTSIDER, subject_id=world.subject_a))

    return Actor(email=MATE, role=world.student_2.role, name="Someone")


@pytest.fixture
def outsider(world):
    return Actor(email=OUTSIDER, role=world.student_1.role, name="Outsider")


@pytest.fixture
def grouped(db_factory, world, mate, graded, tmp_path):
    """A granted group with one submission, scored but not yet approved."""
    with session_scope(db_factory) as session:
        create_group(
            world.faculty_a,
            session,
            subject_id=world.subject_a,
            name="Team Alpha",
            member_emails=[world.student_1.email, MATE],
        )

    with session_scope(db_factory) as session:
        made = submit(
            world.student_1,
            session,
            milestone_id=world.milestone_visible,
            files={"synopsis.txt": b"Objectives, scope and requirements."},
            uploads_root=tmp_path / "uploads",
        )
        submission_id = made.id

    with session_scope(db_factory) as session:
        sheet = save_manual_scores(
            world.faculty_a, session, submission_id=submission_id, scores=FULL
        )
        return {"sheet_id": sheet.id, "submission_id": submission_id}


class TestGuards:
    def test_a_reason_is_required(self, db_factory, world, grouped) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError, match="needs a reason"):
                adjust_member(
                    world.faculty_a,
                    session,
                    score_sheet_id=grouped["sheet_id"],
                    student_email=MATE,
                    delta="-2.00",
                    reason="   ",
                )

    def test_a_student_cannot_adjust_anyone(self, db_factory, world, grouped) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                adjust_member(
                    world.student_1,
                    session,
                    score_sheet_id=grouped["sheet_id"],
                    student_email=MATE,
                    delta="-2.00",
                    reason="Trying it on.",
                )

    def test_another_faculty_cannot_adjust(self, db_factory, world, grouped) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                adjust_member(
                    world.faculty_b,
                    session,
                    score_sheet_id=grouped["sheet_id"],
                    student_email=MATE,
                    delta="-2.00",
                    reason="Not my subject.",
                )

    def test_a_non_member_cannot_be_adjusted(self, db_factory, world, grouped) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError, match="not a member"):
                adjust_member(
                    world.faculty_a,
                    session,
                    score_sheet_id=grouped["sheet_id"],
                    student_email="outsider@pccoepune.org",
                    delta="-2.00",
                    reason="Wrong student.",
                )

    def test_individual_work_cannot_be_adjusted(self, db_factory, world, graded) -> None:
        """There is no group to be marked apart from — override instead."""
        with session_scope(db_factory) as session:
            sheet = save_manual_scores(
                world.faculty_a,
                session,
                submission_id=graded.submission_id,
                scores=FULL,
            )
            sheet_id = sheet.id

        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError, match="not group work"):
                adjust_member(
                    world.faculty_a,
                    session,
                    score_sheet_id=sheet_id,
                    student_email=world.student_1.email,
                    delta="-2.00",
                    reason="Should be refused.",
                )

    def test_an_adjustment_larger_than_the_milestone_is_refused(
        self, db_factory, world, grouped
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError, match="larger than the milestone"):
                adjust_member(
                    world.faculty_a,
                    session,
                    score_sheet_id=grouped["sheet_id"],
                    student_email=MATE,
                    delta="-999",
                    reason="Absurd.",
                )


class TestTheAdjustment:
    def test_only_the_adjusted_member_moves(
        self, db_factory, world, mate, grouped
    ) -> None:
        with session_scope(db_factory) as session:
            adjust_member(
                world.faculty_a,
                session,
                score_sheet_id=grouped["sheet_id"],
                student_email=MATE,
                delta="-3.00",
                reason="Did not contribute to the implementation.",
            )

        with session_scope(db_factory) as session:
            totals = member_totals(
                world.faculty_a, session, score_sheet_id=grouped["sheet_id"]
            )

        assert MATE in totals
        assert world.student_1.email not in totals, "an unadjusted member is not special"

    def test_the_group_total_is_left_alone(
        self, db_factory, world, mate, grouped
    ) -> None:
        """The work was assessed once; only the share of it changes."""
        with session_scope(db_factory) as session:
            before = save_manual_scores(
                world.faculty_a,
                session,
                submission_id=grouped["submission_id"],
                scores=FULL,
            ).final_total

        with session_scope(db_factory) as session:
            sheet = adjust_member(
                world.faculty_a,
                session,
                score_sheet_id=grouped["sheet_id"],
                student_email=MATE,
                delta="-3.00",
                reason="Documentation only.",
            )

        assert sheet.final_total == before

    def test_the_member_total_is_the_group_total_plus_the_delta(
        self, db_factory, world, mate, grouped
    ) -> None:
        with session_scope(db_factory) as session:
            sheet = adjust_member(
                world.faculty_a,
                session,
                score_sheet_id=grouped["sheet_id"],
                student_email=MATE,
                delta="-3.00",
                reason="Documentation only.",
            )
            totals = member_totals(
                world.faculty_a, session, score_sheet_id=grouped["sheet_id"]
            )

        assert totals[MATE] == sheet.final_total - Decimal("3.00")

    def test_a_second_adjustment_replaces_rather_than_compounds(
        self, db_factory, world, mate, grouped
    ) -> None:
        """Two rows for one member are a change of mind, not a double penalty."""
        for delta, reason in (("-3.00", "First view."), ("-1.00", "On reflection.")):
            with session_scope(db_factory) as session:
                sheet = adjust_member(
                    world.faculty_a,
                    session,
                    score_sheet_id=grouped["sheet_id"],
                    student_email=MATE,
                    delta=delta,
                    reason=reason,
                )
                group_total = sheet.final_total

        with session_scope(db_factory) as session:
            totals = member_totals(
                world.faculty_a, session, score_sheet_id=grouped["sheet_id"]
            )

        assert totals[MATE] == group_total - Decimal("1.00")

    def test_both_adjustments_are_kept_in_the_history(
        self, db_factory, world, mate, grouped
    ) -> None:
        for delta, reason in (("-3.00", "First view."), ("-1.00", "On reflection.")):
            with session_scope(db_factory) as session:
                adjust_member(
                    world.faculty_a,
                    session,
                    score_sheet_id=grouped["sheet_id"],
                    student_email=MATE,
                    delta=delta,
                    reason=reason,
                )

        with session_scope(db_factory) as session:
            history = member_adjustment_history(
                world.faculty_a, session, grouped["sheet_id"]
            )

        assert [h["reason"] for h in history] == ["First view.", "On reflection."]
        assert [h["delta"] for h in history] == [Decimal("-3.00"), Decimal("-1.00")]

    def test_nothing_is_ever_deleted(self, db_factory, world, mate, grouped) -> None:
        for delta in ("-3.00", "-1.00", "0.00"):
            with session_scope(db_factory) as session:
                adjust_member(
                    world.faculty_a,
                    session,
                    score_sheet_id=grouped["sheet_id"],
                    student_email=MATE,
                    delta=delta,
                    reason="Revised.",
                )

        with session_scope(db_factory) as session:
            assert session.query(MemberAdjustment).count() == 3


class TestApproval:
    def test_adjusting_an_approved_sheet_clears_the_approval(
        self, db_factory, world, mate, grouped
    ) -> None:
        """Invariant #1: a published mark that moved must be re-owned."""
        with session_scope(db_factory) as session:
            approve_sheet(world.faculty_a, session, score_sheet_id=grouped["sheet_id"])

        with session_scope(db_factory) as session:
            sheet = adjust_member(
                world.faculty_a,
                session,
                score_sheet_id=grouped["sheet_id"],
                student_email=MATE,
                delta="-2.00",
                reason="Contribution was uneven.",
            )

        assert not sheet.is_approved
        assert sheet.approved_by is None
        assert sheet.approved_at is None

    def test_the_sheet_can_be_approved_again_afterwards(
        self, db_factory, world, mate, grouped
    ) -> None:
        with session_scope(db_factory) as session:
            adjust_member(
                world.faculty_a,
                session,
                score_sheet_id=grouped["sheet_id"],
                student_email=MATE,
                delta="-2.00",
                reason="Contribution was uneven.",
            )

        with session_scope(db_factory) as session:
            sheet = approve_sheet(
                world.faculty_a, session, score_sheet_id=grouped["sheet_id"]
            )

        assert sheet.is_approved


class TestTheGrid:
    def test_each_member_shows_their_own_total(
        self, db_factory, world, mate, grouped
    ) -> None:
        with session_scope(db_factory) as session:
            adjust_member(
                world.faculty_a,
                session,
                score_sheet_id=grouped["sheet_id"],
                student_email=MATE,
                delta="-3.00",
                reason="Documentation only.",
            )

        with session_scope(db_factory) as session:
            rows = {
                r.student_email: r
                for r in list_grid_rows(
                    world.faculty_a, session, milestone_id=world.milestone_visible
                )
            }

        adjusted = rows[MATE]
        untouched = rows[world.student_1.email]

        assert adjusted.is_adjusted
        assert adjusted.member_delta == Decimal("-3.00")
        assert adjusted.member_reason == "Documentation only."
        assert not untouched.is_adjusted
        assert adjusted.display_total != untouched.display_total

    def test_an_unadjusted_member_still_shows_the_group_total(
        self, db_factory, world, mate, grouped
    ) -> None:
        with session_scope(db_factory) as session:
            rows = {
                r.student_email: r
                for r in list_grid_rows(
                    world.faculty_a, session, milestone_id=world.milestone_visible
                )
            }

        row = rows[world.student_1.email]
        assert row.display_total == row.sheet.display_total

    def test_absent_beats_an_adjustment(self, db_factory, world, mate, grouped) -> None:
        """§5.1: absence is a status. An adjustment must not make it a number."""
        from datetime import timedelta

        with session_scope(db_factory) as session:
            submission = session.get(Submission, grouped["submission_id"])
            milestone = session.get(ReviewMilestone, world.milestone_visible)
            submission.submitted_at = milestone.due_at + timedelta(days=5)

        with session_scope(db_factory) as session:
            save_manual_scores(
                world.faculty_a,
                session,
                submission_id=grouped["submission_id"],
                scores=FULL,
            )

        with session_scope(db_factory) as session:
            adjust_member(
                world.faculty_a,
                session,
                score_sheet_id=grouped["sheet_id"],
                student_email=MATE,
                delta="-3.00",
                reason="Still absent, but recorded for the file.",
            )

        with session_scope(db_factory) as session:
            rows = {
                r.student_email: r
                for r in list_grid_rows(
                    world.faculty_a, session, milestone_id=world.milestone_visible
                )
            }

        assert rows[MATE].display_total == "ABSENT"


class TestStudentVisibility:
    def test_a_member_can_read_their_own_adjusted_total(
        self, db_factory, world, mate, grouped
    ) -> None:
        with session_scope(db_factory) as session:
            adjust_member(
                world.faculty_a,
                session,
                score_sheet_id=grouped["sheet_id"],
                student_email=MATE,
                delta="-3.00",
                reason="Documentation only.",
            )

        with session_scope(db_factory) as session:
            totals = member_totals(mate, session, score_sheet_id=grouped["sheet_id"])

        assert MATE in totals

    def test_an_enrolled_non_member_cannot(
        self, db_factory, world, mate, outsider, grouped
    ) -> None:
        """Same subject, same milestone, not in the group. Must stay blind."""
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                member_totals(outsider, session, score_sheet_id=grouped["sheet_id"])

    def test_a_student_cannot_read_the_adjustment_history(
        self, db_factory, world, mate, grouped
    ) -> None:
        """The history names who decided and why — that is a faculty record."""
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                member_adjustment_history(mate, session, grouped["sheet_id"])


class TestVersioningAcrossTheGroupTransition:
    """A defect found while writing this file, not a hypothetical.

    A student can submit individually and *then* have their group granted.
    Their existing rows carry no ``group_id``, so numbering purely by group
    restarted at 1 and collided with their own v1 on
    ``uq_submission_student_version`` — an IntegrityError in front of a student
    pressing Submit. ``submit()`` now takes the union of the group's rows and
    the uploader's own.
    """

    def test_a_group_granted_after_an_individual_submission_still_works(
        self, db_factory, world, mate, graded, tmp_path
    ) -> None:
        # `graded` already left student_1 an individual v1.
        with session_scope(db_factory) as session:
            create_group(
                world.faculty_a,
                session,
                subject_id=world.subject_a,
                name="Team Late",
                member_emails=[world.student_1.email, MATE],
            )

        with session_scope(db_factory) as session:
            made = submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files={"again.txt": b"Now as a group."},
                uploads_root=tmp_path / "uploads",
            )

        assert made.version == 2, "the group's first upload follows the student's v1"
        assert made.is_group_work

    def test_the_other_member_then_continues_the_sequence(
        self, db_factory, world, mate, graded, tmp_path
    ) -> None:
        with session_scope(db_factory) as session:
            create_group(
                world.faculty_a,
                session,
                subject_id=world.subject_a,
                name="Team Late",
                member_emails=[world.student_1.email, MATE],
            )

        with session_scope(db_factory) as session:
            submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files={"a.txt": b"Group v2."},
                uploads_root=tmp_path / "uploads",
            )

        with session_scope(db_factory) as session:
            third = submit(
                mate,
                session,
                milestone_id=world.milestone_visible,
                files={"b.txt": b"Group v3, uploaded by the other member."},
                uploads_root=tmp_path / "uploads",
            )

        assert third.version == 3

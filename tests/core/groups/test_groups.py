"""Decision #5 — a group exists only under a faculty grant.

The tests worth reading twice are in ``TestAPendingRequestGrantsNothing``. A
group is the one place this system deliberately widens invariant #6, and the
failure that widening invites is obvious once written down: a student names a
classmate in a request and can read their work before anybody approved
anything. Every read path is asserted against that, not just the one that was
convenient to test.
"""

from __future__ import annotations

import pytest

from core.db.engine import session_scope
from core.db.models import Enrollment, User
from core.errors import NotAuthorized, ValidationError
from core.groups.enums import GroupStatus
from core.groups.service import (
    create_group,
    get_group,
    grant_group,
    granted_group_for,
    list_groups,
    pending_group_count,
    reject_group,
    request_group,
    set_github_username,
)
from core.submissions.service import (
    get_submission,
    get_submission_text,
    latest_submission,
    list_submissions,
    submit,
)

MATE = "someone.else@pccoepune.org"
OUTSIDER = "outsider@pccoepune.org"


@pytest.fixture
def classmates(db_factory, world):
    """Put the second student in the *same* subject, so a group is possible.

    The shared world deliberately keeps them apart; a group needs them
    together, and doing it here rather than in the fixture keeps every other
    isolation test asserting what it was written to assert.
    """
    with session_scope(db_factory) as session:
        session.add(Enrollment(student_email=MATE, subject_id=world.subject_a))
        session.add(User(email=OUTSIDER, role=world.student_1.role, name="Outsider"))
        session.flush()
        session.add(Enrollment(student_email=OUTSIDER, subject_id=world.subject_a))

    from core.auth.actor import Actor

    return Actor(email=MATE, role=world.student_2.role, name="Someone")


def request_a_group(db_factory, world, actor):
    with session_scope(db_factory) as session:
        return request_group(
            actor,
            session,
            subject_id=world.subject_a,
            name="Team Alpha",
            member_emails=[actor.email, MATE],
        )


class TestOnlyFacultyGrant:
    def test_a_student_request_starts_pending(
        self, db_factory, world, classmates
    ) -> None:
        group = request_a_group(db_factory, world, world.student_1)

        assert group.status is GroupStatus.REQUESTED
        assert group.is_pending
        assert not group.is_granted

    def test_a_student_cannot_grant_their_own_request(
        self, db_factory, world, classmates
    ) -> None:
        """The whole decision in one assertion."""
        group = request_a_group(db_factory, world, world.student_1)

        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                grant_group(world.student_1, session, group_id=group.id)

    def test_faculty_grants_it(self, db_factory, world, classmates) -> None:
        group = request_a_group(db_factory, world, world.student_1)

        with session_scope(db_factory) as session:
            granted = grant_group(world.faculty_a, session, group_id=group.id)

        assert granted.is_granted
        assert granted.decided_by == world.faculty_a.email
        assert granted.decided_at is not None

    def test_another_faculty_cannot_grant_it(self, db_factory, world, classmates) -> None:
        group = request_a_group(db_factory, world, world.student_1)

        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                grant_group(world.faculty_b, session, group_id=group.id)

    def test_faculty_can_form_a_group_outright(
        self, db_factory, world, classmates
    ) -> None:
        """The "teacher's request" half — a guide who decides the pairings."""
        with session_scope(db_factory) as session:
            group = create_group(
                world.faculty_a,
                session,
                subject_id=world.subject_a,
                name="Team Beta",
                member_emails=[world.student_1.email, MATE],
            )

        assert group.is_granted
        assert group.requested_by is None

    def test_a_student_cannot_create_a_granted_group(
        self, db_factory, world, classmates
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                create_group(
                    world.student_1,
                    session,
                    subject_id=world.subject_a,
                    name="Team Gamma",
                    member_emails=[world.student_1.email, MATE],
                )

    def test_a_rejection_carries_its_reason(self, db_factory, world, classmates) -> None:
        group = request_a_group(db_factory, world, world.student_1)

        with session_scope(db_factory) as session:
            rejected = reject_group(
                world.faculty_a,
                session,
                group_id=group.id,
                reason="Groups are capped at two this semester.",
            )

        assert rejected.status is GroupStatus.REJECTED
        assert "capped at two" in rejected.decision_note

    def test_a_rejection_without_a_reason_is_refused(
        self, db_factory, world, classmates
    ) -> None:
        group = request_a_group(db_factory, world, world.student_1)

        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError):
                reject_group(world.faculty_a, session, group_id=group.id, reason="   ")


class TestAPendingRequestGrantsNothing:
    """The failure this module is most likely to produce."""

    def test_a_requested_group_does_not_resolve(
        self, db_factory, world, classmates
    ) -> None:
        request_a_group(db_factory, world, world.student_1)

        with session_scope(db_factory) as session:
            found = granted_group_for(
                world.student_1,
                session,
                subject_id=world.subject_a,
                student_email=world.student_1.email,
            )

        assert found is None

    def test_a_named_classmate_cannot_read_the_work_yet(
        self, db_factory, world, classmates, tmp_path
    ) -> None:
        """Naming someone in a request must not open their submissions."""
        request_a_group(db_factory, world, world.student_1)

        with session_scope(db_factory) as session:
            mine = submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files={"synopsis.txt": b"My own work."},
                uploads_root=tmp_path / "uploads",
            )

        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                get_submission(classmates, session, mine.id)

    def test_a_rejected_group_grants_nothing(
        self, db_factory, world, classmates, tmp_path
    ) -> None:
        group = request_a_group(db_factory, world, world.student_1)

        with session_scope(db_factory) as session:
            reject_group(world.faculty_a, session, group_id=group.id, reason="No.")

        with session_scope(db_factory) as session:
            mine = submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files={"synopsis.txt": b"My own work."},
                uploads_root=tmp_path / "uploads",
            )

        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                get_submission(classmates, session, mine.id)

    def test_the_submission_is_not_attributed_to_a_pending_group(
        self, db_factory, world, classmates, tmp_path
    ) -> None:
        request_a_group(db_factory, world, world.student_1)

        with session_scope(db_factory) as session:
            mine = submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files={"synopsis.txt": b"My own work."},
                uploads_root=tmp_path / "uploads",
            )

        assert mine.group_id is None
        assert not mine.is_group_work


class TestGrantedGroupsShareWork:
    @pytest.fixture
    def granted(self, db_factory, world, classmates):
        group = request_a_group(db_factory, world, world.student_1)
        with session_scope(db_factory) as session:
            return grant_group(world.faculty_a, session, group_id=group.id)

    def test_a_submission_is_attributed_to_the_group(
        self, db_factory, world, classmates, granted, tmp_path
    ) -> None:
        with session_scope(db_factory) as session:
            made = submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files={"synopsis.txt": b"Our work."},
                uploads_root=tmp_path / "uploads",
            )

        assert made.group_id == granted.id
        assert made.group_name == "Team Alpha"
        assert made.student_email == world.student_1.email, "the uploader survives"

    def test_a_member_reads_the_work_their_mate_uploaded(
        self, db_factory, world, classmates, granted, tmp_path
    ) -> None:
        with session_scope(db_factory) as session:
            made = submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files={"synopsis.txt": b"Our work."},
                uploads_root=tmp_path / "uploads",
            )

        with session_scope(db_factory) as session:
            seen = get_submission(classmates, session, made.id)
            text = get_submission_text(classmates, session, made.id)
            latest = latest_submission(
                classmates,
                session,
                milestone_id=world.milestone_visible,
                student_email=classmates.email,
            )
            history = list_submissions(
                classmates, session, milestone_id=world.milestone_visible
            )

        assert seen.id == made.id
        assert "Our work" in text
        assert latest is not None and latest.id == made.id
        assert [s.id for s in history] == [made.id]

    def test_an_outsider_still_sees_nothing(
        self, db_factory, world, classmates, granted, tmp_path
    ) -> None:
        """Enrolled in the subject, not in the group. Must stay blind."""
        from core.auth.actor import Actor

        outsider = Actor(email=OUTSIDER, role=world.student_1.role, name="Outsider")

        with session_scope(db_factory) as session:
            made = submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files={"synopsis.txt": b"Our work."},
                uploads_root=tmp_path / "uploads",
            )

        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                get_submission(outsider, session, made.id)

    def test_versions_are_numbered_per_group_not_per_student(
        self, db_factory, world, classmates, granted, tmp_path
    ) -> None:
        """Two members each creating a "v1" makes "which was graded" unanswerable."""
        with session_scope(db_factory) as session:
            first = submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files={"a.txt": b"First cut."},
                uploads_root=tmp_path / "uploads",
            )

        with session_scope(db_factory) as session:
            second = submit(
                classmates,
                session,
                milestone_id=world.milestone_visible,
                files={"b.txt": b"Second cut."},
                uploads_root=tmp_path / "uploads",
            )

        assert (first.version, second.version) == (1, 2)

    def test_the_grid_shows_every_member_on_the_group_row(
        self, db_factory, world, classmates, granted, tmp_path
    ) -> None:
        from core.scoring.grid import list_grid_rows

        with session_scope(db_factory) as session:
            made = submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files={"synopsis.txt": b"Our work."},
                uploads_root=tmp_path / "uploads",
            )

        with session_scope(db_factory) as session:
            rows = list_grid_rows(
                world.faculty_a, session, milestone_id=world.milestone_visible
            )

        by_email = {r.student_email: r for r in rows}

        assert by_email[world.student_1.email].submission_id == made.id
        assert by_email[MATE].submission_id == made.id, "the mate resolves to it too"
        assert by_email[MATE].group_name == "Team Alpha"
        assert by_email[MATE].submitted_by == world.student_1.email
        assert by_email[OUTSIDER].submission_id is None, "not in the group"

    def test_a_student_cannot_be_granted_two_groups_at_once(
        self, db_factory, world, classmates, granted
    ) -> None:
        """Two granted groups makes "which submission is theirs" ambiguous."""
        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError, match="Already in a granted group"):
                create_group(
                    world.faculty_a,
                    session,
                    subject_id=world.subject_a,
                    name="Team Delta",
                    member_emails=[world.student_1.email, OUTSIDER],
                )


class TestValidation:
    def test_a_group_of_one_is_a_student(self, db_factory, world, classmates) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError, match="at least"):
                request_group(
                    world.student_1,
                    session,
                    subject_id=world.subject_a,
                    name="Solo",
                    member_emails=[world.student_1.email],
                )

    def test_a_student_cannot_request_a_group_they_are_not_in(
        self, db_factory, world, classmates
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError, match="one of the members"):
                request_group(
                    world.student_1,
                    session,
                    subject_id=world.subject_a,
                    name="Not mine",
                    member_emails=[MATE, OUTSIDER],
                )

    def test_members_must_be_enrolled(self, db_factory, world, classmates) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError, match="Not enrolled"):
                request_group(
                    world.student_1,
                    session,
                    subject_id=world.subject_a,
                    name="Ghost",
                    member_emails=[world.student_1.email, "nobody@pccoepune.org"],
                )

    def test_a_student_cannot_request_in_a_subject_they_are_not_in(
        self, db_factory, world, classmates
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                request_group(
                    world.student_1,
                    session,
                    subject_id=world.subject_b,
                    name="Elsewhere",
                    member_emails=[world.student_1.email, MATE],
                )

    def test_names_are_unique_within_a_subject(
        self, db_factory, world, classmates
    ) -> None:
        request_a_group(db_factory, world, world.student_1)

        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError, match="already exists"):
                request_group(
                    world.student_1,
                    session,
                    subject_id=world.subject_a,
                    name="Team Alpha",
                    member_emails=[world.student_1.email, OUTSIDER],
                )


class TestListing:
    def test_a_student_sees_only_groups_they_are_named_in(
        self, db_factory, world, classmates
    ) -> None:
        request_a_group(db_factory, world, world.student_1)

        with session_scope(db_factory) as session:
            create_group(
                world.faculty_a,
                session,
                subject_id=world.subject_a,
                name="Someone Elses",
                member_emails=[MATE, OUTSIDER],
            )

        with session_scope(db_factory) as session:
            mine = list_groups(world.student_1, session, subject_id=world.subject_a)
            all_of_them = list_groups(
                world.faculty_a, session, subject_id=world.subject_a
            )

        assert [g.name for g in mine] == ["Team Alpha"]
        assert len(all_of_them) == 2

    def test_a_student_cannot_open_a_group_they_are_not_in(
        self, db_factory, world, classmates
    ) -> None:
        with session_scope(db_factory) as session:
            other = create_group(
                world.faculty_a,
                session,
                subject_id=world.subject_a,
                name="Someone Elses",
                member_emails=[MATE, OUTSIDER],
            )

        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                get_group(world.student_1, session, other.id)

    def test_the_pending_count_is_the_faculty_members_own(
        self, db_factory, world, classmates
    ) -> None:
        request_a_group(db_factory, world, world.student_1)

        with session_scope(db_factory) as session:
            assert pending_group_count(world.faculty_a, session) == 1
            assert pending_group_count(world.faculty_b, session) == 0
            assert pending_group_count(world.student_1, session) == 0


class TestGithubRegister:
    def test_faculty_records_a_students_account(
        self, db_factory, world, classmates
    ) -> None:
        with session_scope(db_factory) as session:
            saved = set_github_username(
                world.faculty_a,
                session,
                student_email=world.student_1.email,
                username="manthan-vs",
            )

        assert saved == "manthan-vs"

    def test_a_leading_at_sign_is_tolerated(self, db_factory, world, classmates) -> None:
        with session_scope(db_factory) as session:
            saved = set_github_username(
                world.faculty_a,
                session,
                student_email=world.student_1.email,
                username="@manthan-vs",
            )

        assert saved == "manthan-vs"

    def test_a_student_cannot_set_their_own(self, db_factory, world, classmates) -> None:
        """Decision #6: a check the checked party configures is not a check."""
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                set_github_username(
                    world.student_1,
                    session,
                    student_email=world.student_1.email,
                    username="whoever",
                )

    def test_faculty_cannot_set_it_for_someone_elses_student(
        self, db_factory, world, classmates
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                set_github_username(
                    world.faculty_b,
                    session,
                    student_email=world.student_1.email,
                    username="manthan-vs",
                )

    def test_an_impossible_account_name_is_refused(
        self, db_factory, world, classmates
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError):
                set_github_username(
                    world.faculty_a,
                    session,
                    student_email=world.student_1.email,
                    username="not a username",
                )

    def test_clearing_it_is_allowed(self, db_factory, world, classmates) -> None:
        with session_scope(db_factory) as session:
            set_github_username(
                world.faculty_a,
                session,
                student_email=world.student_1.email,
                username="manthan-vs",
            )

        with session_scope(db_factory) as session:
            assert (
                set_github_username(
                    world.faculty_a,
                    session,
                    student_email=world.student_1.email,
                    username="",
                )
                is None
            )

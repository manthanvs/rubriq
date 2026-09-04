"""Decision #6 end to end — a URL reaches the database only if it is owned.

``test_links.py`` covers the parser and the ownership rule in isolation. What
this file adds is the part that could still be wrong with a perfect parser: the
service reading the register from the **database** rather than from anything
the student sent, refusing before a file is written, and widening the accepted
owners to group-mates only when a group was actually granted.
"""

from __future__ import annotations

import pytest

from core.auth.actor import Actor
from core.db.engine import session_scope
from core.db.models import Enrollment, Submission, SubmissionLink
from core.errors import ValidationError
from core.groups.service import (
    create_group,
    request_group,
    set_github_username,
)
from core.submissions.service import submit

MATE = "someone.else@pccoepune.org"

MY_REPO = "https://github.com/manthan-vs/rubriq"
MATES_REPO = "https://github.com/rahul-d/rubriq"
STRANGERS_REPO = "https://github.com/torvalds/linux"


@pytest.fixture
def registered(db_factory, world):
    """The student's GitHub account, on record — set by faculty."""
    with session_scope(db_factory) as session:
        set_github_username(
            world.faculty_a,
            session,
            student_email=world.student_1.email,
            username="manthan-vs",
        )


@pytest.fixture
def mate(db_factory, world):
    with session_scope(db_factory) as session:
        session.add(Enrollment(student_email=MATE, subject_id=world.subject_a))
        session.flush()
        set_github_username(
            world.faculty_a, session, student_email=MATE, username="rahul-d"
        )

    return Actor(email=MATE, role=world.student_2.role, name="Someone")


def submit_with(db_factory, world, tmp_path, actor, links, files=None):
    with session_scope(db_factory) as session:
        return submit(
            actor,
            session,
            milestone_id=world.milestone_visible,
            files=files if files is not None else {"a.txt": b"Work."},
            uploads_root=tmp_path / "uploads",
            links=links,
        )


class TestOwnRepository:
    def test_a_registered_students_own_repository_is_stored(
        self, db_factory, world, registered, tmp_path
    ) -> None:
        made = submit_with(db_factory, world, tmp_path, world.student_1, [MY_REPO])

        assert len(made.links) == 1
        link = made.links[0]
        assert (link.owner, link.repo) == ("manthan-vs", "rubriq")
        assert link.matched_profile == world.student_1.email

    def test_a_strangers_repository_is_refused(
        self, db_factory, world, registered, tmp_path
    ) -> None:
        """The requirement, stated as a test."""
        with pytest.raises(ValidationError, match="not an account on record"):
            submit_with(db_factory, world, tmp_path, world.student_1, [STRANGERS_REPO])

    def test_a_refused_link_writes_no_submission_at_all(
        self, db_factory, world, registered, tmp_path
    ) -> None:
        """Validation runs before any file lands, so there is nothing to clean up."""
        with pytest.raises(ValidationError):
            submit_with(db_factory, world, tmp_path, world.student_1, [STRANGERS_REPO])

        with session_scope(db_factory) as session:
            assert session.query(Submission).count() == 0
            assert session.query(SubmissionLink).count() == 0

    def test_an_unregistered_student_gets_an_administrative_message(
        self, db_factory, world, tmp_path
    ) -> None:
        """No profile on record is not something the student can fix by editing."""
        with pytest.raises(ValidationError, match="Ask your guide"):
            submit_with(db_factory, world, tmp_path, world.student_1, [MY_REPO])

    def test_the_register_is_read_from_the_database(
        self, db_factory, world, tmp_path
    ) -> None:
        """Before faculty record it, the very same URL is refused."""
        with pytest.raises(ValidationError):
            submit_with(db_factory, world, tmp_path, world.student_1, [MY_REPO])

        with session_scope(db_factory) as session:
            set_github_username(
                world.faculty_a,
                session,
                student_email=world.student_1.email,
                username="manthan-vs",
            )

        made = submit_with(db_factory, world, tmp_path, world.student_1, [MY_REPO])
        assert len(made.links) == 1


class TestGroupRepositories:
    def test_a_granted_group_may_submit_a_mates_repository(
        self, db_factory, world, registered, mate, tmp_path
    ) -> None:
        with session_scope(db_factory) as session:
            create_group(
                world.faculty_a,
                session,
                subject_id=world.subject_a,
                name="Team Alpha",
                member_emails=[world.student_1.email, MATE],
            )

        made = submit_with(db_factory, world, tmp_path, world.student_1, [MATES_REPO])

        assert made.links[0].matched_profile == MATE

    def test_a_pending_request_does_not_widen_the_register(
        self, db_factory, world, registered, mate, tmp_path
    ) -> None:
        """A group nobody granted is not a group — decision #5 meeting #6."""
        with session_scope(db_factory) as session:
            request_group(
                world.student_1,
                session,
                subject_id=world.subject_a,
                name="Team Alpha",
                member_emails=[world.student_1.email, MATE],
            )

        with pytest.raises(ValidationError, match="not an account on record"):
            submit_with(db_factory, world, tmp_path, world.student_1, [MATES_REPO])


class TestSubmissionShape:
    def test_a_link_alone_is_a_submission(
        self, db_factory, world, registered, tmp_path
    ) -> None:
        """A repository *is* the deliverable for some milestones."""
        made = submit_with(db_factory, world, tmp_path, world.student_1, [MY_REPO], {})

        assert made.files == ()
        assert len(made.links) == 1
        assert not made.has_text, "nothing was extracted, and nothing pretends otherwise"

    def test_neither_files_nor_links_is_refused(
        self, db_factory, world, registered, tmp_path
    ) -> None:
        with pytest.raises(ValidationError, match="at least one file"):
            submit_with(db_factory, world, tmp_path, world.student_1, [], {})

    def test_the_same_repository_twice_is_refused(
        self, db_factory, world, registered, tmp_path
    ) -> None:
        with pytest.raises(ValidationError, match="listed twice"):
            submit_with(
                db_factory,
                world,
                tmp_path,
                world.student_1,
                [MY_REPO, f"{MY_REPO}.git"],
            )

    def test_a_new_version_carries_its_own_links(
        self, db_factory, world, registered, tmp_path
    ) -> None:
        first = submit_with(db_factory, world, tmp_path, world.student_1, [MY_REPO])
        second = submit_with(db_factory, world, tmp_path, world.student_1, [])

        assert len(first.links) == 1
        assert second.links == (), "links are per version, not inherited"

    def test_the_url_is_kept_as_typed(
        self, db_factory, world, registered, tmp_path
    ) -> None:
        made = submit_with(
            db_factory,
            world,
            tmp_path,
            world.student_1,
            ["git@github.com:manthan-vs/rubriq.git"],
        )

        link = made.links[0]
        assert link.url == "git@github.com:manthan-vs/rubriq.git"
        assert link.normalised_url == MY_REPO

    def test_nothing_fetches_the_repository(
        self, db_factory, world, registered, tmp_path
    ) -> None:
        """The URL is an artifact, not a text source.

        If this ever starts failing because someone added a fetch, that is a
        design change to argue for rather than a test to update: evidence has
        to come from text the student submitted, or the guard in §6.5 has
        nothing to verify a span against.
        """
        made = submit_with(db_factory, world, tmp_path, world.student_1, [MY_REPO], {})

        assert made.text_extract_chars == 0

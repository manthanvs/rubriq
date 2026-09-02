"""Fix item 3, and the Phase 2 exit criterion.

§10's Phase 2 exit: *"faculty creates a subject with two milestones; the
enrolled student sees exactly those two and nothing else."* The "and nothing
else" is the whole test — a query that returns the right rows plus one is the
bug this file exists to catch.
"""

from __future__ import annotations

import pytest

from core.academics.enrollment import list_enrollments
from core.academics.milestones import (
    create_milestone,
    get_milestone,
    list_milestones,
    set_milestone_visibility,
)
from core.academics.subjects import create_subject, get_subject, list_subjects
from core.db.engine import session_scope
from core.errors import NotAuthorized, ValidationError


class TestSubjectScoping:
    def test_faculty_sees_only_their_own_subjects(self, db_factory, world) -> None:
        with session_scope(db_factory) as session:
            mine = list_subjects(world.faculty_a, session)
            theirs = list_subjects(world.faculty_b, session)

        assert [s.id for s in mine] == [world.subject_a]
        assert [s.id for s in theirs] == [world.subject_b]

    def test_faculty_cannot_open_a_colleagues_subject(self, db_factory, world) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                get_subject(world.faculty_b, session, world.subject_a)

    def test_student_sees_only_subjects_they_are_enrolled_in(
        self, db_factory, world
    ) -> None:
        with session_scope(db_factory) as session:
            visible = list_subjects(world.student_1, session)

        assert [s.id for s in visible] == [world.subject_a]

    def test_student_cannot_open_another_students_subject(
        self, db_factory, world
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                get_subject(world.student_1, session, world.subject_b)

    def test_a_student_cannot_create_a_subject(self, db_factory, world) -> None:
        """Invariant #5 in practice: role gates the write, not the button."""
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                create_subject(
                    world.student_1, session, code="FAKE01", name="Mine", semester=3
                )

    def test_a_student_cannot_list_the_class_roll(self, db_factory, world) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises((NotAuthorized, ValidationError)):
                list_enrollments(world.student_1, session, world.subject_a)

    def test_faculty_can_list_their_own_roll(self, db_factory, world) -> None:
        with session_scope(db_factory) as session:
            roll = list_enrollments(world.faculty_a, session, world.subject_a)

        assert [e.student_email for e in roll] == [world.student_1.email]


class TestMilestoneScoping:
    def test_faculty_sees_visible_and_draft_milestones(self, db_factory, world) -> None:
        with session_scope(db_factory) as session:
            found = list_milestones(world.faculty_a, session)

        assert {m.id for m in found} == {world.milestone_visible, world.milestone_hidden}

    def test_a_draft_milestone_is_absent_for_students(self, db_factory, world) -> None:
        """Not hidden in the UI — absent from the query."""
        with session_scope(db_factory) as session:
            found = list_milestones(world.student_1, session)

        assert [m.id for m in found] == [world.milestone_visible]

    def test_a_student_cannot_fetch_a_draft_milestone_by_id(
        self, db_factory, world
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                get_milestone(world.student_1, session, world.milestone_hidden)

    def test_a_student_sees_nothing_from_another_subject(self, db_factory, world) -> None:
        with session_scope(db_factory) as session:
            found = list_milestones(world.student_2, session)

        assert found == ()

    def test_a_student_cannot_publish_a_milestone(self, db_factory, world) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                set_milestone_visibility(
                    world.student_1,
                    session,
                    milestone_id=world.milestone_hidden,
                    is_visible=True,
                )

    def test_faculty_cannot_publish_a_colleagues_milestone(
        self, db_factory, world
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                set_milestone_visibility(
                    world.faculty_b,
                    session,
                    milestone_id=world.milestone_hidden,
                    is_visible=True,
                )

    def test_faculty_cannot_add_a_milestone_to_a_colleagues_cycle(
        self, db_factory, world
    ) -> None:
        from datetime import UTC, datetime

        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                create_milestone(
                    world.faculty_b,
                    session,
                    cycle_id=world.cycle_a,
                    index=9,
                    title="Injected",
                    due_at=datetime(2026, 12, 1, tzinfo=UTC),
                    max_marks=10,
                )


class TestPhase2ExitCriterion:
    """ "Faculty creates a subject with two milestones; the enrolled student
    sees exactly those two and nothing else."""

    def test_the_enrolled_student_sees_exactly_the_published_milestones(
        self, db_factory, world
    ) -> None:
        with session_scope(db_factory) as session:
            set_milestone_visibility(
                world.faculty_a,
                session,
                milestone_id=world.milestone_hidden,
                is_visible=True,
            )

        with session_scope(db_factory) as session:
            seen = list_milestones(world.student_1, session)

        assert [(m.index, m.title) for m in seen] == [
            (1, "Review 1"),
            (2, "Review 2 (draft)"),
        ]
        assert {m.subject_id for m in seen} == {world.subject_a}

    def test_and_nothing_else(self, db_factory, world) -> None:
        """The other subject's student still sees none of it."""
        with session_scope(db_factory) as session:
            set_milestone_visibility(
                world.faculty_a,
                session,
                milestone_id=world.milestone_hidden,
                is_visible=True,
            )

        with session_scope(db_factory) as session:
            assert list_milestones(world.student_2, session) == ()
            assert list_subjects(world.student_2, session)[0].id == world.subject_b

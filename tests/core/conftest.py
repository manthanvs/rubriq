"""A two-faculty, two-student world, shared by every test under tests/core.

Isolation bugs hide in single-tenant fixtures: with one faculty member and one
student, every query looks correctly scoped because there is nothing else to
leak. So the fixture always contains a second subject, owned by someone else,
with someone else's student in it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from core.academics.milestones import create_milestone
from core.academics.subjects import create_cycle, create_subject
from core.auth.actor import Actor
from core.auth.roles import Role
from core.config import Settings
from core.db.engine import session_scope
from core.db.models import Enrollment, User

FACULTY_A = "guide@pccoepune.org"
FACULTY_B = "other.faculty@pccoepune.org"
STUDENT_1 = "manthan.sankpal@pccoepune.org"
STUDENT_2 = "someone.else@pccoepune.org"


@dataclass(frozen=True)
class World:
    faculty_a: Actor
    faculty_b: Actor
    student_1: Actor
    student_2: Actor
    subject_a: int
    subject_b: int
    cycle_a: int
    milestone_visible: int
    milestone_hidden: int


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="sqlite://",
        faculty_allowlist=(FACULTY_A, FACULTY_B),
    )


@pytest.fixture
def world(db_factory) -> World:
    faculty_a = Actor(email=FACULTY_A, role=Role.FACULTY, name="Anjana")
    faculty_b = Actor(email=FACULTY_B, role=Role.FACULTY, name="Other")
    student_1 = Actor(email=STUDENT_1, role=Role.STUDENT, name="Manthan")
    student_2 = Actor(email=STUDENT_2, role=Role.STUDENT, name="Someone")

    with session_scope(db_factory) as session:
        for actor in (faculty_a, faculty_b, student_1, student_2):
            session.add(User(email=actor.email, role=actor.role, name=actor.name))
        session.flush()

        subject_a = create_subject(
            faculty_a, session, code="MCA33EL03", name="Mini Project", semester=3
        )
        subject_b = create_subject(
            faculty_b, session, code="MCA33EL04", name="Other Subject", semester=3
        )

        cycle_a = create_cycle(
            faculty_a,
            session,
            subject_id=subject_a.id,
            title="Project 2026",
            academic_year="2026-27",
        )

        visible = create_milestone(
            faculty_a,
            session,
            cycle_id=cycle_a.id,
            index=1,
            title="Review 1",
            due_at=datetime(2026, 10, 1, 18, 30, tzinfo=UTC),
            max_marks=25,
            is_visible=True,
        )
        hidden = create_milestone(
            faculty_a,
            session,
            cycle_id=cycle_a.id,
            index=2,
            title="Review 2 (draft)",
            due_at=datetime(2026, 11, 1, 18, 30, tzinfo=UTC),
            max_marks=25,
            is_visible=False,
        )

        session.add(Enrollment(student_email=STUDENT_1, subject_id=subject_a.id))
        session.add(Enrollment(student_email=STUDENT_2, subject_id=subject_b.id))

        return World(
            faculty_a=faculty_a,
            faculty_b=faculty_b,
            student_1=student_1,
            student_2=student_2,
            subject_a=subject_a.id,
            subject_b=subject_b.id,
            cycle_a=cycle_a.id,
            milestone_visible=visible.id,
            milestone_hidden=hidden.id,
        )

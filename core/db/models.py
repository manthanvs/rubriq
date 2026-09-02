"""ORM models.

The §4 domain model lands one phase at a time. Present here:

* ``User``            — identity and role (Phase 1)
* ``AuditLog``        — every mutation writes one row (Phase 1, read in Phase 7)
* ``Subject``         — a taught subject, owned by one faculty member (Phase 2)
* ``Enrollment``      — which student is in which subject (Phase 2)
* ``ProjectCycle``    — one run of a project through a subject (Phase 2)
* ``ReviewMilestone`` — a dated review with marks attached (Phase 2)

Rubric, Criterion and Submission arrive in Phase 3. Every entity ships with
its migration in the same commit (§12).

**Marks are ``Numeric``, never ``Float``.** Fix item 1 names float drift
rendering 19.999999 as a way score integrity breaks; the cheapest place to
prevent that is the column type, before any arithmetic exists to get wrong.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from core.auth.roles import Role
from core.clock import utc_now
from core.db.types import JSONColumn, UtcDateTime


class Base(DeclarativeBase):
    """Base class for all RubriQ tables."""


class User(Base):
    """A person, keyed by their institute email.

    The email *is* the primary key: it comes from the OIDC claim, it is what
    the faculty allow-list is written in, and it is what enrollment CSVs
    contain. A surrogate id would add a lookup and buy nothing.

    ``role`` is a cache of :func:`core.auth.roles.resolve_role`, refreshed on
    every sign-in. The allow-list is the authority, never this column
    (invariant #5).
    """

    __tablename__ = "users"  # "user" is a reserved word in several engines

    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    role: Mapped[Role] = mapped_column(
        Enum(Role, native_enum=False, length=16),
        nullable=False,
        default=Role.STUDENT,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    department: Mapped[str | None] = mapped_column(String(120))
    prn: Mapped[str | None] = mapped_column(String(32), index=True)
    employee_id: Mapped[str | None] = mapped_column(String(32))

    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        UtcDateTime(),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<User {self.email} {self.role}>"


class AuditLog(Base):
    """One row per mutation (§12).

    Written from Phase 1, surfaced in the UI in Phase 7 (fix item 15). It is
    what answers "how do you know the faculty member, not the AI, decided this
    mark?" — so it is populated from the beginning, not retrofitted.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(120), index=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONColumn)
    at: Mapped[datetime] = mapped_column(
        UtcDateTime(),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} {self.entity}:{self.entity_id}>"


class Subject(Base):
    """A taught subject, owned by exactly one faculty member.

    ``owner_email`` is the whole authorisation story for the teaching side:
    every faculty query in ``core/academics/`` filters on it, so a faculty
    member listing subjects gets theirs and nobody else's (invariant #6).
    """

    __tablename__ = "subject"
    __table_args__ = (UniqueConstraint("code", "semester", name="uq_subject_code_sem"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    semester: Mapped[int] = mapped_column(Integer, nullable=False)
    owner_email: Mapped[str] = mapped_column(
        String(320), ForeignKey("users.email"), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<Subject {self.code} sem{self.semester}>"


class Enrollment(Base):
    """One student in one subject.

    Deactivated rather than deleted, so a student who drops the subject does
    not take their submission history with them (invariant #7).
    """

    __tablename__ = "enrollment"
    __table_args__ = (
        UniqueConstraint("student_email", "subject_id", name="uq_enrollment_student"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_email: Mapped[str] = mapped_column(
        String(320), ForeignKey("users.email"), nullable=False, index=True
    )
    subject_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subject.id"), nullable=False, index=True
    )
    batch: Mapped[str | None] = mapped_column(String(32))
    group_label: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<Enrollment {self.student_email} -> {self.subject_id}>"


class ProjectCycle(Base):
    """One run of a project through a subject, in one academic year."""

    __tablename__ = "project_cycle"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subject.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    academic_year: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<ProjectCycle {self.title} {self.academic_year}>"


class ReviewMilestone(Base):
    """A dated review with marks attached.

    ``is_visible`` is the faculty's draft switch: an invisible milestone is
    absent from every student query, not merely hidden in the student's UI.

    ``max_marks`` is ``Numeric`` because §5.1's penalties are percentages of
    it, and a percentage of a float is how 19.999999 gets onto a mark sheet.
    """

    __tablename__ = "review_milestone"
    __table_args__ = (
        UniqueConstraint("cycle_id", "index", name="uq_milestone_cycle_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project_cycle.id"), nullable=False, index=True
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    max_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<ReviewMilestone {self.index}: {self.title}>"

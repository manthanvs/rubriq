"""ORM models.

The §4 domain model lands one phase at a time. Present here:

* ``User``     — identity and role (Phase 1)
* ``AuditLog`` — every mutation writes one row (Phase 1, read in Phase 7)

Subject, Enrollment and ReviewMilestone arrive in Phase 2; Rubric, Criterion
and Submission in Phase 3. Every entity ships with its migration in the same
commit (§12).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from core.auth.roles import Role
from core.clock import utc_now
from core.db.types import JSONVariant


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

    __tablename__ = "users"  # not "user" — reserved word in Postgres

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
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
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
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} {self.entity}:{self.entity_id}>"

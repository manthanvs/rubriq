"""Declarative base.

No entities yet — the domain model in §4 lands with the phase that needs it
(User and role in Phase 1, Subject/Enrollment/Milestone in Phase 2, Rubric and
Submission in Phase 3). Until then ``Base.metadata`` is empty on purpose, and
an Alembic autogenerate run will correctly produce an empty migration.

Every entity added here ships with its Alembic migration in the same commit.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all RubriQ tables."""

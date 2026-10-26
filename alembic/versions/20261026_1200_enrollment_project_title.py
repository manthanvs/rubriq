"""enrollment project title

The department's assessment sheet prints a Project Title for every student,
and nothing in the schema held one. It belongs to the enrolment: the project
is the same thing across both reviews of a subject.

Revision ID: 9c1e5a7b2d40
Revises: 4f3792f32360
Create Date: 2026-10-26 12:00:00+05:30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9c1e5a7b2d40"
down_revision: str | None = "4f3792f32360"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("enrollment", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("project_title", sa.String(length=200), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("enrollment", schema=None) as batch_op:
        batch_op.drop_column("project_title")

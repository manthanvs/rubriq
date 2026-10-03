"""create the group and link tables phase 8 never created

Phase 8's migration added ``submission.group_id`` and a foreign key pointing
at ``project_group`` -- but never created ``project_group``,
``group_member`` or ``submission_link``. Autogenerate emitted the ALTERs and
missed the three new tables.

Nothing noticed, for two reasons that compounded. The development database
predates that migration and already held the tables, so ``alembic upgrade
head`` had nothing left to do there; and the test suite builds its schema with
``Base.metadata.create_all``, so no test has ever run a migration. The gap only
appeared on a host building the database from nothing, where seeding died on
``no such table: project_group``.

**Idempotent on purpose.** By the time this exists, a database can be stamped
at the previous head either with those tables (anything that grew alongside the
code) or without them (anything built from scratch). One migration has to leave
both correct, so each table is created only if it is absent.


Revision ID: 4f3792f32360
Revises: 1a98d1247246
Create Date: 2026-10-03 19:47:17.845951+05:30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '4f3792f32360'
down_revision: str | None = '1a98d1247246'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "project_group" not in existing:
        op.create_table(
            "project_group",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("subject_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column(
                "status",
                sa.Enum(
                    "REQUESTED", "GRANTED", "REJECTED",
                    name="groupstatus", native_enum=False, length=16,
                ),
                nullable=False,
            ),
            sa.Column("requested_by", sa.String(length=320), nullable=True),
            sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("decided_by", sa.String(length=320), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("decision_note", sa.Text(), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.ForeignKeyConstraint(["decided_by"], ["users.email"]),
            sa.ForeignKeyConstraint(["requested_by"], ["users.email"]),
            sa.ForeignKeyConstraint(["subject_id"], ["subject.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("subject_id", "name", name="uq_group_subject_name"),
        )
        op.create_index("ix_project_group_status", "project_group", ["status"])
        op.create_index(
            "ix_project_group_subject_id", "project_group", ["subject_id"]
        )

    if "group_member" not in existing:
        op.create_table(
            "group_member",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("group_id", sa.Integer(), nullable=False),
            sa.Column("student_email", sa.String(length=320), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.ForeignKeyConstraint(["group_id"], ["project_group.id"]),
            sa.ForeignKeyConstraint(["student_email"], ["users.email"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("group_id", "student_email", name="uq_group_member"),
        )
        op.create_index("ix_group_member_group_id", "group_member", ["group_id"])
        op.create_index(
            "ix_group_member_student_email", "group_member", ["student_email"]
        )

    if "submission_link" not in existing:
        op.create_table(
            "submission_link",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("submission_id", sa.Integer(), nullable=False),
            sa.Column("url", sa.String(length=500), nullable=False),
            sa.Column("normalised_url", sa.String(length=500), nullable=False),
            sa.Column("owner", sa.String(length=39), nullable=False),
            sa.Column("repo", sa.String(length=100), nullable=False),
            sa.Column("ref", sa.String(length=255), nullable=True),
            sa.Column("matched_profile", sa.String(length=320), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.ForeignKeyConstraint(["matched_profile"], ["users.email"]),
            sa.ForeignKeyConstraint(["submission_id"], ["submission.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_submission_link_owner", "submission_link", ["owner"])
        op.create_index(
            "ix_submission_link_submission_id", "submission_link", ["submission_id"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    for table in ("submission_link", "group_member", "project_group"):
        if table in existing:
            op.drop_table(table)

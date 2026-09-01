"""user and audit log

Revision ID: 4c5ce39a003b
Revises:
Create Date: 2026-09-01 18:15:23.097097+05:30

Phase 1. Reviewed by hand after autogenerate, which produced two things that
would have broken on Postgres:

* ``postgresql.JSONB(astext_type=Text())`` — ``Text`` was never imported.
* ``server_default=sa.text('(CURRENT_TIMESTAMP)')`` — a SQLite literal, baked
  in because autogenerate ran against the local SQLite dev database.

Both are replaced below with dialect-neutral forms. The JSON column is written
out in full rather than imported from ``core.db.types`` so this migration stays
a frozen snapshot: changing the type helper later must not rewrite history.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "4c5ce39a003b"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: JSONB on Postgres, JSON on SQLite. Mirrors core.db.types.JSONVariant.
JSON_VARIANT = sa.JSON().with_variant(
    postgresql.JSONB(astext_type=sa.Text()), "postgresql"
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "STUDENT", "FACULTY", "ADMIN", name="role", native_enum=False, length=16
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("department", sa.String(length=120), nullable=True),
        sa.Column("prn", sa.String(length=32), nullable=True),
        sa.Column("employee_id", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("email"),
    )
    op.create_index("ix_users_prn", "users", ["prn"], unique=False)

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("actor_email", sa.String(length=320), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=120), nullable=True),
        sa.Column("payload", JSON_VARIANT, nullable=True),
        sa.Column(
            "at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_action", "audit_log", ["action"], unique=False)
    op.create_index(
        "ix_audit_log_actor_email", "audit_log", ["actor_email"], unique=False
    )
    op.create_index("ix_audit_log_entity_id", "audit_log", ["entity_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_log_entity_id", table_name="audit_log")
    op.drop_index("ix_audit_log_actor_email", table_name="audit_log")
    op.drop_index("ix_audit_log_action", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_users_prn", table_name="users")
    op.drop_table("users")

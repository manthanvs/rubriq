"""Column types that differ between the target database and the dev one.

Postgres is the target (§3) and SQLite is permitted for local development.
Declaring the difference once, here, keeps every model free of dialect checks.
"""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

#: JSONB on Postgres — indexable, which matters for AuditLog and for the
#: raw_response payloads in Phase 5 — and plain JSON on SQLite.
JSONVariant = JSON().with_variant(JSONB(), "postgresql")

"""Column types that differ between the target database and the dev one.

Postgres is the target (§3) and SQLite is permitted for local development.
Declaring the difference once, here, keeps every model free of dialect checks.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB

#: JSONB on Postgres — indexable, which matters for AuditLog and for the
#: raw_response payloads in Phase 5 — and plain JSON on SQLite.
JSONVariant = JSON().with_variant(JSONB(), "postgresql")


class UtcDateTime(TypeDecorator):
    """A timestamp that is always stored as UTC and always read back aware.

    This exists because of a bug that reached the screen before it was caught:
    a milestone entered as ``23:59 IST`` was stored by SQLite as the string
    ``23:59`` with the ``+05:30`` **discarded rather than converted**, then read
    back as naive, assumed to be UTC, and rendered as ``05:29`` the next
    morning — the offset applied twice.

    Postgres ``timestamptz`` converts on the way in, so the same code was
    correct there and wrong on the dev database. That asymmetry is the danger:
    §5.1's late-penalty boundary is computed from these columns, so a deadline
    that drifts by 5½ hours silently changes who is marked late.

    Normalising here rather than in each service means no caller has to
    remember, and a naive datetime is rejected loudly instead of being guessed
    at.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None

        if value.tzinfo is None:
            raise ValueError(
                "Refusing to store a naive datetime. Attach a timezone at the "
                "point the value is created — see core.clock."
            )

        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None

        # Postgres hands back an aware value; SQLite does not.
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

"""Time.

One place that says what "now" is, so tests can reason about it and so no
module reaches for a naive ``datetime.now()``. Everything is stored in UTC.

The ``Asia/Kolkata`` conversion that §5.1's late-penalty boundary depends on
arrives with the scoring engine in Phase 4 — it belongs next to the rule it
serves, not here.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Timezone-aware current time in UTC."""
    return datetime.now(UTC)


def ensure_utc(value: datetime | None) -> datetime | None:
    """Attach UTC to a naive datetime read back from the database.

    Postgres ``timestamptz`` round-trips an aware datetime; SQLite does not,
    and hands back a naive one. Subtracting the two raises ``TypeError``, so
    every datetime that comes *out* of the database passes through here before
    it is compared to anything.
    """
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

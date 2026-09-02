"""Time.

One place that says what "now" is, so tests can reason about it and so no
module reaches for a naive ``datetime.now()``. Everything is stored in UTC.

The ``Asia/Kolkata`` conversion that §5.1's late-penalty boundary depends on
arrives with the scoring engine in Phase 4 — it belongs next to the rule it
serves, not here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

#: India Standard Time, as a fixed offset.
#:
#: Deliberately not ``ZoneInfo("Asia/Kolkata")``. Windows ships no IANA
#: database, so ``zoneinfo`` there depends on the ``tzdata`` package being
#: installed — a dependency that, when missing, fails at runtime on the
#: demo machine rather than at install time.
#:
#: A fixed offset is safe here specifically because India has observed no
#: daylight saving since 1945 and has a single time zone. If this were
#: Europe/London the shortcut would be wrong and ``tzdata`` would be required.
IST = timezone(timedelta(hours=5, minutes=30), name="IST")


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


def to_ist(value: datetime) -> datetime:
    """Render-time conversion to IST.

    Storage is UTC and display is IST; the two are never mixed. A naive value
    read back from SQLite is assumed UTC first (see :func:`ensure_utc`), so
    this is safe on both dialects.
    """
    return ensure_utc(value).astimezone(IST)


def ist_date(value: datetime):
    """The calendar date in IST.

    §5.1 computes days-late from the *date* in Asia/Kolkata, which is what
    makes the 11:59 PM boundary unambiguous. The scoring engine in Phase 4
    calls this on both sides of that subtraction.
    """
    return to_ist(value).date()

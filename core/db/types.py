"""Custom column types.

SQLite is the database (decision #8). These types exist because SQLite's
defaults are not what this application needs, not because two dialects have to
be reconciled.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, TypeDecorator

#: JSON payloads — ``AuditLog.payload`` now, ``Evaluation.raw_response`` from
#: Phase 5. SQLite stores JSON as text and SQLAlchemy handles the
#: serialisation, so values round-trip as Python dicts either way.
#:
#: SQLite cannot index *inside* a JSON document the way Postgres JSONB can. It
#: does not need to here: every JSON column is read by primary key or by an
#: indexed column beside it, never searched by its contents.
JSONColumn = JSON()


class UtcDateTime(TypeDecorator):
    """A timestamp that is always stored as UTC and always read back aware.

    This exists because of a bug that reached the screen before it was caught:
    a milestone entered as ``23:59 IST`` was stored by SQLite as the string
    ``23:59`` with the ``+05:30`` **discarded rather than converted**, then read
    back as naive, assumed to be UTC, and rendered as ``05:29`` the next
    morning — the offset applied twice.

    SQLite has no timezone-aware type at all: it stores whatever string it is
    given. So the conversion has to happen here, in Python, on the way in and
    on the way out. §5.1's late-penalty boundary is computed from these
    columns, and a deadline that drifts by 5½ hours silently changes who is
    marked late.

    A naive datetime is rejected loudly rather than guessed at, because
    guessing is exactly how the original bug happened.
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

        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

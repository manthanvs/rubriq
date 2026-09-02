"""Timestamps survive a round trip as the same instant.

Regression test for a bug that reached the screen: a milestone entered as
``23:59 IST`` came back rendered as ``05:29`` the next morning, because SQLite
stored the wall-clock time and threw the ``+05:30`` away rather than
converting it. Postgres would have been correct, so this was invisible to
every test that did not actually go through the database.

It matters beyond cosmetics: §5.1 computes days-late from these columns, so a
deadline drifting by 5½ hours changes who is recorded as late — fix item 1.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from core.clock import IST, ist_date, to_ist
from core.db.models import ReviewMilestone


def _milestone(db_factory, due_at: datetime) -> int:
    from core.db.engine import session_scope

    with session_scope(db_factory) as session:
        milestone = ReviewMilestone(
            cycle_id=1,
            index=1,
            title="Review 1",
            due_at=due_at,
            max_marks=25,
            is_visible=True,
        )
        session.add(milestone)
        session.flush()
        return milestone.id


@pytest.fixture
def cycle_row(db_factory):
    """A bare cycle row, so the milestone's foreign key resolves."""
    from core.db.engine import session_scope

    with session_scope(db_factory) as session:
        # users first — subject.owner_email references it, and foreign keys
        # are enforced on SQLite here (see build_engine).
        session.execute(
            text(
                "INSERT INTO users (email, role, name, created_at, last_seen_at)"
                " VALUES ('f@pccoepune.org', 'FACULTY', 'F', '2026-01-01', '2026-01-01')"
            )
        )
        session.execute(
            text(
                "INSERT INTO subject (id, code, name, semester, owner_email, is_active,"
                " created_at) VALUES (1, 'X', 'X', 3, 'f@pccoepune.org', 1, '2026-01-01')"
            )
        )
        session.execute(
            text(
                "INSERT INTO project_cycle (id, subject_id, title, academic_year,"
                " is_active, created_at) VALUES (1, 1, 'C', '2026-27', 1, '2026-01-01')"
            )
        )


def test_an_ist_deadline_comes_back_as_the_same_instant(db_factory, cycle_row) -> None:
    from core.db.engine import session_scope

    due_at = datetime(2026, 10, 10, 23, 59, tzinfo=IST)
    milestone_id = _milestone(db_factory, due_at)

    with session_scope(db_factory) as session:
        stored = session.get(ReviewMilestone, milestone_id).due_at

    assert stored == due_at, "the same moment in time"
    assert to_ist(stored).hour == 23
    assert to_ist(stored).minute == 59
    assert ist_date(stored) == due_at.date()


def test_it_is_stored_as_utc_not_as_the_local_wall_clock(db_factory, cycle_row) -> None:
    """The actual defect: SQLite kept 23:59 and dropped the offset."""
    from core.db.engine import session_scope

    _milestone(db_factory, datetime(2026, 10, 10, 23, 59, tzinfo=IST))

    with session_scope(db_factory) as session:
        raw = session.execute(text("SELECT due_at FROM review_milestone")).scalar_one()

    assert "18:29" in str(raw), f"expected UTC 18:29 in the column, found {raw!r}"
    assert "23:59" not in str(raw), "the IST wall clock must not be what is stored"


def test_a_utc_deadline_round_trips_unchanged(db_factory, cycle_row) -> None:
    from core.db.engine import session_scope

    due_at = datetime(2026, 10, 10, 18, 29, tzinfo=UTC)
    milestone_id = _milestone(db_factory, due_at)

    with session_scope(db_factory) as session:
        assert session.get(ReviewMilestone, milestone_id).due_at == due_at


def test_a_naive_datetime_is_refused_rather_than_guessed_at(
    db_factory, cycle_row
) -> None:
    """Silently assuming a zone is how the original bug happened."""
    from core.db.engine import session_scope

    with pytest.raises(Exception) as excinfo:
        with session_scope(db_factory) as session:
            session.add(
                ReviewMilestone(
                    cycle_id=1,
                    index=2,
                    title="Naive",
                    due_at=datetime(2026, 10, 10, 23, 59),  # no tzinfo
                    max_marks=25,
                )
            )

    assert "naive" in str(excinfo.value).lower()


def test_every_datetime_column_uses_the_utc_type() -> None:
    """Guards against a new model reintroducing a plain DateTime."""
    from sqlalchemy import DateTime

    from core.db.models import Base
    from core.db.types import UtcDateTime

    offenders = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, DateTime) and not isinstance(column.type, UtcDateTime)
    ]

    assert not offenders, f"these columns bypass UtcDateTime: {offenders}"

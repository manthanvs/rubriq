"""SQLite is configured for this workload, not left on its defaults.

Decision #8 makes SQLite the database rather than a stand-in, so the pragmas
in ``_configure_sqlite`` stop being a convenience and become part of the
design. Each test here corresponds to one of them, and to the failure it
prevents in a multi-user Streamlit app.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from core.config import Settings
from core.db.engine import (
    SQLITE_BUSY_TIMEOUT_SECONDS,
    build_engine,
    build_session_factory,
    session_scope,
)


@pytest.fixture
def file_engine(tmp_path: Path):
    """A file-backed engine — WAL is meaningless for in-memory databases."""
    engine = build_engine(Settings(database_url=f"sqlite:///{tmp_path / 'x.db'}"))
    yield engine
    engine.dispose()


def test_foreign_keys_are_enforced(file_engine) -> None:
    """SQLite ignores foreign keys unless told otherwise, per connection.

    With them off, a dev database is more permissive than the schema claims,
    and an insert ordering bug passes every test — which is exactly what
    happened once already in the enrollment import.
    """
    with file_engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_write_ahead_logging_is_on(file_engine) -> None:
    """Readers must not block the writer.

    On the default rollback journal, one faculty member saving a score sheet
    stalls every student page load in the same process.
    """
    with file_engine.connect() as connection:
        mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()

    assert str(mode).lower() == "wal"


def test_a_busy_timeout_is_set(file_engine) -> None:
    """A blocked writer waits instead of raising "database is locked"."""
    with file_engine.connect() as connection:
        timeout_ms = connection.execute(text("PRAGMA busy_timeout")).scalar_one()

    assert timeout_ms == int(SQLITE_BUSY_TIMEOUT_SECONDS * 1000)


def test_synchronous_is_normal_not_off(file_engine) -> None:
    """NORMAL is safe under WAL; OFF would risk corruption on power loss."""
    with file_engine.connect() as connection:
        # 0 = OFF, 1 = NORMAL, 2 = FULL
        assert connection.execute(text("PRAGMA synchronous")).scalar_one() == 1


def test_the_pragmas_apply_to_every_pooled_connection(file_engine) -> None:
    """They are set on connect, so a recycled connection must still have them."""
    for _ in range(3):
        with file_engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
            assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() > 0


def test_concurrent_readers_are_not_blocked_by_an_open_write(tmp_path: Path) -> None:
    """The point of WAL, demonstrated rather than asserted from a pragma."""
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'y.db'}")
    engine = build_engine(settings)
    factory = build_session_factory(engine)

    with session_scope(factory) as session:
        session.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY)"))
        session.execute(text("INSERT INTO t (id) VALUES (1)"))

    writer = factory()
    try:
        writer.execute(text("INSERT INTO t (id) VALUES (2)"))  # open, uncommitted

        # A separate connection can still read the committed state.
        with session_scope(factory) as reader:
            assert reader.execute(text("SELECT COUNT(*) FROM t")).scalar_one() == 1
    finally:
        writer.rollback()
        writer.close()
        engine.dispose()

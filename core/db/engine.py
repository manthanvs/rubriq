"""Engine, session factory, and the transaction helper.

This is the only module that constructs a SQLAlchemy engine. Services take a
``Session``; they never reach for a global connection.

**SQLite is the database** (decision #8), not a stand-in for one. That changes
what this module owes it: a default SQLite connection is tuned for a
single-process script, and RubriQ is a multi-user Streamlit app that reruns
its script on every widget interaction. The pragmas in
:func:`_configure_sqlite` are what make that safe, and each is there for a
reason stated inline.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from core.config import Settings

#: How long a blocked writer waits for the lock before raising
#: "database is locked". Streamlit reruns can overlap, and a demo that throws
#: because two clicks landed together is worse than one that waits 5 seconds.
SQLITE_BUSY_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class DbHealth:
    """Result of a connection check.

    Deliberately does not raise: the caller is usually a page that wants to
    render a readable message rather than a traceback (fix item 13).
    """

    ok: bool
    dialect: str
    detail: str


def build_engine(settings: Settings) -> Engine:
    """Create the engine for ``settings.database_url``."""
    kwargs: dict[str, Any] = {"echo": settings.echo_sql, "future": True}

    if settings.is_sqlite:
        kwargs["connect_args"] = {
            # Streamlit runs script reruns on worker threads, and a connection
            # from the pool may be handed to a different one than opened it.
            "check_same_thread": False,
            # Applies the busy timeout to the very first statement, before the
            # PRAGMA below could have run.
            "timeout": SQLITE_BUSY_TIMEOUT_SECONDS,
        }

    engine = create_engine(settings.database_url, **kwargs)

    if settings.is_sqlite:
        _configure_sqlite(engine)

    return engine


def _configure_sqlite(engine: Engine) -> None:
    """Apply the pragmas that make SQLite behave for this workload.

    These run per connection, on connect, because SQLite scopes most pragmas
    to the connection rather than the database file.
    """

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _record):  # pragma: no cover - driver hook
        cursor = dbapi_connection.cursor()
        try:
            # SQLite ignores foreign keys unless asked not to — per connection.
            # Without this an insert referencing a missing parent succeeds, so
            # the database used to write tests is more permissive than the one
            # running the demo. This already caught one real ordering bug.
            cursor.execute("PRAGMA foreign_keys=ON")

            # Write-ahead logging: readers no longer block the writer and the
            # writer no longer blocks readers. With the default rollback
            # journal, one faculty member saving a score sheet would stall
            # every student's page load.
            cursor.execute("PRAGMA journal_mode=WAL")

            # Safe specifically *because* of WAL: a crash can lose the last
            # transaction but cannot corrupt the file. The alternative, FULL,
            # fsyncs on every commit and is needlessly slow here.
            cursor.execute("PRAGMA synchronous=NORMAL")

            # Belt and braces with connect_args["timeout"], and it also covers
            # connections handed out by the pool.
            timeout_ms = int(SQLITE_BUSY_TIMEOUT_SECONDS * 1000)
            cursor.execute(f"PRAGMA busy_timeout={timeout_ms}")
        finally:
            cursor.close()


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Session factory bound to ``engine``.

    ``expire_on_commit=False`` so a committed object can still be read after
    the transaction closes — Streamlit hands these to the view layer.
    """
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """One transaction, committed on success and rolled back on any error.

    Every mutation in ``core/`` goes through this — see §12. Nothing partially
    written, ever.
    """
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_connection(engine: Engine) -> DbHealth:
    """Round-trip a trivial query. Never raises."""
    dialect = engine.dialect.name
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # surfaced to the user as text, not a traceback
        return DbHealth(ok=False, dialect=dialect, detail=f"{type(exc).__name__}: {exc}")
    return DbHealth(ok=True, dialect=dialect, detail="Connected.")

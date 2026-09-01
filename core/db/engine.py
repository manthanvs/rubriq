"""Engine, session factory, and the transaction helper.

This is the only module that constructs a SQLAlchemy engine. Services take a
``Session``; they never reach for a global connection.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from core.config import Settings


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
    """Create the engine for ``settings.database_url``.

    Postgres gets ``pool_pre_ping`` because a Streamlit session can sit idle
    long enough for the server to drop the connection underneath it. SQLite
    gets ``check_same_thread=False`` because Streamlit runs script reruns on
    worker threads.
    """
    kwargs: dict[str, Any] = {"echo": settings.echo_sql, "future": True}

    if settings.dialect == "sqlite":
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_pre_ping"] = True

    return create_engine(settings.database_url, **kwargs)


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

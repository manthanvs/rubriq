"""Shared fixtures.

The suite has no external dependency: everything runs against SQLite. Postgres
behaviour is proved by running the migrations against a real database, not by
the unit tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import Settings
from core.db.engine import build_engine, build_session_factory
from core.db.models import Base


@pytest.fixture
def sqlite_settings() -> Settings:
    """Settings pointing at a private in-memory database."""
    return Settings(database_url="sqlite://")


@pytest.fixture
def db_factory(tmp_path: Path):
    """A session factory over a fresh, empty schema.

    A temp *file* rather than ``sqlite://`` on purpose: in-memory SQLite gives
    each new connection its own empty database, which makes a test that opens
    two sessions silently pass for the wrong reason.
    """
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}")
    engine = build_engine(settings)
    Base.metadata.create_all(engine)

    yield build_session_factory(engine)

    engine.dispose()

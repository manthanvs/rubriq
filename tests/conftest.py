"""Shared fixtures.

The suite has no external dependency: everything runs against in-memory
SQLite. Postgres-specific behaviour is proved by running the migrations
against a real database, not by the unit tests.
"""

from __future__ import annotations

import pytest

from core.config import Settings


@pytest.fixture
def sqlite_settings() -> Settings:
    """Settings pointing at a private in-memory database."""
    return Settings(database_url="sqlite://")

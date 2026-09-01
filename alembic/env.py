"""Alembic environment.

Runs outside Streamlit, so it reads the database URL from the environment
through the same ``Settings`` object the app uses. No Streamlit import here
either — this module lives beside ``core/`` in spirit.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import create_engine, pool

from alembic import context

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

try:  # optional convenience; the environment may be set some other way
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

from core.config import Settings  # noqa: E402  (path must be set up first)
from core.db.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

#: Empty until Phase 1 adds the first entity — an autogenerate run before then
#: correctly produces a no-op migration.
target_metadata = Base.metadata


def _database_url() -> str:
    return Settings.from_env().database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and run migrations against the live database."""
    engine = create_engine(_database_url(), poolclass=pool.NullPool, future=True)

    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # SQLite cannot ALTER most things in place; batch mode rewrites the
            # table instead. Harmless on Postgres, essential for local dev.
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

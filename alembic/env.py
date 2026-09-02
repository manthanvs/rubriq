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
from core.db.types import UtcDateTime  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

#: Empty until Phase 1 adds the first entity — an autogenerate run before then
#: correctly produces a no-op migration.
target_metadata = Base.metadata


def _database_url() -> str:
    return Settings.from_env().database_url


def render_item(type_, obj, autogen_context) -> str | bool:
    """Keep dialect-specific SQL out of generated migrations.

    Autogenerate serialises a ``server_default`` as whatever the connected
    dialect compiles it to, so ``func.now()`` is written into the migration as
    the literal ``sa.text('(CURRENT_TIMESTAMP)')``. Returning the symbolic form
    keeps migrations readable and keeps them portable, which matters for the
    report: a migration file is an SDLC artifact people read, not just run.

    The same hook keeps *application types* out of migrations. Autogenerate
    renders a custom ``TypeDecorator`` by its import path — here that produced
    ``core.db.types.UtcDateTime(...)`` in a file that never imports ``core``,
    which is a ``NameError`` the moment it runs on a fresh database. Worse, even
    with the import it would tie frozen migration history to code that is still
    moving: renaming the class later would break every past migration.

    ``UtcDateTime`` is a Python-side conversion wrapped around
    ``DateTime(timezone=True)``. The conversion is runtime behaviour and means
    nothing to DDL, so the migration gets the plain type it actually creates.

    Returning ``False`` falls back to alembic's default rendering.
    """
    if type_ == "type" and isinstance(obj, UtcDateTime):
        return "sa.DateTime(timezone=True)"

    if type_ == "server_default" and obj is not None:
        text = str(getattr(obj, "arg", obj)).strip().strip("()").upper()
        if text in {"CURRENT_TIMESTAMP", "NOW", "LOCALTIMESTAMP"}:
            return "sa.func.now()"

    return False


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_item=render_item,
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
            # SQLite cannot ALTER most columns in place — it has no
            # DROP COLUMN worth the name and no ALTER COLUMN at all. Batch mode
            # makes alembic rebuild the table and copy the rows instead, which
            # is the only way later phases will be able to change a column.
            render_as_batch=True,
            render_item=render_item,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

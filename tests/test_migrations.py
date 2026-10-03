"""The migrations build the schema the models describe.

No test had ever run a migration. The suite builds its schema with
``Base.metadata.create_all``, which is fast and right for unit tests but means
``alembic/versions/`` was exercised by nothing — and the development database
grew alongside the code, so ``alembic upgrade head`` had nothing left to do
there either.

Phase 8 shipped a migration that added ``submission.group_id`` and a foreign
key pointing at ``project_group``, and never created ``project_group``,
``group_member`` or ``submission_link``. Autogenerate emitted the ALTERs and
missed the tables. Everything passed. It surfaced only when a host built the
database from nothing and seeding died on ``no such table: project_group``.

So this builds from nothing, every time, and compares the result against the
models rather than against a hand-written list — a list would have to be
remembered, which is the failure mode all over again.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from core.db.models import Base

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Alembic's own bookkeeping, which is not part of the model metadata.
ALEMBIC_TABLE = "alembic_version"


@pytest.fixture(scope="module")
def migrated_schema(tmp_path_factory) -> dict[str, set[str]]:
    """``alembic upgrade head`` against an empty file; returns table -> columns."""
    database = tmp_path_factory.mktemp("migrations") / "fresh.db"
    url = f"sqlite:///{database.as_posix()}"

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env={**os.environ, "RUBRIQ_DATABASE_URL": url},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, f"alembic failed:\n{result.stderr}"
    assert database.exists(), "alembic reported success but created no database"

    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        return {
            table: {column["name"] for column in inspector.get_columns(table)}
            for table in inspector.get_table_names()
            if table != ALEMBIC_TABLE
        }
    finally:
        engine.dispose()


def test_every_model_table_is_created(migrated_schema) -> None:
    """The one that was missing. Three tables, silently."""
    missing = set(Base.metadata.tables) - set(migrated_schema)
    assert not missing, f"migrations never create: {sorted(missing)}"


def test_no_table_exists_that_no_model_describes(migrated_schema) -> None:
    """The other direction: a table left behind by a model that moved on."""
    extra = set(migrated_schema) - set(Base.metadata.tables)
    assert not extra, f"migrations create tables no model describes: {sorted(extra)}"


def test_every_model_column_is_created(migrated_schema) -> None:
    """Catches a missed ALTER, which is the same defect one column down."""
    wrong = []
    for name, table in Base.metadata.tables.items():
        if name not in migrated_schema:
            continue  # already reported by the table test
        missing = {c.name for c in table.columns} - migrated_schema[name]
        if missing:
            wrong.append(f"{name}: {sorted(missing)}")

    assert not wrong, "migrations never create these columns: " + "; ".join(wrong)


def test_the_migration_chain_has_a_single_head() -> None:
    """Two heads means `upgrade head` is ambiguous and silently partial."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=REPO_ROOT,
        env={**os.environ, "RUBRIQ_DATABASE_URL": "sqlite:///:memory:"},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    heads = [line for line in result.stdout.splitlines() if "(head)" in line]
    assert len(heads) == 1, f"expected one head, found {len(heads)}:\n{result.stdout}"

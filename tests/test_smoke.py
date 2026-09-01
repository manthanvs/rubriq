"""Phase 0 smoke tests: settings parse, engine connects, transactions roll back.

These run against in-memory SQLite so the suite has no external dependency.
The Postgres path is exercised by ``make migrate`` against a real database.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from core.config import ConfigError, Settings
from core.db.engine import (
    build_engine,
    build_session_factory,
    check_connection,
    session_scope,
)


def test_settings_from_env_reads_the_database_url() -> None:
    settings = Settings.from_env({"RUBRIQ_DATABASE_URL": "sqlite://"})

    assert settings.database_url == "sqlite://"
    assert settings.dialect == "sqlite"
    assert settings.is_postgres is False


def test_settings_falls_back_to_plain_database_url() -> None:
    settings = Settings.from_env({"DATABASE_URL": "postgresql+psycopg://u:p@h/db"})

    assert settings.is_postgres is True


def test_settings_without_a_url_fails_with_an_actionable_message() -> None:
    with pytest.raises(ConfigError) as excinfo:
        Settings.from_env({})

    assert "RUBRIQ_DATABASE_URL" in str(excinfo.value)


def test_settings_from_mapping_reads_secrets_sections() -> None:
    settings = Settings.from_mapping(
        {
            "database": {"url": "sqlite://"},
            "rubriq": {"faculty_allowlist": ["A@pccoepune.org", "a@pccoepune.org"]},
        }
    )

    # Lower-cased and de-duplicated, because it is compared against an OIDC claim.
    assert settings.faculty_allowlist == ("a@pccoepune.org",)
    assert settings.allowed_email_domain == "pccoepune.org"


def test_settings_tolerates_missing_optional_sections() -> None:
    settings = Settings.from_mapping({"database": {"url": "sqlite://"}})

    assert settings.faculty_allowlist == ()
    assert settings.has_llm is False


def test_redacted_never_leaks_the_password_or_the_api_key() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://rubriq:hunter2@localhost:5432/rubriq",
        llm_api_key="sk-secret",
    )

    facts = settings.redacted()

    assert "hunter2" not in facts["database_url"]
    assert "sk-secret" not in str(facts)
    assert facts["llm_api_key_present"] is True


def test_engine_connects(sqlite_settings: Settings) -> None:
    health = check_connection(build_engine(sqlite_settings))

    assert health.ok is True
    assert health.dialect == "sqlite"


def test_check_connection_reports_failure_instead_of_raising() -> None:
    engine = build_engine(Settings(database_url="sqlite:///Z:/nowhere/missing.db"))

    health = check_connection(engine)

    assert health.ok is False
    assert health.detail  # a message a page can render


def test_session_scope_rolls_back_on_error(sqlite_settings: Settings) -> None:
    engine = build_engine(sqlite_settings)
    factory = build_session_factory(engine)

    with session_scope(factory) as session:
        session.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY)"))

    with pytest.raises(RuntimeError):
        with session_scope(factory) as session:
            session.execute(text("INSERT INTO t (id) VALUES (1)"))
            raise RuntimeError("boom")

    with session_scope(factory) as session:
        rows = session.execute(text("SELECT COUNT(*) FROM t")).scalar_one()

    assert rows == 0, "session_scope must roll back a failed transaction"

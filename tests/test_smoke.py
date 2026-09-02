"""Phase 0 smoke tests: settings parse, engine connects, transactions roll back."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from core.config import DEFAULT_DATABASE_URL, ConfigError, Settings
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
    assert settings.is_sqlite is True


def test_settings_falls_back_to_plain_database_url() -> None:
    settings = Settings.from_env({"DATABASE_URL": "sqlite:///elsewhere.db"})

    assert settings.database_url == "sqlite:///elsewhere.db"


def test_no_configuration_at_all_still_produces_a_working_database() -> None:
    """Decision #8: SQLite means there is nothing to install or configure."""
    assert Settings.from_env({}).database_url == DEFAULT_DATABASE_URL
    assert Settings.from_mapping({}).database_url == DEFAULT_DATABASE_URL


def test_the_default_database_url_is_absolute() -> None:
    """A relative URL resolves against the working directory.

    Streamlit launched from the repo root and Alembic launched from elsewhere
    would then use two different files, and the migration would look like it
    never applied.
    """
    assert DEFAULT_DATABASE_URL.startswith("sqlite:///")
    tail = DEFAULT_DATABASE_URL.removeprefix("sqlite:///")

    assert tail.endswith("rubriq.db")
    assert ":" in tail or tail.startswith("/"), f"not an absolute path: {tail}"


def test_a_blank_url_is_still_rejected() -> None:
    """The constructors default it, so a blank means someone passed one."""
    with pytest.raises(ConfigError):
        Settings(database_url="   ")


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


def test_redacted_never_leaks_the_api_key() -> None:
    settings = Settings(database_url="sqlite://", llm_api_key="sk-secret")

    facts = settings.redacted()

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

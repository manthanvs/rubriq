"""The deployment bootstrap, and the two things that must stop it.

It exists so a host with no shell can create its own schema. That makes it the
only code in the project that writes demo rows without somebody typing a
command, so what it *refuses* to do matters more than what it does.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.bootstrap import ensure_database
from core.auth.roles import Role
from core.db.models import Base, User


@pytest.fixture(autouse=True)
def _clear_cache():
    """``ensure_database`` is cached per process; each test needs a clean one."""
    ensure_database.clear()
    yield
    ensure_database.clear()


def _url(tmp_path) -> str:
    return f"sqlite:///{(tmp_path / 'rubriq.db').as_posix()}"


def test_disabled_is_a_no_op(tmp_path):
    """Off by default: no migration, no seed, no file."""
    assert ensure_database(_url(tmp_path), "guide@pccoepune.org", enabled=False) is None
    assert not (tmp_path / "rubriq.db").exists()


def test_populated_database_is_never_seeded(tmp_path, monkeypatch):
    """The guard that matters: a database with a user in it is left alone.

    If this ever regresses, a redeploy drops demo rows on top of real marks.
    """
    url = _url(tmp_path)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as session:
        session.add(
            User(email="real@pccoepune.org", role=Role.FACULTY, name="Real Person")
        )
        session.commit()
    engine.dispose()

    # The schema is already there, so skip the real migration; and make any
    # attempt to seed a loud failure rather than a silent write.
    monkeypatch.setattr("app.bootstrap._migrate", lambda _url: None)
    import scripts.seed_demo as seed_demo

    def _refuse(*args, **kwargs):
        raise AssertionError("seeded a database that already had a user in it")

    monkeypatch.setattr(seed_demo, "build", _refuse)

    assert ensure_database(url, "guide@pccoepune.org", enabled=True) is None


def test_empty_database_is_seeded_under_the_configured_owner(tmp_path, monkeypatch):
    """Enabled and empty is the one case that writes, and it uses the allow-list."""
    url = _url(tmp_path)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()

    monkeypatch.setattr("app.bootstrap._migrate", lambda _url: None)
    import scripts.seed_demo as seed_demo

    seen: dict[str, object] = {}

    def _record(settings, *, faculty_email=None, faculty_name=None):
        seen["owner"] = faculty_email
        return {"students": 8, "submissions": 7, "approved": 5}

    monkeypatch.setattr(seed_demo, "build", _record)

    note = ensure_database(url, "owner@pccoepune.org", enabled=True)
    assert seen["owner"] == "owner@pccoepune.org"
    assert note is not None and "8 students" in note

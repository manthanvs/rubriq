"""Create the schema, and the demo data, on a host that has no shell.

``make seed`` is the local path: ``alembic upgrade head`` followed by the demo
dataset. A Streamlit Community Cloud deployment runs ``streamlit run
app/main.py`` and nothing else, so a fresh deploy would otherwise come up
against a database that does not exist and fail on the first query.

**This is off unless ``[deploy] bootstrap`` is true.** A bootstrap that ran by
default would be one misread setting away from seeding demo rows into a
database holding real marks, which is the kind of mistake that is discovered
afterwards. Off is the safe default and the deployer opts in.

It is also refused outright when the database already holds a user, so even
with the flag on it cannot overwrite a populated instance. The flag controls
whether it *may* run; the emptiness check decides whether it *does*.
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from alembic.config import Config
from sqlalchemy import func, select

from alembic import command
from core.config import DATABASE_URL_ENV_KEYS, Settings
from core.db.engine import build_engine, build_session_factory, session_scope
from core.db.models import User

REPO_ROOT = Path(__file__).resolve().parents[1]


def _migrate(database_url: str) -> None:
    """Bring the schema to head.

    Alembic's ``env.py`` resolves its URL through ``Settings.from_env()``, not
    from ``alembic.ini`` and not from ``st.secrets`` — so the URL has to reach
    it through the environment. Setting it here rather than relying on a
    ``.env`` file is what makes this work on a host that has no ``.env``.
    """
    os.environ[DATABASE_URL_ENV_KEYS[0]] = database_url
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    command.upgrade(config, "head")


def _is_empty(settings: Settings) -> bool:
    factory = build_session_factory(build_engine(settings))
    with session_scope(factory) as session:
        return not session.scalar(select(func.count()).select_from(User))


@st.cache_resource(show_spinner="Preparing the database…")
def ensure_database(
    database_url: str, faculty_email: str, *, enabled: bool
) -> str | None:
    """Migrate, and seed once if nobody exists yet.

    Returns a line to show the deployer, or ``None`` when it did nothing.

    ``cache_resource`` rather than ``cache_data``: this is an effect on the
    world, performed once per process, not a value recomputed per rerun.
    """
    if not enabled:
        return None

    settings = Settings(database_url=database_url)
    _migrate(database_url)

    if not _is_empty(settings):
        return None

    # Imported here, not at module scope: seeding is a deployment concern and
    # nothing in a normal run should pay for importing the seed script.
    from scripts.seed_demo import build as seed_demo

    counts = seed_demo(settings, faculty_email=faculty_email)
    return (
        f"Seeded a demo cohort — {counts['students']} students, "
        f"{counts['submissions']} submissions, {counts['approved']} approved."
    )

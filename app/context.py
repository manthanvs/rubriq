"""Per-page access to settings, the database, and the acting user.

Pages call these rather than building their own engine or reaching into
``st.secrets``. One path in, so a page cannot accidentally talk to a different
database or skip the domain assertion.

``current_actor()`` re-derives the role from settings on every call rather
than caching it in ``session_state``. That is deliberate and it is fix item 3:
*"A role cached in session_state at login and never re-derived."*
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

import streamlit as st
from sqlalchemy.orm import Session

from core.auth.actor import Actor
from core.auth.service import authenticate
from core.config import Settings
from core.db.engine import build_engine, build_session_factory, session_scope


@st.cache_resource(show_spinner=False)
def _resources(database_url: str, echo_sql: bool):
    """Engine and session factory, one per configuration."""
    engine = build_engine(Settings(database_url=database_url, echo_sql=echo_sql))
    return engine, build_session_factory(engine)


def get_settings() -> Settings:
    return Settings.from_mapping(st.secrets)


def claims() -> Mapping[str, Any] | None:
    """The OIDC claim set, or the local dev stand-in. See app/main.py."""
    try:
        if st.user.is_logged_in:
            return {"email": st.user.get("email"), "name": st.user.get("name")}
    except Exception:
        pass

    try:
        dev = st.secrets.get("dev")
    except Exception:
        return None

    if not isinstance(dev, Mapping):
        return None

    email = str(dev.get("impersonate") or "").strip()
    if not email:
        return None

    return {"email": email, "name": str(dev.get("name") or email.split("@")[0])}


def current_actor() -> Actor:
    """The signed-in user, re-authenticated from settings.

    Pages run behind ``main.py``'s gate, so this should never fail — but it
    asserts rather than assumes, because "should never" is how a page ends up
    rendering someone else's data.
    """
    payload = claims()
    if payload is None:
        st.error("Your session has ended. Reload the page to sign in again.")
        st.stop()

    return authenticate(payload, get_settings())


@contextmanager
def db() -> Iterator[Session]:
    """A transaction. Commits on success, rolls back on any error."""
    settings = get_settings()
    _engine, factory = _resources(settings.database_url, settings.echo_sql)

    with session_scope(factory) as session:
        yield session

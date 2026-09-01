"""RubriQ entry point — auth gate and navigation.

The order here is the security model:

1. Load settings.
2. Get the claim set (Google OIDC).
3. ``authenticate()`` — assert the institute domain and resolve the role from
   the allow-list. This runs on **every rerun**, from settings, never from
   ``session_state``. A role is not something the client gets to remember.
4. Only then build the navigation, and only for that role.

Step 3 before step 4 is why a student's faculty pages are never constructed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import streamlit as st

from app.navigation import build_navigation
from app.state import SIGNED_IN_EMAIL_KEY
from core.auth.actor import Actor
from core.auth.service import authenticate, sign_in
from core.config import ConfigError, Settings
from core.db.engine import (
    build_engine,
    build_session_factory,
    check_connection,
    session_scope,
)
from core.errors import AuthError

st.set_page_config(page_title="RubriQ", page_icon="📋", layout="wide")


# -- resources -----------------------------------------------------------


@st.cache_resource(show_spinner=False)
def _session_factory(database_url: str, echo_sql: bool):
    """One engine and session factory per configuration.

    ``cache_resource``, not ``cache_data``: a connection pool is not a value.
    The URL is in the key so repointing the database rebuilds the pool.
    """
    engine = build_engine(Settings(database_url=database_url, echo_sql=echo_sql))
    return engine, build_session_factory(engine)


def _load_settings() -> tuple[Settings | None, str | None]:
    """Read settings, returning a message rather than raising (fix item 13)."""
    try:
        return Settings.from_mapping(st.secrets), None
    except ConfigError as exc:
        return None, str(exc)
    except Exception:
        return None, (
            "No secrets file found. Copy `.streamlit/secrets.toml.example` to "
            "`.streamlit/secrets.toml` and set `[database] url`."
        )


# -- claims --------------------------------------------------------------


def _oidc_configured() -> bool:
    try:
        return "auth" in st.secrets
    except Exception:
        return False


def _dev_claims() -> Mapping[str, Any] | None:
    """Local-only sign-in, for working on pages before OIDC is set up.

    Enabled only by an explicit ``[dev] impersonate`` entry in a secrets file
    that is gitignored and absent from the committed example. It supplies
    *claims* and nothing else: the result still goes through
    ``authenticate()``, so the domain assertion and the allow-list apply
    exactly as they would to a real Google response. A ``@gmail.com`` address
    put here is still refused.

    Delete the ``[dev]`` section to turn it off.
    """
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


def _oidc_claims() -> Mapping[str, Any] | None:
    try:
        if not st.user.is_logged_in:
            return None
    except Exception:
        return None

    return {"email": st.user.get("email"), "name": st.user.get("name")}


# -- render --------------------------------------------------------------


def _render_sign_in() -> None:
    st.title("RubriQ")
    st.caption("Rubric-driven, AI-assisted project review — PCCOE")
    st.divider()

    if _oidc_configured():
        st.write("Sign in with your PCCOE Google account.")
        st.button(
            "Sign in with Google",
            icon=":material/login:",
            type="primary",
            on_click=st.login,
        )
    else:
        st.warning(
            "Google sign-in is not configured yet. Add an `[auth]` section to "
            "`.streamlit/secrets.toml` — see `secrets.toml.example` for the keys.",
            icon=":material/key_off:",
        )

    st.caption("Access is restricted to @pccoepune.org accounts.")


def _render_rejected(message: str) -> None:
    st.title("RubriQ")
    st.error(message, icon=":material/block:")
    st.button("Sign out", icon=":material/logout:", on_click=st.logout)


def _render_identity(actor: Actor, db_ok: bool) -> None:
    with st.sidebar:
        st.markdown(f"**{actor.name or actor.email}**")
        st.caption(actor.email)
        st.caption(f"Role — {actor.role}")

        if not db_ok:
            st.error("Database unreachable.", icon=":material/database:")

        if _oidc_configured():
            st.button("Sign out", icon=":material/logout:", on_click=st.logout)


# -- gate ----------------------------------------------------------------


def _ensure_user_row(factory, claims: Mapping[str, Any], settings: Settings) -> None:
    """Upsert the ``users`` row once per session.

    The *authorisation* decision is re-made every rerun in ``authenticate()``;
    this only records that the person exists. Doing it once per session keeps a
    button click from writing a row.
    """
    if st.session_state.get(SIGNED_IN_EMAIL_KEY) == claims.get("email"):
        return

    with session_scope(factory) as session:
        sign_in(session, claims=claims, settings=settings)

    st.session_state[SIGNED_IN_EMAIL_KEY] = claims.get("email")


def main() -> None:
    settings, error = _load_settings()
    if settings is None:
        st.title("RubriQ")
        st.error(error, icon=":material/settings:")
        st.stop()

    claims = _oidc_claims() or _dev_claims()
    if claims is None:
        _render_sign_in()
        st.stop()

    engine, factory = _session_factory(settings.database_url, settings.echo_sql)
    health = check_connection(engine)

    try:
        # Invariants #4 and #5, re-asserted on every rerun.
        actor = authenticate(claims, settings)
    except AuthError as exc:
        _render_rejected(str(exc))
        st.stop()

    if health.ok:
        _ensure_user_row(factory, claims, settings)

    if _dev_claims() is not None and _oidc_claims() is None:
        st.warning(
            f"Development sign-in is active as **{actor.email}**. "
            "Remove the `[dev]` section from `.streamlit/secrets.toml` before any demo.",
            icon=":material/warning:",
        )

    _render_identity(actor, health.ok)
    build_navigation(actor).run()


main()

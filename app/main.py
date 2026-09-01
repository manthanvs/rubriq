"""RubriQ entry point.

Phase 0: prove the wiring. Settings are read here, from ``st.secrets``, and
handed down into ``core/`` as an argument — that direction of travel is the
whole point of invariant #9 and it is worth getting right on day one.

``st.navigation`` and the role-filtered page list arrive in Phase 1.
"""

from __future__ import annotations

import streamlit as st

from core.config import ConfigError, Settings
from core.db.engine import build_engine, check_connection

st.set_page_config(page_title="RubriQ", page_icon="📋", layout="wide")


@st.cache_resource(show_spinner=False)
def _engine(database_url: str, echo_sql: bool):
    """One engine per configuration, reused across reruns.

    ``cache_resource``, not ``cache_data``: an engine is a connection pool, not
    a value to be copied. The URL is part of the cache key so pointing at a
    different database rebuilds the pool instead of silently reusing the old one.
    """
    return build_engine(Settings(database_url=database_url, echo_sql=echo_sql))


def _load_settings() -> tuple[Settings | None, str | None]:
    """Read settings, returning an error message rather than raising.

    ``st.secrets`` raises when no secrets file exists at all, which is the
    normal state of a fresh clone — that deserves an instruction, not a
    traceback.
    """
    try:
        return Settings.from_mapping(st.secrets), None
    except ConfigError as exc:
        return None, str(exc)
    except Exception:
        return None, (
            "No secrets file found. Copy `.streamlit/secrets.toml.example` to "
            "`.streamlit/secrets.toml` and set `[database] url`."
        )


def main() -> None:
    st.title("RubriQ")
    st.caption("Rubric-driven, AI-assisted project review — PCCOE")

    settings, error = _load_settings()

    if settings is None:
        st.error(error)
        st.stop()

    health = check_connection(_engine(settings.database_url, settings.echo_sql))
    facts = settings.redacted()

    left, right = st.columns(2)

    with left:
        st.subheader("Database")
        if health.ok:
            st.success(f"Connected — {health.dialect}")
        else:
            st.error(f"Not connected — {health.dialect}")
            st.caption(health.detail)
        st.caption(f"`{facts['database_url']}`")

    with right:
        st.subheader("Configuration")
        st.write(f"Allowed domain — `{facts['allowed_email_domain']}`")
        st.write(f"Faculty allow-list — {facts['faculty_allowlist_size']} entry(s)")
        st.write(f"LLM provider — {facts['llm_provider']}")
        st.caption(
            "API key loaded"
            if facts["llm_api_key_present"]
            else "No API key set — AI evaluation arrives in Phase 5."
        )

    st.divider()
    st.subheader("Phase 0 — foundation")
    st.markdown(
        """
        - Streamlit app boots and reads `st.secrets`
        - `core/` package with settings and database wiring
        - Alembic initialised, `Base.metadata` empty until Phase 1
        - `pytest` wired, including the no-Streamlit-in-`core` gate

        Next: **Phase 1 — auth & roles.** Google OIDC, server-side domain
        assertion, and a role-filtered `st.navigation`.
        """
    )


main()

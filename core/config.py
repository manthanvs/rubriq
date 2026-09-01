"""Application settings.

Plain Python — no Streamlit import anywhere in this module (invariant #9).

There are two ways in, because there are two kinds of caller:

* ``Settings.from_mapping(st.secrets)`` — the view layer reads the secrets and
  hands the mapping down. ``core/`` never reaches up for it.
* ``Settings.from_env()`` — Alembic and pytest run outside Streamlit entirely
  and have no ``st.secrets`` to read.

Both funnel into the same constructor, so the two paths cannot drift.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from core.errors import RubriQError

DEFAULT_EMAIL_DOMAIN = "pccoepune.org"

#: Checked in order, first non-empty wins. ``DATABASE_URL`` is the fallback
#: because most hosting providers set that name for you.
DATABASE_URL_ENV_KEYS = ("RUBRIQ_DATABASE_URL", "DATABASE_URL")


class ConfigError(RubriQError, RuntimeError):
    """Raised when required settings are missing or malformed.

    Carries a message meant to be shown to a human — see fix item 13. The app
    renders this, not a traceback.
    """


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything ``core/`` needs to know about its environment.

    Frozen on purpose: settings are read once per rerun and never mutated,
    so a page cannot quietly change the database the next page talks to.
    """

    database_url: str
    allowed_email_domain: str = DEFAULT_EMAIL_DOMAIN
    faculty_allowlist: tuple[str, ...] = ()
    admin_allowlist: tuple[str, ...] = ()
    llm_provider: str | None = None
    llm_api_key: str | None = None
    echo_sql: bool = False

    def __post_init__(self) -> None:
        if not self.database_url.strip():
            raise ConfigError(
                "No database URL configured. Set [database] url in "
                ".streamlit/secrets.toml, or RUBRIQ_DATABASE_URL in the environment."
            )
        if not self.allowed_email_domain.strip():
            raise ConfigError("allowed_email_domain must not be empty (invariant #4).")

    # -- constructors ----------------------------------------------------

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> Settings:
        """Build from a secrets-shaped mapping. See secrets.toml.example."""
        database = _section(raw, "database")
        rubriq = _section(raw, "rubriq")
        llm = _section(raw, "llm")

        return cls(
            database_url=str(database.get("url") or "").strip(),
            allowed_email_domain=str(
                rubriq.get("allowed_email_domain") or DEFAULT_EMAIL_DOMAIN
            ).strip(),
            faculty_allowlist=_as_emails(rubriq.get("faculty_allowlist")),
            admin_allowlist=_as_emails(rubriq.get("admin_allowlist")),
            llm_provider=_optional_str(llm.get("provider")),
            llm_api_key=_optional_str(llm.get("api_key")),
            echo_sql=bool(database.get("echo_sql", False)),
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Build from environment variables, for Alembic and the test suite."""
        env = os.environ if env is None else env

        url = ""
        for key in DATABASE_URL_ENV_KEYS:
            url = (env.get(key) or "").strip()
            if url:
                break

        return cls(
            database_url=url,
            allowed_email_domain=(
                env.get("RUBRIQ_EMAIL_DOMAIN") or DEFAULT_EMAIL_DOMAIN
            ).strip(),
            faculty_allowlist=_as_emails(env.get("RUBRIQ_FACULTY_ALLOWLIST")),
            admin_allowlist=_as_emails(env.get("RUBRIQ_ADMIN_ALLOWLIST")),
            llm_provider=_optional_str(env.get("RUBRIQ_LLM_PROVIDER")),
            llm_api_key=_optional_str(env.get("RUBRIQ_LLM_API_KEY")),
            echo_sql=_as_bool(env.get("RUBRIQ_ECHO_SQL")),
        )

    # -- derived ---------------------------------------------------------

    @property
    def dialect(self) -> str:
        """``postgresql``, ``sqlite``, … — the scheme without the driver."""
        return self.database_url.split(":", 1)[0].split("+", 1)[0].lower()

    @property
    def is_postgres(self) -> bool:
        return self.dialect.startswith("postgres")

    @property
    def has_llm(self) -> bool:
        """Whether an AI call could even be attempted. See invariant #10."""
        return bool(self.llm_provider and self.llm_api_key)

    def redacted(self) -> dict[str, Any]:
        """A dict safe to render on a page or write to a log. Never the key."""
        return {
            "database_url": _redact_url(self.database_url),
            "allowed_email_domain": self.allowed_email_domain,
            "faculty_allowlist_size": len(self.faculty_allowlist),
            "admin_allowlist_size": len(self.admin_allowlist),
            "llm_provider": self.llm_provider or "—",
            "llm_api_key_present": bool(self.llm_api_key),
        }


# -- helpers -------------------------------------------------------------


def _section(raw: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    """Return a named section, or an empty mapping when it is absent.

    Tolerant by design: a missing ``[llm]`` section is normal before Phase 5,
    and a missing ``[database]`` section produces the clear ConfigError from
    ``__post_init__`` rather than a KeyError from here.
    """
    try:
        value = raw.get(name)
    except Exception:  # st.secrets raises rather than returning None
        return {}
    return value if isinstance(value, Mapping) else {}


def _as_emails(value: Any) -> tuple[str, ...]:
    """Normalise an allow-list from TOML list or comma-separated string.

    Lowercased and de-duplicated because it is compared against an OIDC email
    claim, and Google does not promise you a particular case.
    """
    if not value:
        return ()
    items: Iterable[Any]
    items = value.split(",") if isinstance(value, str) else value

    seen: dict[str, None] = {}
    for item in items:
        email = str(item).strip().lower()
        if email:
            seen.setdefault(email, None)
    return tuple(seen)


def _optional_str(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _redact_url(url: str) -> str:
    """Strip the password out of a SQLAlchemy URL for display."""
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    credentials, host = rest.split("@", 1)
    user = credentials.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host}" if ":" in credentials else url

"""Sign-in: turn an OIDC claim set into an :class:`Actor` and a ``User`` row.

This is the one service function in ``core/`` that does not take an ``actor``
argument, because it is what *produces* the actor. Everything downstream does
take one — ``tests/core/test_actor_contract.py`` knows about this exemption by
name, so the hole cannot silently widen.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from core.audit import record
from core.auth.actor import Actor
from core.auth.domain import assert_allowed_domain
from core.auth.roles import Role, resolve_role
from core.clock import ensure_utc, utc_now
from core.config import Settings
from core.db.models import User

#: How stale ``last_seen_at`` may get before it is rewritten. Without this, a
#: signed-in user writes a row on every button click.
LAST_SEEN_REFRESH = timedelta(minutes=15)


def authenticate(claims: Mapping[str, Any], settings: Settings) -> Actor:
    """Verify the claim set and resolve a role. No database access.

    Called on **every** rerun. The allow-list is the authority (invariant #5),
    so a role is re-derived from it each time rather than read back from the
    ``users`` row or cached in ``session_state`` — removing someone from the
    allow-list demotes them immediately, not eventually.

    The domain assertion (invariant #4) runs first, so a ``@gmail.com`` account
    never reaches the database at all.
    """
    email = assert_allowed_domain(claims.get("email"), settings.allowed_email_domain)
    role = resolve_role(email, settings.faculty_allowlist, settings.admin_allowlist)
    name = str(claims.get("name") or "").strip()

    return Actor(email=email, role=role, name=name)


def sign_in(session: Session, *, claims: Mapping[str, Any], settings: Settings) -> Actor:
    """Authenticate, then upsert the matching ``users`` row.

    The caller wraps this in ``session_scope`` — this function never commits,
    so the audit row and the change it describes land together or not at all.
    """
    actor = authenticate(claims, settings)
    now = utc_now()

    user = session.get(User, actor.email)

    if user is None:
        session.add(
            User(
                email=actor.email,
                role=actor.role,
                name=actor.name,
                created_at=now,
                last_seen_at=now,
            )
        )
        record(
            session,
            actor_email=actor.email,
            action="user.created",
            entity="User",
            entity_id=actor.email,
            payload={"role": str(actor.role)},
        )
        return actor

    if user.role != actor.role:
        record(
            session,
            actor_email=actor.email,
            action="user.role_changed",
            entity="User",
            entity_id=actor.email,
            payload={"from": str(user.role), "to": str(actor.role)},
        )
        user.role = actor.role

    if actor.name and user.name != actor.name:
        user.name = actor.name

    last_seen = ensure_utc(user.last_seen_at)
    if last_seen is None or now - last_seen > LAST_SEEN_REFRESH:
        user.last_seen_at = now

    return actor


def is_faculty(user: User) -> bool:
    """Whether this stored user may see faculty pages."""
    return user.role in {Role.FACULTY, Role.ADMIN}

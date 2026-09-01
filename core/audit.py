"""Audit trail.

One helper, called by every mutation. It adds to the session and does *not*
commit: the caller's ``session_scope`` owns the transaction, so the audit row
and the change it describes land together or not at all. An audit log that can
survive a rolled-back mutation is worse than none.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from core.db.models import AuditLog


def record(
    session: Session,
    *,
    actor_email: str,
    action: str,
    entity: str,
    entity_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> AuditLog:
    """Append one audit row inside the caller's transaction.

    ``action`` is a dotted verb (``user.created``, ``score.approved``) so the
    Phase 7 admin view can filter on a prefix.
    """
    entry = AuditLog(
        actor_email=actor_email,
        action=action,
        entity=entity,
        entity_id=None if entity_id is None else str(entity_id),
        payload=payload,
    )
    session.add(entry)
    return entry

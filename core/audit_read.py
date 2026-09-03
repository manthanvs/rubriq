"""Reading the audit trail — fix item 15.

*"AuditLog is written from Phase 1 but read by nobody until here."* This is the
reading half. It is cheap to build and it is the artifact that answers the
question a viva will actually ask: **how do you know the faculty member, not the
AI, decided this mark?**

Kept separate from ``core/audit.py`` so the write path stays a single function
with no query surface attached to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.academics.access import require_faculty
from core.auth.actor import Actor
from core.db.models import AuditLog, User

#: Grouped for the filter, so a faculty member can ask "what happened to marks"
#: without knowing the dotted action names.
ACTION_GROUPS: dict[str, tuple[str, ...]] = {
    "Marks": ("score.saved", "score.approved", "score.overridden", "score.reinstated"),
    "AI runs": (
        "evaluation.started",
        "evaluation.completed",
        "evaluation.failed",
    ),
    "Rubrics": (
        "rubric.created",
        "rubric.published",
        "rubric.cloned",
        "criterion.added",
        "criterion.removed",
    ),
    "Submissions": ("submission.created",),
    "People": (
        "user.created",
        "user.seeded",
        "user.role_changed",
        "enrollment.imported",
    ),
    "Teaching": (
        "subject.created",
        "cycle.created",
        "milestone.created",
        "milestone.visibility_changed",
    ),
    "Questions": ("query.asked", "query.replied"),
}


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One line of history, ready to render."""

    id: int
    at: datetime
    actor_email: str
    actor_name: str
    action: str
    entity: str
    entity_id: str | None
    payload: dict[str, Any]

    @property
    def group(self) -> str:
        for name, actions in ACTION_GROUPS.items():
            if self.action in actions:
                return name
        return "Other"

    @property
    def summary(self) -> str:
        """A sentence a human can read without knowing the schema."""
        payload = self.payload or {}

        if self.action == "score.approved":
            return f"approved a score sheet at {payload.get('final_total', '?')}"
        if self.action == "score.overridden":
            return (
                f"changed {payload.get('criterion', '?')} from "
                f"{payload.get('from', '?')} to {payload.get('to', '?')} — "
                f"{payload.get('reason', 'no reason recorded')}"
            )
        if self.action == "score.reinstated":
            return f"reinstated a late submission — {payload.get('reason', '')}"
        if self.action == "score.saved":
            return f"scored a submission at {payload.get('final_total', '?')}"
        if self.action == "rubric.published":
            return (
                f"published rubric v{payload.get('version', '?')} with "
                f"{payload.get('criteria', '?')} criteria"
            )
        if self.action == "evaluation.completed":
            return (
                f"AI run finished — {payload.get('rejections', 0)} quote(s) "
                f"rejected of {payload.get('criteria', '?')} criteria"
            )
        if self.action == "evaluation.failed":
            return f"AI run failed — {payload.get('reason', '')}"
        if self.action == "enrollment.imported":
            return (
                f"imported {payload.get('enrolled', 0)} student(s), "
                f"{payload.get('rejected', 0)} rejected"
            )
        if self.action == "user.role_changed":
            return f"role changed {payload.get('from', '?')} → {payload.get('to', '?')}"

        return self.action.replace(".", " ")


def list_audit(
    actor: Actor,
    session: Session,
    *,
    group: str | None = None,
    entity: str | None = None,
    entity_id: str | int | None = None,
    actor_email: str | None = None,
    limit: int = 200,
) -> tuple[AuditEntry, ...]:
    """Recent activity, newest first.

    Faculty-only. The log records *who did what*, which includes actions by
    students, so it is not something a student may browse — but it is exactly
    what a faculty member needs when a mark is questioned.
    """
    require_faculty(actor, "read the activity log")

    query = select(AuditLog, User.name).outerjoin(
        User, User.email == AuditLog.actor_email
    )

    if group and group in ACTION_GROUPS:
        query = query.where(AuditLog.action.in_(ACTION_GROUPS[group]))
    if entity:
        query = query.where(AuditLog.entity == entity)
    if entity_id is not None:
        query = query.where(AuditLog.entity_id == str(entity_id))
    if actor_email:
        query = query.where(AuditLog.actor_email == actor_email)

    rows = session.execute(
        query.order_by(AuditLog.at.desc(), AuditLog.id.desc()).limit(limit)
    ).all()

    return tuple(
        AuditEntry(
            id=entry.id,
            at=entry.at,
            actor_email=entry.actor_email,
            actor_name=name or entry.actor_email,
            action=entry.action,
            entity=entry.entity,
            entity_id=entry.entity_id,
            payload=entry.payload or {},
        )
        for entry, name in rows
    )


def history_for(
    actor: Actor, session: Session, *, entity: str, entity_id: int | str
) -> tuple[AuditEntry, ...]:
    """Everything that happened to one thing, oldest first.

    Used by the score-sheet dialog, where the order that reads naturally is
    chronological rather than newest-first.
    """
    entries = list_audit(actor, session, entity=entity, entity_id=entity_id, limit=100)
    return tuple(reversed(entries))

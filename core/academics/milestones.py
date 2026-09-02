"""Review milestone services.

The student-facing rule that matters here: an invisible milestone is absent
from the query, not hidden in the UI. A faculty member drafting Review 3 is
invisible to students in the same sense that another student's submission is.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from core.academics.access import require_faculty, visible_subject_ids
from core.academics.dto import MilestoneDTO
from core.academics.subjects import get_subject
from core.audit import record
from core.auth.actor import Actor
from core.db.models import ProjectCycle, ReviewMilestone, Subject
from core.errors import NotAuthorized, ValidationError


def _base_query(actor: Actor) -> Select:
    """Milestones joined to their subject, scoped to what ``actor`` may see."""
    query = (
        select(ReviewMilestone, Subject)
        .join(ProjectCycle, ProjectCycle.id == ReviewMilestone.cycle_id)
        .join(Subject, Subject.id == ProjectCycle.subject_id)
        .where(Subject.id.in_(visible_subject_ids(actor)))
    )

    if actor.is_student:
        query = query.where(ReviewMilestone.is_visible.is_(True))

    return query


def _to_dto(milestone: ReviewMilestone, subject: Subject) -> MilestoneDTO:
    return MilestoneDTO(
        id=milestone.id,
        cycle_id=milestone.cycle_id,
        subject_id=subject.id,
        subject_code=subject.code,
        subject_name=subject.name,
        index=milestone.index,
        title=milestone.title,
        description=milestone.description,
        due_at=milestone.due_at,
        max_marks=milestone.max_marks,
        is_visible=milestone.is_visible,
    )


def create_milestone(
    actor: Actor,
    session: Session,
    *,
    cycle_id: int,
    index: int,
    title: str,
    due_at: datetime,
    max_marks: Decimal | int | str,
    description: str | None = None,
    is_visible: bool = False,
) -> MilestoneDTO:
    """Add a milestone to a cycle belonging to a subject the actor owns."""
    require_faculty(actor, "create milestones")

    cycle = session.get(ProjectCycle, cycle_id)
    if cycle is None:
        raise NotAuthorized("That project cycle does not exist, or is not yours.")

    get_subject(actor, session, cycle.subject_id)  # authorisation, by reuse

    title = title.strip()
    if not title:
        raise ValidationError("Milestone title is required.")
    if index < 1:
        raise ValidationError("Milestone index starts at 1.")

    # Decimal(str(...)) rather than Decimal(float): Decimal(20.0) is exact but
    # Decimal(0.1) is not, and max_marks feeds §5.1's percentage penalties.
    marks = Decimal(str(max_marks))
    if marks <= 0:
        raise ValidationError("Max marks must be greater than zero.")

    if due_at.tzinfo is None:
        raise ValidationError(
            "due_at must be timezone-aware — §5.1's late boundary is unarguable "
            "only if the stored instant is."
        )

    clash = session.scalar(
        select(ReviewMilestone).where(
            ReviewMilestone.cycle_id == cycle_id,
            ReviewMilestone.index == index,
        )
    )
    if clash is not None:
        raise ValidationError(f"Review {index} already exists in this cycle.")

    milestone = ReviewMilestone(
        cycle_id=cycle_id,
        index=index,
        title=title,
        description=(description or "").strip() or None,
        due_at=due_at,
        max_marks=marks,
        is_visible=is_visible,
    )
    session.add(milestone)
    session.flush()

    record(
        session,
        actor_email=actor.email,
        action="milestone.created",
        entity="ReviewMilestone",
        entity_id=milestone.id,
        payload={
            "cycle_id": cycle_id,
            "index": index,
            "title": title,
            "due_at": due_at.isoformat(),
            "max_marks": str(marks),
            "is_visible": is_visible,
        },
    )

    subject = session.get(Subject, cycle.subject_id)
    return _to_dto(milestone, subject)


def list_milestones(
    actor: Actor,
    session: Session,
    *,
    subject_id: int | None = None,
) -> tuple[MilestoneDTO, ...]:
    """Every milestone visible to ``actor``, soonest first.

    With no ``subject_id`` this is the calendar query: everything across every
    subject they can see.
    """
    query = _base_query(actor)

    if subject_id is not None:
        get_subject(actor, session, subject_id)
        query = query.where(Subject.id == subject_id)

    rows = session.execute(query.order_by(ReviewMilestone.due_at, Subject.code)).all()

    return tuple(_to_dto(milestone, subject) for milestone, subject in rows)


def get_milestone(actor: Actor, session: Session, milestone_id: int) -> MilestoneDTO:
    """One milestone, scoped. Invisible ones are absent for students."""
    row = session.execute(
        _base_query(actor).where(ReviewMilestone.id == milestone_id)
    ).first()

    if row is None:
        raise NotAuthorized("That milestone does not exist, or is not yours.")

    return _to_dto(*row)


def set_milestone_visibility(
    actor: Actor,
    session: Session,
    *,
    milestone_id: int,
    is_visible: bool,
) -> MilestoneDTO:
    """Publish or unpublish a milestone to the enrolled students."""
    require_faculty(actor, "change milestone visibility")

    row = session.execute(
        _base_query(actor).where(ReviewMilestone.id == milestone_id)
    ).first()
    if row is None:
        raise NotAuthorized("That milestone does not exist, or is not yours.")

    milestone, subject = row

    if milestone.is_visible != is_visible:
        milestone.is_visible = is_visible
        record(
            session,
            actor_email=actor.email,
            action="milestone.visibility_changed",
            entity="ReviewMilestone",
            entity_id=milestone.id,
            payload={"is_visible": is_visible},
        )

    return _to_dto(milestone, subject)

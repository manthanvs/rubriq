"""Student questions, escalation and faculty replies — §6.7, Phase 6.

The scoping story is the same as everywhere else: ``actor`` first, filtered in
the query. What is specific to this module is that the *context handed to the
model* is also scoped, by construction — :func:`build_context` reads exactly
three things and there is no parameter that could widen it.

That matters more here than elsewhere. A service that over-selects leaks to a
page; a context that over-selects leaks to a third-party API and then to
whoever asks the assistant the right question.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.academics.access import require_faculty, visible_subject_ids
from core.academics.milestones import get_milestone
from core.audit import record
from core.auth.actor import Actor
from core.clock import utc_now
from core.db.models import (
    ProjectCycle,
    ReviewMilestone,
    StudentQuery,
    Subject,
    User,
)
from core.errors import NotAuthorized, ValidationError
from core.queries.dto import QueryAnswer, QueryContext, StudentQueryDTO
from core.rubrics.service import published_rubric_for

MAX_QUESTION_CHARS = 1000


def build_context(actor: Actor, session: Session, milestone_id: int) -> QueryContext:
    """Assemble everything the assistant is allowed to see.

    ``get_milestone`` does the authorisation, and for a student it returns only
    published milestones in subjects they are enrolled in. ``published_rubric_for``
    never returns a draft. Between them, a student cannot construct a context
    for a milestone that is not theirs or for a rubric not yet published.
    """
    milestone = get_milestone(actor, session, milestone_id)
    rubric = published_rubric_for(actor, session, milestone_id)

    row = session.get(ReviewMilestone, milestone_id)
    subject_id = session.execute(
        select(ProjectCycle.subject_id).where(ProjectCycle.id == row.cycle_id)
    ).scalar_one()
    subject = session.get(Subject, subject_id)

    return QueryContext(
        milestone_id=milestone_id,
        subject_code=subject.code,
        milestone_index=milestone.index,
        milestone_title=milestone.title,
        milestone_description=milestone.description,
        public_notes=row.public_notes,
        due_at=milestone.due_at,
        max_marks=milestone.max_marks,
        rubric_version=rubric.version if rubric else None,
        criteria=rubric.criteria if rubric else (),
    )


def _dto(session: Session, row: StudentQuery) -> StudentQueryDTO:
    student = session.get(User, row.student_email)
    milestone = (
        session.get(ReviewMilestone, row.milestone_id) if row.milestone_id else None
    )

    return StudentQueryDTO(
        id=row.id,
        student_email=row.student_email,
        student_name=(student.name if student else "") or row.student_email,
        milestone_id=row.milestone_id,
        milestone_label=(
            f"Review {milestone.index} — {milestone.title}" if milestone else "—"
        ),
        question=row.question,
        ai_answer=row.ai_answer,
        sources=tuple(row.sources or ()),
        confidence=float(row.confidence) if row.confidence is not None else None,
        escalated=row.escalated,
        escalation_reason=row.escalation_reason,
        faculty_reply=row.faculty_reply,
        replied_by=row.replied_by,
        replied_at=row.replied_at,
        created_at=row.created_at,
    )


def ask(
    actor: Actor,
    session: Session,
    *,
    milestone_id: int,
    question: str,
    answer: QueryAnswer,
) -> StudentQueryDTO:
    """Record a question and whatever the assistant made of it.

    The answer is produced by the caller (``core.ai.provider.answer_student_query``)
    and passed in, so this module never imports the AI layer and the question
    is still recorded when the assistant is unavailable — an escalation with a
    reason is a perfectly good outcome (invariant #10).
    """
    if not actor.is_student:
        raise ValidationError("Only students use the assistant.")

    get_milestone(actor, session, milestone_id)

    question = (question or "").strip()
    if not question:
        raise ValidationError("Ask a question first.")
    if len(question) > MAX_QUESTION_CHARS:
        raise ValidationError(
            f"Questions are limited to {MAX_QUESTION_CHARS} characters."
        )

    row = StudentQuery(
        student_email=actor.email,
        milestone_id=milestone_id,
        question=question,
        ai_answer=answer.answer or None,
        sources=list(answer.sources) or None,
        confidence=Decimal(str(round(answer.confidence, 3))),
        escalated=answer.escalated,
        escalation_reason=answer.reason or None,
    )
    session.add(row)
    session.flush()

    record(
        session,
        actor_email=actor.email,
        action="query.asked",
        entity="StudentQuery",
        entity_id=row.id,
        payload={
            "milestone_id": milestone_id,
            "escalated": answer.escalated,
            "confidence": round(answer.confidence, 3),
        },
    )

    return _dto(session, row)


def list_my_queries(
    actor: Actor, session: Session, *, milestone_id: int | None = None
) -> tuple[StudentQueryDTO, ...]:
    """A student's own questions. Never anyone else's (invariant #6)."""
    query = select(StudentQuery).where(StudentQuery.student_email == actor.email)

    if milestone_id is not None:
        get_milestone(actor, session, milestone_id)
        query = query.where(StudentQuery.milestone_id == milestone_id)

    rows = session.scalars(query.order_by(StudentQuery.created_at)).all()
    return tuple(_dto(session, row) for row in rows)


def list_escalated(
    actor: Actor, session: Session, *, include_replied: bool = False
) -> tuple[StudentQueryDTO, ...]:
    """The faculty inbox — escalated questions on milestones they own.

    Scoped through ``visible_subject_ids``, so a faculty member sees questions
    from their own students and nobody else's.
    """
    require_faculty(actor, "read the query inbox")

    query = (
        select(StudentQuery)
        .join(ReviewMilestone, ReviewMilestone.id == StudentQuery.milestone_id)
        .join(ProjectCycle, ProjectCycle.id == ReviewMilestone.cycle_id)
        .where(
            ProjectCycle.subject_id.in_(visible_subject_ids(actor)),
            StudentQuery.escalated.is_(True),
        )
    )

    if not include_replied:
        query = query.where(StudentQuery.faculty_reply.is_(None))

    rows = session.scalars(query.order_by(StudentQuery.created_at)).all()
    return tuple(_dto(session, row) for row in rows)


def reply(
    actor: Actor, session: Session, *, query_id: int, message: str
) -> StudentQueryDTO:
    """Answer an escalated question by hand."""
    require_faculty(actor, "reply to student questions")

    row = session.get(StudentQuery, query_id)
    if row is None:
        raise NotAuthorized("That question does not exist, or is not yours.")

    if row.milestone_id is not None:
        get_milestone(actor, session, row.milestone_id)

    message = (message or "").strip()
    if not message:
        raise ValidationError("A reply cannot be empty.")

    row.faculty_reply = message
    row.replied_by = actor.email
    row.replied_at = utc_now()

    record(
        session,
        actor_email=actor.email,
        action="query.replied",
        entity="StudentQuery",
        entity_id=row.id,
        payload={"milestone_id": row.milestone_id},
    )

    return _dto(session, row)


def escalated_count(actor: Actor, session: Session) -> int:
    """How many questions are waiting on this faculty member."""
    return len(list_escalated(actor, session))

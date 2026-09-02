"""Subject and project-cycle services.

Every public function takes ``actor`` first and scopes its query by it.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.academics.access import require_faculty, visible_subject_ids
from core.academics.dto import CycleDTO, SubjectDTO
from core.audit import record
from core.auth.actor import Actor
from core.db.models import Enrollment, ProjectCycle, Subject
from core.errors import NotAuthorized, ValidationError


def _to_dto(subject: Subject, enrolled_count: int = 0) -> SubjectDTO:
    return SubjectDTO(
        id=subject.id,
        code=subject.code,
        name=subject.name,
        semester=subject.semester,
        owner_email=subject.owner_email,
        enrolled_count=enrolled_count,
    )


def create_subject(
    actor: Actor,
    session: Session,
    *,
    code: str,
    name: str,
    semester: int,
) -> SubjectDTO:
    """Create a subject owned by ``actor``.

    The owner is the actor, never a parameter. A faculty member cannot create
    a subject "on behalf of" a colleague, because that would be a way to write
    a row they would then be unable to see.
    """
    require_faculty(actor, "create subjects")

    code = code.strip().upper()
    name = name.strip()

    if not code:
        raise ValidationError("Subject code is required.")
    if not name:
        raise ValidationError("Subject name is required.")
    if not 1 <= semester <= 6:
        raise ValidationError("Semester must be between 1 and 6.")

    clash = session.scalar(
        select(Subject).where(Subject.code == code, Subject.semester == semester)
    )
    if clash is not None:
        raise ValidationError(f"{code} already exists for semester {semester}.")

    subject = Subject(code=code, name=name, semester=semester, owner_email=actor.email)
    session.add(subject)
    session.flush()  # assign the id before it is audited and returned

    record(
        session,
        actor_email=actor.email,
        action="subject.created",
        entity="Subject",
        entity_id=subject.id,
        payload={"code": code, "name": name, "semester": semester},
    )

    return _to_dto(subject)


def list_subjects(actor: Actor, session: Session) -> tuple[SubjectDTO, ...]:
    """Subjects visible to ``actor``, with their active enrollment counts."""
    counts = (
        select(Enrollment.subject_id, func.count().label("n"))
        .where(Enrollment.is_active.is_(True))
        .group_by(Enrollment.subject_id)
        .subquery()
    )

    rows = session.execute(
        select(Subject, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.subject_id == Subject.id)
        .where(Subject.id.in_(visible_subject_ids(actor)))
        .order_by(Subject.semester, Subject.code)
    ).all()

    return tuple(_to_dto(subject, count) for subject, count in rows)


def get_subject(actor: Actor, session: Session, subject_id: int) -> SubjectDTO:
    """One subject, or :class:`NotAuthorized` if it is not visible to ``actor``.

    "Not visible" and "does not exist" deliberately produce the same error:
    telling a student that subject 47 exists but is not theirs is itself a
    small leak.
    """
    subject = session.scalar(
        select(Subject).where(
            Subject.id == subject_id,
            Subject.id.in_(visible_subject_ids(actor)),
        )
    )

    if subject is None:
        raise NotAuthorized("That subject does not exist, or is not yours.")

    return _to_dto(subject)


def create_cycle(
    actor: Actor,
    session: Session,
    *,
    subject_id: int,
    title: str,
    academic_year: str,
) -> CycleDTO:
    """Add a project cycle to a subject the actor owns."""
    require_faculty(actor, "create project cycles")
    get_subject(actor, session, subject_id)  # authorisation, by reuse

    title = title.strip()
    academic_year = academic_year.strip()

    if not title:
        raise ValidationError("Cycle title is required.")
    if not academic_year:
        raise ValidationError("Academic year is required.")

    cycle = ProjectCycle(subject_id=subject_id, title=title, academic_year=academic_year)
    session.add(cycle)
    session.flush()

    record(
        session,
        actor_email=actor.email,
        action="cycle.created",
        entity="ProjectCycle",
        entity_id=cycle.id,
        payload={"subject_id": subject_id, "title": title, "year": academic_year},
    )

    return CycleDTO(
        id=cycle.id,
        subject_id=subject_id,
        title=title,
        academic_year=academic_year,
    )


def list_cycles(actor: Actor, session: Session, subject_id: int) -> tuple[CycleDTO, ...]:
    """Cycles for one visible subject."""
    get_subject(actor, session, subject_id)

    cycles = session.scalars(
        select(ProjectCycle)
        .where(
            ProjectCycle.subject_id == subject_id,
            ProjectCycle.is_active.is_(True),
        )
        .order_by(ProjectCycle.id)
    ).all()

    return tuple(
        CycleDTO(
            id=cycle.id,
            subject_id=cycle.subject_id,
            title=cycle.title,
            academic_year=cycle.academic_year,
        )
        for cycle in cycles
    )

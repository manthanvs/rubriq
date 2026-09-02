"""Rubric versioning and immutability — fix item 6.

The rule, in one line: **``published_at IS NOT NULL`` makes a rubric and its
criteria read-only.** Every mutating function in this module starts by asserting
that, and the assertion lives here rather than in the UI because a disabled
button is not a constraint.

Editing a published rubric is not an error, though — it clones to
``version + 1`` and the clone starts unpublished. So the faculty member can
always change their mind about the *next* grading without retroactively
changing what an already-graded submission was measured against.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.academics.access import require_faculty
from core.academics.milestones import get_milestone
from core.audit import record
from core.auth.actor import Actor
from core.clock import utc_now
from core.db.models import Criterion, Rubric
from core.errors import NotAuthorized, ValidationError
from core.rubrics.dto import CriterionDTO, RubricDTO

#: Weights are a share of 100. Enforced at publish, not at every edit — a
#: half-built draft is allowed to be inconsistent, a published one is not.
REQUIRED_TOTAL_WEIGHT = Decimal("100")


def _criterion_dto(criterion: Criterion) -> CriterionDTO:
    return CriterionDTO(
        id=criterion.id,
        code=criterion.code,
        title=criterion.title,
        description=criterion.description,
        weight=criterion.weight,
        max_score=criterion.max_score,
        expected_evidence=criterion.expected_evidence,
        is_mandatory=criterion.is_mandatory,
        order_index=criterion.order_index,
    )


def _rubric_dto(session: Session, rubric: Rubric) -> RubricDTO:
    criteria = session.scalars(
        select(Criterion)
        .where(Criterion.rubric_id == rubric.id, Criterion.is_active.is_(True))
        .order_by(Criterion.order_index, Criterion.code)
    ).all()

    return RubricDTO(
        id=rubric.id,
        milestone_id=rubric.milestone_id,
        version=rubric.version,
        published_at=rubric.published_at,
        published_by=rubric.published_by,
        criteria=tuple(_criterion_dto(c) for c in criteria),
    )


def _load_editable(actor: Actor, session: Session, rubric_id: int) -> Rubric:
    """Fetch a rubric the actor owns, refusing if it is frozen.

    Every mutation funnels through here, so there is exactly one place that
    decides what "editable" means and no code path that forgets to ask.
    """
    require_faculty(actor, "edit rubrics")

    rubric = session.get(Rubric, rubric_id)
    if rubric is None:
        raise NotAuthorized("That rubric does not exist, or is not yours.")

    get_milestone(actor, session, rubric.milestone_id)  # authorisation, by reuse

    if rubric.published_at is not None:
        raise ValidationError(
            f"Rubric v{rubric.version} is published and cannot be edited. "
            "Use 'Edit as new version' to create a draft copy — the published "
            "version stays exactly as it was graded against."
        )

    return rubric


# -- reads ---------------------------------------------------------------


def list_rubrics(
    actor: Actor, session: Session, milestone_id: int
) -> tuple[RubricDTO, ...]:
    """Every version for a milestone, newest first."""
    get_milestone(actor, session, milestone_id)

    rubrics = session.scalars(
        select(Rubric)
        .where(Rubric.milestone_id == milestone_id)
        .order_by(Rubric.version.desc())
    ).all()

    return tuple(_rubric_dto(session, r) for r in rubrics)


def get_rubric(actor: Actor, session: Session, rubric_id: int) -> RubricDTO:
    rubric = session.get(Rubric, rubric_id)
    if rubric is None:
        raise NotAuthorized("That rubric does not exist, or is not yours.")

    get_milestone(actor, session, rubric.milestone_id)
    return _rubric_dto(session, rubric)


def published_rubric_for(
    actor: Actor, session: Session, milestone_id: int
) -> RubricDTO | None:
    """The rubric a student sees, and the only one gradeable against.

    Highest published version wins. A draft is never returned here, which is
    what stops a submission being evaluated against a half-written rubric.
    """
    get_milestone(actor, session, milestone_id)

    rubric = session.scalars(
        select(Rubric)
        .where(
            Rubric.milestone_id == milestone_id,
            Rubric.published_at.is_not(None),
        )
        .order_by(Rubric.version.desc())
        .limit(1)
    ).first()

    return None if rubric is None else _rubric_dto(session, rubric)


def draft_rubric_for(
    actor: Actor, session: Session, milestone_id: int
) -> RubricDTO | None:
    """The unpublished working copy, if one exists."""
    get_milestone(actor, session, milestone_id)

    rubric = session.scalars(
        select(Rubric)
        .where(Rubric.milestone_id == milestone_id, Rubric.published_at.is_(None))
        .order_by(Rubric.version.desc())
        .limit(1)
    ).first()

    return None if rubric is None else _rubric_dto(session, rubric)


# -- writes --------------------------------------------------------------


def create_rubric(actor: Actor, session: Session, *, milestone_id: int) -> RubricDTO:
    """Start a draft rubric for a milestone.

    Refuses if a draft already exists — two concurrent drafts for the same
    milestone would leave "which one publishes" undefined.
    """
    require_faculty(actor, "create rubrics")
    get_milestone(actor, session, milestone_id)

    existing_draft = session.scalars(
        select(Rubric).where(
            Rubric.milestone_id == milestone_id, Rubric.published_at.is_(None)
        )
    ).first()
    if existing_draft is not None:
        raise ValidationError(
            f"A draft rubric (v{existing_draft.version}) already exists for this "
            "milestone. Edit or publish it before starting another."
        )

    highest = session.scalar(
        select(func.max(Rubric.version)).where(Rubric.milestone_id == milestone_id)
    )
    version = (highest or 0) + 1

    rubric = Rubric(milestone_id=milestone_id, version=version)
    session.add(rubric)
    session.flush()

    record(
        session,
        actor_email=actor.email,
        action="rubric.created",
        entity="Rubric",
        entity_id=rubric.id,
        payload={"milestone_id": milestone_id, "version": version},
    )

    return _rubric_dto(session, rubric)


def add_criterion(
    actor: Actor,
    session: Session,
    *,
    rubric_id: int,
    code: str,
    title: str,
    weight: Decimal | int | str,
    max_score: Decimal | int | str,
    description: str | None = None,
    expected_evidence: str | None = None,
    is_mandatory: bool = False,
) -> RubricDTO:
    """Add a criterion to a draft rubric."""
    rubric = _load_editable(actor, session, rubric_id)

    code = code.strip().upper()
    title = title.strip()

    if not code:
        raise ValidationError("Criterion code is required (C1, C2, …).")
    if not title:
        raise ValidationError("Criterion title is required.")

    # Decimal(str(...)) — Decimal(0.1) is not 0.1, and these feed §5's totals.
    weight_value = Decimal(str(weight))
    max_score_value = Decimal(str(max_score))

    if weight_value <= 0:
        raise ValidationError("Weight must be greater than zero.")
    if max_score_value <= 0:
        raise ValidationError("Max score must be greater than zero.")

    clash = session.scalars(
        select(Criterion).where(Criterion.rubric_id == rubric_id, Criterion.code == code)
    ).first()
    if clash is not None:
        raise ValidationError(f"Criterion {code} already exists in this rubric.")

    highest_order = session.scalar(
        select(func.max(Criterion.order_index)).where(Criterion.rubric_id == rubric_id)
    )

    session.add(
        Criterion(
            rubric_id=rubric_id,
            code=code,
            title=title,
            description=(description or "").strip() or None,
            weight=weight_value,
            max_score=max_score_value,
            expected_evidence=(expected_evidence or "").strip() or None,
            is_mandatory=is_mandatory,
            order_index=(highest_order or 0) + 1,
        )
    )
    session.flush()

    record(
        session,
        actor_email=actor.email,
        action="criterion.added",
        entity="Rubric",
        entity_id=rubric_id,
        payload={"code": code, "weight": str(weight_value)},
    )

    return _rubric_dto(session, rubric)


def remove_criterion(
    actor: Actor, session: Session, *, rubric_id: int, code: str
) -> RubricDTO:
    """Deactivate a criterion on a draft rubric.

    Deactivated, not deleted (invariant #7): ``CriterionScore`` rows from an
    earlier version still point at criteria, and a dangling reference is how a
    graded submission loses the thing it was graded on.
    """
    rubric = _load_editable(actor, session, rubric_id)

    criterion = session.scalars(
        select(Criterion).where(
            Criterion.rubric_id == rubric_id,
            Criterion.code == code.strip().upper(),
            Criterion.is_active.is_(True),
        )
    ).first()

    if criterion is None:
        raise ValidationError(f"No active criterion {code} in this rubric.")

    criterion.is_active = False

    record(
        session,
        actor_email=actor.email,
        action="criterion.removed",
        entity="Rubric",
        entity_id=rubric_id,
        payload={"code": criterion.code},
    )

    return _rubric_dto(session, rubric)


def publish_rubric(actor: Actor, session: Session, *, rubric_id: int) -> RubricDTO:
    """Freeze a draft. The only transition into the immutable state.

    Validates before freezing, because a published rubric with weights summing
    to 95 silently makes every ``base_total`` out of 95 rather than the
    milestone's max marks — the second failure fix item 1 names.
    """
    rubric = _load_editable(actor, session, rubric_id)
    dto = _rubric_dto(session, rubric)

    if not dto.criteria:
        raise ValidationError("A rubric needs at least one criterion before publishing.")

    if dto.total_weight != REQUIRED_TOTAL_WEIGHT:
        raise ValidationError(
            f"Weights must sum to {REQUIRED_TOTAL_WEIGHT}, not {dto.total_weight}. "
            f"Adjust the {len(dto.criteria)} criteria and try again."
        )

    rubric.published_at = utc_now()
    rubric.published_by = actor.email

    record(
        session,
        actor_email=actor.email,
        action="rubric.published",
        entity="Rubric",
        entity_id=rubric.id,
        payload={
            "milestone_id": rubric.milestone_id,
            "version": rubric.version,
            "criteria": len(dto.criteria),
        },
    )

    return _rubric_dto(session, rubric)


def clone_for_edit(actor: Actor, session: Session, *, rubric_id: int) -> RubricDTO:
    """Copy a published rubric into a new unpublished version.

    This is the *only* way to change a published rubric, and it changes nothing
    about the original: v1 keeps its criteria, its ``published_at`` and its
    grading history, byte for byte.
    """
    require_faculty(actor, "edit rubrics")

    source = session.get(Rubric, rubric_id)
    if source is None:
        raise NotAuthorized("That rubric does not exist, or is not yours.")

    get_milestone(actor, session, source.milestone_id)

    if source.published_at is None:
        raise ValidationError(
            f"Rubric v{source.version} is already a draft — edit it directly."
        )

    existing_draft = session.scalars(
        select(Rubric).where(
            Rubric.milestone_id == source.milestone_id, Rubric.published_at.is_(None)
        )
    ).first()
    if existing_draft is not None:
        raise ValidationError(
            f"A draft (v{existing_draft.version}) already exists for this milestone."
        )

    highest = session.scalar(
        select(func.max(Rubric.version)).where(Rubric.milestone_id == source.milestone_id)
    )

    clone = Rubric(milestone_id=source.milestone_id, version=(highest or 0) + 1)
    session.add(clone)
    session.flush()

    originals = session.scalars(
        select(Criterion)
        .where(Criterion.rubric_id == source.id, Criterion.is_active.is_(True))
        .order_by(Criterion.order_index, Criterion.code)
    ).all()

    for original in originals:
        session.add(
            Criterion(
                rubric_id=clone.id,
                code=original.code,
                title=original.title,
                description=original.description,
                weight=original.weight,
                max_score=original.max_score,
                expected_evidence=original.expected_evidence,
                is_mandatory=original.is_mandatory,
                order_index=original.order_index,
            )
        )

    session.flush()

    record(
        session,
        actor_email=actor.email,
        action="rubric.cloned",
        entity="Rubric",
        entity_id=clone.id,
        payload={"from_version": source.version, "to_version": clone.version},
    )

    return _rubric_dto(session, clone)

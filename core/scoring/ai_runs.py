"""Persisting an AI evaluation — §6.6, and fix item 9.

The graph produces verdicts and per-criterion scores. This module writes them
down and then asks ``core/scoring/engine.py`` for the totals, so invariant #2
holds: *"the LLM is never asked to do arithmetic that decides marks."* Nothing
here multiplies a weight.

The sheet it writes is **unapproved**. Invariant #1: the AI produces an
estimate, and a faculty member approves it or overrides it before it is final.

Fix item 9's distinction lives in :func:`next_evaluation_version`: a retry
increments the version, which produces a new ``thread_id``, which is what makes
a genuine retry start clean instead of resuming the checkpoint that poisoned
the last attempt. A browser refresh does *not* come through here — it re-enters
the generator with the version it already had.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.academics.access import require_faculty
from core.academics.milestones import get_milestone
from core.audit import record
from core.auth.actor import Actor
from core.db.models import (
    Criterion,
    CriterionScore,
    Evaluation,
    ReviewMilestone,
    Rubric,
    ScoreSheet,
    Submission,
)
from core.errors import NotAuthorized, ValidationError
from core.scoring.dto import ScoreSheetDTO
from core.scoring.enums import EvaluationEngine, EvaluationStatus, Verdict
from core.scoring.policy import AttendanceStatus
from core.scoring.sheets import _recompute, _sheet_dto


def next_evaluation_version(session: Session, submission_id: int) -> int:
    """The version a fresh attempt should use.

    Incrementing is what gives a retry a new ``thread_id`` (§6.3) and therefore
    a clean start. Fix item 9: *"don't collapse that distinction."*
    """
    highest = session.scalar(
        select(func.max(Evaluation.version)).where(
            Evaluation.submission_id == submission_id
        )
    )
    return (highest or 0) + 1


def _published_rubric_row(session: Session, milestone_id: int) -> Rubric | None:
    """The rubric an evaluation must pin itself to.

    Private: it returns a row and performs no scoping, so every caller must
    already have gone through ``get_milestone``. The actor contract would flag
    it as a public service that forgot its actor, and it would be right to.
    """
    return session.scalars(
        select(Rubric)
        .where(Rubric.milestone_id == milestone_id, Rubric.published_at.is_not(None))
        .order_by(Rubric.version.desc())
        .limit(1)
    ).first()


def start_ai_evaluation(
    actor: Actor, session: Session, *, submission_id: int
) -> Evaluation:
    """Open a ``RUNNING`` evaluation row before the graph is invoked.

    Written first, so a run that dies mid-flight leaves a visible ``RUNNING``
    row rather than nothing at all — fix item 9's *"a FAILED evaluation sits
    invisible and gets approved as a zero"* starts with the row not existing.
    """
    require_faculty(actor, "run AI evaluation")

    submission = session.get(Submission, submission_id)
    if submission is None:
        raise NotAuthorized("That submission does not exist, or is not yours.")

    get_milestone(actor, session, submission.milestone_id)

    rubric = _published_rubric_row(session, submission.milestone_id)
    if rubric is None:
        raise ValidationError(
            "This milestone has no published rubric, so there is nothing to "
            "evaluate against."
        )

    evaluation = Evaluation(
        submission_id=submission_id,
        # Pinned, not looked up later — fix item 2.
        submission_version=submission.version,
        rubric_id=rubric.id,
        rubric_version=rubric.version,
        version=next_evaluation_version(session, submission_id),
        engine=EvaluationEngine.AI,
        status=EvaluationStatus.RUNNING,
        created_by=actor.email,
    )
    session.add(evaluation)
    session.flush()

    record(
        session,
        actor_email=actor.email,
        action="evaluation.started",
        entity="Evaluation",
        entity_id=evaluation.id,
        payload={
            "submission_id": submission_id,
            "version": evaluation.version,
            "rubric_version": rubric.version,
        },
    )

    return evaluation


def finish_ai_evaluation(
    actor: Actor,
    session: Session,
    *,
    evaluation_id: int,
    result,
) -> ScoreSheetDTO:
    """Write the graph's output and compute the sheet from it.

    ``result`` is a ``core.ai.provider.EvaluationResult``. Taken as a plain
    object rather than imported for typing, so this module carries no import
    path into ``core/ai`` — and therefore none into langgraph.
    """
    require_faculty(actor, "record AI evaluation")

    evaluation = session.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise NotAuthorized("That evaluation does not exist, or is not yours.")

    submission = session.get(Submission, evaluation.submission_id)
    get_milestone(actor, session, submission.milestone_id)

    evaluation.model_name = result.model_name
    evaluation.prompt_version = result.prompt_version
    evaluation.graph_version = result.graph_version
    # §6.5: stored verbatim whatever happens, including on failure.
    evaluation.raw_response = {"text": result.raw_response}

    if result.failed:
        evaluation.status = EvaluationStatus.FAILED
        evaluation.failure_reason = result.failure_reason

        record(
            session,
            actor_email=actor.email,
            action="evaluation.failed",
            entity="Evaluation",
            entity_id=evaluation.id,
            payload={"reason": result.failure_reason},
        )
        # No sheet: a failed run has no marks to show, and inventing zeroes
        # here is exactly how one gets approved as a real score.
        raise ValidationError(
            f"AI evaluation failed: {result.failure_reason}. The run is marked "
            "FAILED and can be retried."
        )

    criteria = {
        c.code: c
        for c in session.scalars(
            select(Criterion).where(
                Criterion.rubric_id == evaluation.rubric_id,
                Criterion.is_active.is_(True),
            )
        ).all()
    }

    for item in result.criteria:
        criterion = criteria.get(item.code)
        if criterion is None:
            continue  # the model answered for a criterion this rubric lost

        session.add(
            CriterionScore(
                evaluation_id=evaluation.id,
                criterion_id=criterion.id,
                score=Decimal(str(item.score)),
                verdict=item.verdict,
                confidence=Decimal(str(item.confidence)),
                # The model's original span, untouched (fix item 5).
                evidence_span=item.evidence or None,
                rationale=item.rationale or None,
            )
        )

    missing = set(criteria) - {c.code for c in result.criteria}
    for code in sorted(missing):
        # A criterion the model skipped is NO_EVIDENCE, not absent from the
        # sheet — otherwise the weights would not sum and the engine would
        # refuse the whole submission.
        session.add(
            CriterionScore(
                evaluation_id=evaluation.id,
                criterion_id=criteria[code].id,
                score=Decimal("0"),
                verdict=Verdict.NO_EVIDENCE,
                rationale="The model returned no answer for this criterion.",
            )
        )

    evaluation.status = EvaluationStatus.COMPLETE
    session.flush()

    milestone = session.get(ReviewMilestone, submission.milestone_id)

    sheet = ScoreSheet(
        evaluation_id=evaluation.id,
        submission_id=submission.id,
        max_marks=milestone.max_marks,
        weighted_percent=Decimal("0"),
        base_total=Decimal("0"),
        penalty=Decimal("0"),
        final_total=Decimal("0"),
        attendance_status=AttendanceStatus.PRESENT,
    )
    session.add(sheet)
    session.flush()

    # Totals come from the engine, never from the graph (invariant #2).
    _recompute(session, sheet)
    session.flush()

    record(
        session,
        actor_email=actor.email,
        action="evaluation.completed",
        entity="Evaluation",
        entity_id=evaluation.id,
        payload={
            "submission_id": submission.id,
            "version": evaluation.version,
            "criteria": len(result.criteria),
            "rejections": len(result.rejections),
            "rejection_rate": round(result.rejection_rate, 3),
            "final_total": str(sheet.final_total),
        },
    )

    return _sheet_dto(session, sheet)


def mark_evaluation_failed(
    actor: Actor, session: Session, *, evaluation_id: int, reason: str
) -> None:
    """Record that a run died, so it is visible rather than merely absent."""
    require_faculty(actor, "record AI evaluation")

    evaluation = session.get(Evaluation, evaluation_id)
    if evaluation is None:
        return

    submission = session.get(Submission, evaluation.submission_id)
    get_milestone(actor, session, submission.milestone_id)

    evaluation.status = EvaluationStatus.FAILED
    evaluation.failure_reason = reason[:2000]

    record(
        session,
        actor_email=actor.email,
        action="evaluation.failed",
        entity="Evaluation",
        entity_id=evaluation.id,
        payload={"reason": reason[:500]},
    )

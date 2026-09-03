"""Score sheets: manual scoring, approval, overrides — fix item 4.

Three rules run this module, and each is a failure fix item 4 names:

* **Approval is one transaction** — recompute, write the sheet, stamp
  ``approved_by``/``approved_at``, write an ``AuditLog`` row. All of it or none
  of it, so invariant #1 is never half-true.
* **Approval is blocked** while the evaluation is not ``COMPLETE`` or a
  mandatory criterion sits at ``NO_EVIDENCE``.
* **Overrides are append-only** and require a non-empty reason, checked here
  rather than on the widget. An override on an approved sheet *clears the
  approval*, because a mark that changed has to be re-owned by a person.

Every total on a stored sheet came from :func:`core.scoring.engine.compute_score_sheet`.
Nothing in this module does arithmetic of its own.
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
from core.db.models import (
    Criterion,
    CriterionScore,
    Evaluation,
    LatePolicyRow,
    ProjectCycle,
    ReviewMilestone,
    Rubric,
    ScoreOverride,
    ScoreSheet,
    Submission,
    User,
)
from core.errors import NotAuthorized, ValidationError
from core.scoring.dto import CriterionScoreDTO, ScoreSheetDTO
from core.scoring.engine import CriterionScoreInput, compute_score_sheet
from core.scoring.enums import EvaluationEngine, EvaluationStatus, Verdict
from core.scoring.policy import DEFAULT_LATE_POLICY, AttendanceStatus, LatePolicy


def _policy_for(session: Session, milestone: ReviewMilestone) -> LatePolicy:
    """Milestone override, then subject override, then §5.1's default.

    Most specific wins, so a subject-wide policy can be relaxed for one review
    without editing the other milestones.
    """
    subject_id = session.execute(
        select(ProjectCycle.subject_id).where(ProjectCycle.id == milestone.cycle_id)
    ).scalar_one()

    for scope, scope_id in (("MILESTONE", milestone.id), ("SUBJECT", subject_id)):
        row = session.scalars(
            select(LatePolicyRow)
            .where(LatePolicyRow.scope == scope, LatePolicyRow.scope_id == scope_id)
            .order_by(LatePolicyRow.version.desc())
            .limit(1)
        ).first()
        if row is not None:
            return LatePolicy.from_rules(row.rules)

    return DEFAULT_LATE_POLICY


def policy_for_milestone(
    actor: Actor, session: Session, *, milestone_id: int
) -> LatePolicy:
    """The late policy in force for one milestone.

    Public because the student's Submit page has to state the consequence of
    submitting now *before* they confirm (fix item 10), and it must state the
    same policy the scoring engine will later apply — not a hard-coded default
    that drifts the moment a subject overrides one.
    """
    milestone = get_milestone(actor, session, milestone_id)  # authorisation
    row = session.get(ReviewMilestone, milestone.id)
    return _policy_for(session, row)


def _load_for_grading(
    actor: Actor, session: Session, submission_id: int
) -> tuple[Submission, ReviewMilestone]:
    """Fetch a submission the actor may grade, or refuse."""
    require_faculty(actor, "score submissions")

    submission = session.get(Submission, submission_id)
    if submission is None:
        raise NotAuthorized("That submission does not exist, or is not yours.")

    get_milestone(actor, session, submission.milestone_id)  # authorisation, by reuse
    milestone = session.get(ReviewMilestone, submission.milestone_id)

    return submission, milestone


def _criteria_of(session: Session, rubric_id: int) -> list[Criterion]:
    return list(
        session.scalars(
            select(Criterion)
            .where(Criterion.rubric_id == rubric_id, Criterion.is_active.is_(True))
            .order_by(Criterion.order_index, Criterion.code)
        ).all()
    )


def _sheet_dto(session: Session, sheet: ScoreSheet) -> ScoreSheetDTO:
    evaluation = session.get(Evaluation, sheet.evaluation_id)
    criteria = {c.id: c for c in _criteria_of(session, evaluation.rubric_id)}

    rows = session.scalars(
        select(CriterionScore).where(CriterionScore.evaluation_id == evaluation.id)
    ).all()

    scored = []
    for row in rows:
        criterion = criteria.get(row.criterion_id)
        if criterion is None:
            continue  # deactivated on a later rubric version; not shown
        scored.append(
            CriterionScoreDTO(
                criterion_id=criterion.id,
                code=criterion.code,
                title=criterion.title,
                weight=criterion.weight,
                max_score=criterion.max_score,
                is_mandatory=criterion.is_mandatory,
                score=row.score,
                verdict=row.verdict,
                confidence=row.confidence,
                evidence_span=row.evidence_span,
                rationale=row.rationale,
            )
        )

    scored.sort(key=lambda c: c.code)

    override_count = (
        session.scalar(
            select(func.count())
            .select_from(ScoreOverride)
            .where(ScoreOverride.score_sheet_id == sheet.id)
        )
        or 0
    )

    return ScoreSheetDTO(
        id=sheet.id,
        evaluation_id=sheet.evaluation_id,
        submission_id=sheet.submission_id,
        engine=evaluation.engine,
        evaluation_status=evaluation.status,
        submission_version=evaluation.submission_version,
        rubric_version=evaluation.rubric_version,
        max_marks=sheet.max_marks,
        weighted_percent=sheet.weighted_percent,
        base_total=sheet.base_total,
        penalty=sheet.penalty,
        final_total=sheet.final_total,
        days_late=sheet.days_late,
        attendance_status=sheet.attendance_status,
        reinstated=sheet.reinstated,
        reinstate_reason=sheet.reinstate_reason,
        approved_by=sheet.approved_by,
        approved_at=sheet.approved_at,
        faculty_note=sheet.faculty_note,
        criteria=tuple(scored),
        override_count=override_count,
    )


def _recompute(session: Session, sheet: ScoreSheet) -> None:
    """Recalculate totals from the persisted criterion rows.

    The round-trip fix item 1 asks for: what is stored always equals what the
    engine produces from the rows beside it.
    """
    evaluation = session.get(Evaluation, sheet.evaluation_id)
    submission = session.get(Submission, sheet.submission_id)
    milestone = session.get(ReviewMilestone, submission.milestone_id)

    criteria = {c.id: c for c in _criteria_of(session, evaluation.rubric_id)}
    rows = session.scalars(
        select(CriterionScore).where(CriterionScore.evaluation_id == evaluation.id)
    ).all()

    inputs = [
        CriterionScoreInput(
            code=criteria[row.criterion_id].code,
            score=row.score,
            max_score=criteria[row.criterion_id].max_score,
            weight=criteria[row.criterion_id].weight,
        )
        for row in rows
        if row.criterion_id in criteria
    ]

    result = compute_score_sheet(
        inputs,
        max_marks=milestone.max_marks,
        due_at=milestone.due_at,
        submitted_at=submission.submitted_at,
        policy=_policy_for(session, milestone),
        reinstated=sheet.reinstated,
    )

    sheet.max_marks = result.max_marks
    sheet.weighted_percent = result.weighted_percent
    sheet.base_total = result.base_total
    sheet.penalty = result.penalty
    sheet.final_total = result.final_total
    sheet.days_late = result.days_late
    sheet.attendance_status = result.attendance


# -- scoring -------------------------------------------------------------


def save_manual_scores(
    actor: Actor,
    session: Session,
    *,
    submission_id: int,
    scores: dict[str, tuple[Decimal | int | str, Verdict]],
    faculty_note: str | None = None,
) -> ScoreSheetDTO:
    """Score a submission by hand and write its sheet.

    Refuses once the sheet is approved — a change after approval goes through
    :func:`override_criterion`, so it leaves a reason and an audit trail.
    """
    submission, milestone = _load_for_grading(actor, session, submission_id)

    rubric = session.scalars(
        select(Rubric)
        .where(
            Rubric.milestone_id == submission.milestone_id,
            Rubric.published_at.is_not(None),
        )
        .order_by(Rubric.version.desc())
        .limit(1)
    ).first()

    if rubric is None:
        raise ValidationError(
            "This milestone has no published rubric, so there is nothing to "
            "score against."
        )

    criteria = _criteria_of(session, rubric.id)
    by_code = {c.code: c for c in criteria}

    unknown = sorted(set(scores) - set(by_code))
    if unknown:
        raise ValidationError(f"Not criteria of this rubric: {', '.join(unknown)}.")

    missing = sorted(set(by_code) - set(scores))
    if missing:
        raise ValidationError(
            f"Every criterion needs a score. Missing: {', '.join(missing)}."
        )

    evaluation = session.scalars(
        select(Evaluation)
        .where(
            Evaluation.submission_id == submission_id,
            Evaluation.engine == EvaluationEngine.MANUAL,
        )
        .order_by(Evaluation.version.desc())
        .limit(1)
    ).first()

    if evaluation is None:
        highest = session.scalar(
            select(func.max(Evaluation.version)).where(
                Evaluation.submission_id == submission_id
            )
        )
        evaluation = Evaluation(
            submission_id=submission_id,
            submission_version=submission.version,
            rubric_id=rubric.id,
            rubric_version=rubric.version,
            version=(highest or 0) + 1,
            engine=EvaluationEngine.MANUAL,
            status=EvaluationStatus.COMPLETE,
            created_by=actor.email,
        )
        session.add(evaluation)
        session.flush()

    sheet = session.scalars(
        select(ScoreSheet).where(ScoreSheet.evaluation_id == evaluation.id)
    ).first()

    if sheet is not None and sheet.approved_at is not None:
        raise ValidationError(
            f"This sheet was approved by {sheet.approved_by}. Change a mark with "
            "an override so the reason is recorded."
        )

    existing = {
        row.criterion_id: row
        for row in session.scalars(
            select(CriterionScore).where(CriterionScore.evaluation_id == evaluation.id)
        ).all()
    }

    for code, (raw_score, verdict) in scores.items():
        criterion = by_code[code]
        value = Decimal(str(raw_score))

        if value < 0 or value > criterion.max_score:
            raise ValidationError(
                f"{code}: score must be between 0 and {criterion.max_score}."
            )
        # Invariant #3, enforced for manual scoring too: no evidence, no marks.
        if verdict is Verdict.NO_EVIDENCE and value != 0:
            raise ValidationError(f"{code}: NO_EVIDENCE must score 0, not {value}.")

        row = existing.get(criterion.id)
        if row is None:
            session.add(
                CriterionScore(
                    evaluation_id=evaluation.id,
                    criterion_id=criterion.id,
                    score=value,
                    verdict=verdict,
                )
            )
        else:
            row.score = value
            row.verdict = verdict

    session.flush()

    if sheet is None:
        sheet = ScoreSheet(
            evaluation_id=evaluation.id,
            submission_id=submission_id,
            max_marks=milestone.max_marks,
            weighted_percent=Decimal("0"),
            base_total=Decimal("0"),
            penalty=Decimal("0"),
            final_total=Decimal("0"),
            # Placeholder only — _recompute below replaces every one of these
            # from the engine before the row is ever read.
            attendance_status=AttendanceStatus.PRESENT,
        )
        session.add(sheet)
        session.flush()

    if faculty_note is not None:
        sheet.faculty_note = faculty_note.strip() or None

    _recompute(session, sheet)
    session.flush()

    record(
        session,
        actor_email=actor.email,
        action="score.saved",
        entity="ScoreSheet",
        entity_id=sheet.id,
        payload={
            "submission_id": submission_id,
            "final_total": str(sheet.final_total),
            "criteria": len(scores),
        },
    )

    return _sheet_dto(session, sheet)


# -- approval ------------------------------------------------------------


def approval_blockers(sheet: ScoreSheetDTO) -> tuple[str, ...]:
    """Why this sheet cannot be approved yet. Empty means it can.

    A pure function of the DTO so the grid can show the reason *before* the
    button is pressed, and the bulk action can exclude rows without trying
    them one at a time.
    """
    reasons: list[str] = []

    if sheet.evaluation_status is not EvaluationStatus.COMPLETE:
        reasons.append(f"the evaluation is {sheet.evaluation_status}, not COMPLETE")

    unresolved = sheet.unresolved_mandatory
    if unresolved:
        reasons.append(f"mandatory criteria unevidenced: {', '.join(unresolved)}")

    return tuple(reasons)


def approve_sheet(
    actor: Actor,
    session: Session,
    *,
    score_sheet_id: int,
    faculty_note: str | None = None,
) -> ScoreSheetDTO:
    """Recompute, stamp, audit — one transaction, all or nothing."""
    require_faculty(actor, "approve score sheets")

    sheet = session.get(ScoreSheet, score_sheet_id)
    if sheet is None:
        raise NotAuthorized("That score sheet does not exist, or is not yours.")

    submission = session.get(Submission, sheet.submission_id)
    get_milestone(actor, session, submission.milestone_id)

    if sheet.approved_at is not None:
        raise ValidationError(
            f"Already approved by {sheet.approved_by}. Override a criterion to "
            "change it — that clears the approval and records why."
        )

    # Recompute first: approving a stale total would defeat the point.
    _recompute(session, sheet)
    session.flush()

    dto = _sheet_dto(session, sheet)
    blockers = approval_blockers(dto)
    if blockers:
        raise ValidationError("Cannot approve — " + "; ".join(blockers) + ".")

    if faculty_note is not None:
        sheet.faculty_note = faculty_note.strip() or None

    sheet.approved_by = actor.email
    sheet.approved_at = utc_now()

    record(
        session,
        actor_email=actor.email,
        action="score.approved",
        entity="ScoreSheet",
        entity_id=sheet.id,
        payload={
            "submission_id": sheet.submission_id,
            "final_total": str(sheet.final_total),
            "attendance": str(sheet.attendance_status),
        },
    )

    return _sheet_dto(session, sheet)


def override_criterion(
    actor: Actor,
    session: Session,
    *,
    score_sheet_id: int,
    criterion_code: str,
    new_score: Decimal | int | str,
    reason: str,
    new_verdict: Verdict | None = None,
) -> ScoreSheetDTO:
    """Change one criterion, recording old, new, who and why.

    Append-only: the ``ScoreOverride`` row is never updated. If the sheet was
    approved, the approval is **cleared** — a total that moved has to be
    re-owned by a person before it is final again (invariant #1).
    """
    require_faculty(actor, "override scores")

    sheet = session.get(ScoreSheet, score_sheet_id)
    if sheet is None:
        raise NotAuthorized("That score sheet does not exist, or is not yours.")

    submission = session.get(Submission, sheet.submission_id)
    get_milestone(actor, session, submission.milestone_id)

    # Checked in core/, not merely marked required on the widget.
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("An override needs a reason. It becomes the audit trail.")

    evaluation = session.get(Evaluation, sheet.evaluation_id)
    criterion = session.scalars(
        select(Criterion).where(
            Criterion.rubric_id == evaluation.rubric_id,
            Criterion.code == criterion_code.strip().upper(),
        )
    ).first()
    if criterion is None:
        raise ValidationError(f"No criterion {criterion_code} on this rubric.")

    row = session.scalars(
        select(CriterionScore).where(
            CriterionScore.evaluation_id == evaluation.id,
            CriterionScore.criterion_id == criterion.id,
        )
    ).first()
    if row is None:
        raise ValidationError(f"{criterion_code} has not been scored yet.")

    value = Decimal(str(new_score))
    if value < 0 or value > criterion.max_score:
        raise ValidationError(
            f"{criterion.code}: score must be between 0 and {criterion.max_score}."
        )

    verdict = new_verdict or row.verdict
    if verdict is Verdict.NO_EVIDENCE and value != 0:
        raise ValidationError(f"{criterion.code}: NO_EVIDENCE must score 0.")

    session.add(
        ScoreOverride(
            score_sheet_id=sheet.id,
            criterion_id=criterion.id,
            old_score=row.score,
            new_score=value,
            old_verdict=row.verdict,
            new_verdict=verdict,
            reason=reason,
            overridden_by=actor.email,
        )
    )

    was_approved = sheet.approved_at is not None
    previous_score = row.score

    row.score = value
    row.verdict = verdict
    session.flush()

    _recompute(session, sheet)

    if was_approved:
        sheet.approved_by = None
        sheet.approved_at = None

    record(
        session,
        actor_email=actor.email,
        action="score.overridden",
        entity="ScoreSheet",
        entity_id=sheet.id,
        payload={
            "criterion": criterion.code,
            "from": str(previous_score),
            "to": str(value),
            "reason": reason,
            "approval_cleared": was_approved,
        },
    )

    return _sheet_dto(session, sheet)


def reinstate(
    actor: Actor, session: Session, *, score_sheet_id: int, reason: str
) -> ScoreSheetDTO:
    """Zero the late penalty on an absent submission. §5.1's reinstatement."""
    require_faculty(actor, "reinstate submissions")

    sheet = session.get(ScoreSheet, score_sheet_id)
    if sheet is None:
        raise NotAuthorized("That score sheet does not exist, or is not yours.")

    submission = session.get(Submission, sheet.submission_id)
    get_milestone(actor, session, submission.milestone_id)

    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Reinstatement needs a reason (§5.1).")

    sheet.reinstated = True
    sheet.reinstate_reason = reason
    # A reinstated total is a different total; it must be approved afresh.
    sheet.approved_by = None
    sheet.approved_at = None

    _recompute(session, sheet)

    record(
        session,
        actor_email=actor.email,
        action="score.reinstated",
        entity="ScoreSheet",
        entity_id=sheet.id,
        payload={"reason": reason, "final_total": str(sheet.final_total)},
    )

    return _sheet_dto(session, sheet)


# -- reads ---------------------------------------------------------------


def get_sheet(actor: Actor, session: Session, score_sheet_id: int) -> ScoreSheetDTO:
    sheet = session.get(ScoreSheet, score_sheet_id)
    if sheet is None:
        raise NotAuthorized("That score sheet does not exist, or is not yours.")

    submission = session.get(Submission, sheet.submission_id)
    get_milestone(actor, session, submission.milestone_id)

    if actor.is_student and submission.student_email != actor.email:
        raise NotAuthorized("You can only see your own score sheet.")

    return _sheet_dto(session, sheet)


def sheet_for_submission(
    actor: Actor, session: Session, submission_id: int
) -> ScoreSheetDTO | None:
    """The sheet attached to a submission's latest evaluation, if any."""
    submission = session.get(Submission, submission_id)
    if submission is None:
        raise NotAuthorized("That submission does not exist, or is not yours.")

    get_milestone(actor, session, submission.milestone_id)

    if actor.is_student and submission.student_email != actor.email:
        raise NotAuthorized("You can only see your own score sheet.")

    sheet = session.scalars(
        select(ScoreSheet)
        .join(Evaluation, Evaluation.id == ScoreSheet.evaluation_id)
        .where(ScoreSheet.submission_id == submission_id)
        .order_by(Evaluation.version.desc())
        .limit(1)
    ).first()

    return None if sheet is None else _sheet_dto(session, sheet)


def override_history(
    actor: Actor, session: Session, score_sheet_id: int
) -> tuple[dict, ...]:
    """Who changed what, when and why — fix item 15's raw material."""
    get_sheet(actor, session, score_sheet_id)  # authorisation, by reuse

    rows = session.execute(
        select(ScoreOverride, Criterion.code, User.name)
        .join(Criterion, Criterion.id == ScoreOverride.criterion_id)
        .outerjoin(User, User.email == ScoreOverride.overridden_by)
        .where(ScoreOverride.score_sheet_id == score_sheet_id)
        .order_by(ScoreOverride.overridden_at.desc())
    ).all()

    return tuple(
        {
            "criterion": code,
            "from": override.old_score,
            "to": override.new_score,
            "reason": override.reason,
            "by": name or override.overridden_by,
            "at": override.overridden_at,
        }
        for override, code, name in rows
    )

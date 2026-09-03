"""Fix item 4 — approval and override integrity.

The proofs it asks for, one test each:

* approving a non-``COMPLETE`` evaluation raises;
* an override with ``reason=""`` raises;
* after an override, the stored ``final_total`` equals a fresh recompute;
* two sequential approvals produce two audit rows and never mutate the first.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from core.db.engine import session_scope
from core.db.models import AuditLog, Evaluation, ScoreOverride, ScoreSheet
from core.errors import NotAuthorized, ValidationError
from core.scoring.enums import EvaluationStatus, Verdict
from core.scoring.policy import AttendanceStatus
from core.scoring.sheets import (
    approval_blockers,
    approve_sheet,
    get_sheet,
    override_criterion,
    override_history,
    reinstate,
    save_manual_scores,
    sheet_for_submission,
)

FULL = {"C1": (10, Verdict.FOLLOWED), "C2": (10, Verdict.FOLLOWED)}
PARTIAL = {"C1": (5, Verdict.PARTIAL), "C2": (8, Verdict.FOLLOWED)}


def _save(db_factory, world, graded, scores=None):
    with session_scope(db_factory) as session:
        return save_manual_scores(
            world.faculty_a,
            session,
            submission_id=graded.submission_id,
            scores=scores or FULL,
        )


class TestManualScoring:
    def test_scoring_writes_a_sheet_computed_by_the_engine(
        self, db_factory, world, graded
    ) -> None:
        sheet = _save(db_factory, world, graded)

        # 100% of a 25-mark milestone, submitted on time.
        assert sheet.weighted_percent == Decimal("100.00")
        assert sheet.final_total == Decimal("25.00")
        assert sheet.attendance_status is AttendanceStatus.PRESENT
        assert sheet.provenance == "MANUAL"

    def test_partial_scores_weigh_correctly(self, db_factory, world, graded) -> None:
        sheet = _save(db_factory, world, graded, PARTIAL)

        # 0.5*60 + 0.8*40 = 30 + 32 = 62 percent of 25 = 15.50
        assert sheet.weighted_percent == Decimal("62.00")
        assert sheet.final_total == Decimal("15.50")

    def test_every_criterion_must_be_scored(self, db_factory, world, graded) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError) as excinfo:
                save_manual_scores(
                    world.faculty_a,
                    session,
                    submission_id=graded.submission_id,
                    scores={"C1": (10, Verdict.FOLLOWED)},
                )

        assert "C2" in str(excinfo.value)

    def test_no_evidence_must_score_zero(self, db_factory, world, graded) -> None:
        """Invariant #3 applies to manual scoring, not only to the AI."""
        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError):
                save_manual_scores(
                    world.faculty_a,
                    session,
                    submission_id=graded.submission_id,
                    scores={
                        "C1": (7, Verdict.NO_EVIDENCE),
                        "C2": (10, Verdict.FOLLOWED),
                    },
                )

    def test_a_score_above_the_maximum_is_refused(
        self, db_factory, world, graded
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError):
                save_manual_scores(
                    world.faculty_a,
                    session,
                    submission_id=graded.submission_id,
                    scores={"C1": (99, Verdict.FOLLOWED), "C2": (10, Verdict.FOLLOWED)},
                )

    def test_a_student_cannot_score(self, db_factory, world, graded) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                save_manual_scores(
                    world.student_1,
                    session,
                    submission_id=graded.submission_id,
                    scores=FULL,
                )

    def test_another_faculty_cannot_score_your_students(
        self, db_factory, world, graded
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                save_manual_scores(
                    world.faculty_b,
                    session,
                    submission_id=graded.submission_id,
                    scores=FULL,
                )


class TestApprovalGates:
    def test_approving_a_running_evaluation_raises(
        self, db_factory, world, graded
    ) -> None:
        sheet = _save(db_factory, world, graded)

        with session_scope(db_factory) as session:
            evaluation = session.get(Evaluation, sheet.evaluation_id)
            evaluation.status = EvaluationStatus.RUNNING

        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError) as excinfo:
                approve_sheet(world.faculty_a, session, score_sheet_id=sheet.id)

        assert "COMPLETE" in str(excinfo.value)

    def test_an_unresolved_mandatory_criterion_blocks_approval(
        self, db_factory, world, graded
    ) -> None:
        sheet = _save(
            db_factory,
            world,
            graded,
            {"C1": (0, Verdict.NO_EVIDENCE), "C2": (10, Verdict.FOLLOWED)},
        )

        assert sheet.unresolved_mandatory == ("C1",)
        assert approval_blockers(sheet)

        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError) as excinfo:
                approve_sheet(world.faculty_a, session, score_sheet_id=sheet.id)

        assert "C1" in str(excinfo.value)

    def test_a_non_mandatory_criterion_at_no_evidence_does_not_block(
        self, db_factory, world, graded
    ) -> None:
        sheet = _save(
            db_factory,
            world,
            graded,
            {"C1": (10, Verdict.FOLLOWED), "C2": (0, Verdict.NO_EVIDENCE)},
        )

        assert approval_blockers(sheet) == ()

        with session_scope(db_factory) as session:
            approved = approve_sheet(world.faculty_a, session, score_sheet_id=sheet.id)

        assert approved.is_approved

    def test_approval_stamps_who_and_when(self, db_factory, world, graded) -> None:
        """Without both, invariant #1 is unprovable."""
        sheet = _save(db_factory, world, graded)

        with session_scope(db_factory) as session:
            approved = approve_sheet(
                world.faculty_a,
                session,
                score_sheet_id=sheet.id,
                faculty_note="Good work.",
            )

        assert approved.approved_by == world.faculty_a.email
        assert approved.approved_at is not None
        assert approved.faculty_note == "Good work."

    def test_approval_writes_an_audit_row(self, db_factory, world, graded) -> None:
        sheet = _save(db_factory, world, graded)

        with session_scope(db_factory) as session:
            approve_sheet(world.faculty_a, session, score_sheet_id=sheet.id)

        with session_scope(db_factory) as session:
            actions = session.scalars(
                select(AuditLog.action).where(AuditLog.action.like("score.%"))
            ).all()

        assert "score.approved" in actions

    def test_a_student_cannot_approve(self, db_factory, world, graded) -> None:
        sheet = _save(db_factory, world, graded)

        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                approve_sheet(world.student_1, session, score_sheet_id=sheet.id)

    def test_re_approving_refuses_and_leaves_the_first_untouched(
        self, db_factory, world, graded
    ) -> None:
        sheet = _save(db_factory, world, graded)

        with session_scope(db_factory) as session:
            first = approve_sheet(world.faculty_a, session, score_sheet_id=sheet.id)

        # The owner, not a colleague — a colleague would be refused earlier,
        # by scoping, and would not exercise the re-approval guard at all.
        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError):
                approve_sheet(world.faculty_a, session, score_sheet_id=sheet.id)

        with session_scope(db_factory) as session:
            after = get_sheet(world.faculty_a, session, sheet.id)

        assert after.approved_by == first.approved_by
        assert after.approved_at == first.approved_at

    def test_scoring_an_approved_sheet_is_refused(
        self, db_factory, world, graded
    ) -> None:
        """A change after approval must go through an override, with a reason."""
        sheet = _save(db_factory, world, graded)

        with session_scope(db_factory) as session:
            approve_sheet(world.faculty_a, session, score_sheet_id=sheet.id)

        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError) as excinfo:
                save_manual_scores(
                    world.faculty_a,
                    session,
                    submission_id=graded.submission_id,
                    scores=PARTIAL,
                )

        assert "override" in str(excinfo.value).lower()


class TestOverrides:
    def test_an_empty_reason_is_refused_in_core(self, db_factory, world, graded) -> None:
        """Not merely marked required on the widget."""
        sheet = _save(db_factory, world, graded)

        for bad in ("", "   ", "\n\t"):
            with session_scope(db_factory) as session:
                with pytest.raises(ValidationError):
                    override_criterion(
                        world.faculty_a,
                        session,
                        score_sheet_id=sheet.id,
                        criterion_code="C1",
                        new_score=8,
                        reason=bad,
                    )

    def test_the_stored_total_equals_a_fresh_recompute(
        self, db_factory, world, graded
    ) -> None:
        """Fix item 4's exact proof."""
        sheet = _save(db_factory, world, graded)

        with session_scope(db_factory) as session:
            after = override_criterion(
                world.faculty_a,
                session,
                score_sheet_id=sheet.id,
                criterion_code="C1",
                new_score=5,
                reason="Objectives were not measurable.",
            )

        # 0.5*60 + 1.0*40 = 70 percent of 25 = 17.50
        assert after.final_total == Decimal("17.50")

        with session_scope(db_factory) as session:
            stored = session.get(ScoreSheet, sheet.id)
            reread = get_sheet(world.faculty_a, session, sheet.id)

        assert stored.final_total == reread.final_total == Decimal("17.50")

    def test_an_override_is_append_only(self, db_factory, world, graded) -> None:
        sheet = _save(db_factory, world, graded)

        for score, reason in ((8, "First correction."), (6, "Second look.")):
            with session_scope(db_factory) as session:
                override_criterion(
                    world.faculty_a,
                    session,
                    score_sheet_id=sheet.id,
                    criterion_code="C1",
                    new_score=score,
                    reason=reason,
                )

        with session_scope(db_factory) as session:
            rows = session.scalars(
                select(ScoreOverride).where(ScoreOverride.score_sheet_id == sheet.id)
            ).all()

        assert len(rows) == 2, "each correction is its own row"
        assert {r.reason for r in rows} == {"First correction.", "Second look."}
        assert [r.old_score for r in rows] == [Decimal("10.00"), Decimal("8.00")]

    def test_an_override_clears_the_approval(self, db_factory, world, graded) -> None:
        """A total that moved must be re-owned by a person (invariant #1)."""
        sheet = _save(db_factory, world, graded)

        with session_scope(db_factory) as session:
            approve_sheet(world.faculty_a, session, score_sheet_id=sheet.id)

        with session_scope(db_factory) as session:
            after = override_criterion(
                world.faculty_a,
                session,
                score_sheet_id=sheet.id,
                criterion_code="C1",
                new_score=7,
                reason="Re-read the objectives section.",
            )

        assert after.is_approved is False
        assert after.approved_by is None

    def test_approve_override_approve_leaves_two_audit_rows(
        self, db_factory, world, graded
    ) -> None:
        sheet = _save(db_factory, world, graded)

        with session_scope(db_factory) as session:
            approve_sheet(world.faculty_a, session, score_sheet_id=sheet.id)
        with session_scope(db_factory) as session:
            override_criterion(
                world.faculty_a,
                session,
                score_sheet_id=sheet.id,
                criterion_code="C1",
                new_score=9,
                reason="Rounded up after discussion.",
            )
        with session_scope(db_factory) as session:
            approve_sheet(world.faculty_a, session, score_sheet_id=sheet.id)

        with session_scope(db_factory) as session:
            approvals = session.scalars(
                select(AuditLog).where(AuditLog.action == "score.approved")
            ).all()
            history = override_history(world.faculty_a, session, sheet.id)

        assert len(approvals) == 2
        assert len(history) == 1
        assert history[0]["reason"] == "Rounded up after discussion."

    def test_the_provenance_chip_flips_to_overridden(
        self, db_factory, world, graded
    ) -> None:
        """Fix item 8: a hand-corrected mark is never mistaken for a model output."""
        sheet = _save(db_factory, world, graded)
        assert sheet.provenance == "MANUAL"

        with session_scope(db_factory) as session:
            after = override_criterion(
                world.faculty_a,
                session,
                score_sheet_id=sheet.id,
                criterion_code="C2",
                new_score=6,
                reason="Requirements were not numbered.",
            )

        assert after.provenance == "OVERRIDDEN"


class TestReinstatement:
    def test_reinstating_zeroes_the_penalty_and_needs_a_reason(
        self, db_factory, world, graded
    ) -> None:
        sheet = _save(db_factory, world, graded)

        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError):
                reinstate(world.faculty_a, session, score_sheet_id=sheet.id, reason="  ")

        with session_scope(db_factory) as session:
            after = reinstate(
                world.faculty_a,
                session,
                score_sheet_id=sheet.id,
                reason="Medical certificate produced.",
            )

        assert after.reinstated is True
        assert after.penalty == Decimal("0.00")
        assert after.attendance_status is AttendanceStatus.REINSTATED
        assert after.reinstate_reason == "Medical certificate produced."


class TestScoping:
    def test_a_student_sees_their_own_sheet(self, db_factory, world, graded) -> None:
        sheet = _save(db_factory, world, graded)

        with session_scope(db_factory) as session:
            mine = get_sheet(world.student_1, session, sheet.id)

        assert mine.id == sheet.id

    def test_a_student_cannot_see_another_students_sheet(
        self, db_factory, world, graded
    ) -> None:
        sheet = _save(db_factory, world, graded)

        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                get_sheet(world.student_2, session, sheet.id)

    def test_sheet_for_submission_returns_none_before_scoring(
        self, db_factory, world, graded
    ) -> None:
        with session_scope(db_factory) as session:
            assert (
                sheet_for_submission(world.faculty_a, session, graded.submission_id)
                is None
            )

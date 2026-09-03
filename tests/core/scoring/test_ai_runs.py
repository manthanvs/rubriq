"""Persisting AI evaluations — invariants #1 and #2, and fix item 9.

The three things that matter here:

* the totals on a persisted AI sheet come from the engine, not from the model;
* the sheet lands **unapproved**, because the AI never publishes a final mark;
* a retry increments the evaluation version, which is what gives it a new
  thread and a clean start rather than the poisoned checkpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest
from sqlalchemy import select

from core.db.engine import session_scope
from core.db.models import CriterionScore, Evaluation
from core.errors import NotAuthorized, ValidationError
from core.scoring.ai_runs import (
    finish_ai_evaluation,
    mark_evaluation_failed,
    next_evaluation_version,
    start_ai_evaluation,
)
from core.scoring.enums import EvaluationEngine, EvaluationStatus, Verdict
from core.scoring.sheets import approval_blockers, approve_sheet


@dataclass
class FakeCriterion:
    code: str
    verdict: Verdict
    score: Decimal
    confidence: float = 0.9
    evidence: str = "Objectives, scope and requirements."
    rationale: str = "Stated in the document."


@dataclass
class FakeResult:
    """Stands in for core.ai.provider.EvaluationResult."""

    criteria: tuple
    rejections: tuple = ()
    model_name: str = "gemini-2.0-flash"
    prompt_version: str = "eval-v1"
    graph_version: str = "eval-graph-v1"
    raw_response: str = '{"criteria": []}'
    failed: bool = False
    failure_reason: str = ""

    @property
    def rejection_rate(self) -> float:
        return len(self.rejections) / len(self.criteria) if self.criteria else 0.0


def full_result() -> FakeResult:
    return FakeResult(
        criteria=(
            FakeCriterion("C1", Verdict.FOLLOWED, Decimal("9")),
            FakeCriterion("C2", Verdict.PARTIAL, Decimal("6")),
        )
    )


class TestPersisting:
    def test_totals_come_from_the_engine_not_the_model(
        self, db_factory, world, graded
    ) -> None:
        """Invariant #2: the LLM never does arithmetic that decides marks."""
        with session_scope(db_factory) as session:
            evaluation = start_ai_evaluation(
                world.faculty_a, session, submission_id=graded.submission_id
            )
            evaluation_id = evaluation.id

        with session_scope(db_factory) as session:
            sheet = finish_ai_evaluation(
                world.faculty_a,
                session,
                evaluation_id=evaluation_id,
                result=full_result(),
            )

        # C1 9/10 at weight 60, C2 6/10 at weight 40 = 54 + 24 = 78 percent
        # of a 25-mark milestone = 19.50, submitted on time.
        assert sheet.weighted_percent == Decimal("78.00")
        assert sheet.final_total == Decimal("19.50")

    def test_the_sheet_lands_unapproved(self, db_factory, world, graded) -> None:
        """Invariant #1: the AI produces an estimate, never a final mark."""
        with session_scope(db_factory) as session:
            evaluation_id = start_ai_evaluation(
                world.faculty_a, session, submission_id=graded.submission_id
            ).id

        with session_scope(db_factory) as session:
            sheet = finish_ai_evaluation(
                world.faculty_a,
                session,
                evaluation_id=evaluation_id,
                result=full_result(),
            )

        assert sheet.is_approved is False
        assert sheet.approved_by is None
        assert sheet.engine is EvaluationEngine.AI
        assert sheet.provenance == "AI"

    def test_the_evidence_span_is_stored_untouched(
        self, db_factory, world, graded
    ) -> None:
        """Fix item 5: what is stored is the model's original span."""
        span = "Objectives,   scope\nand requirements."

        with session_scope(db_factory) as session:
            evaluation_id = start_ai_evaluation(
                world.faculty_a, session, submission_id=graded.submission_id
            ).id

        with session_scope(db_factory) as session:
            finish_ai_evaluation(
                world.faculty_a,
                session,
                evaluation_id=evaluation_id,
                result=FakeResult(
                    criteria=(
                        FakeCriterion(
                            "C1", Verdict.FOLLOWED, Decimal("9"), evidence=span
                        ),
                        FakeCriterion("C2", Verdict.PARTIAL, Decimal("6")),
                    )
                ),
            )

        with session_scope(db_factory) as session:
            stored = session.scalars(
                select(CriterionScore.evidence_span).where(
                    CriterionScore.evaluation_id == evaluation_id
                )
            ).all()

        assert span in stored

    def test_a_criterion_the_model_skipped_becomes_no_evidence(
        self, db_factory, world, graded
    ) -> None:
        """Otherwise the weights would not sum and the engine would refuse."""
        with session_scope(db_factory) as session:
            evaluation_id = start_ai_evaluation(
                world.faculty_a, session, submission_id=graded.submission_id
            ).id

        with session_scope(db_factory) as session:
            sheet = finish_ai_evaluation(
                world.faculty_a,
                session,
                evaluation_id=evaluation_id,
                result=FakeResult(
                    criteria=(FakeCriterion("C1", Verdict.FOLLOWED, Decimal("10")),)
                ),
            )

        by_code = {c.code: c for c in sheet.criteria}
        assert by_code["C2"].verdict is Verdict.NO_EVIDENCE
        assert by_code["C2"].score == 0
        assert sheet.final_total == Decimal("15.00")  # 60% of 25

    def test_the_evaluation_pins_its_inputs(self, db_factory, world, graded) -> None:
        """Fix item 2: submission_version and rubric_version, both recorded."""
        with session_scope(db_factory) as session:
            evaluation = start_ai_evaluation(
                world.faculty_a, session, submission_id=graded.submission_id
            )

            assert evaluation.submission_version >= 1
            assert evaluation.rubric_version >= 1
            assert evaluation.rubric_id == graded.rubric_id

    def test_the_run_is_stamped_for_reproducibility(
        self, db_factory, world, graded
    ) -> None:
        with session_scope(db_factory) as session:
            evaluation_id = start_ai_evaluation(
                world.faculty_a, session, submission_id=graded.submission_id
            ).id

        with session_scope(db_factory) as session:
            finish_ai_evaluation(
                world.faculty_a,
                session,
                evaluation_id=evaluation_id,
                result=full_result(),
            )

        with session_scope(db_factory) as session:
            evaluation = session.get(Evaluation, evaluation_id)

        assert evaluation.prompt_version == "eval-v1"
        assert evaluation.graph_version == "eval-graph-v1"
        assert evaluation.model_name == "gemini-2.0-flash"
        assert evaluation.raw_response  # §6.5, stored verbatim


class TestFailureIsVisible:
    def test_a_run_starts_as_running_not_absent(self, db_factory, world, graded) -> None:
        """A row that does not exist cannot be shown as FAILED."""
        with session_scope(db_factory) as session:
            evaluation = start_ai_evaluation(
                world.faculty_a, session, submission_id=graded.submission_id
            )

            assert evaluation.status is EvaluationStatus.RUNNING

    def test_a_failed_result_writes_no_sheet(self, db_factory, world, graded) -> None:
        """Fix item 9: inventing zeroes is how a failure gets approved."""
        with session_scope(db_factory) as session:
            evaluation_id = start_ai_evaluation(
                world.faculty_a, session, submission_id=graded.submission_id
            ).id

        with pytest.raises(ValidationError, match="FAILED"):
            with session_scope(db_factory) as session:
                finish_ai_evaluation(
                    world.faculty_a,
                    session,
                    evaluation_id=evaluation_id,
                    result=FakeResult(
                        criteria=(),
                        failed=True,
                        failure_reason="provider timed out",
                    ),
                )

    def test_marking_failed_records_the_reason(self, db_factory, world, graded) -> None:
        with session_scope(db_factory) as session:
            evaluation_id = start_ai_evaluation(
                world.faculty_a, session, submission_id=graded.submission_id
            ).id

        with session_scope(db_factory) as session:
            mark_evaluation_failed(
                world.faculty_a,
                session,
                evaluation_id=evaluation_id,
                reason="429 rate limited",
            )

        with session_scope(db_factory) as session:
            evaluation = session.get(Evaluation, evaluation_id)

        assert evaluation.status is EvaluationStatus.FAILED
        assert "429" in evaluation.failure_reason

    def test_a_failed_evaluation_cannot_be_approved(
        self, db_factory, world, graded
    ) -> None:
        """Approval is blocked on anything but COMPLETE (fix item 4)."""
        with session_scope(db_factory) as session:
            evaluation_id = start_ai_evaluation(
                world.faculty_a, session, submission_id=graded.submission_id
            ).id

        with session_scope(db_factory) as session:
            sheet = finish_ai_evaluation(
                world.faculty_a,
                session,
                evaluation_id=evaluation_id,
                result=full_result(),
            )

        with session_scope(db_factory) as session:
            session.get(Evaluation, evaluation_id).status = EvaluationStatus.FAILED

        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError, match="COMPLETE"):
                approve_sheet(world.faculty_a, session, score_sheet_id=sheet.id)


class TestRetry:
    def test_a_retry_increments_the_evaluation_version(
        self, db_factory, world, graded
    ) -> None:
        """Which produces a new thread_id, and therefore a clean start."""
        with session_scope(db_factory) as session:
            first = start_ai_evaluation(
                world.faculty_a, session, submission_id=graded.submission_id
            ).version

        with session_scope(db_factory) as session:
            second = start_ai_evaluation(
                world.faculty_a, session, submission_id=graded.submission_id
            ).version

        assert (first, second) == (1, 2)

    def test_next_version_accounts_for_manual_evaluations_too(
        self, db_factory, world, graded
    ) -> None:
        """Versions are per submission, not per engine."""
        from core.scoring.sheets import save_manual_scores

        with session_scope(db_factory) as session:
            save_manual_scores(
                world.faculty_a,
                session,
                submission_id=graded.submission_id,
                scores={"C1": (8, Verdict.FOLLOWED), "C2": (7, Verdict.FOLLOWED)},
            )

        with session_scope(db_factory) as session:
            assert next_evaluation_version(session, graded.submission_id) == 2


class TestScoping:
    def test_a_student_cannot_start_an_ai_run(self, db_factory, world, graded) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                start_ai_evaluation(
                    world.student_1, session, submission_id=graded.submission_id
                )

    def test_another_faculty_cannot_run_on_your_students(
        self, db_factory, world, graded
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                start_ai_evaluation(
                    world.faculty_b, session, submission_id=graded.submission_id
                )

    def test_a_milestone_without_a_published_rubric_is_refused(
        self, db_factory, world, tmp_path
    ) -> None:
        from core.submissions.service import submit

        with session_scope(db_factory) as session:
            submission = submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files={"a.txt": b"Some text that is long enough to matter."},
                # tmp_path, not a repo-relative path: a test that writes into
                # the working tree leaves files for git to find.
                uploads_root=tmp_path / "uploads",
            )

        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError, match="no published rubric"):
                start_ai_evaluation(world.faculty_a, session, submission_id=submission.id)


class TestApprovalStillGates:
    def test_an_unevidenced_mandatory_criterion_blocks_approval(
        self, db_factory, world, graded
    ) -> None:
        """The AI demoting C1 must stop the sheet being waved through."""
        with session_scope(db_factory) as session:
            evaluation_id = start_ai_evaluation(
                world.faculty_a, session, submission_id=graded.submission_id
            ).id

        with session_scope(db_factory) as session:
            sheet = finish_ai_evaluation(
                world.faculty_a,
                session,
                evaluation_id=evaluation_id,
                result=FakeResult(
                    criteria=(
                        FakeCriterion(
                            "C1", Verdict.NO_EVIDENCE, Decimal("0"), evidence=""
                        ),
                        FakeCriterion("C2", Verdict.FOLLOWED, Decimal("9")),
                    )
                ),
            )

        assert sheet.unresolved_mandatory == ("C1",)
        assert approval_blockers(sheet)

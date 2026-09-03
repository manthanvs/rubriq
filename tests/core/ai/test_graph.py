"""The evaluation graph — §6.3, and fix item 9.

The Phase 5b exit criterion is *"refresh the browser mid-run and confirm the
resumed run makes **no duplicate LLM calls**"*. :class:`TestResumeAndRetry` is
that, counted rather than assumed: the provider tallies every call, the run is
interrupted, and the tally is checked after resuming.

That class also holds the distinction fix item 9 warns against collapsing — a
refresh resumes the same thread, a retry starts a new one.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from core.ai.checkpoint import thread_id
from core.ai.provider import stream_evaluation
from core.ai.schemas import AIResponseError
from core.rubrics.dto import CriterionDTO, RubricDTO
from core.scoring.enums import Verdict

SUBMISSION = """\
Mini Project Synopsis

1. Problem statement
Faculty mark project reviews against a rubric students never see beforehand.
Marks vary between reviewers.

2. Objectives
Publish a rubric per milestone before submission opens.
Produce an evidence-backed estimated score sheet that faculty approve.

3. Scope
Out of scope: plagiarism detection, executing student code.
"""


def rubric(count: int = 2) -> RubricDTO:
    return RubricDTO(
        id=1,
        milestone_id=1,
        version=1,
        published_at=None,
        published_by=None,
        criteria=tuple(
            CriterionDTO(
                id=index,
                code=f"C{index}",
                title=f"Criterion {index}",
                description=None,
                weight=Decimal("100") / count,
                max_score=Decimal("10"),
                expected_evidence="Something specific.",
                is_mandatory=index == 1,
                order_index=index,
            )
            for index in range(1, count + 1)
        ),
    )


def good_json(codes: list[str], evidence: str = "Marks vary between reviewers") -> str:
    return json.dumps(
        {
            "criteria": [
                {
                    "code": code,
                    "verdict": "FOLLOWED",
                    "score": 8,
                    "max_score": 10,
                    "confidence": 0.9,
                    "evidence": evidence,
                    "rationale": "Stated in the document.",
                }
                for code in codes
            ],
            "overall_observations": ["Reads well."],
            "missing_items": [],
        }
    )


class CountingProvider:
    """Returns scripted responses and tallies how many times it was called."""

    name = "counting"
    model = "counting-1"

    def __init__(self, responses: list[str], *, fail_after: int | None = None) -> None:
        self._responses = list(responses)
        self._fail_after = fail_after
        self.calls = 0
        self.prompts: list[str] = []

    def complete(self, *, system: str, user: str) -> str:
        self.calls += 1
        self.prompts.append(user)

        if self._fail_after is not None and self.calls > self._fail_after:
            raise TimeoutError("provider went away")

        if not self._responses:
            raise AssertionError("provider called more times than scripted")
        return self._responses.pop(0)


def run(provider, *, version: int = 1, path, criteria: int = 2, submission_id: int = 1):
    """Drive the generator to completion and return (nodes, result)."""
    nodes: list[str] = []
    result = None

    for node, payload in stream_evaluation(
        rubric(criteria),
        SUBMISSION,
        provider=provider,
        submission_id=submission_id,
        evaluation_version=version,
        checkpoint_path=path,
    ):
        nodes.append(node)
        if payload is not None:
            result = payload

    return nodes, result


@pytest.fixture
def checkpoint(tmp_path):
    return tmp_path / "ai_checkpoints.db"


class TestHappyPath:
    def test_the_graph_walks_the_expected_nodes(self, checkpoint) -> None:
        provider = CountingProvider([good_json(["C1", "C2"])])
        nodes, result = run(provider, path=checkpoint)

        assert nodes[:2] == ["prepare", "evaluate"]
        assert "parse_schema" in nodes
        assert "verify_evidence" in nodes
        assert "aggregate" in nodes
        assert nodes[-1] == "done"
        assert result is not None
        assert not result.failed

    def test_every_criterion_comes_back(self, checkpoint) -> None:
        provider = CountingProvider([good_json(["C1", "C2"])])
        _nodes, result = run(provider, path=checkpoint)

        assert {c.code for c in result.criteria} == {"C1", "C2"}
        assert all(c.verdict is Verdict.FOLLOWED for c in result.criteria)

    def test_criteria_are_batched(self, checkpoint) -> None:
        """Decision #4b: batched, so six criteria are not six calls."""
        provider = CountingProvider(
            [good_json(["C1", "C2", "C3", "C4"]), good_json(["C5", "C6"])]
        )
        _nodes, result = run(provider, path=checkpoint, criteria=6)

        assert provider.calls == 2, "batch size 4 means two calls for six criteria"
        assert len(result.criteria) == 6

    def test_the_result_is_stamped_with_the_graph_version(self, checkpoint) -> None:
        provider = CountingProvider([good_json(["C1", "C2"])])
        _nodes, result = run(provider, path=checkpoint)

        assert result.graph_version == "eval-graph-v1"
        assert result.prompt_version == "eval-v1"

    def test_aggregate_computes_no_totals(self, checkpoint) -> None:
        """Invariant #2: a graph node must never decide a mark.

        The result carries per-criterion scores and nothing that looks like a
        total; core/scoring/engine.py does that from the persisted rows.
        """
        provider = CountingProvider([good_json(["C1", "C2"])])
        _nodes, result = run(provider, path=checkpoint)

        for attribute in ("base_total", "final_total", "penalty", "weighted_percent"):
            assert not hasattr(result, attribute), (
                f"the graph produced {attribute}; totals belong to core/scoring"
            )


class TestEvidenceGuardRunsInsideTheGraph:
    def test_a_fabricated_span_is_demoted(self, checkpoint) -> None:
        provider = CountingProvider(
            [good_json(["C1", "C2"], evidence="Deployed on a Kubernetes cluster.")]
        )
        _nodes, result = run(provider, path=checkpoint)

        assert all(c.verdict is Verdict.NO_EVIDENCE for c in result.criteria)
        assert all(c.score == 0 for c in result.criteria)
        assert len(result.rejections) == 2

    def test_rejections_are_reportable(self, checkpoint) -> None:
        provider = CountingProvider(
            [good_json(["C1", "C2"], evidence="Written in Rust for memory safety.")]
        )
        _nodes, result = run(provider, path=checkpoint)

        assert result.rejection_rate == 1.0
        assert all("Rust" in r.span for r in result.rejections)


class TestRepairLoop:
    def test_one_bad_response_is_repaired(self, checkpoint) -> None:
        provider = CountingProvider(["I cannot help with that.", good_json(["C1", "C2"])])
        nodes, result = run(provider, path=checkpoint)

        assert "repair" in nodes
        assert provider.calls == 2
        assert not result.failed
        assert {c.code for c in result.criteria} == {"C1", "C2"}

    def test_the_repair_prompt_quotes_the_validation_error(self, checkpoint) -> None:
        """So the model is told what was wrong, not merely asked again."""
        provider = CountingProvider(["not json at all", good_json(["C1", "C2"])])
        run(provider, path=checkpoint)

        assert "previous response was rejected" in provider.prompts[1]
        assert "not valid JSON" in provider.prompts[1]

    def test_repair_is_capped_at_one_attempt(self, checkpoint) -> None:
        """§6.3: on the second failure the batch resolves, it does not loop."""
        provider = CountingProvider(["still not json", "and still not json"])
        nodes, result = run(provider, path=checkpoint)

        assert provider.calls == 2, "one evaluate plus one repair, then stop"
        assert nodes.count("repair") == 1
        assert "demote_criterion" in nodes

    def test_an_unrepairable_batch_becomes_no_evidence_not_a_failure(
        self, checkpoint
    ) -> None:
        """One bad batch never fails the whole submission."""
        provider = CountingProvider(["bad", "still bad"])
        _nodes, result = run(provider, path=checkpoint)

        assert not result.failed
        assert len(result.criteria) == 2
        assert all(c.verdict is Verdict.NO_EVIDENCE for c in result.criteria)
        assert all(c.score == 0 for c in result.criteria)
        assert len(result.rejections) == 2

    def test_a_later_batch_gets_a_fresh_repair_allowance(self, checkpoint) -> None:
        """repair_attempts resets per batch, not per run."""
        provider = CountingProvider(
            [
                "bad",  # batch 1 evaluate
                good_json(["C1", "C2", "C3", "C4"]),  # batch 1 repair, succeeds
                "bad",  # batch 2 evaluate
                good_json(["C5", "C6"]),  # batch 2 repair, succeeds
            ]
        )
        _nodes, result = run(provider, path=checkpoint, criteria=6)

        assert provider.calls == 4
        assert len(result.criteria) == 6


class TestProviderFailure:
    def test_a_dead_provider_marks_the_run_failed(self, checkpoint) -> None:
        """Fix item 9: FAILED is surfaced, not swallowed as a silent zero."""
        provider = CountingProvider([], fail_after=0)
        _nodes, result = run(provider, path=checkpoint)

        assert result.failed
        assert "provider went away" in result.failure_reason

    def test_a_dead_provider_is_not_repaired_against(self, checkpoint) -> None:
        """Repairing would just call the same broken provider again."""
        provider = CountingProvider([], fail_after=0)
        nodes, _result = run(provider, path=checkpoint)

        assert "repair" not in nodes


class TestResumeAndRetry:
    """The Phase 5b exit criterion, and fix item 9's central distinction."""

    def test_resuming_the_same_thread_makes_no_duplicate_calls(self, checkpoint) -> None:
        """The exit criterion, counted.

        Six criteria means two batches. The first run is abandoned after the
        first batch — standing in for a browser refresh mid-run. Re-entering
        with the same evaluation_version must resume from the checkpoint and
        call the provider only for the batch that never completed.
        """
        first = CountingProvider(
            [good_json(["C1", "C2", "C3", "C4"]), good_json(["C5", "C6"])]
        )

        # Abandon the generator partway, as a rerun would.
        stream = stream_evaluation(
            rubric(6),
            SUBMISSION,
            provider=first,
            submission_id=1,
            evaluation_version=1,
            checkpoint_path=checkpoint,
        )
        for node, _payload in stream:
            if node == "aggregate":
                break
        stream.close()

        calls_before = first.calls
        assert calls_before == 1, "only the first batch should have been sent"

        # Re-enter with the SAME version — a refresh, not a retry.
        second = CountingProvider([good_json(["C5", "C6"])])
        _nodes, result = run(second, version=1, path=checkpoint, criteria=6)

        assert second.calls == 1, (
            "the resumed run re-sent a completed batch — the checkpoint was "
            "not used, which is exactly what the exit criterion forbids"
        )
        assert len(result.criteria) == 6, "the resumed run still produced everything"

    def test_a_retry_uses_a_new_thread_and_starts_clean(self, checkpoint) -> None:
        """Fix item 9: a genuine retry must not resume a poisoned checkpoint."""
        first = CountingProvider(["bad", "still bad"])
        _nodes, failed = run(first, version=1, path=checkpoint)

        assert all(c.verdict is Verdict.NO_EVIDENCE for c in failed.criteria)

        # Retry increments the version, so the thread id differs.
        second = CountingProvider([good_json(["C1", "C2"])])
        _nodes, retried = run(second, version=2, path=checkpoint)

        assert second.calls == 1, "a retry must start fresh, not replay"
        assert all(c.verdict is Verdict.FOLLOWED for c in retried.criteria)

    def test_the_thread_id_scheme_is_deterministic(self) -> None:
        """§6.3: so a resumed run is provably the same run."""
        assert thread_id(7, 2) == "eval:7:2"
        assert thread_id(7, 2) == thread_id(7, 2)
        assert thread_id(7, 2) != thread_id(7, 3)

    def test_different_submissions_never_share_a_thread(self, checkpoint) -> None:
        first = CountingProvider([good_json(["C1", "C2"])])
        run(first, path=checkpoint, submission_id=1)

        second = CountingProvider([good_json(["C1", "C2"])])
        _nodes, result = run(second, path=checkpoint, submission_id=2)

        assert second.calls == 1, "submission 2 must not resume submission 1"
        assert len(result.criteria) == 2


class TestGuards:
    def test_an_empty_rubric_is_refused_before_any_call(self, checkpoint) -> None:
        provider = CountingProvider([])
        empty = RubricDTO(
            id=1,
            milestone_id=1,
            version=1,
            published_at=None,
            published_by=None,
            criteria=(),
        )

        with pytest.raises(AIResponseError):
            list(
                stream_evaluation(
                    empty,
                    SUBMISSION,
                    provider=provider,
                    submission_id=1,
                    evaluation_version=1,
                    checkpoint_path=checkpoint,
                )
            )

        assert provider.calls == 0

    def test_identity_is_stripped_before_the_first_call(self, checkpoint) -> None:
        """Invariant #8, enforced by the prepare node."""
        provider = CountingProvider([good_json(["C1", "C2"])])

        list(
            stream_evaluation(
                rubric(2),
                "Submitted by Manthan Sankpal, PRN 125M1H064.\n" + SUBMISSION,
                provider=provider,
                submission_id=1,
                evaluation_version=1,
                student_name="Manthan Sankpal",
                student_prn="125M1H064",
                checkpoint_path=checkpoint,
            )
        )

        sent = provider.prompts[0]
        assert "Manthan" not in sent
        assert "125M1H064" not in sent

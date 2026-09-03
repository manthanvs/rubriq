"""The response contract — §6.5.

The rule this file mostly exists for: **``NO_EVIDENCE`` forces score 0, and it
is a Pydantic validator.** Fix item 5 names the failure as the rule being
"enforced in the UI and skipped in a batch run", so it is tested at the schema
level where no caller can route around it.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from core.ai.schemas import (
    MAX_EVIDENCE_WORDS,
    AIResponseError,
    CriterionResult,
    EvaluationResponse,
    parse_response,
    strip_fences,
)
from core.scoring.enums import Verdict


def payload(**overrides) -> dict:
    base = {
        "code": "c1",
        "verdict": "FOLLOWED",
        "score": 8,
        "max_score": 10,
        "confidence": 0.9,
        "evidence": "Marks vary between reviewers and students cannot tell.",
        "rationale": "Clearly stated in the problem statement.",
    }
    base.update(overrides)
    return base


def response_json(**overrides) -> str:
    return json.dumps({"criteria": [payload(**overrides)]})


class TestNoEvidenceForcesZero:
    def test_a_nonzero_score_with_no_evidence_verdict_is_refused(self) -> None:
        with pytest.raises(ValueError, match="NO_EVIDENCE must score 0"):
            CriterionResult.model_validate(
                payload(verdict="NO_EVIDENCE", score=7, evidence="")
            )

    def test_it_is_refused_through_the_json_path_too(self) -> None:
        """The batch path, which is where the UI check would be skipped."""
        with pytest.raises(AIResponseError) as excinfo:
            parse_response(response_json(verdict="NO_EVIDENCE", score=5, evidence=""))

        assert "NO_EVIDENCE" in str(excinfo.value)

    def test_no_evidence_at_zero_is_accepted(self) -> None:
        result = CriterionResult.model_validate(
            payload(verdict="NO_EVIDENCE", score=0, evidence="")
        )

        assert result.verdict is Verdict.NO_EVIDENCE
        assert result.score == 0


class TestEveryScoreCitesSomething:
    def test_a_score_without_a_span_is_refused(self) -> None:
        """Invariant #3: no span means NO_EVIDENCE, not a number."""
        with pytest.raises(ValueError, match="cited no evidence"):
            CriterionResult.model_validate(payload(score=6, evidence="   "))

    def test_a_zero_score_may_omit_the_span(self) -> None:
        result = CriterionResult.model_validate(
            payload(score=0, verdict="NOT_FOLLOWED", evidence="")
        )

        assert result.score == 0


class TestBounds:
    def test_a_score_above_its_maximum_is_refused(self) -> None:
        with pytest.raises(ValueError, match="outside"):
            CriterionResult.model_validate(payload(score=11, max_score=10))

    def test_a_negative_score_is_refused(self) -> None:
        with pytest.raises(ValueError):
            CriterionResult.model_validate(payload(score=-1))

    def test_confidence_outside_zero_to_one_is_refused(self) -> None:
        with pytest.raises(ValueError):
            CriterionResult.model_validate(payload(confidence=1.4))

    def test_a_zero_maximum_is_refused(self) -> None:
        with pytest.raises(ValueError):
            CriterionResult.model_validate(payload(max_score=0, score=0))

    def test_an_over_long_span_is_truncated_not_rejected(self) -> None:
        """One long quote should not fail a whole batch."""
        long_span = " ".join(f"word{i}" for i in range(MAX_EVIDENCE_WORDS + 25))
        result = CriterionResult.model_validate(payload(evidence=long_span))

        assert len(result.evidence.split()) == MAX_EVIDENCE_WORDS


class TestParsing:
    def test_a_code_fence_is_stripped(self) -> None:
        """The prompt forbids fences; models add them anyway."""
        fenced = "```json\n" + response_json() + "\n```"

        assert parse_response(fenced).criteria[0].code == "C1"

    def test_a_bare_fence_is_stripped(self) -> None:
        assert strip_fences("```\n{}\n```") == "{}"

    def test_the_code_is_upper_cased(self) -> None:
        assert parse_response(response_json(code="c3")).criteria[0].code == "C3"

    def test_unknown_extra_keys_are_ignored(self) -> None:
        """A model that adds a field should not fail the run."""
        raw = json.dumps({"criteria": [payload(reasoning_tokens=812)], "cost_usd": 0.004})

        assert parse_response(raw).criteria[0].score == Decimal("8")

    def test_empty_output_is_reported_clearly(self) -> None:
        with pytest.raises(AIResponseError, match="empty"):
            parse_response("   ")

    def test_prose_instead_of_json_is_reported_clearly(self) -> None:
        with pytest.raises(AIResponseError, match="not valid JSON"):
            parse_response("Certainly! Here is my assessment of the submission.")

    def test_a_json_array_is_refused(self) -> None:
        with pytest.raises(AIResponseError, match="Expected a JSON object"):
            parse_response("[1, 2, 3]")

    def test_an_empty_criteria_list_is_refused(self) -> None:
        with pytest.raises(AIResponseError):
            parse_response(json.dumps({"criteria": []}))

    def test_duplicate_codes_are_refused(self) -> None:
        """Two answers for one criterion leaves "which is the mark" undefined."""
        raw = json.dumps({"criteria": [payload(), payload()]})

        with pytest.raises(AIResponseError, match="Duplicate"):
            parse_response(raw)

    def test_the_validation_message_names_the_problem(self) -> None:
        """It becomes the repair prompt in Phase 5b, so it must be specific."""
        with pytest.raises(AIResponseError) as excinfo:
            parse_response(response_json(verdict="MAYBE"))

        assert "verdict" in str(excinfo.value)


class TestShape:
    def test_observations_and_missing_items_default_to_empty(self) -> None:
        parsed = parse_response(response_json())

        assert parsed.overall_observations == []
        assert parsed.missing_items == []

    def test_by_code_indexes_the_results(self) -> None:
        raw = json.dumps({"criteria": [payload(code="C1"), payload(code="C2", score=5)]})
        parsed = EvaluationResponse.model_validate(json.loads(raw))

        assert set(parsed.by_code()) == {"C1", "C2"}
        assert parsed.by_code()["C2"].score == Decimal("5")

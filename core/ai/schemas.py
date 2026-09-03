"""The AI response contract — §6.5.

The shape the model must return, enforced by Pydantic rather than by hope.

The load-bearing rule here is fix item 5's: **``NO_EVIDENCE`` forces
``score == 0``, and it is a validator.** Enforcing it in the UI would leave a
batch run free to write a nonzero score for a criterion nothing was found for,
which is exactly the failure the item names — "enforced in the UI and skipped
in a batch run".
"""

from __future__ import annotations

import json
import re
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from core.errors import RubriQError
from core.scoring.enums import Verdict

#: §6.5 caps the evidence span. A model that quotes half the document is not
#: citing evidence, it is hedging.
MAX_EVIDENCE_WORDS = 40

#: The system prompt forbids code fences, but models emit them anyway. Stripped
#: rather than rejected — a fenced-but-valid response is not worth a retry.
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


class AIResponseError(RubriQError):
    """The model returned something that is not a valid response."""


class CriterionResult(BaseModel):
    """One criterion, as the model reports it."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    code: str
    verdict: Verdict
    score: Decimal
    max_score: Decimal
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = ""
    rationale: str = ""

    @field_validator("code")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    @field_validator("evidence")
    @classmethod
    def _cap_evidence(cls, value: str) -> str:
        """Truncate rather than reject an over-long span.

        Losing the tail of a quote is recoverable; failing the whole batch
        because one span ran long is not.
        """
        words = value.split()
        if len(words) <= MAX_EVIDENCE_WORDS:
            return value
        return " ".join(words[:MAX_EVIDENCE_WORDS])

    @model_validator(mode="after")
    def _no_evidence_scores_zero(self) -> CriterionResult:
        """Invariant #3, as a validator so nothing can route around it."""
        if self.verdict is Verdict.NO_EVIDENCE and self.score != 0:
            raise ValueError(
                f"{self.code}: NO_EVIDENCE must score 0, not {self.score}. "
                "A criterion with no cited span has not been evidenced."
            )
        return self

    @model_validator(mode="after")
    def _score_within_range(self) -> CriterionResult:
        if self.max_score <= 0:
            raise ValueError(f"{self.code}: max_score must be greater than zero.")
        if not (0 <= self.score <= self.max_score):
            raise ValueError(
                f"{self.code}: score {self.score} is outside 0…{self.max_score}."
            )
        return self

    @model_validator(mode="after")
    def _a_scored_criterion_cites_something(self) -> CriterionResult:
        """A nonzero score with an empty span is a verdict with no basis.

        The guard would demote it anyway once it failed to match; catching it
        here makes the reason legible instead of leaving it as a mysterious
        fuzzy-match failure against the empty string.
        """
        if self.score > 0 and not self.evidence.strip():
            raise ValueError(
                f"{self.code}: scored {self.score} but cited no evidence. "
                "Every score must quote a span (invariant #3)."
            )
        return self


class EvaluationResponse(BaseModel):
    """The whole payload for one batch of criteria."""

    model_config = ConfigDict(extra="ignore")

    criteria: list[CriterionResult]
    overall_observations: list[str] = Field(default_factory=list)
    missing_items: list[str] = Field(default_factory=list)

    @field_validator("criteria")
    @classmethod
    def _at_least_one(cls, value: list[CriterionResult]) -> list[CriterionResult]:
        if not value:
            raise ValueError("The response contained no criteria.")
        return value

    @model_validator(mode="after")
    def _codes_are_unique(self) -> EvaluationResponse:
        codes = [c.code for c in self.criteria]
        duplicates = sorted({c for c in codes if codes.count(c) > 1})
        if duplicates:
            raise ValueError(f"Duplicate criterion codes: {', '.join(duplicates)}.")
        return self

    def by_code(self) -> dict[str, CriterionResult]:
        return {c.code: c for c in self.criteria}


def strip_fences(raw: str) -> str:
    """Remove a ```json wrapper if the model added one despite instructions."""
    text = (raw or "").strip()
    text = _FENCE.sub("", text)
    return text.strip()


def parse_response(raw: str) -> EvaluationResponse:
    """Parse and validate a model response.

    Raises :class:`AIResponseError` with the reason, which is what the repair
    prompt in Phase 5b will feed back to the model.
    """
    text = strip_fences(raw)

    if not text:
        raise AIResponseError("The model returned an empty response.")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIResponseError(
            f"Response was not valid JSON: {exc.msg} at position {exc.pos}."
        ) from exc

    if not isinstance(payload, dict):
        raise AIResponseError(f"Expected a JSON object, got {type(payload).__name__}.")

    try:
        return EvaluationResponse.model_validate(payload)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise AIResponseError(f"Response failed validation — {problems}") from exc


# -- the student assistant (§6.4) ----------------------------------------


class QueryClassification(BaseModel):
    """Whether a question can be answered from the milestone context alone."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    in_scope: bool
    reason: str = ""


class QueryResponse(BaseModel):
    """An answer drawn only from the supplied context.

    ``sources`` names the parts of the context used — a criterion code, "due
    date", "notes". §6.7 allows direct context stuffing and no vector store, so
    a source is a label rather than a retrieved chunk, but it still lets the
    student see *where* an answer came from instead of being asked to trust it.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    answer: str
    sources: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)

    @model_validator(mode="after")
    def _an_answer_is_not_blank(self) -> QueryResponse:
        if not self.answer.strip():
            raise ValueError("The answer was empty; escalate instead of saying nothing.")
        return self


def parse_classification(raw: str) -> QueryClassification:
    """Parse the classify node's response."""
    return _parse_into(raw, QueryClassification)


def parse_query_response(raw: str) -> QueryResponse:
    """Parse the answer node's response."""
    return _parse_into(raw, QueryResponse)


def _parse_into(raw: str, model: type[BaseModel]):
    text = strip_fences(raw)
    if not text:
        raise AIResponseError("The model returned an empty response.")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIResponseError(f"Response was not valid JSON: {exc.msg}.") from exc

    if not isinstance(payload, dict):
        raise AIResponseError(f"Expected a JSON object, got {type(payload).__name__}.")

    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise AIResponseError(f"Response failed validation — {problems}") from exc

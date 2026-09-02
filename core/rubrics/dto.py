"""Plain values returned by the rubric services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CriterionDTO:
    id: int
    code: str
    title: str
    description: str | None
    weight: Decimal
    max_score: Decimal
    expected_evidence: str | None
    is_mandatory: bool
    order_index: int


@dataclass(frozen=True, slots=True)
class RubricDTO:
    """A rubric and its active criteria.

    ``is_published`` is derived from ``published_at`` rather than stored
    separately — one fact, one column, so the two cannot disagree.
    """

    id: int
    milestone_id: int
    version: int
    published_at: datetime | None
    published_by: str | None
    criteria: tuple[CriterionDTO, ...]

    @property
    def is_published(self) -> bool:
        return self.published_at is not None

    @property
    def total_weight(self) -> Decimal:
        return sum((c.weight for c in self.criteria), Decimal("0"))

    @property
    def weights_are_valid(self) -> bool:
        """Publishing requires exactly 100, with at least one criterion."""
        return bool(self.criteria) and self.total_weight == Decimal("100")

    @property
    def mandatory_codes(self) -> tuple[str, ...]:
        return tuple(c.code for c in self.criteria if c.is_mandatory)

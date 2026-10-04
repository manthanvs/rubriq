"""The department's grading scale, driven row by row from the published table.

The scale is published for the 50-mark whole. It is stored as percentages
because its four boundaries are exactly 90, 70, 50 and 30 per cent — so one
table reproduces the published scale and also applies to a single 25-mark
review, instead of a second table existing to disagree with the first.

Boundaries are tested on both sides. A band that is right in the middle of its
range and wrong at its edge is the usual way this breaks, and the edge is
where a student's grade actually changes.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.errors import ValidationError
from core.scoring.policy import GradeBand, grade_band

#: Straight from the rubric: 45-50 Excellent, 35-44 Good, 25-34 Satisfactory,
#: 15-24 Needs Improvement, 0-14 Poor.
PUBLISHED_SCALE = [
    (50, GradeBand.EXCELLENT),
    (45, GradeBand.EXCELLENT),
    (44, GradeBand.GOOD),
    (35, GradeBand.GOOD),
    (34, GradeBand.SATISFACTORY),
    (25, GradeBand.SATISFACTORY),
    (24, GradeBand.NEEDS_IMPROVEMENT),
    (15, GradeBand.NEEDS_IMPROVEMENT),
    (14, GradeBand.POOR),
    (0, GradeBand.POOR),
]


@pytest.mark.parametrize(("total", "expected"), PUBLISHED_SCALE)
def test_the_published_scale_out_of_fifty(total: int, expected: GradeBand) -> None:
    assert grade_band(Decimal(total), Decimal(50)) is expected


@pytest.mark.parametrize(
    ("total", "expected"),
    [
        (Decimal("25"), GradeBand.EXCELLENT),
        (Decimal("22.5"), GradeBand.EXCELLENT),
        (Decimal("22.4"), GradeBand.GOOD),
        (Decimal("17.5"), GradeBand.GOOD),
        (Decimal("17.4"), GradeBand.SATISFACTORY),
        (Decimal("12.5"), GradeBand.SATISFACTORY),
        (Decimal("12.4"), GradeBand.NEEDS_IMPROVEMENT),
        (Decimal("7.5"), GradeBand.NEEDS_IMPROVEMENT),
        (Decimal("7.4"), GradeBand.POOR),
        (Decimal("0"), GradeBand.POOR),
    ],
)
def test_the_same_scale_on_a_single_review(total: Decimal, expected: GradeBand) -> None:
    """Half the marks, the same percentages, so the two cannot drift."""
    assert grade_band(total, Decimal(25)) is expected


def test_a_band_is_never_computed_from_a_negative_total() -> None:
    """final_total is clamped at zero upstream; reaching here means a bug."""
    with pytest.raises(ValidationError):
        grade_band(Decimal("-1"), Decimal(50))


@pytest.mark.parametrize("out_of", [Decimal(0), Decimal("-25")])
def test_an_impossible_denominator_is_refused(out_of: Decimal) -> None:
    with pytest.raises(ValidationError):
        grade_band(Decimal(10), out_of)


def test_full_marks_is_excellent_at_any_scale() -> None:
    for out_of in (Decimal(25), Decimal(50), Decimal(100)):
        assert grade_band(out_of, out_of) is GradeBand.EXCELLENT

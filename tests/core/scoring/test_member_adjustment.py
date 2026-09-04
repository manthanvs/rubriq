"""Phase 9 — one member of a group marked apart from it.

The arithmetic is a single addition, so the tests are almost entirely about the
two clamps and the rounding. That is where a wrong number would come from: an
adjustment large enough to push a mark below zero or above the milestone's
maximum is exactly the kind of input a tired reviewer types at the end of a
long cohort, and neither bound is the UI's job to enforce.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.errors import ValidationError
from core.scoring.engine import apply_member_adjustment

MAX = Decimal("25.00")


def adjust(group: str, delta: str, max_marks: str = "25.00") -> Decimal:
    return apply_member_adjustment(Decimal(group), Decimal(delta), Decimal(max_marks))


class TestTheOrdinaryCase:
    def test_no_adjustment_leaves_the_group_mark_alone(self) -> None:
        assert adjust("18.50", "0") == Decimal("18.50")

    def test_a_negative_delta_reduces_the_member(self) -> None:
        """The common case: one member contributed less than the others."""
        assert adjust("18.50", "-2.00") == Decimal("16.50")

    def test_a_positive_delta_raises_the_member(self) -> None:
        assert adjust("18.50", "1.50") == Decimal("20.00")

    def test_fractional_deltas_are_kept(self) -> None:
        assert adjust("18.50", "-0.25") == Decimal("18.25")


class TestTheClamps:
    """Both bounds are enforced in the engine, not trusted to the caller."""

    def test_a_delta_below_zero_stops_at_zero(self) -> None:
        assert adjust("6.00", "-10.00") == Decimal("0.00")

    def test_a_delta_above_the_maximum_stops_at_the_maximum(self) -> None:
        assert adjust("24.00", "10.00") == MAX

    def test_exactly_zero_is_reachable(self) -> None:
        assert adjust("6.00", "-6.00") == Decimal("0.00")

    def test_exactly_the_maximum_is_reachable(self) -> None:
        assert adjust("20.00", "5.00") == MAX

    @pytest.mark.parametrize("delta", ["-1000", "1000"])
    def test_an_absurd_delta_still_lands_inside_the_range(self, delta: str) -> None:
        result = adjust("12.00", delta)

        assert Decimal("0") <= result <= MAX

    def test_the_maximum_scales_with_the_milestone(self) -> None:
        """A 50-mark review must not be clamped at 25."""
        assert adjust("48.00", "10.00", max_marks="50.00") == Decimal("50.00")


class TestRounding:
    def test_the_result_is_two_decimal_places(self) -> None:
        assert adjust("18.333", "0") == Decimal("18.33")

    def test_rounding_is_half_up_like_every_other_total(self) -> None:
        assert adjust("18.125", "0") == Decimal("18.13")

    def test_a_zero_group_total_with_no_delta_is_zero(self) -> None:
        assert adjust("0.00", "0") == Decimal("0.00")


class TestGuards:
    def test_a_negative_maximum_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            adjust("10.00", "0", max_marks="-5.00")

    def test_an_absent_group_total_of_zero_stays_zero(self) -> None:
        """A negative delta must not make an already-zero mark go below it."""
        assert adjust("0.00", "-5.00") == Decimal("0.00")


def test_the_group_total_is_recoverable_from_the_delta() -> None:
    """The reason a delta beats a replacement: the baseline stays visible.

    A reviewer looking at 16.50 with a delta of −2.00 can see the group earned
    18.50. A stored replacement of 16.50 says nothing about what it replaced.
    """
    group = Decimal("18.50")
    delta = Decimal("-2.00")

    member = apply_member_adjustment(group, delta, MAX)

    assert member == Decimal("16.50")
    assert member - delta == group

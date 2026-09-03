"""Fix item 1 — score and penalty integrity.

§5 says to write this table-driven test *before any UI touches the engine*, so
this file exists before the review grid does.

The failures it guards, in fix item 1's own words:

* penalty subtracted per-criterion instead of from the milestone total;
* weights that do not sum to 100, so ``base_total`` is silently not out of
  ``max_marks``;
* ``days_late`` computed from a UTC timestamp, so an 11:45 PM IST submission
  counts as next-day late;
* float drift rendering 19.999999;
* ``final_total`` going negative.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from core.clock import IST
from core.errors import ValidationError
from core.scoring.engine import (
    CriterionScoreInput,
    compute_score_sheet,
    days_late,
    weighted_percent,
)
from core.scoring.policy import DEFAULT_LATE_POLICY, AttendanceStatus, LatePolicy

MAX_MARKS = Decimal("25")

#: 10 Oct 2026, 23:59 IST — the deadline used throughout.
DUE_AT = datetime(2026, 10, 10, 23, 59, tzinfo=IST)


def full_marks() -> list[CriterionScoreInput]:
    """Three criteria, weights 60/30/10, every one scored full."""
    return [
        CriterionScoreInput("C1", Decimal("10"), Decimal("10"), Decimal("60")),
        CriterionScoreInput("C2", Decimal("10"), Decimal("10"), Decimal("30")),
        CriterionScoreInput("C3", Decimal("10"), Decimal("10"), Decimal("10")),
    ]


def submitted_days_after(days: int) -> datetime:
    """A submission ``days`` calendar days after the due date, in IST.

    ``timedelta`` rather than arithmetic on the day number, so a 30-day-late
    case does not fall off the end of the month.
    """
    return datetime(2026, 10, 10, 12, 0, tzinfo=IST) + timedelta(days=days)


class TestSection51Table:
    """Every row of §5.1, driven directly."""

    @pytest.mark.parametrize(
        ("late", "expected_penalty_percent", "expected_final", "expected_status"),
        [
            (0, Decimal("0"), Decimal("25.00"), AttendanceStatus.PRESENT),
            (1, Decimal("10"), Decimal("22.50"), AttendanceStatus.LATE),
            (2, Decimal("20"), Decimal("20.00"), AttendanceStatus.LATE),
            (3, Decimal("35"), Decimal("16.25"), AttendanceStatus.LATE),
            (4, Decimal("100"), Decimal("0.00"), AttendanceStatus.ABSENT),
            (5, Decimal("100"), Decimal("0.00"), AttendanceStatus.ABSENT),
            (6, Decimal("100"), Decimal("0.00"), AttendanceStatus.ABSENT),
            (30, Decimal("100"), Decimal("0.00"), AttendanceStatus.ABSENT),
        ],
    )
    def test_each_band(
        self,
        late: int,
        expected_penalty_percent: Decimal,
        expected_final: Decimal,
        expected_status: AttendanceStatus,
    ) -> None:
        result = compute_score_sheet(
            full_marks(),
            max_marks=MAX_MARKS,
            due_at=DUE_AT,
            submitted_at=submitted_days_after(late),
        )

        assert result.days_late == late
        assert result.penalty_percent == expected_penalty_percent
        assert result.final_total == expected_final
        assert result.attendance is expected_status

    def test_beyond_five_days_needs_reinstatement(self) -> None:
        """§5.1: "> 5 … needs explicit faculty reinstatement to be scored"."""
        at_five = compute_score_sheet(
            full_marks(),
            max_marks=MAX_MARKS,
            due_at=DUE_AT,
            submitted_at=submitted_days_after(5),
        )
        at_six = compute_score_sheet(
            full_marks(),
            max_marks=MAX_MARKS,
            due_at=DUE_AT,
            submitted_at=submitted_days_after(6),
        )

        assert at_five.needs_reinstatement is False
        assert at_six.needs_reinstatement is True

    def test_absence_is_a_status_not_a_zero(self) -> None:
        """The distinction §5.1 exists to preserve, and fix item 10 renders."""
        absent = compute_score_sheet(
            full_marks(),
            max_marks=MAX_MARKS,
            due_at=DUE_AT,
            submitted_at=submitted_days_after(4),
        )
        scored_zero = compute_score_sheet(
            [
                CriterionScoreInput("C1", Decimal("0"), Decimal("10"), Decimal("60")),
                CriterionScoreInput("C2", Decimal("0"), Decimal("10"), Decimal("30")),
                CriterionScoreInput("C3", Decimal("0"), Decimal("10"), Decimal("10")),
            ],
            max_marks=MAX_MARKS,
            due_at=DUE_AT,
            submitted_at=submitted_days_after(0),
        )

        assert absent.final_total == scored_zero.final_total == Decimal("0.00")
        assert absent.attendance is AttendanceStatus.ABSENT
        assert scored_zero.attendance is AttendanceStatus.PRESENT
        assert absent.display_total == "ABSENT"
        assert scored_zero.display_total == "0.00"

    def test_reinstatement_zeroes_the_penalty_but_keeps_the_history(self) -> None:
        result = compute_score_sheet(
            full_marks(),
            max_marks=MAX_MARKS,
            due_at=DUE_AT,
            submitted_at=submitted_days_after(9),
            reinstated=True,
        )

        assert result.penalty == Decimal("0.00")
        assert result.final_total == Decimal("25.00")
        assert result.attendance is AttendanceStatus.REINSTATED
        assert result.days_late == 9, "the lateness is still recorded"


class TestIstBoundary:
    """The 11:59 PM boundary, which is why §5.1 counts IST dates."""

    def test_one_minute_before_midnight_ist_is_not_late(self) -> None:
        result = compute_score_sheet(
            full_marks(),
            max_marks=MAX_MARKS,
            due_at=DUE_AT,
            submitted_at=datetime(2026, 10, 10, 23, 59, 59, tzinfo=IST),
        )

        assert result.days_late == 0
        assert result.penalty == Decimal("0.00")

    def test_one_second_after_midnight_ist_is_one_day_late(self) -> None:
        result = compute_score_sheet(
            full_marks(),
            max_marks=MAX_MARKS,
            due_at=DUE_AT,
            submitted_at=datetime(2026, 10, 11, 0, 0, 1, tzinfo=IST),
        )

        assert result.days_late == 1
        assert result.final_total == Decimal("22.50")

    def test_a_late_evening_ist_submission_is_not_pushed_to_the_next_day(self) -> None:
        """The exact bug fix item 1 names: 23:45 IST is 18:15 UTC, same day.

        Counting on the UTC date would call this on-time submission late.
        """
        submitted = datetime(2026, 10, 10, 23, 45, tzinfo=IST)

        assert submitted.astimezone(UTC).day == 10  # same UTC day here
        assert days_late(DUE_AT, submitted) == 0

    def test_a_submission_after_1830_utc_still_counts_as_the_ist_day(self) -> None:
        """18:31 UTC on the 10th is 00:01 IST on the 11th — one day late."""
        submitted = datetime(2026, 10, 10, 18, 31, tzinfo=UTC)

        assert submitted.day == 10, "still the 10th in UTC"
        assert days_late(DUE_AT, submitted) == 1, "but the 11th in IST"

    def test_submitting_early_is_never_negative_days(self) -> None:
        assert days_late(DUE_AT, datetime(2026, 10, 1, 9, 0, tzinfo=IST)) == 0

    def test_utc_and_ist_inputs_agree(self) -> None:
        """The same instant expressed two ways must give the same answer."""
        as_ist = datetime(2026, 10, 12, 9, 0, tzinfo=IST)
        as_utc = as_ist.astimezone(UTC)

        assert days_late(DUE_AT, as_ist) == days_late(DUE_AT, as_utc) == 2


class TestWeights:
    def test_weights_must_sum_to_one_hundred(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            weighted_percent(
                [
                    CriterionScoreInput(
                        "C1", Decimal("10"), Decimal("10"), Decimal("60")
                    ),
                    CriterionScoreInput(
                        "C2", Decimal("10"), Decimal("10"), Decimal("30")
                    ),
                ]
            )

        assert "90" in str(excinfo.value)

    def test_the_penalty_applies_to_the_total_not_to_each_criterion(self) -> None:
        """§5.1: "Penalty applies to the milestone total, never to individual
        criteria." Per-criterion would compound and give a different answer."""
        result = compute_score_sheet(
            full_marks(),
            max_marks=MAX_MARKS,
            due_at=DUE_AT,
            submitted_at=submitted_days_after(2),
        )

        assert result.base_total == Decimal("25.00")
        assert result.penalty == Decimal("5.00")  # 20% of 25, once
        assert result.final_total == Decimal("20.00")

    def test_partial_scores_weigh_correctly(self) -> None:
        result = compute_score_sheet(
            [
                CriterionScoreInput("C1", Decimal("5"), Decimal("10"), Decimal("60")),
                CriterionScoreInput("C2", Decimal("8"), Decimal("10"), Decimal("30")),
                CriterionScoreInput("C3", Decimal("10"), Decimal("10"), Decimal("10")),
            ],
            max_marks=MAX_MARKS,
            due_at=DUE_AT,
            submitted_at=submitted_days_after(0),
        )

        # 0.5*60 + 0.8*30 + 1.0*10 = 30 + 24 + 10 = 64 percent
        assert result.weighted_percent == Decimal("64.00")
        assert result.final_total == Decimal("16.00")  # 64% of 25

    def test_a_score_above_its_maximum_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            weighted_percent(
                [CriterionScoreInput("C1", Decimal("11"), Decimal("10"), Decimal("100"))]
            )

    def test_a_negative_score_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            weighted_percent(
                [CriterionScoreInput("C1", Decimal("-1"), Decimal("10"), Decimal("100"))]
            )

    def test_no_criteria_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            weighted_percent([])


class TestArithmeticHygiene:
    def test_thirds_do_not_drift(self) -> None:
        """Float would give 19.999999…; Decimal gives 20.00."""
        result = compute_score_sheet(
            [
                CriterionScoreInput("C1", Decimal("10"), Decimal("30"), Decimal("33.33")),
                CriterionScoreInput("C2", Decimal("10"), Decimal("30"), Decimal("33.33")),
                CriterionScoreInput("C3", Decimal("10"), Decimal("30"), Decimal("33.34")),
            ],
            max_marks=Decimal("60"),
            due_at=DUE_AT,
            submitted_at=submitted_days_after(0),
        )

        assert result.weighted_percent == Decimal("33.33")
        assert result.final_total == Decimal("20.00")
        assert str(result.final_total) == "20.00", "no float tail"

    def test_every_number_is_quantised_to_two_places(self) -> None:
        result = compute_score_sheet(
            [
                CriterionScoreInput("C1", Decimal("7"), Decimal("9"), Decimal("100")),
            ],
            max_marks=Decimal("25"),
            due_at=DUE_AT,
            submitted_at=submitted_days_after(1),
        )

        for value in (
            result.base_total,
            result.penalty,
            result.final_total,
            result.weighted_percent,
        ):
            assert value.as_tuple().exponent == -2, f"{value} is not 2dp"

    def test_final_total_never_goes_negative(self) -> None:
        """A penalty larger than the score must floor at zero, not go under."""
        harsh = LatePolicy(
            bands=(
                DEFAULT_LATE_POLICY.bands[0],
                # 90% of max marks against a submission that scored 10%.
                type(DEFAULT_LATE_POLICY.bands[1])(
                    min_days=1, max_days=None, percent=Decimal("90")
                ),
            )
        )

        result = compute_score_sheet(
            [CriterionScoreInput("C1", Decimal("1"), Decimal("10"), Decimal("100"))],
            max_marks=Decimal("25"),
            due_at=DUE_AT,
            submitted_at=submitted_days_after(1),
            policy=harsh,
        )

        assert result.base_total == Decimal("2.50")
        assert result.penalty == Decimal("22.50")
        assert result.final_total == Decimal("0.00")

    def test_max_marks_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            compute_score_sheet(
                full_marks(),
                max_marks=Decimal("0"),
                due_at=DUE_AT,
                submitted_at=submitted_days_after(0),
            )


class TestPolicySerialisation:
    def test_the_default_policy_round_trips_through_json(self) -> None:
        """`LatePolicy.rules` is stored as JSON; it must come back identical."""
        restored = LatePolicy.from_rules(DEFAULT_LATE_POLICY.to_rules())

        assert restored == DEFAULT_LATE_POLICY

    def test_an_empty_rules_payload_falls_back_to_the_default(self) -> None:
        assert LatePolicy.from_rules(None) == DEFAULT_LATE_POLICY
        assert LatePolicy.from_rules({}) == DEFAULT_LATE_POLICY

    def test_a_policy_with_a_gap_is_refused_rather_than_guessed(self) -> None:
        gapped = LatePolicy(
            bands=(DEFAULT_LATE_POLICY.bands[0],)  # only covers 0 days
        )

        with pytest.raises(ValidationError):
            gapped.band_for(3)

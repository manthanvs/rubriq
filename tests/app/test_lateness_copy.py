"""Fix item 10 — the student is told the *band*, not a generic penalty.

§5.1 has three shapes of outcome, not one: a percentage, an ABSENT status, and
an ABSENT status that needs a faculty reinstatement before it can be scored at
all. Wording that flattens those into "a late penalty will apply" understates
two of them, and the understated ones are the two that matter.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.components.lateness import consequence_text
from core.scoring.policy import DEFAULT_LATE_POLICY

MAX_MARKS = Decimal("25.00")


def text_for(days_late: int) -> str:
    return consequence_text(DEFAULT_LATE_POLICY.band_for(days_late), MAX_MARKS)


class TestTheBandsAreDistinguished:
    def test_on_time_promises_nothing(self) -> None:
        assert text_for(0) == "No penalty applies."

    @pytest.mark.parametrize(
        "days,percent,marks",
        [(1, "10%", "2.50"), (2, "20%", "5.00"), (3, "35%", "8.75")],
    )
    def test_a_penalty_band_names_its_percentage_and_its_marks(
        self, days: int, percent: str, marks: str
    ) -> None:
        """ "10 %" and "2.5 of 25" are the same fact; only one reads quickly."""
        message = text_for(days)

        assert percent in message
        assert f"{marks} of 25.00 marks" in message

    @pytest.mark.parametrize("days", [4, 5])
    def test_the_absent_band_does_not_call_itself_a_penalty(self, days: int) -> None:
        message = text_for(days)

        assert "ABSENT" in message
        assert "penalty" not in message

    @pytest.mark.parametrize("days", [6, 30])
    def test_past_five_days_the_reinstatement_requirement_is_stated(
        self, days: int
    ) -> None:
        """Without this the student thinks a late submission is enough."""
        message = text_for(days)

        assert "ABSENT" in message
        assert "reinstate" in message

    def test_absence_still_invites_the_submission(self) -> None:
        """§5.1 stores and evaluates an absent submission for feedback."""
        for days in (4, 6):
            assert "Submit anyway" in text_for(days)


def test_the_marks_scale_with_the_milestone() -> None:
    """A 50-mark review must not quote a 25-mark penalty."""
    band = DEFAULT_LATE_POLICY.band_for(2)

    assert "10.00 of 50.00 marks" in consequence_text(band, Decimal("50.00"))


def test_every_band_produces_a_sentence() -> None:
    """A band with no wording would render an empty error box."""
    for days in range(0, 40):
        assert text_for(days).strip()

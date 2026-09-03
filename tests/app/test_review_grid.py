"""Fix item 12 — review-grid readability, as a contract rather than a screenshot.

The three things that actually break when this page is edited are: the totals
sliding off the right-hand edge behind a wide rubric, an identity column
scrolling out of view, and ``ABSENT`` being rendered as a number. The first two
are layout; the third is §5.1 and is guarded here too because the grid is where
it would be noticed last.

No database and no Streamlit runtime — these functions shape a table out of
DTOs, so they can be called directly.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from app.components.review_grid import (
    CRITERION_OVERFLOW,
    build_criterion_frame,
    build_frame,
    grid_column_config,
    split_criteria,
)
from core.clock import IST
from core.scoring.dto import CriterionScoreDTO, GridRow, ScoreSheetDTO
from core.scoring.enums import EvaluationEngine, EvaluationStatus, Verdict
from core.scoring.policy import AttendanceStatus

IDENTITY = ("!", "PRN", "Name")
TOTALS = ("Base", "Penalty", "Final", "By")
WHEN = datetime(2026, 9, 1, 10, 0, tzinfo=IST)


class FakeCriterion:
    """Just enough of a criterion for the tooltip lookup."""

    def __init__(self, code: str) -> None:
        self.code = code
        self.title = f"Criterion {code}"


class FakeRubric:
    def __init__(self, count: int) -> None:
        self.criteria = [FakeCriterion(f"C{i}") for i in range(1, count + 1)]


def codes_for(count: int) -> tuple[str, ...]:
    return tuple(f"C{i}" for i in range(1, count + 1))


def criterion_score(code: str, verdict: Verdict) -> CriterionScoreDTO:
    return CriterionScoreDTO(
        criterion_id=1,
        code=code,
        title=f"Criterion {code}",
        weight=Decimal("50"),
        max_score=Decimal("10"),
        is_mandatory=False,
        score=Decimal("8"),
        verdict=verdict,
        confidence=None,
        evidence_span=None,
        rationale=None,
    )


def sheet(
    *,
    codes: tuple[str, ...] = ("C1", "C2"),
    attendance: AttendanceStatus = AttendanceStatus.PRESENT,
    days_late: int = 0,
    engine: EvaluationEngine = EvaluationEngine.MANUAL,
    override_count: int = 0,
) -> ScoreSheetDTO:
    return ScoreSheetDTO(
        id=1,
        evaluation_id=1,
        submission_id=1,
        engine=engine,
        evaluation_status=EvaluationStatus.COMPLETE,
        submission_version=1,
        rubric_version=1,
        max_marks=Decimal("25.00"),
        weighted_percent=Decimal("80.00"),
        base_total=Decimal("20.00"),
        penalty=Decimal("2.50"),
        final_total=Decimal("17.50"),
        days_late=days_late,
        attendance_status=attendance,
        reinstated=False,
        reinstate_reason=None,
        approved_by=None,
        approved_at=None,
        faculty_note=None,
        criteria=tuple(criterion_score(c, Verdict.FOLLOWED) for c in codes),
        override_count=override_count,
    )


def row(*, prn: str = "125M1H064", scored: bool = True, **kwargs) -> GridRow:
    return GridRow(
        student_email="manthan.sankpal@pccoepune.org",
        student_name="Manthan Sankpal",
        prn=prn,
        submission_id=1 if scored else None,
        submission_version=1 if scored else None,
        submitted_at=WHEN if scored else None,
        has_newer_version=False,
        sheet=sheet(**kwargs) if scored else None,
    )


class TestOverflow:
    def test_a_narrow_rubric_keeps_its_verdicts_inline(self) -> None:
        codes = codes_for(CRITERION_OVERFLOW)

        inline, overflowed = split_criteria(codes)

        assert inline == codes
        assert overflowed is False

    def test_one_criterion_past_the_limit_moves_the_whole_block(self) -> None:
        """All of them, not the tail — a table hiding only C9 reads as a bug."""
        inline, overflowed = split_criteria(codes_for(CRITERION_OVERFLOW + 1))

        assert inline == ()
        assert overflowed is True

    def test_the_totals_survive_a_wide_rubric(self) -> None:
        """The point of the whole item: Final must not scroll off the edge."""
        inline, _ = split_criteria(codes_for(20))
        frame = build_frame((row(),), inline)

        assert tuple(frame.columns)[-len(TOTALS) :] == TOTALS
        assert not [c for c in frame.columns if c.startswith("C")]

    def test_the_overflow_table_repeats_the_identity(self) -> None:
        codes = codes_for(12)

        frame = build_criterion_frame((row(codes=codes),), codes)

        assert tuple(frame.columns) == ("PRN", "Name", *codes)


class TestColumnOrder:
    def test_identity_leads_and_totals_close(self) -> None:
        columns = tuple(build_frame((row(),), ("C1", "C2")).columns)

        assert columns[: len(IDENTITY)] == IDENTITY
        assert columns[-len(TOTALS) :] == TOTALS

    def test_criteria_sit_between_status_and_the_totals(self) -> None:
        columns = tuple(build_frame((row(),), ("C1", "C2")).columns)

        assert columns.index("Status") < columns.index("C1")
        assert columns.index("C2") < columns.index("Base")

    def test_a_student_with_no_submission_still_gets_a_row(self) -> None:
        """A grid that omits non-submitters is how someone gets missed."""
        frame = build_frame((row(scored=False),), ("C1",))

        assert len(frame) == 1
        assert frame.iloc[0]["Status"] == "No submission"
        assert frame.iloc[0]["C1"] == ""


class TestCellRendering:
    def test_an_absent_student_is_never_a_number(self) -> None:
        """§5.1 / fix item 10, guarded at the place it would be seen last."""
        frame = build_frame((row(attendance=AttendanceStatus.ABSENT),), ("C1",))

        assert frame.iloc[0]["Final"] == "ABSENT"

    def test_days_late_is_blank_rather_than_zero_when_nothing_was_scored(self) -> None:
        frame = build_frame((row(scored=False),), ())

        assert frame.iloc[0]["Days Late"] == ""

    def test_an_unscored_row_shows_no_totals_at_all(self) -> None:
        """Fix item 13: a null in a numeric column renders as the word "None"."""
        record = build_frame((row(scored=False),), ()).iloc[0]

        assert (record["Base"], record["Penalty"], record["Final"]) == ("", "", "")

    def test_the_totals_keep_two_decimal_places(self) -> None:
        record = build_frame((row(),), ()).iloc[0]

        assert (record["Base"], record["Penalty"]) == ("20.00", "2.50")

    def test_a_scored_row_on_time_shows_a_real_zero(self) -> None:
        frame = build_frame((row(days_late=0),), ())

        assert frame.iloc[0]["Days Late"] == "0"

    def test_an_overridden_mark_is_not_labelled_as_the_model(self) -> None:
        frame = build_frame(
            (row(engine=EvaluationEngine.AI, override_count=1),), ("C1",)
        )

        assert frame.iloc[0]["By"] == "OVERRIDDEN"

    def test_the_attention_dot_matches_the_predicate(self) -> None:
        needs = row(scored=False)
        frame = build_frame((needs,), ())

        assert needs.needs_attention is True
        assert frame.iloc[0]["!"] == "●"

    def test_the_version_reads_as_a_version(self) -> None:
        assert build_frame((row(),), ()).iloc[0]["Ver"] == "v1"


class TestColumnConfig:
    def test_identity_columns_are_pinned(self) -> None:
        config = grid_column_config(FakeRubric(2), ("C1", "C2"))

        assert [name for name, c in config.items() if c.get("pinned")] == list(IDENTITY)

    def test_every_column_has_an_explicit_width(self) -> None:
        """Content-sized columns reflow the whole grid when one name is long."""
        config = grid_column_config(FakeRubric(3), codes_for(3))

        assert all(c.get("width") for c in config.values())

    def test_every_rendered_column_is_configured(self) -> None:
        """A column with no config is one Streamlit sizes for itself."""
        codes = codes_for(4)
        frame = build_frame((row(codes=codes),), codes)
        config = grid_column_config(FakeRubric(4), codes)

        assert set(frame.columns) <= set(config)

    def test_a_criterion_carries_its_title_as_a_tooltip(self) -> None:
        """``C3`` alone tells a reader nothing about what it asked for."""
        config = grid_column_config(FakeRubric(3), codes_for(3))

        assert config["C3"]["help"] == "Criterion C3"

    @pytest.mark.parametrize("count", [1, CRITERION_OVERFLOW, 20])
    def test_the_config_covers_the_overflow_table_too(self, count: int) -> None:
        codes = codes_for(count)
        frame = build_criterion_frame((row(codes=codes),), codes)
        config = grid_column_config(FakeRubric(count), codes)

        assert set(frame.columns) <= set(config)


def test_the_grid_renders_a_full_cohort_shape() -> None:
    """One frame carrying every §5.1 outcome, as the seeded demo does."""
    rows = (
        row(prn="A", days_late=0),
        row(prn="B", days_late=2),
        row(prn="C", attendance=AttendanceStatus.ABSENT, days_late=4),
        row(prn="D", scored=False),
    )

    frame = build_frame(rows, ("C1", "C2"))

    assert list(frame["Status"]) == [
        "Estimate",
        "Estimate",
        "Absent",
        "No submission",
    ]
    assert list(frame["Final"]) == ["17.50", "17.50", "ABSENT", ""]

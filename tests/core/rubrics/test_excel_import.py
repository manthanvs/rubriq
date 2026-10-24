"""Reading a rubric out of the department's spreadsheet.

The fixture is the guide's own file, not one written to pass. A parser tested
only against input its author invented is a parser tested against its own
assumptions, and the whole point of this feature is that it reads *her*
workbook.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from core.errors import ValidationError
from core.rubrics.excel_import import (
    ParsedReview,
    describe_failure,
    parse_rubric_workbook,
)

FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "department_rubric.xlsx"
)


@pytest.fixture(scope="module")
def reviews() -> tuple[ParsedReview, ...]:
    return parse_rubric_workbook(FIXTURE.read_bytes())


def test_both_reviews_are_found(reviews) -> None:
    assert [r.index for r in reviews] == [1, 2]


def test_the_titles_do_not_repeat_their_marks(reviews) -> None:
    """The heading says "Review 1 (25 Marks) - … (25 Marks)". Once is enough."""
    assert reviews[0].title == "Project Introduction & Synopsis Submission"
    assert reviews[1].title == "Implementation, Demo & Final Submission"
    for review in reviews:
        assert "marks" not in review.title.lower()


def test_marks_come_from_the_heading(reviews) -> None:
    assert all(r.max_marks == Decimal(25) for r in reviews)


def test_the_criteria_are_the_departments(reviews) -> None:
    assert [c.title for c in reviews[0].criteria] == [
        "Problem Definition",
        "Requirements Analysis",
        "Technology Stack",
        "System Design",
        "Synopsis Submission",
    ]
    assert [c.title for c in reviews[1].criteria] == [
        "Functionality",
        "Code Quality",
        "User Interface (UI)",
        "Project Demonstration",
        "Submission",
    ]


def test_weights_sum_to_exactly_one_hundred(reviews) -> None:
    """Publishing validates this, so an import that cannot publish is useless.

    Five equal shares of 100 is 20 each, but three would be 33.33 each and sum
    to 99.99. The last criterion absorbs the remainder.
    """
    for review in reviews:
        assert review.weight_total == Decimal(100)


def test_the_top_of_a_range_is_the_score(reviews) -> None:
    """"Satisfactory (2-3)" is worth at most 3, not 2."""
    scores = {level.label: level.score for level in reviews[0].levels}
    assert scores["Excellent"] == 5
    assert scores["Satisfactory"] == 3
    assert scores["Poor"] == 0
    assert all(c.max_score == 5 for c in reviews[0].criteria)


def test_every_criterion_keeps_its_descriptors(reviews) -> None:
    first = reviews[0].criteria[0]
    assert dict(first.descriptors)["Excellent"].startswith("Clear, specific")
    assert "Excellent" in first.description
    assert "Poor" in first.description


def _book(rows: list[list[str]]) -> bytes:
    import io

    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_a_workbook_with_no_rubric_is_refused_readably() -> None:
    data = _book([["Attendance"], ["Name", "Present"], ["Someone", "Yes"]])

    with pytest.raises(ValidationError) as excinfo:
        parse_rubric_workbook(data)

    message = str(excinfo.value)
    assert "Review 1 (25 Marks)" in message, "the message should show the shape"
    assert message == describe_failure()


def test_a_file_that_is_not_a_workbook_is_refused_readably() -> None:
    with pytest.raises(ValidationError, match="could not be opened"):
        parse_rubric_workbook(b"this is not a spreadsheet")


def test_the_grading_scale_is_not_read_as_criteria() -> None:
    """Everything after "Grading Scale" is prose, not rubric rows."""
    data = _book(
        [
            ["Review 1 (25 Marks) - Something"],
            ["Criteria", "Excellent (5)", "Poor (0)"],
            ["Only Criterion", "good", "bad"],
            [],
            ["Grading Scale:"],
            ["45-50 Marks: Excellent"],
        ]
    )

    (review,) = parse_rubric_workbook(data)
    assert [c.title for c in review.criteria] == ["Only Criterion"]


def test_three_criteria_still_sum_to_one_hundred() -> None:
    """33.33 three times is 99.99, which publishing would reject."""
    data = _book(
        [
            ["Review 1 (25 Marks) - Something"],
            ["Criteria", "Excellent (5)", "Poor (0)"],
            ["One", "a", "b"],
            ["Two", "a", "b"],
            ["Three", "a", "b"],
        ]
    )

    (review,) = parse_rubric_workbook(data)
    assert review.weight_total == Decimal(100)

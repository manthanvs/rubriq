"""Read a rubric out of the department's own spreadsheet.

The guide writes rubrics in Excel. Rather than asking her to retype them into
a web form, the workbook is the input: upload it and the reviews, criteria and
descriptors come out of it.

**This parses; it does not ask a model to.** The sheet is a regular table — a
title row, a header row naming the levels, then one row per criterion — and a
parser reads it exactly, every time, offline, in milliseconds. Handing a
structured table to a language model would be slower, cost money, and
introduce the one failure a rubric importer must not have: a criterion that
comes back subtly reworded. Invariant #2 says deterministic rules run in
Python; the shape of a spreadsheet is a deterministic rule.

Where a model does earn its place is a workbook that does *not* match this
shape, and :func:`describe_failure` exists to hand that case on with a useful
message rather than a stack trace.

The expected shape, from ``Final Rubrics Mini Project.xlsx``::

    Review 1 (25 Marks) - Project Introduction & Synopsis Submission
    Criteria | Excellent (5) | Good (4) | Satisfactory (2-3) | ... | Poor (0)
    Problem Definition | Clear, specific ... | Clear but broad ... | ...
    Requirements Analysis | ...
    ...
    Grading Scale:
    45-50 Marks: Excellent - ...
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from decimal import Decimal

from core.errors import ValidationError

#: "Review 1 (25 Marks) - Project Introduction & Synopsis Submission".
#: Tolerant about the dash, the spacing and the word Mark/Marks, because a
#: human types this row.
REVIEW_HEADING = re.compile(
    r"^\s*review\s*(?P<index>\d+)\s*\(\s*(?P<marks>\d+)\s*marks?\s*\)\s*[-–—:]*\s*(?P<title>.*)$",
    re.IGNORECASE,
)

#: "Excellent (5)" or "Satisfactory (2-3)" — the score is the top of a range,
#: because a band of 2-3 is still worth at most 3.
LEVEL_HEADING = re.compile(
    r"^\s*(?P<label>.+?)\s*\(\s*(?P<low>\d+)\s*(?:[-–]\s*(?P<high>\d+)\s*)?\)\s*$"
)

#: Where the criteria stop. Anything at or after this is the grading scale.
END_MARKERS = ("grading scale",)

#: A header row starts with this cell.
CRITERIA_HEADER = "criteria"

#: The source heading repeats its marks at the end of the title. Keeping both
#: renders "Review 1 — Project Introduction (25 Marks)" everywhere the title
#: appears, next to a max_marks column already saying 25.
TRAILING_MARKS = re.compile(r"\s*\(\s*\d+\s*marks?\s*\)\s*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ParsedLevel:
    """One column of the rubric: a label, its score, and what it describes."""

    label: str
    score: Decimal


@dataclass(frozen=True, slots=True)
class ParsedCriterion:
    code: str
    title: str
    #: label -> descriptor, in the order the columns appeared.
    descriptors: tuple[tuple[str, str], ...]
    max_score: Decimal
    weight: Decimal

    @property
    def description(self) -> str:
        """The levels as one line, which is how a student reads them."""
        return " · ".join(
            f"{label} {descriptor}"
            for label, descriptor in self.descriptors
            if descriptor
        )


@dataclass(frozen=True, slots=True)
class ParsedReview:
    index: int
    title: str
    max_marks: Decimal
    levels: tuple[ParsedLevel, ...]
    criteria: tuple[ParsedCriterion, ...]

    @property
    def weight_total(self) -> Decimal:
        return sum((c.weight for c in self.criteria), Decimal("0"))


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _levels(row: list[str]) -> tuple[ParsedLevel, ...]:
    """Read the level columns from a header row, skipping the first cell."""
    out: list[ParsedLevel] = []
    for cell in row[1:]:
        if not cell:
            continue
        match = LEVEL_HEADING.match(cell)
        if match is None:
            # A column that does not declare a score cannot be marked against.
            continue
        high = match.group("high") or match.group("low")
        out.append(ParsedLevel(label=match.group("label").strip(), score=Decimal(high)))
    return tuple(out)


def parse_rubric_workbook(data: bytes) -> tuple[ParsedReview, ...]:
    """Every review found in the workbook, in the order they appear.

    Raises :class:`ValidationError` with a message meant for a person when the
    sheet does not have the expected shape.
    """
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - openpyxl is a hard dep
        raise ValidationError("Reading .xlsx files needs openpyxl installed.") from exc

    try:
        workbook = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except Exception as exc:
        raise ValidationError(
            "That file could not be opened as an Excel workbook. Save it as "
            ".xlsx and try again."
        ) from exc

    reviews: list[ParsedReview] = []

    for sheet in workbook.worksheets:
        rows = [
            [_text(cell) for cell in row]
            for row in sheet.iter_rows(values_only=True)
        ]

        index = 0
        while index < len(rows):
            row = rows[index]
            first = row[0] if row else ""

            if any(marker in first.lower() for marker in END_MARKERS):
                break

            heading = REVIEW_HEADING.match(" ".join(c for c in row if c)) if row else None
            if heading is None:
                index += 1
                continue

            index, review = _read_review(rows, index, heading)
            if review is not None:
                reviews.append(review)

    workbook.close()

    if not reviews:
        raise ValidationError(describe_failure())
    return tuple(reviews)


def _read_review(rows, start: int, heading) -> tuple[int, ParsedReview | None]:
    """Read one review block beginning at its heading row."""
    index = start + 1
    levels: tuple[ParsedLevel, ...] = ()

    # The header row may not be the very next one.
    while index < len(rows):
        row = rows[index]
        if row and row[0].lower().startswith(CRITERIA_HEADER):
            levels = _levels(row)
            index += 1
            break
        if row and REVIEW_HEADING.match(" ".join(c for c in row if c)):
            return index, None  # a heading with no criteria under it
        index += 1

    if not levels:
        return index, None

    criteria: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    while index < len(rows):
        row = rows[index]
        first = row[0] if row else ""

        if not first:
            index += 1
            if criteria:
                break  # a blank line after criteria ends the block
            continue
        if any(marker in first.lower() for marker in END_MARKERS):
            break
        if REVIEW_HEADING.match(" ".join(c for c in row if c)):
            break

        descriptors = tuple(
            (level.label, row[position + 1] if position + 1 < len(row) else "")
            for position, level in enumerate(levels)
        )
        criteria.append((first, descriptors))
        index += 1

    if not criteria:
        return index, None

    max_score = max(level.score for level in levels)

    # Equal weights summing to exactly 100: the last one absorbs the remainder
    # so five criteria do not sum to 99.99 and fail the publish check.
    share = (Decimal("100") / len(criteria)).quantize(Decimal("0.01"))
    weights = [share] * len(criteria)
    weights[-1] = Decimal("100") - share * (len(criteria) - 1)

    return index, ParsedReview(
        index=int(heading.group("index")),
        title=TRAILING_MARKS.sub("", heading.group("title")).strip()
        or f"Review {heading.group('index')}",
        max_marks=Decimal(heading.group("marks")),
        levels=levels,
        criteria=tuple(
            ParsedCriterion(
                code=f"C{position}",
                title=title,
                descriptors=descriptors,
                max_score=max_score,
                weight=weight,
            )
            for position, (title, descriptors), weight in zip(
                range(1, len(criteria) + 1), criteria, weights, strict=True
            )
        ),
    )


def describe_failure() -> str:
    """What a workbook has to look like, for when one does not."""
    return (
        "No rubric was found in that workbook. A sheet should contain a row "
        "reading like “Review 1 (25 Marks) - Project Introduction”, then a row "
        "beginning “Criteria” whose other cells name the levels and their "
        "scores — “Excellent (5)”, “Good (4)”, “Satisfactory (2-3)” — and then "
        "one row per criterion with its descriptions. Anything from “Grading "
        "Scale” onwards is ignored."
    )

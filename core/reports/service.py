"""Reporting aggregates — §8's Reports page.

Read-only, actor-scoped, and computing nothing that ``core/scoring`` already
computes. Every figure here is an aggregate *of persisted score sheets*, so a
report can never disagree with the grid: if they differed, one of them would be
recomputing marks, and only one place is allowed to do that (invariant #2).

Absent submissions are excluded from mark statistics and counted separately.
§5.1 exists to keep "absent" and "scored zero" apart, and an average that
silently folds absences in as zeroes destroys exactly that distinction.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from core.academics.access import require_faculty
from core.auth.actor import Actor
from core.scoring.dto import GridRow
from core.scoring.enums import Verdict
from core.scoring.grid import list_grid_rows
from core.scoring.policy import AttendanceStatus, GradeBand, grade_band


@dataclass(frozen=True, slots=True)
class Band:
    """One bar of the distribution."""

    label: str
    low: Decimal
    high: Decimal
    count: int


@dataclass(frozen=True, slots=True)
class CriterionStat:
    """How a cohort did on one criterion."""

    code: str
    title: str
    max_score: Decimal
    is_mandatory: bool
    scored: int
    mean_percent: Decimal
    verdicts: dict[str, int]

    @property
    def followed_share(self) -> float:
        total = sum(self.verdicts.values())
        return (self.verdicts.get(str(Verdict.FOLLOWED), 0) / total) if total else 0.0

    @property
    def unevidenced(self) -> int:
        return self.verdicts.get(str(Verdict.NO_EVIDENCE), 0)


@dataclass(frozen=True, slots=True)
class MilestoneReport:
    """Everything the Reports page renders for one milestone."""

    enrolled: int
    submitted: int
    scored: int
    approved: int
    absent: int
    not_submitted: int
    max_marks: Decimal
    mean: Decimal | None
    median: Decimal | None
    lowest: Decimal | None
    highest: Decimal | None
    bands: tuple[Band, ...]
    #: The department's named scale, in published order and always complete —
    #: a band with nobody in it is a fact about the cohort, so it is reported
    #: as zero rather than omitted.
    grades: tuple[tuple[GradeBand, int], ...]
    criteria: tuple[CriterionStat, ...]

    @property
    def has_marks(self) -> bool:
        return self.scored > 0

    @property
    def weakest(self) -> CriterionStat | None:
        """The criterion the cohort did worst on — the point of the page."""
        graded = [c for c in self.criteria if c.scored]
        return min(graded, key=lambda c: c.mean_percent) if graded else None


def _percentile(values: list[Decimal], fraction: float) -> Decimal:
    """Nearest-rank percentile. Small cohorts make interpolation misleading."""
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def _bands(
    marks: list[Decimal], max_marks: Decimal, buckets: int = 5
) -> tuple[Band, ...]:
    """Fixed-width bands across 0…max_marks.

    Fixed rather than data-driven, so two milestones can be compared and a
    cohort that all scored well still looks like a cohort that scored well.
    """
    if max_marks <= 0:
        return ()

    width = max_marks / buckets
    out: list[Band] = []

    for index in range(buckets):
        low = width * index
        high = max_marks if index == buckets - 1 else width * (index + 1)
        # The top band is closed so full marks lands somewhere.
        count = sum(
            1
            for mark in marks
            if (low <= mark < high) or (index == buckets - 1 and mark == high)
        )
        out.append(
            Band(
                label=f"{low:.0f}–{high:.0f}",
                low=low,
                high=high,
                count=count,
            )
        )

    return tuple(out)


def _grades(
    marks: list[Decimal], max_marks: Decimal
) -> tuple[tuple[GradeBand, int], ...]:
    """Count the cohort into the department's named bands.

    Every band appears, including the empty ones. "Nobody was Poor" is a
    result; a missing row looks like a question nobody asked.
    """
    if max_marks <= 0:
        return ()
    counts = dict.fromkeys(GradeBand, 0)
    for mark in marks:
        counts[grade_band(mark, max_marks)] += 1
    return tuple(counts.items())


def build_report(actor: Actor, session: Session, *, milestone_id: int) -> MilestoneReport:
    """Aggregate one milestone's grid into the Reports page's figures."""
    require_faculty(actor, "read reports")

    rows: tuple[GridRow, ...] = list_grid_rows(actor, session, milestone_id=milestone_id)

    submitted = [r for r in rows if r.has_submitted]
    scored = [r for r in rows if r.sheet is not None]
    approved = [r for r in scored if r.sheet.is_approved]
    absent = [r for r in scored if r.sheet.is_absent]

    max_marks = scored[0].sheet.max_marks if scored else Decimal("0")

    # Absences are a status, not a zero (§5.1) — excluded from the statistics
    # and reported on their own.
    #
    # ``member_mark`` rather than ``sheet.final_total``: a member of a granted
    # group who was marked apart from it holds a different mark, and a class
    # average that used the group's figure would disagree with both the review
    # grid and the exported spreadsheet. Fix item 11's rule — one set of
    # numbers, wherever they are shown — applies to a chart as much as to a
    # column.
    marks = [r.member_mark for r in scored if not r.sheet.is_absent]

    criteria: dict[str, dict] = {}
    for row in scored:
        if row.sheet.is_absent:
            continue
        for criterion in row.sheet.criteria:
            entry = criteria.setdefault(
                criterion.code,
                {
                    "title": criterion.title,
                    "max_score": criterion.max_score,
                    "is_mandatory": criterion.is_mandatory,
                    "scores": [],
                    "verdicts": {},
                },
            )
            entry["scores"].append(criterion.score)
            key = str(criterion.verdict)
            entry["verdicts"][key] = entry["verdicts"].get(key, 0) + 1

    stats = []
    for code in sorted(criteria):
        entry = criteria[code]
        scores = entry["scores"]
        mean_percent = (
            (sum(scores) / len(scores) / entry["max_score"] * 100).quantize(
                Decimal("0.1")
            )
            if scores and entry["max_score"]
            else Decimal("0.0")
        )
        stats.append(
            CriterionStat(
                code=code,
                title=entry["title"],
                max_score=entry["max_score"],
                is_mandatory=entry["is_mandatory"],
                scored=len(scores),
                mean_percent=mean_percent,
                verdicts=entry["verdicts"],
            )
        )

    return MilestoneReport(
        enrolled=len(rows),
        submitted=len(submitted),
        scored=len(scored),
        approved=len(approved),
        absent=len(absent),
        not_submitted=len(rows) - len(submitted),
        max_marks=max_marks,
        mean=(sum(marks) / len(marks)).quantize(Decimal("0.01")) if marks else None,
        median=_percentile(marks, 0.5) if marks else None,
        lowest=min(marks) if marks else None,
        highest=max(marks) if marks else None,
        bands=_bands(marks, max_marks) if marks else (),
        grades=_grades(marks, max_marks) if marks else (),
        criteria=tuple(stats),
    )


def attendance_mix(
    actor: Actor, session: Session, *, milestone_id: int
) -> dict[str, int]:
    """How the cohort was recorded, keeping absence distinct from a zero."""
    require_faculty(actor, "read reports")

    rows = list_grid_rows(actor, session, milestone_id=milestone_id)
    mix = {str(status): 0 for status in AttendanceStatus}
    mix["NOT SUBMITTED"] = 0
    mix["NOT SCORED"] = 0

    for row in rows:
        if not row.has_submitted:
            mix["NOT SUBMITTED"] += 1
        elif row.sheet is None:
            mix["NOT SCORED"] += 1
        else:
            mix[str(row.sheet.attendance_status)] += 1

    return {key: value for key, value in mix.items() if value}

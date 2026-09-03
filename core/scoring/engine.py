"""The deterministic scoring engine — fix item 1.

Pure functions, zero database access, `Decimal` throughout. This is the only
place in RubriQ where a mark is calculated: not the UI, not the exporters, not
the reports page. Fix item 1's fix is stated as *"one entry point"*, and
:func:`compute_score_sheet` is it.

**Two scales, reconciled.** §5 gives ``base_total = Σ (score / max_score) *
weight`` — with weights summing to 100 that is a *percentage*. §5.1 then takes
penalties as a share "of milestone max marks", and fix item 1 says a bad weight
sum leaves ``base_total`` "silently not out of ``max_marks``". Those only agree
if the weighted percentage is scaled onto the milestone's marks, so that is
what happens here:

    weighted_percent = Σ (score / max_score) * weight        # 0 … 100
    base_total       = weighted_percent × max_marks ÷ 100    # 0 … max_marks
    penalty          = band_percent     × max_marks ÷ 100
    final_total      = max(0, base_total − penalty)

Everything downstream — grid, exports, reports — is therefore out of
``max_marks``, and nothing has to remember which scale it is holding.

**Rounding happens once**, at the end, half-up. Intermediate arithmetic keeps
full `Decimal` precision, so 19.999999 never reaches a mark sheet and two
different callers cannot round differently and disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from core.clock import ist_date
from core.errors import ValidationError
from core.scoring.policy import DEFAULT_LATE_POLICY, AttendanceStatus, LatePolicy

#: Marks are stored to two decimal places (see ``Numeric(6, 2)`` on the models).
QUANTUM = Decimal("0.01")

#: Weights are a share of 100. Enforced here as well as at rubric publish,
#: because this function is reachable from a stored rubric that was published
#: before a later rule change.
REQUIRED_TOTAL_WEIGHT = Decimal("100")


def money(value: Decimal) -> Decimal:
    """Round half-up to two places. The single rounding boundary."""
    return value.quantize(QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class CriterionScoreInput:
    """One criterion's mark, with the rubric facts needed to weigh it."""

    code: str
    score: Decimal
    max_score: Decimal
    weight: Decimal


@dataclass(frozen=True, slots=True)
class ScoreSheetResult:
    """The computed sheet. Every number is out of ``max_marks``."""

    max_marks: Decimal
    weighted_percent: Decimal
    base_total: Decimal
    penalty: Decimal
    final_total: Decimal
    days_late: int
    attendance: AttendanceStatus
    penalty_percent: Decimal
    needs_reinstatement: bool
    reinstated: bool

    @property
    def is_absent(self) -> bool:
        return self.attendance is AttendanceStatus.ABSENT

    @property
    def display_total(self) -> str:
        """What a human should read.

        ``ABSENT`` never renders as a number anywhere, Excel included — that is
        fix item 10, and putting it here means the grid, the exporters and the
        student's feedback page cannot each decide differently.
        """
        return "ABSENT" if self.is_absent else f"{self.final_total}"


def days_late(due_at: datetime, submitted_at: datetime) -> int:
    """Whole calendar days late, counted in IST.

    §5.1 computes this on the *date* in ``Asia/Kolkata`` precisely so the
    11:59 PM boundary is unarguable: a submission at 23:59 IST on the due date
    is not late, one at 00:01 IST the next morning is one day late. Both sides
    are converted before subtracting — comparing a UTC instant against an IST
    date is the first failure fix item 1 names.

    Never negative: submitting early is not "minus two days late".
    """
    difference = (ist_date(submitted_at) - ist_date(due_at)).days
    return max(0, difference)


def weighted_percent(scores: list[CriterionScoreInput]) -> Decimal:
    """``Σ (score / max_score) * weight`` — a percentage, 0 … 100.

    Refuses a rubric whose weights do not sum to 100. Without that check the
    result is silently out of the wrong denominator, which fix item 1 names as
    the way a whole cohort's marks quietly shift.
    """
    if not scores:
        raise ValidationError("Cannot score a submission with no criteria.")

    total_weight = sum((s.weight for s in scores), Decimal("0"))
    if total_weight != REQUIRED_TOTAL_WEIGHT:
        raise ValidationError(
            f"Criterion weights sum to {total_weight}, not {REQUIRED_TOTAL_WEIGHT}. "
            "The total would not be out of the milestone's max marks."
        )

    earned = Decimal("0")
    for entry in scores:
        if entry.max_score <= 0:
            raise ValidationError(f"{entry.code}: max score must be greater than zero.")
        if entry.score < 0:
            raise ValidationError(f"{entry.code}: score cannot be negative.")
        if entry.score > entry.max_score:
            raise ValidationError(
                f"{entry.code}: score {entry.score} exceeds its maximum "
                f"{entry.max_score}."
            )

        earned += (entry.score / entry.max_score) * entry.weight

    return earned


def compute_score_sheet(
    scores: list[CriterionScoreInput],
    *,
    max_marks: Decimal,
    due_at: datetime,
    submitted_at: datetime,
    policy: LatePolicy | None = None,
    reinstated: bool = False,
) -> ScoreSheetResult:
    """The one entry point. Nothing else in RubriQ does mark arithmetic.

    ``reinstated`` is the faculty override from §5.1: it zeroes the penalty for
    a submission that would otherwise be absent. It does not erase the history —
    the status stays ``REINSTATED`` so a report can still show what happened.
    """
    if max_marks <= 0:
        raise ValidationError("Milestone max marks must be greater than zero.")

    policy = policy or DEFAULT_LATE_POLICY

    late_days = days_late(due_at, submitted_at)
    band = policy.band_for(late_days)

    percent = weighted_percent(scores)
    base = percent * max_marks / Decimal("100")

    if reinstated:
        # Reinstatement zeroes the penalty, whatever band applied.
        penalty = Decimal("0")
        attendance = AttendanceStatus.REINSTATED
    elif band.absent:
        # Recorded 0 — but as a *status*, not as a mark someone earned.
        penalty = base
        attendance = AttendanceStatus.ABSENT
    else:
        penalty = band.percent * max_marks / Decimal("100")
        attendance = AttendanceStatus.LATE if late_days > 0 else AttendanceStatus.PRESENT

    final = base - penalty
    if final < 0:
        final = Decimal("0")  # §5.1: never negative

    result = ScoreSheetResult(
        max_marks=money(max_marks),
        weighted_percent=money(percent),
        base_total=money(base),
        penalty=money(penalty),
        final_total=money(final),
        days_late=late_days,
        attendance=attendance,
        penalty_percent=band.percent,
        needs_reinstatement=band.needs_reinstatement and not reinstated,
        reinstated=reinstated,
    )

    # Asserted, not assumed — fix item 1 asks for exactly this.
    assert result.final_total >= 0, "final_total went negative"
    assert result.final_total <= result.max_marks, "final_total exceeded max_marks"

    return result

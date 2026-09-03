"""The late and absence policy from §5.1.

Data, not logic. :mod:`core.scoring.engine` applies it; this module only says
what it is, so a subject-specific override is a different table of bands rather
than a different code path.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from core.errors import ValidationError


class AttendanceStatus(StrEnum):
    """How a submission is *recorded*, which is not the same as its mark.

    §5.1: *"Absence is a status, not a zero. Reports must distinguish 'absent'
    from 'attempted, scored 0'."* That distinction is the reason this enum
    exists at all, and fix item 10 requires it never render as a number —
    including in Excel.
    """

    PRESENT = "PRESENT"
    LATE = "LATE"
    ABSENT = "ABSENT"

    #: Absent, then explicitly reinstated by a faculty member with a reason.
    #: The penalty is zeroed but the history stays visible (fix item 10).
    REINSTATED = "REINSTATED"


@dataclass(frozen=True, slots=True)
class PenaltyBand:
    """One row of §5.1's table.

    ``percent`` is a share of the milestone's max marks, not of the score the
    student earned — §5.1: *"Penalty applies to the milestone total, never to
    individual criteria."*
    """

    min_days: int
    max_days: int | None  # None means unbounded
    percent: Decimal
    absent: bool = False
    needs_reinstatement: bool = False

    def covers(self, days: int) -> bool:
        if days < self.min_days:
            return False
        return self.max_days is None or days <= self.max_days


@dataclass(frozen=True, slots=True)
class LatePolicy:
    """An ordered set of bands. The first one that covers the day count wins."""

    bands: tuple[PenaltyBand, ...]

    def band_for(self, days_late: int) -> PenaltyBand:
        for band in self.bands:
            if band.covers(days_late):
                return band

        raise ValidationError(
            f"No penalty band covers {days_late} days late. The policy has a "
            "gap — every day count must map to exactly one outcome."
        )

    def to_rules(self) -> dict[str, Any]:
        """Serialise for ``LatePolicy.rules``."""
        return {
            "bands": [
                {
                    "min_days": b.min_days,
                    "max_days": b.max_days,
                    "percent": str(b.percent),
                    "absent": b.absent,
                    "needs_reinstatement": b.needs_reinstatement,
                }
                for b in self.bands
            ]
        }

    @classmethod
    def from_rules(cls, rules: dict[str, Any] | None) -> LatePolicy:
        """Rebuild from a stored JSON payload, falling back to the default."""
        if not rules or not rules.get("bands"):
            return DEFAULT_LATE_POLICY

        return cls(
            bands=tuple(
                PenaltyBand(
                    min_days=int(b["min_days"]),
                    max_days=None if b.get("max_days") is None else int(b["max_days"]),
                    # str() first: Decimal(0.1) is not 0.1, and these decide marks.
                    percent=Decimal(str(b["percent"])),
                    absent=bool(b.get("absent", False)),
                    needs_reinstatement=bool(b.get("needs_reinstatement", False)),
                )
                for b in rules["bands"]
            )
        )


#: §5.1's table, verbatim. The test suite drives every row of it.
DEFAULT_LATE_POLICY = LatePolicy(
    bands=(
        PenaltyBand(min_days=0, max_days=0, percent=Decimal("0")),
        PenaltyBand(min_days=1, max_days=1, percent=Decimal("10")),
        PenaltyBand(min_days=2, max_days=2, percent=Decimal("20")),
        PenaltyBand(min_days=3, max_days=3, percent=Decimal("35")),
        PenaltyBand(
            min_days=4,
            max_days=5,
            percent=Decimal("100"),
            absent=True,
        ),
        PenaltyBand(
            min_days=6,
            max_days=None,
            percent=Decimal("100"),
            absent=True,
            needs_reinstatement=True,
        ),
    )
)

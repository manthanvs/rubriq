"""Submission lifecycle status.

Deliberately **not** where lateness lives. `LATE` and `ABSENT` are functions of
``due_at`` and ``submitted_at``, computed by ``core/scoring/`` in Phase 4 from
the IST calendar date on both sides (§5.1). Storing them here would create a
second source of truth that drifts the moment a deadline is corrected — which
is the first failure fix item 1 names.

What *is* stored is the thing that cannot be derived from a timestamp: whether
this version is the one currently standing.
"""

from __future__ import annotations

from enum import StrEnum


class SubmissionStatus(StrEnum):
    """Where a submission version sits in its own history."""

    #: The latest version for this student and milestone.
    SUBMITTED = "SUBMITTED"

    #: A newer version exists. Kept and still retrievable (invariant #7); this
    #: is what lets the Phase 4 grid warn that it is grading a stale version
    #: rather than silently rebinding to the new one (fix item 2).
    SUPERSEDED = "SUPERSEDED"

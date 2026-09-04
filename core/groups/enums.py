"""Group lifecycle.

Separate from ``core/db/models.py`` so the models module can import it without
a cycle — the same arrangement ``SubmissionStatus`` and the scoring enums use.
"""

from __future__ import annotations

from enum import StrEnum


class GroupStatus(StrEnum):
    """Where a project group sits.

    Decision #5: **a group exists only under faculty grant.** Students may ask
    for one, and asking is recorded — but ``REQUESTED`` confers nothing. Every
    query that widens a student's visibility to their group's work filters on
    ``GRANTED``, so a pending request cannot leak one student's submission to
    another.

    ``REJECTED`` is a state rather than a deletion (invariant #7): a student who
    was refused a group should be able to see that they were, and why.
    """

    REQUESTED = "REQUESTED"
    GRANTED = "GRANTED"
    REJECTED = "REJECTED"

    @property
    def confers_access(self) -> bool:
        """Whether membership of a group in this state lets a member see its work.

        One property, read by the scoping subquery, so "granted means visible"
        is stated once rather than re-derived at each call site.
        """
        return self is GroupStatus.GRANTED

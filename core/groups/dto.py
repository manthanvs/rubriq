"""Plain values returned by the group services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.groups.enums import GroupStatus


@dataclass(frozen=True, slots=True)
class GroupMemberDTO:
    student_email: str
    student_name: str
    prn: str | None
    github_username: str | None

    @property
    def label(self) -> str:
        return f"{self.student_name or self.student_email} ({self.prn or '—'})"


@dataclass(frozen=True, slots=True)
class GroupDTO:
    """One project group and everyone in it."""

    id: int
    subject_id: int
    name: str
    status: GroupStatus
    requested_by: str | None
    requested_at: datetime | None
    decided_by: str | None
    decided_at: datetime | None
    decision_note: str | None
    members: tuple[GroupMemberDTO, ...]

    @property
    def is_granted(self) -> bool:
        return self.status is GroupStatus.GRANTED

    @property
    def is_pending(self) -> bool:
        return self.status is GroupStatus.REQUESTED

    @property
    def member_emails(self) -> tuple[str, ...]:
        return tuple(m.student_email for m in self.members)

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def status_label(self) -> str:
        """One renderer, so the two roles cannot describe a group differently."""
        if self.status is GroupStatus.GRANTED:
            return "Granted"
        if self.status is GroupStatus.REQUESTED:
            return "Awaiting approval"
        return "Not approved"

    @property
    def github_profiles(self) -> dict[str, str | None]:
        """Email → registered GitHub account, for the link ownership check.

        Built here rather than in the submission service so there is one
        definition of "whose repositories may this group submit" (decision #6).
        """
        return {m.student_email: m.github_username for m in self.members}

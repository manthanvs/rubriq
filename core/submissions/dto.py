"""Plain values returned by the submission services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.submissions.status import SubmissionStatus


@dataclass(frozen=True, slots=True)
class SubmissionFileDTO:
    id: int
    filename: str
    size_bytes: int
    sha256: str
    extracted_chars: int
    extract_note: str | None

    @property
    def extraction_failed(self) -> bool:
        return self.extracted_chars == 0 and bool(self.extract_note)


@dataclass(frozen=True, slots=True)
class SubmissionLinkDTO:
    """A repository URL that passed the ownership check (decision #6).

    ``matched_profile`` records *whose* registered account allowed it — the
    submitter's own, or a granted group-mate's. Keeping it means "why was this
    accepted" is answerable later without re-parsing a string.
    """

    id: int
    url: str
    normalised_url: str
    owner: str
    repo: str
    ref: str | None
    matched_profile: str

    @property
    def label(self) -> str:
        return f"{self.owner}/{self.repo}" + (f" @ {self.ref}" if self.ref else "")


@dataclass(frozen=True, slots=True)
class SubmissionDTO:
    """One submission version.

    Carries the *size* of the extracted text rather than the text itself:
    listing ten submissions should not drag ten documents through memory. Use
    ``get_submission_text`` when the text is actually wanted.
    """

    id: int
    milestone_id: int
    student_email: str
    student_name: str
    prn: str | None
    version: int
    status: SubmissionStatus
    submitted_at: datetime
    text_extract_chars: int
    note: str | None
    files: tuple[SubmissionFileDTO, ...]
    links: tuple[SubmissionLinkDTO, ...] = ()

    #: Set when this submission is a granted group's work (decision #5).
    group_id: int | None = None
    group_name: str | None = None

    @property
    def is_group_work(self) -> bool:
        return self.group_id is not None

    @property
    def is_latest(self) -> bool:
        return self.status is SubmissionStatus.SUBMITTED

    @property
    def has_text(self) -> bool:
        """Whether anything downstream can read this submission.

        A submission with files but no text is a scanned PDF: gradeable by
        hand, invisible to the Phase 5 evidence guard.
        """
        return self.text_extract_chars > 0

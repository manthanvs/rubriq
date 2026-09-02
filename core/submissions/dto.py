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

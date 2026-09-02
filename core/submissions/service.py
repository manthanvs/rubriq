"""Submission versioning — the schema half of fix item 2.

Re-uploading never overwrites. It creates ``version + 1`` and marks the
previous version ``SUPERSEDED``, so v1 stays retrievable, still bound to its
own text and its own files. That is what lets Phase 4 warn a grader that a
newer version exists rather than silently rebinding an approval to work the
faculty member never read.

Enforcement of *which* version may be graded belongs to Phases 4 and 5b. What
lands here is the guarantee those phases rely on: versions are immutable, and
``(milestone_id, student_email, version)`` is unique in the database, not just
in intention.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.academics.milestones import get_milestone
from core.audit import record
from core.auth.actor import Actor
from core.clock import utc_now
from core.db.models import Submission, SubmissionFile, User
from core.errors import NotAuthorized, ValidationError
from core.submissions.dto import SubmissionDTO, SubmissionFileDTO
from core.submissions.extract import (
    ALLOWED_EXTENSIONS,
    combine,
    extension_of,
    extract_text,
)
from core.submissions.status import SubmissionStatus
from core.submissions.storage import save_files

#: Matches .streamlit/config.toml's maxUploadSize. Checked here too, because
#: the Streamlit limit is a UI convenience and this is the actual rule.
MAX_FILE_BYTES = 25 * 1024 * 1024

MAX_FILES_PER_SUBMISSION = 10


def _file_dto(row: SubmissionFile) -> SubmissionFileDTO:
    return SubmissionFileDTO(
        id=row.id,
        filename=row.filename,
        size_bytes=row.size_bytes,
        sha256=row.sha256,
        extracted_chars=row.extracted_chars,
        extract_note=row.extract_note,
    )


def _dto(session: Session, submission: Submission) -> SubmissionDTO:
    files = session.scalars(
        select(SubmissionFile)
        .where(SubmissionFile.submission_id == submission.id)
        .order_by(SubmissionFile.id)
    ).all()

    student = session.get(User, submission.student_email)

    return SubmissionDTO(
        id=submission.id,
        milestone_id=submission.milestone_id,
        student_email=submission.student_email,
        student_name=(student.name if student else "") or "",
        prn=student.prn if student else None,
        version=submission.version,
        status=submission.status,
        submitted_at=submission.submitted_at,
        text_extract_chars=len(submission.text_extract or ""),
        note=submission.note,
        files=tuple(_file_dto(f) for f in files),
    )


def _assert_can_see(actor: Actor, student_email: str) -> None:
    """A student may only ever address their own work (invariant #6)."""
    if actor.is_student and student_email != actor.email:
        raise NotAuthorized("You can only view your own submissions.")


# -- writes --------------------------------------------------------------


def submit(
    actor: Actor,
    session: Session,
    *,
    milestone_id: int,
    files: dict[str, bytes],
    uploads_root: Path,
    note: str | None = None,
) -> SubmissionDTO:
    """Store a new submission version for the acting student.

    ``get_milestone`` does the authorisation: for a student it returns only
    milestones that are published *and* belong to a subject they are enrolled
    in, so submitting to someone else's milestone fails before any file is
    written.
    """
    if not actor.is_student:
        raise NotAuthorized("Only students submit work.")

    get_milestone(actor, session, milestone_id)

    if not files:
        raise ValidationError("Attach at least one file.")
    if len(files) > MAX_FILES_PER_SUBMISSION:
        raise ValidationError(f"At most {MAX_FILES_PER_SUBMISSION} files per submission.")

    for filename, data in files.items():
        suffix = extension_of(filename)
        if suffix not in ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
            raise ValidationError(f"{filename}: only {allowed} are accepted.")
        if len(data) > MAX_FILE_BYTES:
            raise ValidationError(
                f"{filename} is {len(data) // (1024 * 1024)} MB; the limit is "
                f"{MAX_FILE_BYTES // (1024 * 1024)} MB."
            )
        if not data:
            raise ValidationError(f"{filename} is empty.")

    highest = session.scalar(
        select(func.max(Submission.version)).where(
            Submission.milestone_id == milestone_id,
            Submission.student_email == actor.email,
        )
    )
    version = (highest or 0) + 1

    # Demote the previous versions first, so at no point do two rows claim to
    # be the live one.
    previous = session.scalars(
        select(Submission).where(
            Submission.milestone_id == milestone_id,
            Submission.student_email == actor.email,
            Submission.status == SubmissionStatus.SUBMITTED,
        )
    ).all()
    for row in previous:
        row.status = SubmissionStatus.SUPERSEDED

    extractions = {name: extract_text(name, data) for name, data in files.items()}
    stored = save_files(
        uploads_root,
        milestone_id=milestone_id,
        student_email=actor.email,
        version=version,
        files=files,
    )

    submission = Submission(
        milestone_id=milestone_id,
        student_email=actor.email,
        version=version,
        status=SubmissionStatus.SUBMITTED,
        submitted_at=utc_now(),
        text_extract=combine(extractions),
        note=(note or "").strip() or None,
    )
    session.add(submission)
    session.flush()

    for record_file in stored:
        result = extractions[record_file.original_name]
        session.add(
            SubmissionFile(
                submission_id=submission.id,
                filename=record_file.original_name,
                stored_path=record_file.stored_path,
                content_type=extension_of(record_file.original_name),
                size_bytes=record_file.size_bytes,
                sha256=record_file.sha256,
                extracted_chars=result.char_count,
                extract_note=result.note or None,
            )
        )

    session.flush()

    record(
        session,
        actor_email=actor.email,
        action="submission.created",
        entity="Submission",
        entity_id=submission.id,
        payload={
            "milestone_id": milestone_id,
            "version": version,
            "files": len(stored),
            "extracted_chars": len(submission.text_extract),
        },
    )

    return _dto(session, submission)


# -- reads ---------------------------------------------------------------


def list_submissions(
    actor: Actor,
    session: Session,
    *,
    milestone_id: int,
    student_email: str | None = None,
) -> tuple[SubmissionDTO, ...]:
    """Submission versions for a milestone, newest first.

    A student sees their own history and nothing else, whatever they pass as
    ``student_email``.
    """
    get_milestone(actor, session, milestone_id)

    target = actor.email if actor.is_student else student_email
    if target is not None:
        _assert_can_see(actor, target)

    query = select(Submission).where(Submission.milestone_id == milestone_id)
    if target is not None:
        query = query.where(Submission.student_email == target)

    rows = session.scalars(
        query.order_by(Submission.student_email, Submission.version.desc())
    ).all()

    return tuple(_dto(session, row) for row in rows)


def latest_submission(
    actor: Actor, session: Session, *, milestone_id: int, student_email: str
) -> SubmissionDTO | None:
    """The version currently standing, or None if nothing was submitted."""
    get_milestone(actor, session, milestone_id)
    _assert_can_see(actor, student_email)

    row = session.scalars(
        select(Submission)
        .where(
            Submission.milestone_id == milestone_id,
            Submission.student_email == student_email,
        )
        .order_by(Submission.version.desc())
        .limit(1)
    ).first()

    return None if row is None else _dto(session, row)


def get_submission(actor: Actor, session: Session, submission_id: int) -> SubmissionDTO:
    """One specific version — including superseded ones (invariant #7)."""
    submission = session.get(Submission, submission_id)
    if submission is None:
        raise NotAuthorized("That submission does not exist, or is not yours.")

    get_milestone(actor, session, submission.milestone_id)
    _assert_can_see(actor, submission.student_email)

    return _dto(session, submission)


def get_submission_text(actor: Actor, session: Session, submission_id: int) -> str:
    """The extracted text for one version, fetched only when wanted."""
    submission = session.get(Submission, submission_id)
    if submission is None:
        raise NotAuthorized("That submission does not exist, or is not yours.")

    get_milestone(actor, session, submission.milestone_id)
    _assert_can_see(actor, submission.student_email)

    return submission.text_extract or ""

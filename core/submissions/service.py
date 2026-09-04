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

Phase 8 adds two things without disturbing that:

* **Groups (decision #5).** When the submitter belongs to a *granted* group,
  the submission is the group's: versions are numbered per group rather than
  per student, and every member reads the same row. ``student_email`` remains
  the uploader, so "who pressed submit" survives. A group that has only been
  *requested* changes nothing — that is the whole gate.
* **Repository links (decision #6).** A GitHub URL is accepted only when its
  owner matches a profile faculty recorded, and it is stored as an artifact.
  Nothing fetches it; evidence still has to be in the document.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from core.academics.milestones import get_milestone
from core.audit import record
from core.auth.actor import Actor
from core.clock import utc_now
from core.db.models import (
    ProjectGroup,
    Submission,
    SubmissionFile,
    SubmissionLink,
    User,
)
from core.errors import NotAuthorized, ValidationError
from core.groups.dto import GroupDTO
from core.groups.service import granted_group_for, granted_group_ids_for
from core.submissions.dto import (
    SubmissionDTO,
    SubmissionFileDTO,
    SubmissionLinkDTO,
)
from core.submissions.extract import (
    ALLOWED_EXTENSIONS,
    combine,
    extension_of,
    extract_text,
)
from core.submissions.links import GitHubRef, assert_owned, parse_github_url
from core.submissions.status import SubmissionStatus
from core.submissions.storage import save_files

#: Matches .streamlit/config.toml's maxUploadSize. Checked here too, because
#: the Streamlit limit is a UI convenience and this is the actual rule.
MAX_FILE_BYTES = 25 * 1024 * 1024

MAX_FILES_PER_SUBMISSION = 10

#: More than this and it is not a project, it is a reading list.
MAX_LINKS_PER_SUBMISSION = 5


def _file_dto(row: SubmissionFile) -> SubmissionFileDTO:
    return SubmissionFileDTO(
        id=row.id,
        filename=row.filename,
        size_bytes=row.size_bytes,
        sha256=row.sha256,
        extracted_chars=row.extracted_chars,
        extract_note=row.extract_note,
    )


def _link_dto(row: SubmissionLink) -> SubmissionLinkDTO:
    return SubmissionLinkDTO(
        id=row.id,
        url=row.url,
        normalised_url=row.normalised_url,
        owner=row.owner,
        repo=row.repo,
        ref=row.ref,
        matched_profile=row.matched_profile,
    )


def _dto(session: Session, submission: Submission) -> SubmissionDTO:
    files = session.scalars(
        select(SubmissionFile)
        .where(SubmissionFile.submission_id == submission.id)
        .order_by(SubmissionFile.id)
    ).all()

    links = session.scalars(
        select(SubmissionLink)
        .where(SubmissionLink.submission_id == submission.id)
        .order_by(SubmissionLink.id)
    ).all()

    group_name = None
    if submission.group_id is not None:
        group_name = session.scalar(
            select(ProjectGroup.name).where(ProjectGroup.id == submission.group_id)
        )

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
        links=tuple(_link_dto(link) for link in links),
        group_id=submission.group_id,
        group_name=group_name,
    )


def _assert_can_see(
    actor: Actor,
    student_email: str,
    *,
    session: Session | None = None,
    group_id: int | None = None,
) -> None:
    """A student may address their own work, or their granted group's.

    Invariant #6 with decision #5's single exception, written in one place.
    The exception is narrow on purpose: it needs a group id on the row *and*
    a granted membership for the actor. A requested group has neither, so a
    pending request cannot show anyone anything.
    """
    if not actor.is_student or student_email == actor.email:
        return

    if session is not None and group_id is not None:
        member = session.scalar(
            select(ProjectGroup.id).where(
                ProjectGroup.id == group_id,
                ProjectGroup.id.in_(granted_group_ids_for(actor.email)),
            )
        )
        if member is not None:
            return

    raise NotAuthorized("You can only view your own submissions.")


def _check_links(
    session: Session,
    *,
    actor: Actor,
    group: GroupDTO | None,
    links: list[str],
) -> list[tuple[GitHubRef, str]]:
    """Parse each URL and bind it to a registered profile, or refuse it.

    The profiles come from the database — the submitter's own, plus every
    granted group-mate's — never from anything the student supplied alongside
    the URL. A check whose reference value is provided by the party being
    checked is not a check (decision #6).
    """
    if not links:
        return []

    me = session.get(User, actor.email)
    profiles: dict[str, str | None] = {actor.email: me.github_username if me else None}
    if group is not None:
        profiles.update(group.github_profiles)

    accepted: list[tuple[GitHubRef, str]] = []
    seen: set[str] = set()

    for raw in links:
        ref = parse_github_url(raw)
        if ref.normalised_url in seen:
            raise ValidationError(f"{ref.label} is listed twice.")
        seen.add(ref.normalised_url)
        accepted.append((ref, assert_owned(ref, profiles)))

    return accepted


# -- writes --------------------------------------------------------------


def submit(
    actor: Actor,
    session: Session,
    *,
    milestone_id: int,
    files: dict[str, bytes],
    uploads_root: Path,
    note: str | None = None,
    links: list[str] | None = None,
) -> SubmissionDTO:
    """Store a new submission version for the acting student, or their group.

    ``get_milestone`` does the authorisation: for a student it returns only
    milestones that are published *and* belong to a subject they are enrolled
    in, so submitting to someone else's milestone fails before any file is
    written.

    If the student belongs to a **granted** group for the subject, the row is
    the group's: it carries ``group_id``, its version follows the group's
    history rather than this student's, and every member reads it. A pending
    request is not a group and changes nothing here.

    ``links`` are GitHub repository URLs. Each is parsed and checked against
    the GitHub accounts faculty recorded for the submitter — plus, for a group
    submission, their granted group-mates. A URL owned by anybody else is
    refused before a single file is written.
    """
    if not actor.is_student:
        raise NotAuthorized("Only students submit work.")

    milestone = get_milestone(actor, session, milestone_id)
    group = granted_group_for(
        actor, session, subject_id=milestone.subject_id, student_email=actor.email
    )

    links = [raw for raw in (links or []) if (raw or "").strip()]

    if not files and not links:
        raise ValidationError("Attach at least one file, or add a repository link.")
    if len(files) > MAX_FILES_PER_SUBMISSION:
        raise ValidationError(f"At most {MAX_FILES_PER_SUBMISSION} files per submission.")
    if len(links) > MAX_LINKS_PER_SUBMISSION:
        raise ValidationError(f"At most {MAX_LINKS_PER_SUBMISSION} links per submission.")

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

    # Checked before any file lands on disk, so a refused link leaves nothing
    # behind to clean up.
    accepted_links = _check_links(session, actor=actor, group=group, links=links)

    # Version numbering follows whoever owns the work. For a group that is the
    # group: if it were per student, two members would each create a "v1" and
    # "which version was graded" would stop having an answer.
    #
    # The uploader's own earlier rows are included as well, and that is not
    # belt-and-braces. A student can submit individually and *then* have their
    # group granted; those earlier rows carry no group_id, so numbering purely
    # by group would restart at 1 and collide with their existing v1 on
    # ``uq_submission_student_version``. Taking the union keeps versions
    # monotonic across that transition.
    scope = (
        or_(
            Submission.group_id == group.id,
            Submission.student_email == actor.email,
        )
        if group is not None
        else Submission.student_email == actor.email
    )

    highest = session.scalar(
        select(func.max(Submission.version)).where(
            Submission.milestone_id == milestone_id, scope
        )
    )
    version = (highest or 0) + 1

    # Demote the previous versions first, so at no point do two rows claim to
    # be the live one.
    previous = session.scalars(
        select(Submission).where(
            Submission.milestone_id == milestone_id,
            scope,
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
        group_id=group.id if group is not None else None,
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

    for ref, owner_email in accepted_links:
        session.add(
            SubmissionLink(
                submission_id=submission.id,
                url=ref.url,
                normalised_url=ref.normalised_url,
                owner=ref.owner,
                repo=ref.repo,
                ref=ref.ref,
                matched_profile=owner_email,
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
            "links": [ref.normalised_url for ref, _ in accepted_links],
            "group_id": submission.group_id,
            "extracted_chars": len(submission.text_extract),
        },
    )

    return _dto(session, submission)


# -- reads ---------------------------------------------------------------


def _belongs_to(session: Session, student_email: str):
    """A predicate for "submissions that count as this student's".

    Their own rows, plus the rows of any group they are a *granted* member of.
    Group ids are not filtered by subject here because they do not need to be:
    every caller also filters by ``milestone_id``, and a milestone belongs to
    exactly one subject, so a group from elsewhere can never match.
    """
    group_ids = list(session.scalars(granted_group_ids_for(student_email)).all())

    if not group_ids:
        return Submission.student_email == student_email

    return or_(
        Submission.student_email == student_email,
        Submission.group_id.in_(group_ids),
    )


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

    query = select(Submission).where(Submission.milestone_id == milestone_id)
    if target is not None:
        # Group-aware: a member sees the version their group-mate uploaded,
        # because it is the group's submission and therefore theirs.
        query = query.where(_belongs_to(session, target))

    rows = session.scalars(
        query.order_by(Submission.student_email, Submission.version.desc())
    ).all()

    return tuple(_dto(session, row) for row in rows)


def latest_submission(
    actor: Actor, session: Session, *, milestone_id: int, student_email: str
) -> SubmissionDTO | None:
    """The version currently standing, or None if nothing was submitted."""
    get_milestone(actor, session, milestone_id)
    if actor.is_student and student_email != actor.email:
        raise NotAuthorized("You can only view your own submissions.")

    row = session.scalars(
        select(Submission)
        .where(
            Submission.milestone_id == milestone_id,
            _belongs_to(session, student_email),
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
    _assert_can_see(
        actor,
        submission.student_email,
        session=session,
        group_id=submission.group_id,
    )

    return _dto(session, submission)


def get_submission_text(actor: Actor, session: Session, submission_id: int) -> str:
    """The extracted text for one version, fetched only when wanted."""
    submission = session.get(Submission, submission_id)
    if submission is None:
        raise NotAuthorized("That submission does not exist, or is not yours.")

    get_milestone(actor, session, submission.milestone_id)
    _assert_can_see(
        actor,
        submission.student_email,
        session=session,
        group_id=submission.group_id,
    )

    return submission.text_extract or ""

"""Enrollment, and the CSV import that fix item 7 is about.

The failure it names: *"A 40-row CSV imports 31 rows and reports success."*

So the import is two calls, not one. :func:`preview_enrollment_import` parses
and validates and writes nothing; :func:`commit_enrollment_import` re-parses
from the same text and writes. Nothing is committed that the faculty member
has not already seen a verdict for, and the summary afterwards names every
row that did not land.

``commit`` deliberately re-validates from the raw text rather than trusting a
preview object handed back to it. A preview is a snapshot; between rendering
it and clicking the button, another import may have enrolled the same student
(fix item 14: re-read before writing).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.academics.access import require_faculty
from core.academics.dto import EnrollmentDTO
from core.academics.subjects import get_subject
from core.audit import record
from core.auth.actor import Actor
from core.auth.domain import assert_allowed_domain, normalise_email
from core.auth.roles import Role, resolve_role
from core.clock import utc_now
from core.config import Settings
from core.db.models import Enrollment, User
from core.errors import AuthError, ValidationError

REQUIRED_HEADERS = ("email", "name", "prn")
OPTIONAL_HEADERS = ("batch", "group_label")

#: Offered as a download from the import page, so nobody has to guess.
TEMPLATE_CSV = (
    "email,name,prn,batch,group_label\n"
    "student.one@pccoepune.org,Student One,125M1H001,A,G1\n"
    "student.two@pccoepune.org,Student Two,125M1H002,A,G1\n"
)


class ImportVerdict(StrEnum):
    """What will happen to one row. Shown per row, before anything commits."""

    NEW = "NEW"
    ALREADY_ENROLLED = "ALREADY_ENROLLED"
    INVALID_DOMAIN = "INVALID_DOMAIN"
    MALFORMED = "MALFORMED"
    DUPLICATE_IN_FILE = "DUPLICATE_IN_FILE"
    FACULTY_ADDRESS = "FACULTY_ADDRESS"


#: The only verdict that results in a write.
COMMITTABLE = frozenset({ImportVerdict.NEW})


@dataclass(frozen=True, slots=True)
class ImportRow:
    line_number: int
    email: str
    name: str
    prn: str
    batch: str
    group_label: str
    verdict: ImportVerdict
    message: str

    @property
    def is_committable(self) -> bool:
        return self.verdict in COMMITTABLE


@dataclass(frozen=True, slots=True)
class ImportPreview:
    """The result of a dry run. Holds no session and writes nothing."""

    rows: tuple[ImportRow, ...]

    @property
    def committable(self) -> tuple[ImportRow, ...]:
        return tuple(row for row in self.rows if row.is_committable)

    @property
    def rejected(self) -> tuple[ImportRow, ...]:
        return tuple(row for row in self.rows if not row.is_committable)

    @property
    def counts(self) -> dict[ImportVerdict, int]:
        tally = dict.fromkeys(ImportVerdict, 0)
        for row in self.rows:
            tally[row.verdict] += 1
        return tally

    def __len__(self) -> int:
        return len(self.rows)


def _read_rows(csv_text: str) -> list[dict[str, str]]:
    """Parse the CSV, checking headers explicitly.

    A missing header is raised, not guessed at: silently importing a file
    whose columns are in a different order is worse than refusing it.
    """
    # Excel writes a BOM on "CSV UTF-8", and it lands on the first header name.
    text = csv_text.lstrip("﻿")

    reader = csv.DictReader(io.StringIO(text))
    headers = tuple(name.strip().lower() for name in (reader.fieldnames or ()))

    missing = [name for name in REQUIRED_HEADERS if name not in headers]
    if missing:
        raise ValidationError(
            f"CSV is missing required column(s): {', '.join(missing)}. "
            f"Expected headers: {', '.join(REQUIRED_HEADERS + OPTIONAL_HEADERS)}."
        )

    rows = []
    for raw in reader:
        rows.append(
            {
                (key or "").strip().lower(): (value or "").strip()
                for key, value in raw.items()
            }
        )
    return rows


def _verdict(
    fields: dict[str, object], verdict: ImportVerdict, message: str
) -> ImportRow:
    """Attach a verdict to already-extracted row fields."""
    return ImportRow(**fields, verdict=verdict, message=message)  # type: ignore[arg-type]


def preview_enrollment_import(
    actor: Actor,
    session: Session,
    *,
    subject_id: int,
    csv_text: str,
    settings: Settings,
) -> ImportPreview:
    """Validate every row against the domain rule and the current enrollments.

    Writes nothing. Re-running it is free and produces the same answer, which
    is what makes the import idempotent: a row already enrolled comes back as
    ``ALREADY_ENROLLED`` rather than being enrolled twice.
    """
    require_faculty(actor, "import enrollments")
    get_subject(actor, session, subject_id)  # authorisation, by reuse

    parsed = _read_rows(csv_text)

    existing = set(
        session.scalars(
            select(Enrollment.student_email).where(
                Enrollment.subject_id == subject_id,
                Enrollment.is_active.is_(True),
            )
        ).all()
    )

    seen_in_file: set[str] = set()
    rows: list[ImportRow] = []

    for offset, raw in enumerate(parsed):
        line_number = offset + 2  # +1 for the header, +1 for 1-based counting
        email = normalise_email(raw.get("email"))
        name = raw.get("name", "")
        prn = raw.get("prn", "")
        batch = raw.get("batch", "")
        group_label = raw.get("group_label", "")

        if not email and not name and not prn:
            continue  # a trailing blank line, not an error

        # Everything but the verdict is known now; the checks below only
        # decide which verdict to attach.
        fields = {
            "line_number": line_number,
            "email": email,
            "name": name,
            "prn": prn,
            "batch": batch,
            "group_label": group_label,
        }

        if not email:
            rows.append(_verdict(fields, ImportVerdict.MALFORMED, "No email address."))
            continue
        if not name:
            rows.append(_verdict(fields, ImportVerdict.MALFORMED, "No name."))
            continue
        if not prn:
            rows.append(_verdict(fields, ImportVerdict.MALFORMED, "No PRN."))
            continue

        try:
            assert_allowed_domain(email, settings.allowed_email_domain)
        except AuthError as exc:
            kind = (
                ImportVerdict.INVALID_DOMAIN if "@" in email else ImportVerdict.MALFORMED
            )
            rows.append(_verdict(fields, kind, str(exc)))
            continue

        role = resolve_role(email, settings.faculty_allowlist, settings.admin_allowlist)
        if role is not Role.STUDENT:
            rows.append(
                _verdict(
                    fields,
                    ImportVerdict.FACULTY_ADDRESS,
                    "On the faculty allow-list — cannot be enrolled as a student.",
                )
            )
            continue

        if email in seen_in_file:
            rows.append(
                _verdict(
                    fields,
                    ImportVerdict.DUPLICATE_IN_FILE,
                    "Appears earlier in this file.",
                )
            )
            continue

        seen_in_file.add(email)

        if email in existing:
            rows.append(
                _verdict(
                    fields,
                    ImportVerdict.ALREADY_ENROLLED,
                    "Already enrolled — no change.",
                )
            )
            continue

        rows.append(_verdict(fields, ImportVerdict.NEW, "Will be enrolled."))

    return ImportPreview(rows=tuple(rows))


def commit_enrollment_import(
    actor: Actor,
    session: Session,
    *,
    subject_id: int,
    csv_text: str,
    settings: Settings,
) -> ImportPreview:
    """Enrol every ``NEW`` row, in the caller's single transaction.

    Returns a **fresh** preview describing what was actually done, so the
    summary shown afterwards reflects the committed state rather than the
    state the page was rendering a minute ago.
    """
    require_faculty(actor, "import enrollments")

    preview = preview_enrollment_import(
        actor, session, subject_id=subject_id, csv_text=csv_text, settings=settings
    )

    now = utc_now()

    # Two passes, users first, with a flush between them.
    #
    # SQLAlchemy orders a flush by *mapper* dependency, and mapper dependencies
    # come from relationship(), not from ForeignKey columns alone. Enrollment
    # declares no relationship to User, so the unit of work does not know one
    # depends on the other and emits the inserts in table-sort order —
    # `enrollment` before `users`. The parent row does not exist yet and the
    # foreign key fails.
    #
    # Flushing the users explicitly makes the ordering ours rather than
    # SQLAlchemy's. The tests catch this only because build_engine switches
    # SQLite foreign keys on; with them off, SQLite accepts the orphaned row
    # and the roll quietly contains enrollments pointing at no user.
    for row in preview.committable:
        user = session.get(User, row.email)
        if user is None:
            session.add(
                User(
                    email=row.email,
                    role=Role.STUDENT,
                    name=row.name,
                    prn=row.prn,
                    created_at=now,
                    last_seen_at=now,
                )
            )
        else:
            if not user.name:
                user.name = row.name
            if not user.prn:
                user.prn = row.prn

    session.flush()

    for row in preview.committable:
        session.add(
            Enrollment(
                student_email=row.email,
                subject_id=subject_id,
                batch=row.batch or None,
                group_label=row.group_label or None,
            )
        )

    record(
        session,
        actor_email=actor.email,
        action="enrollment.imported",
        entity="Subject",
        entity_id=subject_id,
        payload={
            "enrolled": len(preview.committable),
            "rejected": len(preview.rejected),
            "verdicts": {str(k): v for k, v in preview.counts.items() if v},
        },
    )

    return preview


def rejected_rows_csv(preview: ImportPreview) -> str:
    """The rejected rows, as a CSV the faculty member can fix and re-upload.

    Same columns as the input plus the verdict, so correcting it is an edit
    rather than a transcription exercise.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([*REQUIRED_HEADERS, *OPTIONAL_HEADERS, "verdict", "reason"])

    for row in preview.rejected:
        writer.writerow(
            [
                row.email,
                row.name,
                row.prn,
                row.batch,
                row.group_label,
                str(row.verdict),
                row.message,
            ]
        )

    return buffer.getvalue()


def list_enrollments(
    actor: Actor, session: Session, subject_id: int
) -> tuple[EnrollmentDTO, ...]:
    """Students enrolled in one visible subject."""
    get_subject(actor, session, subject_id)

    if actor.is_student:
        raise ValidationError("Students cannot list a subject's roll.")

    rows = session.execute(
        select(Enrollment, User)
        .join(User, User.email == Enrollment.student_email)
        .where(
            Enrollment.subject_id == subject_id,
            Enrollment.is_active.is_(True),
        )
        .order_by(User.prn, User.email)
    ).all()

    return tuple(
        EnrollmentDTO(
            id=enrollment.id,
            student_email=enrollment.student_email,
            student_name=user.name,
            prn=user.prn,
            batch=enrollment.batch,
            group_label=enrollment.group_label,
        )
        for enrollment, user in rows
    )

"""ORM models.

The §4 domain model lands one phase at a time. Present here:

* ``User``            — identity and role (Phase 1)
* ``AuditLog``        — every mutation writes one row (Phase 1, read in Phase 7)
* ``Subject``         — a taught subject, owned by one faculty member (Phase 2)
* ``Enrollment``      — which student is in which subject (Phase 2)
* ``ProjectCycle``    — one run of a project through a subject (Phase 2)
* ``ReviewMilestone`` — a dated review with marks attached (Phase 2)
* ``Rubric`` / ``Criterion`` — versioned, frozen on publish (Phase 3)
* ``Submission`` / ``SubmissionFile`` — versioned student work (Phase 3)

Evaluation, CriterionScore and ScoreSheet arrive in Phases 4-5. Every entity
ships with its migration in the same commit (§12).

**Marks are ``Numeric``, never ``Float``.** Fix item 1 names float drift
rendering 19.999999 as a way score integrity breaks; the cheapest place to
prevent that is the column type, before any arithmetic exists to get wrong.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from core.auth.roles import Role
from core.clock import utc_now
from core.db.types import JSONColumn, UtcDateTime
from core.submissions.status import SubmissionStatus


class Base(DeclarativeBase):
    """Base class for all RubriQ tables."""


class User(Base):
    """A person, keyed by their institute email.

    The email *is* the primary key: it comes from the OIDC claim, it is what
    the faculty allow-list is written in, and it is what enrollment CSVs
    contain. A surrogate id would add a lookup and buy nothing.

    ``role`` is a cache of :func:`core.auth.roles.resolve_role`, refreshed on
    every sign-in. The allow-list is the authority, never this column
    (invariant #5).
    """

    __tablename__ = "users"  # "user" is a reserved word in several engines

    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    role: Mapped[Role] = mapped_column(
        Enum(Role, native_enum=False, length=16),
        nullable=False,
        default=Role.STUDENT,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    department: Mapped[str | None] = mapped_column(String(120))
    prn: Mapped[str | None] = mapped_column(String(32), index=True)
    employee_id: Mapped[str | None] = mapped_column(String(32))

    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        UtcDateTime(),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<User {self.email} {self.role}>"


class AuditLog(Base):
    """One row per mutation (§12).

    Written from Phase 1, surfaced in the UI in Phase 7 (fix item 15). It is
    what answers "how do you know the faculty member, not the AI, decided this
    mark?" — so it is populated from the beginning, not retrofitted.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(120), index=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONColumn)
    at: Mapped[datetime] = mapped_column(
        UtcDateTime(),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} {self.entity}:{self.entity_id}>"


class Subject(Base):
    """A taught subject, owned by exactly one faculty member.

    ``owner_email`` is the whole authorisation story for the teaching side:
    every faculty query in ``core/academics/`` filters on it, so a faculty
    member listing subjects gets theirs and nobody else's (invariant #6).
    """

    __tablename__ = "subject"
    __table_args__ = (UniqueConstraint("code", "semester", name="uq_subject_code_sem"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    semester: Mapped[int] = mapped_column(Integer, nullable=False)
    owner_email: Mapped[str] = mapped_column(
        String(320), ForeignKey("users.email"), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<Subject {self.code} sem{self.semester}>"


class Enrollment(Base):
    """One student in one subject.

    Deactivated rather than deleted, so a student who drops the subject does
    not take their submission history with them (invariant #7).
    """

    __tablename__ = "enrollment"
    __table_args__ = (
        UniqueConstraint("student_email", "subject_id", name="uq_enrollment_student"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_email: Mapped[str] = mapped_column(
        String(320), ForeignKey("users.email"), nullable=False, index=True
    )
    subject_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subject.id"), nullable=False, index=True
    )
    batch: Mapped[str | None] = mapped_column(String(32))
    group_label: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<Enrollment {self.student_email} -> {self.subject_id}>"


class ProjectCycle(Base):
    """One run of a project through a subject, in one academic year."""

    __tablename__ = "project_cycle"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subject.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    academic_year: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<ProjectCycle {self.title} {self.academic_year}>"


class ReviewMilestone(Base):
    """A dated review with marks attached.

    ``is_visible`` is the faculty's draft switch: an invisible milestone is
    absent from every student query, not merely hidden in the student's UI.

    ``max_marks`` is ``Numeric`` because §5.1's penalties are percentages of
    it, and a percentage of a float is how 19.999999 gets onto a mark sheet.
    """

    __tablename__ = "review_milestone"
    __table_args__ = (
        UniqueConstraint("cycle_id", "index", name="uq_milestone_cycle_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project_cycle.id"), nullable=False, index=True
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    max_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<ReviewMilestone {self.index}: {self.title}>"


class Rubric(Base):
    """A versioned rubric for one milestone. Frozen once published.

    Fix item 6 is entirely about this table. ``published_at IS NOT NULL`` makes
    the rubric and its criteria read-only at the service layer: editing a
    published rubric clones to ``version + 1`` rather than mutating in place,
    so a submission graded against v1 is still graded against exactly what its
    grader saw.

    Only a published rubric is selectable for evaluation, which stops a
    submission being scored against a half-written draft.
    """

    __tablename__ = "rubric"
    __table_args__ = (
        UniqueConstraint("milestone_id", "version", name="uq_rubric_milestone_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    milestone_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("review_milestone.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    published_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    published_by: Mapped[str | None] = mapped_column(
        String(320), ForeignKey("users.email")
    )
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=utc_now, server_default=func.now()
    )

    @property
    def is_published(self) -> bool:
        return self.published_at is not None

    def __repr__(self) -> str:
        state = "published" if self.is_published else "draft"
        return f"<Rubric m{self.milestone_id} v{self.version} {state}>"


class Criterion(Base):
    """One row of a rubric.

    ``weight`` is a share of 100 across the rubric; ``max_score`` is what the
    criterion is marked out of. §5 combines them as
    ``Σ (score / max_score) * weight``, so both are ``Numeric`` — fix item 1
    starts with the column type.

    Never deleted. A criterion dropped from a later version is deactivated on
    that version, because ``CriterionScore`` rows from earlier gradings still
    reference it (invariant #7).
    """

    __tablename__ = "criterion"
    __table_args__ = (UniqueConstraint("rubric_id", "code", name="uq_criterion_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rubric_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("rubric.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    max_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    expected_evidence: Mapped[str | None] = mapped_column(Text)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return f"<Criterion {self.code} w{self.weight}>"


class Submission(Base):
    """One version of one student's work for one milestone.

    Versioned rather than overwritten (invariant #7): re-uploading creates
    ``version + 1`` and leaves the previous row and its files intact. The
    unique constraint on ``(milestone_id, student_email, version)`` is what
    makes that provable rather than merely intended — fix item 2.

    ``text_extract`` is populated at upload so the AI layer in Phase 5 never
    touches a file, and so the evidence guard has something to fuzzy-match
    against without re-parsing a PDF.
    """

    __tablename__ = "submission"
    __table_args__ = (
        UniqueConstraint(
            "milestone_id",
            "student_email",
            "version",
            name="uq_submission_student_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    milestone_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("review_milestone.id"), nullable=False, index=True
    )
    student_email: Mapped[str] = mapped_column(
        String(320), ForeignKey("users.email"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus, native_enum=False, length=16),
        nullable=False,
        default=SubmissionStatus.SUBMITTED,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=utc_now
    )
    text_extract: Mapped[str] = mapped_column(Text, nullable=False, default="")
    note: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<Submission m{self.milestone_id} {self.student_email} v{self.version}>"


class SubmissionFile(Base):
    """One uploaded file belonging to a submission version.

    ``sha256`` is stored so a re-upload of byte-identical work is visible as
    such, and so a file on disk can be checked against what was recorded.
    Files live outside the database under ``uploads/``; the row is the record,
    the file is the payload.
    """

    __tablename__ = "submission_file"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("submission.id"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    extracted_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extract_note: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=utc_now, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<SubmissionFile {self.filename}>"

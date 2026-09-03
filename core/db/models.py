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
* ``Evaluation`` / ``CriterionScore`` — one scoring run and its rows (Phase 4)
* ``ScoreSheet`` / ``ScoreOverride`` — the approved mark and its history (Phase 4)
* ``LatePolicyRow`` — a per-subject override of §5.1 (Phase 4)
* ``StudentQuery`` — a question, its answer, and any escalation (Phase 6)

Every entity ships with its migration in the same commit (§12).

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
from core.scoring.enums import EvaluationEngine, EvaluationStatus, Verdict
from core.scoring.policy import AttendanceStatus
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

    #: Guidance the assistant may quote, and students may read. §6.7 lists it
    #: as part of the query context; anything not written here is not context,
    #: which is what keeps the assistant's world small enough to be safe.
    public_notes: Mapped[str | None] = mapped_column(Text)

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


class Evaluation(Base):
    """One scoring run over one submission version.

    **This row is where fix item 2 is enforced.** It pins its inputs: which
    submission version it read, and which rubric version it measured against.
    Without those columns, re-evaluating after a student re-uploads would
    silently rebind an approved mark to work the grader never saw.

    ``version`` increments per retry (fix item 9): a genuine retry starts a new
    evaluation with a new ``thread_id`` in Phase 5, while a browser refresh
    resumes the existing one.
    """

    __tablename__ = "evaluation"
    __table_args__ = (
        UniqueConstraint("submission_id", "version", name="uq_evaluation_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("submission.id"), nullable=False, index=True
    )
    #: Pinned, not looked up later — the submission may since have a v3.
    submission_version: Mapped[int] = mapped_column(Integer, nullable=False)
    rubric_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("rubric.id"), nullable=False, index=True
    )
    rubric_version: Mapped[int] = mapped_column(Integer, nullable=False)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    engine: Mapped[EvaluationEngine] = mapped_column(
        Enum(EvaluationEngine, native_enum=False, length=16), nullable=False
    )
    status: Mapped[EvaluationStatus] = mapped_column(
        Enum(EvaluationStatus, native_enum=False, length=16),
        nullable=False,
        default=EvaluationStatus.PENDING,
    )

    # Populated by Phase 5; null for manual scoring.
    model_name: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    graph_version: Mapped[str | None] = mapped_column(String(32))
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSONColumn)
    failure_reason: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[str] = mapped_column(
        String(320), ForeignKey("users.email"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=utc_now, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Evaluation s{self.submission_id} v{self.version} {self.status}>"


class CriterionScore(Base):
    """One criterion's mark within one evaluation.

    ``verdict`` is stored rather than derived from ``score`` (§4). A zero could
    mean "attempted and wrong" or "not present in the document at all", and the
    student's feedback page has to tell those apart.
    """

    __tablename__ = "criterion_score"
    __table_args__ = (
        UniqueConstraint("evaluation_id", "criterion_id", name="uq_criterion_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("evaluation.id"), nullable=False, index=True
    )
    criterion_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("criterion.id"), nullable=False, index=True
    )
    score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    verdict: Mapped[Verdict] = mapped_column(
        Enum(Verdict, native_enum=False, length=16), nullable=False
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    evidence_span: Mapped[str | None] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<CriterionScore c{self.criterion_id} {self.score} {self.verdict}>"


class ScoreSheet(Base):
    """The computed totals for one evaluation, and their approval.

    Points at an ``evaluation_id``, never a bare submission — fix item 2:
    *"ScoreSheet references a specific evaluation_id, never a bare
    submission."* One sheet per evaluation, enforced by the unique constraint.

    ``approved_by`` and ``approved_at`` are what make invariant #1 provable.
    Until they are set this row is an estimate, and the exporters say so.
    """

    __tablename__ = "score_sheet"
    __table_args__ = (
        UniqueConstraint("evaluation_id", name="uq_score_sheet_evaluation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("evaluation.id"), nullable=False, index=True
    )
    submission_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("submission.id"), nullable=False, index=True
    )

    max_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    weighted_percent: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    base_total: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    penalty: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    final_total: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)

    days_late: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attendance_status: Mapped[AttendanceStatus] = mapped_column(
        Enum(AttendanceStatus, native_enum=False, length=16), nullable=False
    )
    reinstated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reinstate_reason: Mapped[str | None] = mapped_column(Text)

    approved_by: Mapped[str | None] = mapped_column(
        String(320), ForeignKey("users.email")
    )
    approved_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    faculty_note: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=utc_now, server_default=func.now()
    )

    @property
    def is_approved(self) -> bool:
        return self.approved_at is not None

    def __repr__(self) -> str:
        state = "approved" if self.is_approved else "estimate"
        return f"<ScoreSheet e{self.evaluation_id} {self.final_total} {state}>"


class ScoreOverride(Base):
    """An append-only record of a faculty member changing one criterion.

    Never updated, never deleted (fix item 4): two corrections to the same
    criterion produce two rows, so the history answers who changed what, when,
    and why. ``reason`` is required, and the emptiness check lives in ``core/``
    rather than on the widget.
    """

    __tablename__ = "score_override"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    score_sheet_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("score_sheet.id"), nullable=False, index=True
    )
    criterion_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("criterion.id"), nullable=False
    )
    old_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    new_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    old_verdict: Mapped[Verdict | None] = mapped_column(
        Enum(Verdict, native_enum=False, length=16)
    )
    new_verdict: Mapped[Verdict | None] = mapped_column(
        Enum(Verdict, native_enum=False, length=16)
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    overridden_by: Mapped[str] = mapped_column(
        String(320), ForeignKey("users.email"), nullable=False
    )
    overridden_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=utc_now, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<ScoreOverride c{self.criterion_id} {self.old_score}->{self.new_score}>"


class LatePolicyRow(Base):
    """A stored override of §5.1's default bands, per subject or milestone."""

    __tablename__ = "late_policy"
    __table_args__ = (
        UniqueConstraint("scope", "scope_id", "version", name="uq_late_policy_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)  # SUBJECT | MILESTONE
    scope_id: Mapped[int] = mapped_column(Integer, nullable=False)
    rules: Mapped[dict[str, Any]] = mapped_column(JSONColumn, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=utc_now, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<LatePolicyRow {self.scope}:{self.scope_id} v{self.version}>"


class StudentQuery(Base):
    """A question a student asked, and what happened to it.

    Stored rather than ephemeral for two reasons: the faculty inbox needs
    something to pick up when an answer escalates, and a question the assistant
    refused is evidence about the rubric — several students asking the same
    unanswerable thing means the rubric does not say enough.

    ``sources`` records which parts of the context the answer drew on, so a
    student can be shown *where* an answer came from rather than being asked to
    trust it.
    """

    __tablename__ = "student_query"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_email: Mapped[str] = mapped_column(
        String(320), ForeignKey("users.email"), nullable=False, index=True
    )
    milestone_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("review_milestone.id"), index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)

    ai_answer: Mapped[str | None] = mapped_column(Text)
    sources: Mapped[list[str] | None] = mapped_column(JSONColumn)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))

    #: True when the assistant declined to answer from context alone. The
    #: faculty inbox lists exactly these (§6.4).
    escalated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    escalation_reason: Mapped[str | None] = mapped_column(Text)

    faculty_reply: Mapped[str | None] = mapped_column(Text)
    replied_by: Mapped[str | None] = mapped_column(String(320), ForeignKey("users.email"))
    replied_at: Mapped[datetime | None] = mapped_column(UtcDateTime())

    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=utc_now, server_default=func.now()
    )

    @property
    def is_answered(self) -> bool:
        return bool(self.faculty_reply) or bool(self.ai_answer and not self.escalated)

    def __repr__(self) -> str:
        state = "escalated" if self.escalated else "answered"
        return f"<StudentQuery {self.student_email} {state}>"

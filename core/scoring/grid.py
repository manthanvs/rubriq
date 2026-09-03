"""The review grid query — §7, and fix item 8.

One function builds the rows, and the "needs attention" predicate lives on the
DTO rather than in the page. The dashboard count and the grid filter therefore
call the same code: fix item 8's named failure is *"the dashboard's pending
count disagrees with the grid"*, and two implementations of one idea is how
that happens.

Rows are returned for **every enrolled student**, including those who have not
submitted. A grid that silently omits non-submitters is how someone gets
missed entirely.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.academics.access import require_faculty
from core.academics.milestones import get_milestone
from core.auth.actor import Actor
from core.db.models import Enrollment, ProjectCycle, ReviewMilestone, Submission, User
from core.scoring.dto import GridRow
from core.scoring.sheets import sheet_for_submission


def list_grid_rows(
    actor: Actor, session: Session, *, milestone_id: int
) -> tuple[GridRow, ...]:
    """One row per enrolled student for this milestone.

    Default order is fix item 8's: rows needing attention first, then by PRN,
    so the four rows that need a human are at the top of a cohort of thirty.
    """
    require_faculty(actor, "open the review grid")
    get_milestone(actor, session, milestone_id)

    milestone = session.get(ReviewMilestone, milestone_id)
    subject_id = session.execute(
        select(ProjectCycle.subject_id).where(ProjectCycle.id == milestone.cycle_id)
    ).scalar_one()

    students = (
        session.execute(
            select(User)
            .join(Enrollment, Enrollment.student_email == User.email)
            .where(
                Enrollment.subject_id == subject_id,
                Enrollment.is_active.is_(True),
            )
            .order_by(User.prn, User.email)
        )
        .scalars()
        .all()
    )

    rows: list[GridRow] = []

    for student in students:
        versions = session.scalars(
            select(Submission)
            .where(
                Submission.milestone_id == milestone_id,
                Submission.student_email == student.email,
            )
            .order_by(Submission.version.desc())
        ).all()

        if not versions:
            rows.append(
                GridRow(
                    student_email=student.email,
                    student_name=student.name,
                    prn=student.prn,
                    submission_id=None,
                    submission_version=None,
                    submitted_at=None,
                    has_newer_version=False,
                    sheet=None,
                )
            )
            continue

        latest = versions[0]

        # Grade the version that has a sheet, if one does; otherwise the latest.
        graded = None
        for candidate in versions:
            found = sheet_for_submission(actor, session, candidate.id)
            if found is not None:
                graded = (candidate, found)
                break

        target, sheet = graded if graded else (latest, None)

        rows.append(
            GridRow(
                student_email=student.email,
                student_name=student.name,
                prn=student.prn,
                submission_id=target.id,
                submission_version=target.version,
                submitted_at=target.submitted_at,
                # Fix item 2: the grid must say when it is showing a stale
                # version rather than silently rebinding to the new one.
                has_newer_version=target.version < latest.version,
                sheet=sheet,
            )
        )

    rows.sort(key=lambda r: (not r.needs_attention, r.prn or "", r.student_email))
    return tuple(rows)


def attention_count(actor: Actor, session: Session, *, milestone_id: int) -> int:
    """How many rows need a human. The dashboard's number.

    Deliberately implemented as a count of :func:`list_grid_rows` rather than
    its own query — the two cannot drift if there is only one of them.
    """
    return sum(
        1
        for row in list_grid_rows(actor, session, milestone_id=milestone_id)
        if row.needs_attention
    )

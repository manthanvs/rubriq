"""The review grid query — §7, and fix item 8.

One function builds the rows, and the "needs attention" predicate lives on the
DTO rather than in the page. The dashboard count and the grid filter therefore
call the same code: fix item 8's named failure is *"the dashboard's pending
count disagrees with the grid"*, and two implementations of one idea is how
that happens.

Rows are returned for **every enrolled student**, including those who have not
submitted. A grid that silently omits non-submitters is how someone gets
missed entirely.

Decision #5 changes what "this student's submission" resolves to, not the shape
of the grid: a member of a granted group resolves to the group's row, so every
member shows the same version, the same sheet and the same mark. One row per
student is kept deliberately — collapsing a group into a single row is how a
member ends up with no record of their own.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.academics.access import require_faculty
from core.academics.milestones import get_milestone
from core.auth.actor import Actor
from core.db.models import (
    Enrollment,
    GroupMember,
    MemberAdjustment,
    ProjectCycle,
    ProjectGroup,
    ReviewMilestone,
    ScoreSheet,
    Submission,
    User,
)
from core.groups.enums import GroupStatus
from core.scoring.dto import GridRow
from core.scoring.sheets import member_totals, sheet_for_submission


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

    # One query for the whole cohort's granted groups, rather than one per
    # student inside the loop.
    membership = dict(
        session.execute(
            select(GroupMember.student_email, ProjectGroup.id)
            .join(ProjectGroup, ProjectGroup.id == GroupMember.group_id)
            .where(
                ProjectGroup.subject_id == subject_id,
                ProjectGroup.status == GroupStatus.GRANTED,
            )
        ).all()
    )
    group_names = dict(
        session.execute(
            select(ProjectGroup.id, ProjectGroup.name).where(
                ProjectGroup.subject_id == subject_id,
                ProjectGroup.status == GroupStatus.GRANTED,
            )
        ).all()
    )

    # One query for every adjustment in this milestone, rather than one per
    # student inside the loop.
    adjustment_rows = session.execute(
        select(
            MemberAdjustment.student_email,
            MemberAdjustment.delta,
            MemberAdjustment.reason,
        )
        .join(ScoreSheet, ScoreSheet.id == MemberAdjustment.score_sheet_id)
        .join(Submission, Submission.id == ScoreSheet.submission_id)
        .where(Submission.milestone_id == milestone_id)
        .order_by(MemberAdjustment.id)
    ).all()
    adjustments = {email: delta for email, delta, _ in adjustment_rows}
    reasons = {email: reason for email, _, reason in adjustment_rows}

    rows: list[GridRow] = []

    for student in students:
        group_id = membership.get(student.email)

        scope = (
            Submission.group_id == group_id
            if group_id is not None
            else Submission.student_email == student.email
        )

        versions = session.scalars(
            select(Submission)
            .where(Submission.milestone_id == milestone_id, scope)
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
                    group_name=group_names.get(group_id) if group_id else None,
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

        # Phase 9: a member marked apart from their group carries their own
        # total. Absent from the mapping means "the group's total", which is
        # the ordinary case rather than a special one.
        member_total = member_delta = member_reason = None
        if sheet is not None and group_id is not None:
            totals = member_totals(actor, session, score_sheet_id=sheet.id)
            if student.email in totals:
                member_total = totals[student.email]
                member_delta = adjustments.get(student.email)
                member_reason = reasons.get(student.email)

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
                member_total=member_total,
                member_delta=member_delta,
                member_reason=member_reason,
                group_name=group_names.get(group_id) if group_id else None,
                submitted_by=(
                    target.student_email
                    if target.student_email != student.email
                    else None
                ),
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

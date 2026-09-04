"""Project groups — decision #5: *groups only under the teacher's grant.*

Two routes in, one gate out:

* a **student requests** a group, naming their intended partners, and the
  request sits at ``REQUESTED`` doing nothing;
* a **faculty member creates** one directly, which lands at ``GRANTED``.

Either way, the only state that changes what anyone can see is ``GRANTED``, and
only a faculty member who owns the subject can put a group into it.

**On invariant #6.** "Students never see another student's data" acquires one
deliberate exception here: a member of a granted group can see that group's
submission. That is what a group *is*. The widening is confined to the scoping
helper below and is gated on ``GroupStatus.GRANTED``, so a pending request
grants nothing at all — which is the failure this module is most likely to
produce, and the one most heavily tested.

Every public function takes ``actor`` first and scopes by it (fix item 3).
"""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from core.academics.access import require_faculty, visible_subject_ids
from core.audit import record
from core.auth.actor import Actor
from core.clock import utc_now
from core.db.models import Enrollment, GroupMember, ProjectGroup, Subject, User
from core.errors import NotAuthorized, ValidationError
from core.groups.dto import GroupDTO, GroupMemberDTO
from core.groups.enums import GroupStatus
from core.submissions.links import USERNAME

#: A project group of one is a student, and a group of seven is a class.
MIN_MEMBERS = 2
MAX_MEMBERS = 6


# -- scoping -------------------------------------------------------------


def granted_group_ids_for(student_email: str) -> Select:
    """A ``SELECT`` of the group ids this student is a *granted* member of.

    Composed into a ``WHERE`` clause rather than evaluated and filtered in
    Python, for the reason fix item 3 gives: data that has already left the
    database has already left it.
    """
    return (
        select(GroupMember.group_id)
        .join(ProjectGroup, ProjectGroup.id == GroupMember.group_id)
        .where(
            GroupMember.student_email == student_email,
            ProjectGroup.status == GroupStatus.GRANTED,
        )
    )


# -- helpers -------------------------------------------------------------


def _member_dto(user: User) -> GroupMemberDTO:
    return GroupMemberDTO(
        student_email=user.email,
        student_name=user.name or "",
        prn=user.prn,
        github_username=user.github_username,
    )


def _dto(session: Session, group: ProjectGroup) -> GroupDTO:
    members = (
        session.execute(
            select(User)
            .join(GroupMember, GroupMember.student_email == User.email)
            .where(GroupMember.group_id == group.id)
            .order_by(User.prn, User.email)
        )
        .scalars()
        .all()
    )

    return GroupDTO(
        id=group.id,
        subject_id=group.subject_id,
        name=group.name,
        status=group.status,
        requested_by=group.requested_by,
        requested_at=group.requested_at,
        decided_by=group.decided_by,
        decided_at=group.decided_at,
        decision_note=group.decision_note,
        members=tuple(_member_dto(u) for u in members),
    )


def _load_visible(actor: Actor, session: Session, group_id: int) -> ProjectGroup:
    """Fetch a group the actor may see at all, or refuse.

    Faculty see groups in subjects they own; a student sees only groups they
    are named in — including their own pending requests, so they can tell that
    they asked.
    """
    group = session.get(ProjectGroup, group_id)
    if group is None:
        raise NotAuthorized("That group does not exist, or is not yours.")

    if group.subject_id not in set(session.scalars(visible_subject_ids(actor)).all()):
        raise NotAuthorized("That group does not exist, or is not yours.")

    if actor.is_student:
        named = session.scalar(
            select(GroupMember.id).where(
                GroupMember.group_id == group_id,
                GroupMember.student_email == actor.email,
            )
        )
        if named is None:
            raise NotAuthorized("That group does not exist, or is not yours.")

    return group


def _assert_enrolled(session: Session, *, subject_id: int, emails: list[str]) -> None:
    enrolled = set(
        session.scalars(
            select(Enrollment.student_email).where(
                Enrollment.subject_id == subject_id,
                Enrollment.is_active.is_(True),
                Enrollment.student_email.in_(emails),
            )
        ).all()
    )
    missing = [e for e in emails if e not in enrolled]
    if missing:
        raise ValidationError(
            "Not enrolled in this subject: " + ", ".join(sorted(missing)) + "."
        )


def _clean_members(actor: Actor, emails: list[str]) -> list[str]:
    cleaned: list[str] = []
    for raw in emails:
        email = (raw or "").strip().lower()
        if email and email not in cleaned:
            cleaned.append(email)

    if actor.is_student and actor.email.lower() not in cleaned:
        # A student asking for a group they are not in is either a mistake or
        # an attempt to see somebody else's work. Neither is worth supporting.
        raise ValidationError("You have to be one of the members of your own group.")

    if len(cleaned) < MIN_MEMBERS:
        raise ValidationError(f"A group needs at least {MIN_MEMBERS} members.")
    if len(cleaned) > MAX_MEMBERS:
        raise ValidationError(f"A group can have at most {MAX_MEMBERS} members.")

    return cleaned


def _assert_no_double_grant(
    session: Session, *, subject_id: int, emails: list[str], excluding: int | None
) -> None:
    """Refuse a grant that would put anyone in two granted groups at once.

    Two granted groups for one student in one subject makes "which submission
    is theirs" ambiguous, and ambiguity in that question is a wrong mark.
    """
    query = (
        select(User.name, GroupMember.student_email, ProjectGroup.name)
        .join(GroupMember, GroupMember.group_id == ProjectGroup.id)
        .join(User, User.email == GroupMember.student_email)
        .where(
            ProjectGroup.subject_id == subject_id,
            ProjectGroup.status == GroupStatus.GRANTED,
            GroupMember.student_email.in_(emails),
        )
    )
    if excluding is not None:
        query = query.where(ProjectGroup.id != excluding)

    clashes = session.execute(query).all()
    if clashes:
        detail = ", ".join(f"{email} (in {gname})" for _name, email, gname in clashes)
        raise ValidationError(f"Already in a granted group for this subject: {detail}.")


def _write_members(session: Session, *, group_id: int, emails: list[str]) -> None:
    session.query(GroupMember).filter(GroupMember.group_id == group_id).delete()
    session.flush()
    for email in emails:
        session.add(GroupMember(group_id=group_id, student_email=email))
    session.flush()


def _assert_name_free(session: Session, *, subject_id: int, name: str) -> None:
    clash = session.scalar(
        select(ProjectGroup.id).where(
            ProjectGroup.subject_id == subject_id, ProjectGroup.name == name
        )
    )
    if clash is not None:
        raise ValidationError(f"A group called '{name}' already exists in this subject.")


# -- writes --------------------------------------------------------------


def request_group(
    actor: Actor,
    session: Session,
    *,
    subject_id: int,
    name: str,
    member_emails: list[str],
) -> GroupDTO:
    """A student asks for a group. It confers nothing until a grant.

    The request is stored rather than emailed because a request nobody can see
    later is indistinguishable from one that was never made.
    """
    if not actor.is_student:
        raise NotAuthorized("Faculty create groups directly rather than requesting one.")

    if subject_id not in set(session.scalars(visible_subject_ids(actor)).all()):
        raise NotAuthorized("You are not enrolled in that subject.")

    name = (name or "").strip()
    if not name:
        raise ValidationError("Give the group a name.")

    members = _clean_members(actor, member_emails)
    _assert_enrolled(session, subject_id=subject_id, emails=members)
    _assert_name_free(session, subject_id=subject_id, name=name)

    group = ProjectGroup(
        subject_id=subject_id,
        name=name,
        status=GroupStatus.REQUESTED,
        requested_by=actor.email,
        requested_at=utc_now(),
    )
    session.add(group)
    session.flush()

    _write_members(session, group_id=group.id, emails=members)

    record(
        session,
        actor_email=actor.email,
        action="group.requested",
        entity="ProjectGroup",
        entity_id=group.id,
        payload={"subject_id": subject_id, "name": name, "members": members},
    )

    return _dto(session, group)


def create_group(
    actor: Actor,
    session: Session,
    *,
    subject_id: int,
    name: str,
    member_emails: list[str],
    note: str | None = None,
) -> GroupDTO:
    """A faculty member forms a group outright. Granted on creation.

    This is the "teacher's request" half of decision #5 — a guide who decides
    the pairings themselves should not have to ask the students to ask.
    """
    require_faculty(actor, "create project groups")

    owned = session.scalar(
        select(Subject.id).where(
            Subject.id == subject_id, Subject.owner_email == actor.email
        )
    )
    if owned is None and not actor.is_admin:
        raise NotAuthorized("You do not own that subject.")

    name = (name or "").strip()
    if not name:
        raise ValidationError("Give the group a name.")

    members = _clean_members(actor, member_emails)
    _assert_enrolled(session, subject_id=subject_id, emails=members)
    _assert_name_free(session, subject_id=subject_id, name=name)
    _assert_no_double_grant(
        session, subject_id=subject_id, emails=members, excluding=None
    )

    now = utc_now()
    group = ProjectGroup(
        subject_id=subject_id,
        name=name,
        status=GroupStatus.GRANTED,
        decided_by=actor.email,
        decided_at=now,
        decision_note=(note or "").strip() or None,
    )
    session.add(group)
    session.flush()

    _write_members(session, group_id=group.id, emails=members)

    record(
        session,
        actor_email=actor.email,
        action="group.created",
        entity="ProjectGroup",
        entity_id=group.id,
        payload={"subject_id": subject_id, "name": name, "members": members},
    )

    return _dto(session, group)


def grant_group(
    actor: Actor, session: Session, *, group_id: int, note: str | None = None
) -> GroupDTO:
    """Approve a pending request. The only transition that confers access."""
    require_faculty(actor, "grant project groups")

    group = _load_visible(actor, session, group_id)

    if group.status is GroupStatus.GRANTED:
        raise ValidationError("That group is already granted.")

    members = list(
        session.scalars(
            select(GroupMember.student_email).where(GroupMember.group_id == group.id)
        ).all()
    )
    if len(members) < MIN_MEMBERS:
        raise ValidationError(f"A group needs at least {MIN_MEMBERS} members.")

    _assert_enrolled(session, subject_id=group.subject_id, emails=members)
    _assert_no_double_grant(
        session, subject_id=group.subject_id, emails=members, excluding=group.id
    )

    group.status = GroupStatus.GRANTED
    group.decided_by = actor.email
    group.decided_at = utc_now()
    group.decision_note = (note or "").strip() or None
    session.flush()

    record(
        session,
        actor_email=actor.email,
        action="group.granted",
        entity="ProjectGroup",
        entity_id=group.id,
        payload={"members": members, "note": group.decision_note},
    )

    return _dto(session, group)


def reject_group(
    actor: Actor, session: Session, *, group_id: int, reason: str
) -> GroupDTO:
    """Refuse a request, with a reason the student can read.

    A reason is required for the same purpose it is required on a score
    override: a decision with no recorded justification is one nobody can
    review later.
    """
    require_faculty(actor, "decide project groups")

    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Give a reason — the student will see it.")

    group = _load_visible(actor, session, group_id)

    group.status = GroupStatus.REJECTED
    group.decided_by = actor.email
    group.decided_at = utc_now()
    group.decision_note = reason
    session.flush()

    record(
        session,
        actor_email=actor.email,
        action="group.rejected",
        entity="ProjectGroup",
        entity_id=group.id,
        payload={"reason": reason},
    )

    return _dto(session, group)


def set_github_username(
    actor: Actor, session: Session, *, student_email: str, username: str | None
) -> str | None:
    """Record the GitHub account a student's repository URLs must belong to.

    Faculty-only, deliberately. Decision #6 says the profiles are *already
    shared with the teachers*; letting a student set their own would make the
    ownership check something the person being checked configures, which is
    not a check.
    """
    require_faculty(actor, "record a student's GitHub account")

    student_email = (student_email or "").strip().lower()
    user = session.get(User, student_email)
    if user is None:
        raise ValidationError(f"No such user: {student_email}.")

    visible = set(session.scalars(visible_subject_ids(actor)).all())
    shares_subject = session.scalar(
        select(Enrollment.id).where(
            Enrollment.student_email == student_email,
            Enrollment.subject_id.in_(visible),
            Enrollment.is_active.is_(True),
        )
    )
    if shares_subject is None:
        raise NotAuthorized("That student is not enrolled in a subject you own.")

    cleaned = (username or "").strip().lstrip("@") or None
    if cleaned is not None:
        if not USERNAME.match(cleaned):
            raise ValidationError(f"'{cleaned}' is not a valid GitHub account name.")

    previous = user.github_username
    user.github_username = cleaned
    session.flush()

    record(
        session,
        actor_email=actor.email,
        action="student.github_set",
        entity="User",
        entity_id=student_email,
        payload={"from": previous, "to": cleaned},
    )

    return cleaned


# -- reads ---------------------------------------------------------------


def list_groups(
    actor: Actor,
    session: Session,
    *,
    subject_id: int,
    status: GroupStatus | None = None,
) -> tuple[GroupDTO, ...]:
    """Groups in a subject: all of them for its owner, only your own if student."""
    if subject_id not in set(session.scalars(visible_subject_ids(actor)).all()):
        raise NotAuthorized("That subject does not exist, or is not yours.")

    query = select(ProjectGroup).where(ProjectGroup.subject_id == subject_id)

    if status is not None:
        query = query.where(ProjectGroup.status == status)

    if actor.is_student:
        query = query.where(
            ProjectGroup.id.in_(
                select(GroupMember.group_id).where(
                    GroupMember.student_email == actor.email
                )
            )
        )

    rows = session.scalars(query.order_by(ProjectGroup.name)).all()
    return tuple(_dto(session, row) for row in rows)


def pending_group_count(actor: Actor, session: Session) -> int:
    """Requests waiting on this faculty member, for the dashboard."""
    if not actor.is_faculty:
        return 0

    return int(
        session.scalar(
            select(func.count())
            .select_from(ProjectGroup)
            .where(
                ProjectGroup.status == GroupStatus.REQUESTED,
                ProjectGroup.subject_id.in_(visible_subject_ids(actor)),
            )
        )
        or 0
    )


def granted_group_for(
    actor: Actor, session: Session, *, subject_id: int, student_email: str
) -> GroupDTO | None:
    """The granted group this student belongs to in this subject, if any.

    Returns ``None`` for a student with a pending request — which is the point
    of the whole module, so it is asserted rather than assumed.
    """
    if actor.is_student and student_email != actor.email:
        raise NotAuthorized("You can only look up your own group.")

    if subject_id not in set(session.scalars(visible_subject_ids(actor)).all()):
        raise NotAuthorized("That subject does not exist, or is not yours.")

    group = session.scalars(
        select(ProjectGroup).where(
            ProjectGroup.subject_id == subject_id,
            ProjectGroup.status == GroupStatus.GRANTED,
            ProjectGroup.id.in_(
                select(GroupMember.group_id).where(
                    GroupMember.student_email == student_email
                )
            ),
        )
    ).first()

    return None if group is None else _dto(session, group)


def get_group(actor: Actor, session: Session, group_id: int) -> GroupDTO:
    return _dto(session, _load_visible(actor, session, group_id))

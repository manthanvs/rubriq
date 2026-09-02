"""Query scoping — the single answer to "which subjects may this actor see?".

Fix item 3 names the failure mode precisely: *"A query that fetches all rows
and filters in pandas afterwards — the data already left the database, so the
invariant is already broken."*

So scoping is a subquery, composed into the ``WHERE`` clause of every read in
this package. There is one definition of visibility and every query uses it,
which means a new service cannot accidentally invent a laxer one.
"""

from __future__ import annotations

from sqlalchemy import Select, select

from core.auth.actor import Actor
from core.db.models import Enrollment, Subject
from core.errors import NotAuthorized


def visible_subject_ids(actor: Actor) -> Select:
    """A ``SELECT`` of the subject ids ``actor`` may see.

    * Faculty — subjects they own. Not "subjects in their department", not
      "all subjects": ownership is the only relationship that grants access.
    * Student — subjects they are actively enrolled in.
    * Admin — everything, because an admin's job is the audit view (§14 #15).
    """
    if actor.is_admin:
        return select(Subject.id).where(Subject.is_active.is_(True))

    if actor.is_faculty:
        return select(Subject.id).where(
            Subject.owner_email == actor.email,
            Subject.is_active.is_(True),
        )

    return (
        select(Enrollment.subject_id)
        .join(Subject, Subject.id == Enrollment.subject_id)
        .where(
            Enrollment.student_email == actor.email,
            Enrollment.is_active.is_(True),
            Subject.is_active.is_(True),
        )
    )


def require_faculty(actor: Actor, action: str) -> None:
    """Guard a write that only the teaching side may perform.

    Raises rather than returning False: a caller that forgets to check the
    return value of a permission function is a bug that fails open.
    """
    if not actor.is_faculty:
        raise NotAuthorized(f"Only faculty can {action}.")

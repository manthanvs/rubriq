"""Group panels, shared by the faculty and student sides (decision #5).

Both roles look at the same groups and must describe them identically — a
student told "awaiting approval" while their guide sees "granted" is the kind
of disagreement that produces an email rather than a submission. So the status
wording lives on ``GroupDTO`` and the rendering lives here, called from both
pages, exactly as the calendar and the rubric view already are.

View only: every decision goes through ``core/groups/service.py``, which is
where the grant gate is.
"""

from __future__ import annotations

import streamlit as st

from app.context import db
from app.state import after_mutation
from core.auth.actor import Actor
from core.clock import to_ist
from core.errors import RubriQError
from core.groups.dto import GroupDTO
from core.groups.service import grant_group, reject_group

STATUS_ICON = {
    "Granted": ":material/verified:",
    "Awaiting approval": ":material/hourglass_top:",
    "Not approved": ":material/block:",
}


def group_table(groups: tuple[GroupDTO, ...]) -> list[dict]:
    """One row per group. Pure, so a test can assert the shape."""
    return [
        {
            "Group": group.name,
            "Status": group.status_label,
            "Members": ", ".join(
                m.student_name or m.student_email for m in group.members
            ),
            "Size": group.size,
            "Decided by": group.decided_by or "—",
            "Note": group.decision_note or "—",
        }
        for group in groups
    ]


def render_group_summary(group: GroupDTO) -> None:
    """The card a student sees for their own group."""
    st.info(
        f"**{group.name}** — {group.status_label}",
        icon=STATUS_ICON.get(group.status_label, ":material/group:"),
    )

    st.caption("Members: " + ", ".join(m.label for m in group.members))

    for member in group.members:
        if not member.github_username:
            who = member.student_name or member.student_email
            st.caption(
                f"No GitHub account on record for {who} — repository links "
                "from that account will be refused until your guide adds it."
            )

    if group.decision_note:
        st.caption(f"Note from your guide: {group.decision_note}")


def render_pending_decisions(actor: Actor, groups: tuple[GroupDTO, ...]) -> None:
    """Grant or refuse, one request at a time.

    A refusal needs a reason for the same purpose a score override does: a
    decision with nothing recorded behind it is one nobody can review later,
    and the student is owed an answer they can read.
    """
    pending = [g for g in groups if g.is_pending]

    if not pending:
        st.caption("No group requests waiting.")
        return

    for group in pending:
        with st.container(border=True):
            st.markdown(f"**{group.name}** · {group.size} members")
            st.caption(", ".join(m.label for m in group.members))

            if group.requested_at:
                st.caption(
                    f"Requested by {group.requested_by} on "
                    f"{to_ist(group.requested_at).strftime('%d %b %Y, %I:%M %p')} IST"
                )

            missing = [m.label for m in group.members if not m.github_username]
            if missing:
                st.caption("No GitHub account on record for: " + ", ".join(missing) + ".")

            grant_col, reject_col = st.columns(2)

            if grant_col.button(
                "Grant",
                key=f"grant_{group.id}",
                type="primary",
                icon=":material/verified:",
            ):
                try:
                    with db() as session:
                        grant_group(actor, session, group_id=group.id)
                    after_mutation(f"Granted {group.name}.")
                except RubriQError as exc:
                    st.error(str(exc), icon=":material/error:")

            with reject_col.popover("Refuse", icon=":material/block:"):
                reason = st.text_input(
                    "Reason (the student sees this)", key=f"r_{group.id}"
                )
                if st.button("Confirm refusal", key=f"rb_{group.id}"):
                    try:
                        with db() as session:
                            reject_group(actor, session, group_id=group.id, reason=reason)
                        after_mutation(f"Refused {group.name}.")
                    except RubriQError as exc:
                        st.error(str(exc), icon=":material/error:")

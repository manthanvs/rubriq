"""Activity — faculty. Fix item 15.

Every mutation in RubriQ has written an AuditLog row since Phase 1. This is
where they are finally read.

It exists to answer one question convincingly: *how do you know the faculty
member, not the AI, decided this mark?* The answer is a timestamped line naming
the person, the change, and — for an override — their stated reason.

Timestamps are IST, because that is the clock the deadline policy is written in
and mixing two on one screen is how someone misreads a boundary.
"""

from __future__ import annotations

import streamlit as st

from app.context import current_actor, db
from core.audit_read import ACTION_GROUPS, list_audit
from core.clock import to_ist
from core.errors import RubriQError

actor = current_actor()

st.title("Activity")
st.caption(
    "Every change RubriQ has recorded, newest first. This is the trail that "
    "shows a mark was decided by a person."
)

left, right = st.columns([2, 2])

group = left.selectbox("Show", options=["Everything", *ACTION_GROUPS.keys()], index=0)
who = right.text_input("By (email contains)", placeholder="anjana")

try:
    with db() as session:
        entries = list_audit(
            actor,
            session,
            group=None if group == "Everything" else group,
            limit=300,
        )
except RubriQError as exc:
    st.error(str(exc), icon=":material/error:")
    st.stop()

if who.strip():
    needle = who.strip().casefold()
    entries = tuple(e for e in entries if needle in e.actor_email.casefold())

if not entries:
    st.info(
        "Nothing recorded yet for this filter. Activity appears here as soon as "
        "anyone creates a subject, scores a submission or approves a sheet.",
        icon=":material/history:",
    )
    st.stop()

st.caption(f"{len(entries)} entries")

st.dataframe(
    [
        {
            "When (IST)": to_ist(e.at).strftime("%d %b %Y, %I:%M %p"),
            "Who": e.actor_name,
            "Area": e.group,
            "What happened": e.summary,
            "On": f"{e.entity} {e.entity_id}" if e.entity_id else e.entity,
        }
        for e in entries
    ],
    hide_index=True,
    width="stretch",
    column_config={
        "When (IST)": st.column_config.TextColumn(width="medium"),
        "Who": st.column_config.TextColumn(width="medium"),
        "Area": st.column_config.TextColumn(width="small"),
        "What happened": st.column_config.TextColumn(width="large"),
        "On": st.column_config.TextColumn(width="small"),
    },
)

st.caption(
    "Nothing here can be edited or deleted — the log is append-only, which is "
    "what makes it evidence rather than a note."
)

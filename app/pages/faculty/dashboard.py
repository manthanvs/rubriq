"""Dashboard — faculty.

Owned subjects, what is due next, and how many rows need a human.

That last number comes from :func:`core.scoring.grid.attention_count`, which is
the same function the Review Grid filters on — fix item 8 exists because a
dashboard count and a grid filter that compute the same thing separately will
eventually disagree, and the faculty member will believe whichever is worse.
"""

from __future__ import annotations

import streamlit as st

from app.components.calendar import next_deadline, render_agenda
from app.context import current_actor, db
from core.academics.milestones import list_milestones
from core.academics.subjects import list_subjects
from core.errors import RubriQError
from core.groups.service import pending_group_count
from core.queries.service import escalated_count
from core.scoring.grid import attention_count

actor = current_actor()

st.title("Dashboard")
st.caption(f"Signed in as {actor.name or actor.email}")

with db() as session:
    subjects = list_subjects(actor, session)
    milestones = list_milestones(actor, session)

if not subjects:
    st.info(
        "No subjects yet — create one on the Subjects page to get started.",
        icon=":material/school:",
    )
    st.stop()

enrolled = sum(s.enrolled_count for s in subjects)
published = [m for m in milestones if m.is_visible]
upcoming = next_deadline(tuple(published))

needs_attention = 0
for milestone in published:
    try:
        with db() as session:
            needs_attention += attention_count(actor, session, milestone_id=milestone.id)
    except RubriQError:
        # A milestone with no rubric yet cannot be graded; it is not a failure.
        continue

with db() as session:
    waiting_questions = escalated_count(actor, session)
    waiting_groups = pending_group_count(actor, session)

a, b, c, d = st.columns(4)
a.metric("Subjects", len(subjects))
b.metric("Students", enrolled)
c.metric("Published reviews", len(published))
d.metric(
    "Needs attention",
    needs_attention,
    help="Rows in the Review Grid waiting on you: unsubmitted, unscored, "
    "unapproved, or blocked by an unevidenced mandatory criterion.",
)

if waiting_groups:
    # Decision #5 puts the grant here, so a request that nobody sees is a
    # request that silently never happens.
    st.info(
        f"**{waiting_groups}** project group request(s) are waiting for your "
        "approval — Subjects → Groups.",
        icon=":material/group_add:",
    )

if waiting_questions:
    st.info(
        f"**{waiting_questions}** student question(s) the assistant could not "
        "answer are waiting in your Query Inbox.",
        icon=":material/forward_to_inbox:",
    )

st.divider()
st.subheader("Your subjects")

st.dataframe(
    [
        {
            "Code": s.code,
            "Name": s.name,
            "Sem": s.semester,
            "Enrolled": s.enrolled_count,
        }
        for s in subjects
    ],
    hide_index=True,
    width="stretch",
)

st.subheader("Coming up")

if upcoming is not None:
    st.caption(f"Next: **{upcoming.subject_code} — {upcoming.title}**")

render_agenda(
    milestones,
    show_visibility=True,
    empty_message="Nothing scheduled — add milestones from Subjects → Milestones.",
)

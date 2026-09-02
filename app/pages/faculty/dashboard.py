"""Dashboard — faculty.

Owned subjects and what is due next. The pending-approval count arrives in
Phase 4, and when it does it must come from the same "needs attention"
predicate the Review Grid filters on — fix item 8 exists because a dashboard
count and a grid filter that compute the same thing separately will disagree.
"""

from __future__ import annotations

import streamlit as st

from app.components.calendar import next_deadline, render_agenda
from app.context import current_actor, db
from core.academics.milestones import list_milestones
from core.academics.subjects import list_subjects

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

a, b, c, d = st.columns(4)
a.metric("Subjects", len(subjects))
b.metric("Students", enrolled)
c.metric("Milestones", len(milestones))
d.metric("Published", len(published))

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
    use_container_width=True,
)

st.subheader("Coming up")

if upcoming is not None:
    st.caption(f"Next: **{upcoming.subject_code} — {upcoming.title}**")

render_agenda(
    milestones,
    show_visibility=True,
    empty_message="Nothing scheduled — add milestones from Subjects → Milestones.",
)

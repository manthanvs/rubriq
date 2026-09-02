"""Dashboard — student.

Enrolled subjects and the next deadline. Submission status chips arrive in
Phase 3 alongside the Submit page, and they will use the one shared status
renderer fix item 10 asks for rather than deriving status here.
"""

from __future__ import annotations

import streamlit as st

from app.components.calendar import next_deadline, render_agenda
from app.context import current_actor, db
from core.academics.milestones import list_milestones
from core.academics.subjects import list_subjects
from core.clock import ist_date, to_ist, utc_now

actor = current_actor()

st.title("Dashboard")
st.caption(f"Signed in as {actor.name or actor.email}")

with db() as session:
    subjects = list_subjects(actor, session)
    milestones = list_milestones(actor, session)

if not subjects:
    st.info(
        "You are not enrolled in any subject yet. Your guide enrols the class "
        "from the Subjects page — check back once that is done.",
        icon=":material/school:",
    )
    st.stop()

upcoming = next_deadline(milestones)

a, b = st.columns(2)
a.metric("Subjects", len(subjects))
b.metric("Deadlines published", len(milestones))

if upcoming is not None:
    days = (ist_date(upcoming.due_at) - ist_date(utc_now())).days
    when = "today" if days == 0 else ("tomorrow" if days == 1 else f"in {days} days")
    st.success(
        f"**Next deadline — {upcoming.subject_code}, {upcoming.title}**  \n"
        f"{to_ist(upcoming.due_at).strftime('%d %b %Y, %I:%M %p')} IST · {when}",
        icon=":material/event_upcoming:",
    )

st.divider()
st.subheader("Your subjects")

st.dataframe(
    [{"Code": s.code, "Name": s.name, "Sem": s.semester} for s in subjects],
    hide_index=True,
    use_container_width=True,
)

st.subheader("Deadlines")
render_agenda(
    milestones,
    empty_message="No deadlines published yet.",
)

"""Dashboard — student.

Enrolled subjects, and the one question a student actually opens this page to
ask: what is due next, and have I done it.

The countdown is the headline because that is the question. Everything else
on the page is context for it. Status wording comes from the shared renderer
in ``app/components/theme.py`` — fix item 10 — so a milestone cannot be
described one way here and another way on Submit.
"""

from __future__ import annotations

import streamlit as st

from app.components.calendar import next_deadline, render_agenda
from app.components.theme import metric_card, section, status_chip
from app.context import current_actor, db
from app.navigation import page_path_for
from core.academics.milestones import list_milestones
from core.academics.subjects import list_subjects
from core.clock import ist_date, to_ist, utc_now
from core.errors import RubriQError
from core.submissions.service import list_submissions

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
submit_page = page_path_for(actor.role, "student_submit")

# -- the headline -------------------------------------------------------
if upcoming is not None:
    days = (ist_date(upcoming.due_at) - ist_date(utc_now())).days
    if days < 0:
        when, icon = f"{abs(days)} day(s) ago", ":material/event_busy:"
    elif days == 0:
        when, icon = "today", ":material/priority_high:"
    elif days == 1:
        when, icon = "tomorrow", ":material/event_upcoming:"
    else:
        when, icon = f"in {days} days", ":material/event_upcoming:"

    with st.container(border=True):
        st.markdown(f"**Next deadline — {upcoming.subject_code}, {upcoming.title}**")
        a, b = st.columns([1, 2])
        metric_card(a, "Due", when, icon=icon)
        b.caption("Closes at")
        b.markdown(
            f"### {to_ist(upcoming.due_at).strftime('%d %b %Y')}\n"
            f"{to_ist(upcoming.due_at).strftime('%I:%M %p')} IST"
        )
        if submit_page:
            st.page_link(
                submit_page, label="Go to Submit", icon=":material/upload_file:"
            )
elif milestones:
    # Published but all in the past. "None published" would be a different
    # thing and would send the student looking for a page that has nothing
    # wrong with it.
    latest = max(milestones, key=lambda m: m.due_at)
    st.info(
        f"No upcoming deadlines — the last one, **{latest.title}**, closed on "
        f"{to_ist(latest.due_at).strftime('%d %b %Y')}.",
        icon=":material/event_available:",
    )
else:
    st.info(
        "No deadlines published yet. Your guide publishes a review when it "
        "opens, and it will appear here.",
        icon=":material/event:",
    )

c, d = st.columns(2)
metric_card(c, "Subjects", len(subjects), icon=":material/school:")
metric_card(d, "Deadlines published", len(milestones), icon=":material/event:")

st.divider()

# -- where each review stands -------------------------------------------
if milestones:
    section("Your reviews", "Where each one stands right now.")

    for milestone in milestones:
        try:
            with db() as session:
                versions = list_submissions(
                    actor,
                    session,
                    milestone_id=milestone.id,
                    student_email=actor.email,
                )
        except RubriQError:
            versions = []

        with st.container(border=True):
            left, right = st.columns([3, 1])
            left.markdown(f"**{milestone.subject_code} — {milestone.title}**")
            left.caption(
                f"Due {to_ist(milestone.due_at).strftime('%d %b %Y, %I:%M %p')} IST"
            )
            with right:
                if versions:
                    status_chip("Submitted")
                    st.caption(f"v{max(v.version for v in versions)}")
                else:
                    status_chip("Not submitted")

    st.divider()

section("Your subjects")

st.dataframe(
    [{"Code": s.code, "Name": s.name, "Sem": s.semester} for s in subjects],
    hide_index=True,
    width="stretch",
    column_config={
        "Code": st.column_config.TextColumn("Code", width=90, pinned=True),
        "Name": st.column_config.TextColumn("Name", width="large"),
        "Sem": st.column_config.NumberColumn("Sem", width=70),
    },
)

section("Deadlines")
render_agenda(
    milestones,
    empty_message="No deadlines published yet.",
)

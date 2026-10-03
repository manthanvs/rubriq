"""Dashboard — faculty.

Owned subjects, what is due next, and how many rows need a human.

That last number comes from :func:`core.scoring.grid.attention_count`, which is
the same function the Review Grid filters on — fix item 8 exists because a
dashboard count and a grid filter that compute the same thing separately will
eventually disagree, and the faculty member will believe whichever is worse.

Everything that reports a count here is a way *into* the page that resolves
it. A dashboard that says "5 rows need attention" and leaves you to find them
has told you about a problem and then made it your job to locate it.
"""

from __future__ import annotations

import streamlit as st

from app.components.calendar import next_deadline, render_agenda
from app.components.theme import metric_card, section
from app.context import current_actor, db
from app.navigation import page_path_for
from core.academics.milestones import list_milestones
from core.academics.subjects import list_subjects
from core.errors import RubriQError
from core.groups.service import pending_group_count
from core.queries.service import escalated_count
from core.scoring.grid import attention_count, list_grid_rows

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
metric_card(a, "Subjects", len(subjects), icon=":material/school:")
metric_card(b, "Students", enrolled, icon=":material/groups:")
metric_card(c, "Published reviews", len(published), icon=":material/task:")
metric_card(
    d,
    "Needs attention",
    needs_attention,
    icon=":material/pending_actions:",
    help="Rows in the Review Grid waiting on you: unsubmitted, unscored, "
    "unapproved, or blocked by an unevidenced mandatory criterion.",
)

# -- what to do next ----------------------------------------------------
# Each of these was an st.info that named a number and a page. A link is the
# same sentence with the walk already done.
grid_page = page_path_for(actor.role, "faculty_review_grid")
inbox_page = page_path_for(actor.role, "faculty_query_inbox")
subjects_page = page_path_for(actor.role, "faculty_subjects")

if needs_attention or waiting_groups or waiting_questions:
    with st.container(border=True):
        st.markdown("**Waiting on you**")
        if needs_attention and grid_page:
            st.page_link(
                grid_page,
                label=f"{needs_attention} row(s) need a decision",
                icon=":material/pending_actions:",
            )
        if waiting_groups and subjects_page:
            # Decision #5 puts the grant here, so a request that nobody sees
            # is a request that silently never happens.
            st.page_link(
                subjects_page,
                label=f"{waiting_groups} group request(s) awaiting approval",
                icon=":material/group_add:",
            )
        if waiting_questions and inbox_page:
            st.page_link(
                inbox_page,
                label=f"{waiting_questions} escalated question(s)",
                icon=":material/forward_to_inbox:",
            )
elif published:
    st.success("Nothing is waiting on you.", icon=":material/check_circle:")

st.divider()

# -- per-review progress ------------------------------------------------
if published:
    section(
        "Review progress",
        "Pick a review to see how far through it you are.",
    )
    chosen = st.selectbox(
        "Review",
        published,
        format_func=lambda m: f"{m.subject_code} — {m.title}",
        label_visibility="collapsed",
    )

    try:
        with db() as session:
            rows = list_grid_rows(actor, session, milestone_id=chosen.id)
    except RubriQError as exc:
        st.info(str(exc), icon=":material/info:")
        rows = []

    if rows:
        approved = sum(1 for r in rows if r.sheet and r.sheet.is_approved)
        scored = sum(1 for r in rows if r.sheet)
        absent = sum(1 for r in rows if r.sheet and r.sheet.is_absent)
        no_submission = sum(1 for r in rows if not r.submission_id)

        st.progress(
            approved / len(rows),
            text=f"{approved} of {len(rows)} approved",
        )

        w, x, y, z = st.columns(4)
        metric_card(w, "Approved", approved, icon=":material/verified:")
        metric_card(x, "Scored", scored, icon=":material/grading:")
        metric_card(y, "Absent", absent, icon=":material/event_busy:")
        metric_card(z, "No submission", no_submission, icon=":material/inbox:")

        if grid_page:
            st.page_link(
                grid_page,
                label=f"Open the grid for {chosen.title}",
                icon=":material/table_chart:",
            )
    elif published:
        st.caption("No rows yet — nobody is enrolled, or the rubric is unpublished.")

    st.divider()

# -- subjects -----------------------------------------------------------
section("Your subjects")

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
    column_config={
        "Code": st.column_config.TextColumn("Code", width=90, pinned=True),
        "Name": st.column_config.TextColumn("Name", width="large"),
        "Sem": st.column_config.NumberColumn("Sem", width=70),
        "Enrolled": st.column_config.NumberColumn(
            "Enrolled", width=100, format="%d students"
        ),
    },
)

section("Coming up")

if upcoming is not None:
    st.caption(f"Next: **{upcoming.subject_code} — {upcoming.title}**")

render_agenda(
    milestones,
    show_visibility=True,
    empty_message="Nothing scheduled — add milestones from Subjects → Milestones.",
)

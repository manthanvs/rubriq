"""Query Inbox — faculty.

Questions the assistant declined to answer. §6.4: escalation returns no
invented answer, so what arrives here is the student's question and the reason
it was handed over — never a half-answer the student has already read and may
believe.

Scoped through the same ``visible_subject_ids`` every other faculty read uses,
so this is your students' questions and nobody else's.
"""

from __future__ import annotations

import streamlit as st

from app.context import current_actor, db
from app.state import flash, invalidate, render_flash
from core.clock import to_ist
from core.errors import RubriQError
from core.queries.service import list_escalated, reply

actor = current_actor()

st.title("Query Inbox")
render_flash()

show_replied = st.toggle("Include questions I have already answered", value=False)

with db() as session:
    queries = list_escalated(actor, session, include_replied=show_replied)

waiting = [q for q in queries if q.awaiting_reply]

left, right = st.columns(2)
left.metric("Waiting on you", len(waiting))
right.metric("Shown", len(queries))

if not queries:
    st.success(
        "Nothing waiting. Questions the assistant cannot answer from the rubric "
        "appear here.",
        icon=":material/inbox:",
    )
    st.stop()

st.caption(
    "The assistant escalates rather than guessing. A question here means the "
    "rubric did not answer it — several students asking the same thing is worth "
    "reading as feedback on the rubric."
)

for entry in queries:
    with st.container(border=True):
        header, stamp = st.columns([3, 1])
        header.markdown(f"**{entry.student_name}** · {entry.milestone_label}")
        stamp.caption(to_ist(entry.created_at).strftime("%d %b, %I:%M %p"))

        st.write(f"> {entry.question}")

        if entry.escalation_reason:
            st.caption(f"Escalated because: {entry.escalation_reason}")

        if entry.faculty_reply:
            st.success(
                f"**You replied** on "
                f"{to_ist(entry.replied_at).strftime('%d %b, %I:%M %p')} IST\n\n"
                f"{entry.faculty_reply}",
                icon=":material/check:",
            )
            continue

        with st.form(f"reply_{entry.id}", clear_on_submit=True):
            message = st.text_area(
                "Your reply",
                key=f"msg_{entry.id}",
                placeholder="The student sees this on their Ask RubriQ page.",
            )

            if st.form_submit_button("Send reply", type="primary"):
                try:
                    with db() as session:
                        reply(actor, session, query_id=entry.id, message=message)
                    invalidate()
                    flash(f"Replied to {entry.student_name}.")
                    st.rerun()
                except RubriQError as exc:
                    st.error(str(exc), icon=":material/error:")

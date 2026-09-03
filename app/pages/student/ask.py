"""Ask RubriQ — student.

Chat scoped to one milestone (§8). The assistant answers from the published
rubric, the milestone description and the guide's notes, and hands anything
else to the guide rather than guessing.

The escalate button is not a fallback for when the answer is poor — it is the
same path the assistant takes on its own, so a student who disagrees with an
answer reaches a human by the identical route.
"""

from __future__ import annotations

import streamlit as st

from app.context import current_actor, db, get_settings
from app.state import invalidate
from core.academics.milestones import list_milestones
from core.ai.provider import AIUnavailable, RetryingProvider, build_provider
from core.errors import RubriQError
from core.queries.dto import QueryAnswer
from core.queries.service import ask, build_context, list_my_queries

actor = current_actor()

st.title("Ask RubriQ")

with db() as session:
    milestones = list_milestones(actor, session)

if not milestones:
    st.info(
        "Nothing to ask about yet — no milestones have been published for your subjects.",
        icon=":material/event_busy:",
    )
    st.stop()

milestone = st.selectbox(
    "Milestone",
    options=milestones,
    format_func=lambda m: f"{m.subject_code} · Review {m.index} — {m.title}",
)

st.caption(
    "The assistant reads the published rubric, this milestone's description and "
    "your guide's notes — nothing else. It cannot see your submission, your "
    "marks, or anyone else's work, and it never predicts a score."
)

with db() as session:
    history = list_my_queries(actor, session, milestone_id=milestone.id)

for entry in history:
    with st.chat_message("user"):
        st.write(entry.question)

    with st.chat_message("assistant"):
        if entry.faculty_reply:
            st.success(
                f"**Your guide replied:**\n\n{entry.faculty_reply}",
                icon=":material/person:",
            )
        elif entry.escalated:
            st.warning(
                f"{entry.escalation_reason}\n\n"
                "This has gone to your guide and will appear here when they reply.",
                icon=":material/forward_to_inbox:",
            )
        else:
            st.write(entry.ai_answer or "")
            if entry.sources:
                st.caption("Based on: " + ", ".join(entry.sources))

question = st.chat_input("Ask about this milestone…")

if not question:
    st.stop()

settings = get_settings()

try:
    # Wrapped: a 503 under load is the common case and waiting fixes it.
    # Without this a busy model becomes an escalation the guide has to
    # answer by hand.
    provider = RetryingProvider(build_provider(settings))
except AIUnavailable as exc:
    # Invariant #10: the question still reaches a human. A student blocked by
    # an unconfigured API key is worse than one whose question was escalated.
    with db() as session:
        ask(
            actor,
            session,
            milestone_id=milestone.id,
            question=question,
            answer=QueryAnswer(
                answer="",
                escalated=True,
                reason=(
                    "The assistant is unavailable, so this went straight to your guide."
                ),
            ),
        )
    invalidate()
    st.caption(str(exc))
    st.rerun()

try:
    with db() as session:
        context = build_context(actor, session, milestone.id)

    with st.spinner("Reading the rubric…"):
        # Imported here so the page does not pull the graph in on every load.
        from core.ai.provider import answer_student_query

        result = answer_student_query(
            question, context, provider=provider, student_email=actor.email
        )

    with db() as session:
        ask(
            actor,
            session,
            milestone_id=milestone.id,
            question=question,
            answer=QueryAnswer(
                answer=result.answer,
                escalated=result.escalated,
                reason=result.reason,
                sources=result.sources,
                confidence=result.confidence,
            ),
        )

    invalidate()
    st.rerun()

except RubriQError as exc:
    st.error(str(exc), icon=":material/error:")

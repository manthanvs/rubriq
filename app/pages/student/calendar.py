"""Calendar — student.

Read-only, and scoped to this student's own subjects. The scoping is in the
query, not in this page: ``list_milestones`` for a student never returns a
draft or another subject's row, so there is nothing here to filter out.
"""

from __future__ import annotations

import streamlit as st

from app.components.calendar import render_agenda
from app.context import current_actor, db
from core.academics.milestones import list_milestones

actor = current_actor()

st.title("Calendar")
st.caption("Your review deadlines. Times in IST.")

with db() as session:
    milestones = list_milestones(actor, session)

render_agenda(
    milestones,
    empty_message=(
        "No deadlines published yet — they appear here once your guide publishes them."
    ),
)

"""Calendar — faculty.

Milestones across every subject this faculty member owns, drafts included.
Same renderer as the student calendar (§8); only the data differs, because a
student's query never returns a draft.
"""

from __future__ import annotations

import streamlit as st

from app.components.calendar import render_agenda
from app.context import current_actor, db
from core.academics.milestones import list_milestones

actor = current_actor()

st.title("Calendar")
st.caption("Every milestone across the subjects you own. Times in IST.")

with db() as session:
    milestones = list_milestones(actor, session)

render_agenda(
    milestones,
    show_visibility=True,
    empty_message="No milestones scheduled — add some from Subjects → Milestones.",
)

if milestones:
    drafts = [m for m in milestones if not m.is_visible]
    if drafts:
        st.caption(f"{len(drafts)} draft milestone(s) are not visible to students yet.")

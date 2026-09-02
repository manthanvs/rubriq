"""The shared milestone calendar.

Written once and called by both roles (§8). The student's copy differs only in
the data it is handed — a student's query never returns a draft milestone — not
in what it renders.

**Decision #3 — agenda table, not `streamlit-calendar`.** Recorded here because
§13 asks for the reason, and this is where anyone looking for it will land:

* The calendar is a supporting page. §7's review grid is the centrepiece, and
  a third-party FullCalendar wrapper is dependency risk spent in the wrong
  place — its own theming, its own compatibility surface against Streamlit and
  Python versions, and a demo that breaks if it lags a release.
* An agenda answers the question students actually have. "When is my next
  deadline" is a sorted list; a month grid buries it among empty cells.
* Sorting by soonest-first makes lateness legible at a glance, which is what
  fix item 10 asks for — lateness visible *before* it matters, not after.
* It is swappable. Both roles call this one function, so replacing the body
  with a component later touches exactly one file.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from core.academics.dto import MilestoneDTO
from core.clock import ist_date, to_ist, utc_now


def _countdown(due_at: datetime, today) -> str:
    """Days remaining, in IST calendar days — the unit §5.1 penalises in."""
    delta = (ist_date(due_at) - today).days

    if delta > 1:
        return f"in {delta} days"
    if delta == 1:
        return "tomorrow"
    if delta == 0:
        return "today"
    if delta == -1:
        return "1 day ago"
    return f"{abs(delta)} days ago"


def render_agenda(
    milestones: tuple[MilestoneDTO, ...],
    *,
    show_visibility: bool = False,
    empty_message: str = "No milestones scheduled yet.",
) -> None:
    """Render milestones as a sorted agenda. Times shown in IST."""
    if not milestones:
        st.info(empty_message, icon=":material/event_busy:")
        return

    today = ist_date(utc_now())

    frame = pd.DataFrame(
        [
            {
                "Due (IST)": to_ist(m.due_at).strftime("%d %b %Y, %I:%M %p"),
                "When": _countdown(m.due_at, today),
                "Subject": m.subject_code,
                "Review": m.index,
                "Milestone": m.title,
                "Marks": float(m.max_marks),
                "Published": m.is_visible,
            }
            for m in milestones
        ]
    )

    if not show_visibility:
        frame = frame.drop(columns=["Published"])

    columns = {
        "Due (IST)": st.column_config.TextColumn(width="medium"),
        "When": st.column_config.TextColumn(width="small"),
        "Subject": st.column_config.TextColumn(width="small"),
        "Review": st.column_config.NumberColumn(width="small", format="%d"),
        "Marks": st.column_config.NumberColumn(width="small", format="%.0f"),
    }
    if show_visibility:
        columns["Published"] = st.column_config.CheckboxColumn(
            "Published", width="small", help="Draft milestones are invisible to students."
        )

    st.dataframe(
        frame,
        column_config=columns,
        hide_index=True,
        use_container_width=True,
    )


def next_deadline(milestones: tuple[MilestoneDTO, ...]) -> MilestoneDTO | None:
    """The soonest milestone still ahead, or None."""
    today = ist_date(utc_now())
    upcoming = [m for m in milestones if ist_date(m.due_at) >= today]
    return upcoming[0] if upcoming else None

"""Submit — student.

The rubric is rendered **above** the file picker, not below it. §10 calls that
"the entire point of the system": a student who reads what they are being
measured against before they upload is the difference this project is trying to
make.

A milestone with no published rubric cannot be submitted against at all —
there would be nothing to have read.
"""

from __future__ import annotations

import streamlit as st

from app.components.rubric_view import render_rubric, render_version_badge
from app.context import current_actor, db, get_settings
from app.state import flash, invalidate, render_flash
from core.academics.dto import MilestoneDTO
from core.academics.milestones import list_milestones
from core.clock import ist_date, to_ist, utc_now
from core.errors import RubriQError
from core.rubrics.service import published_rubric_for
from core.submissions.extract import ALLOWED_EXTENSIONS
from core.submissions.service import list_submissions, submit


def render_deadline(milestone: MilestoneDTO) -> None:
    """State the deadline and, if it has passed, how far.

    The penalty *arithmetic* belongs to §5.1 and lands in Phase 4. What belongs
    here now is that lateness is visible before the upload rather than
    discovered afterwards (fix item 10).
    """
    due = to_ist(milestone.due_at)
    days = (ist_date(milestone.due_at) - ist_date(utc_now())).days

    if days > 1:
        st.caption(f"Due {due.strftime('%d %b %Y, %I:%M %p')} IST — in {days} days.")
    elif days == 1:
        st.warning(
            f"Due tomorrow — {due.strftime('%d %b %Y, %I:%M %p')} IST.",
            icon=":material/schedule:",
        )
    elif days == 0:
        st.warning(
            f"Due today at {due.strftime('%I:%M %p')} IST.", icon=":material/schedule:"
        )
    else:
        late = abs(days)
        st.error(
            f"This deadline passed {late} day(s) ago "
            f"({due.strftime('%d %b %Y, %I:%M %p')} IST). You can still submit, and "
            "a late penalty will apply to the milestone total.",
            icon=":material/running_with_errors:",
        )


def render_history(milestone: MilestoneDTO) -> None:
    with db() as session:
        history = list_submissions(actor, session, milestone_id=milestone.id)

    if not history:
        st.caption("You have not submitted anything for this milestone yet.")
        return

    st.dataframe(
        [
            {
                "Version": s.version,
                "Status": "Current" if s.is_latest else "Superseded",
                "Submitted (IST)": to_ist(s.submitted_at).strftime("%d %b %Y, %I:%M %p"),
                "Files": ", ".join(f.filename for f in s.files) or "—",
                "Text read": f"{s.text_extract_chars:,} chars" if s.has_text else "none",
            }
            for s in history
        ],
        hide_index=True,
        use_container_width=True,
    )

    st.caption(
        "Every version is kept. Re-uploading creates a new version and leaves "
        "the previous one retrievable."
    )

    unreadable = [
        f for s in history if s.is_latest for f in s.files if f.extraction_failed
    ]
    for file in unreadable:
        st.warning(
            f"**{file.filename}** — {file.extract_note} It is stored and your guide "
            "can open it, but automated feedback will not be able to read it.",
            icon=":material/description:",
        )


actor = current_actor()

st.title("Submit")

render_flash()

with db() as session:
    milestones = list_milestones(actor, session)

if not milestones:
    st.info(
        "Nothing to submit yet — no milestones have been published for your subjects.",
        icon=":material/event_busy:",
    )
    st.stop()

milestone = st.selectbox(
    "Milestone",
    options=milestones,
    format_func=lambda m: f"{m.subject_code} · Review {m.index} — {m.title}",
)

render_deadline(milestone)

if milestone.description:
    st.write(milestone.description)

st.divider()

# --- the rubric, before the upload ---------------------------------------

st.subheader("What you are being marked on")

with db() as session:
    rubric = published_rubric_for(actor, session, milestone.id)

render_rubric(
    rubric,
    empty_message=(
        "Your guide has not published a rubric for this milestone yet. "
        "Submission opens once they do — you should know what you are being "
        "measured against before you upload."
    ),
)

if rubric is None:
    st.stop()

render_version_badge(rubric)

st.divider()

# --- the upload ----------------------------------------------------------

st.subheader("Your submission")

render_history(milestone)

uploaded = st.file_uploader(
    "Files",
    type=[extension.lstrip(".") for extension in sorted(ALLOWED_EXTENSIONS)],
    accept_multiple_files=True,
    help="PDF, DOCX, TXT or MD. Text is read at upload so your guide's tools "
    "can quote from it.",
)

note = st.text_area(
    "Note for your guide (optional)",
    placeholder="Anything they should know about this submission.",
)

if not uploaded:
    st.caption("Attach at least one file to submit.")
    st.stop()

st.caption(f"{len(uploaded)} file(s) ready: " + ", ".join(f.name for f in uploaded))

if st.button("Submit", type="primary", icon=":material/upload:"):
    files = {file.name: file.getvalue() for file in uploaded}

    try:
        with db() as session:
            result = submit(
                actor,
                session,
                milestone_id=milestone.id,
                files=files,
                uploads_root=get_settings().uploads_root,
                note=note,
            )
        invalidate()
        flash(
            f"Submitted as version {result.version}. "
            f"{result.text_extract_chars:,} characters of text were read."
        )
        st.rerun()
    except RubriQError as exc:
        st.error(str(exc), icon=":material/error:")

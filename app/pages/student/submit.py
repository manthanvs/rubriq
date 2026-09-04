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

from app.components.groups import render_group_summary
from app.components.lateness import consequence_text
from app.components.rubric_view import render_rubric, render_version_badge
from app.context import current_actor, db, get_settings
from app.state import after_mutation, flash, invalidate
from core.academics.dto import MilestoneDTO
from core.academics.milestones import list_milestones
from core.clock import ist_date, to_ist, utc_now
from core.errors import RubriQError
from core.groups.service import granted_group_for, list_groups, request_group
from core.rubrics.service import published_rubric_for
from core.scoring.sheets import policy_for_milestone
from core.submissions.extract import ALLOWED_EXTENSIONS
from core.submissions.service import list_submissions, submit


def lateness_consequence(milestone: MilestoneDTO, days_late: int) -> str:
    """What submitting right now actually costs, in the student's own terms.

    The policy is read from the database rather than assumed, so a subject that
    overrides §5.1 tells the student the truth about *its* rules. The wording
    itself lives in ``app/components/lateness.py``, where it is testable.
    """
    with db() as session:
        policy = policy_for_milestone(actor, session, milestone_id=milestone.id)

    return consequence_text(policy.band_for(days_late), milestone.max_marks)


def render_deadline(milestone: MilestoneDTO) -> None:
    """State the deadline and, if it has passed, what submitting now costs."""
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
            f"({due.strftime('%d %b %Y, %I:%M %p')} IST). You can still submit. "
            + lateness_consequence(milestone, late),
            icon=":material/running_with_errors:",
        )


def render_group_panel(milestone: MilestoneDTO):
    """Where the student sees, or asks for, their group. Returns it if granted.

    Decision #5 puts the grant with the guide, so the honest thing to show a
    student with a pending request is that nothing has happened yet — not a
    hopeful "your group" that quietly submits individually.
    """
    with db() as session:
        granted = granted_group_for(
            actor,
            session,
            subject_id=milestone.subject_id,
            student_email=actor.email,
        )
        mine = list_groups(actor, session, subject_id=milestone.subject_id)

    if granted is not None:
        st.success(
            f"You are submitting as **{granted.name}**. One submission counts "
            "for everyone in it, and every member sees the same versions and "
            "the same feedback.",
            icon=":material/group:",
        )
        st.caption("Members: " + ", ".join(m.label for m in granted.members))
        return granted

    pending = [g for g in mine if g.is_pending]
    refused = [g for g in mine if not g.is_granted and not g.is_pending]

    if pending:
        st.warning(
            f"**{pending[0].name}** is waiting for your guide to approve it. "
            "Until they do, anything you submit is yours alone.",
            icon=":material/hourglass_top:",
        )
        render_group_summary(pending[0])
        return None

    if refused:
        st.info(
            f"**{refused[0].name}** was not approved: {refused[0].decision_note}",
            icon=":material/block:",
        )

    with st.expander("Work in a group?"):
        st.caption(
            "Groups need your guide's approval. Ask here and they will see the "
            "request — nothing changes until they grant it."
        )
        with st.form("request_group"):
            name = st.text_input("Group name", placeholder="Team Alpha")
            mates = st.text_input(
                "Your partners' institute emails, comma separated",
                placeholder="rahul.deshmukh@pccoepune.org",
            )
            if st.form_submit_button("Ask my guide", type="primary"):
                members = [actor.email] + [
                    part.strip() for part in mates.split(",") if part.strip()
                ]
                try:
                    with db() as session:
                        request_group(
                            actor,
                            session,
                            subject_id=milestone.subject_id,
                            name=name,
                            member_emails=members,
                        )
                    after_mutation("Request sent. Your guide decides from here.")
                except RubriQError as exc:
                    st.error(str(exc), icon=":material/error:")

    return None


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
        width="stretch",
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

group = render_group_panel(milestone)

render_history(milestone)

uploaded = st.file_uploader(
    "Files",
    type=[extension.lstrip(".") for extension in sorted(ALLOWED_EXTENSIONS)],
    accept_multiple_files=True,
    help="PDF, DOCX, TXT or MD. Text is read at upload so your guide's tools "
    "can quote from it.",
)

repo_text = st.text_area(
    "Repository links (optional, one per line)",
    placeholder="https://github.com/your-account/your-project",
    help="GitHub only, and only repositories owned by the account your guide "
    "has on record for you — or for a group-mate, once a group is granted. "
    "The link is recorded alongside your submission; nothing is downloaded "
    "from it, so anything you want marked still has to be in the document.",
)
repo_links = [line.strip() for line in repo_text.splitlines() if line.strip()]

note = st.text_area(
    "Note for your guide (optional)",
    placeholder="Anything they should know about this submission.",
)

if not uploaded and not repo_links:
    st.caption("Attach at least one file, or add a repository link, to submit.")
    st.stop()

ready = []
if uploaded:
    ready.append(f"{len(uploaded)} file(s): " + ", ".join(f.name for f in uploaded))
if repo_links:
    ready.append(f"{len(repo_links)} link(s)")
st.caption("Ready — " + "; ".join(ready) + ".")

if st.button("Submit", type="primary", icon=":material/upload:"):
    files = {file.name: file.getvalue() for file in uploaded or []}

    try:
        with db() as session:
            result = submit(
                actor,
                session,
                milestone_id=milestone.id,
                files=files,
                uploads_root=get_settings().uploads_root,
                note=note,
                links=repo_links,
            )
        invalidate()
        whose = f" for {result.group_name}" if result.is_group_work else ""
        flash(
            f"Submitted as version {result.version}{whose}. "
            f"{result.text_extract_chars:,} characters of text were read."
        )
        st.rerun()
    except RubriQError as exc:
        st.error(str(exc), icon=":material/error:")

"""Feedback — student.

Gated on approval. Until a faculty member has signed the sheet off, there is
nothing here: invariant #1 says the AI never publishes a final mark, and
showing an unapproved estimate to a student would publish it in the only sense
that matters.

What it shows is the "followed / not followed" view §4 asks for, per criterion,
which is why ``verdict`` is a stored column rather than something inferred from
the score.
"""

from __future__ import annotations

import streamlit as st

from app.context import current_actor, db
from core.academics.milestones import list_milestones
from core.clock import to_ist
from core.scoring.enums import Verdict
from core.scoring.sheets import sheet_for_submission
from core.submissions.service import latest_submission

VERDICT_HELP = {
    Verdict.FOLLOWED: "Followed",
    Verdict.PARTIAL: "Partly followed",
    Verdict.NOT_FOLLOWED: "Not followed",
    Verdict.NO_EVIDENCE: "No evidence found",
}

actor = current_actor()

st.title("Feedback")

with db() as session:
    milestones = list_milestones(actor, session)

if not milestones:
    st.info("No milestones published yet.", icon=":material/event_busy:")
    st.stop()

milestone = st.selectbox(
    "Milestone",
    options=milestones,
    format_func=lambda m: f"{m.subject_code} · Review {m.index} — {m.title}",
)

with db() as session:
    submission = latest_submission(
        actor, session, milestone_id=milestone.id, student_email=actor.email
    )
    sheet = (
        sheet_for_submission(actor, session, submission.id)
        if submission is not None
        else None
    )

if submission is None:
    st.info(
        "You have not submitted anything for this milestone.", icon=":material/inbox:"
    )
    st.stop()

if sheet is None or not sheet.is_approved:
    st.info(
        "Your guide has not published feedback for this milestone yet. It "
        "appears here once they have reviewed and approved your score sheet.",
        icon=":material/hourglass_top:",
    )
    st.stop()

left, right = st.columns(2)
left.metric("Your mark", sheet.display_total, help=f"Out of {sheet.max_marks:g}")
right.metric("Days late", sheet.days_late)

if sheet.is_absent:
    st.error(
        "This submission was recorded as **absent** under the late policy. That "
        "is a status, not a mark of zero — speak to your guide about "
        "reinstatement if there were circumstances.",
        icon=":material/event_busy:",
    )
elif sheet.reinstated:
    st.info(
        f"Reinstated by your guide — {sheet.reinstate_reason}", icon=":material/gavel:"
    )
elif sheet.penalty > 0:
    st.warning(
        f"A late penalty of {sheet.penalty:g} was applied to the milestone "
        f"total ({sheet.base_total:g} before penalty).",
        icon=":material/running_with_errors:",
    )

st.caption(
    f"Approved by {sheet.approved_by} on "
    f"{to_ist(sheet.approved_at).strftime('%d %b %Y, %I:%M %p')} IST"
)

st.divider()
st.subheader("Against each criterion")

for criterion in sheet.criteria:
    with st.container(border=True):
        head, mark = st.columns([4, 1])
        head.markdown(
            f"**{criterion.verdict.glyph} {criterion.code} — {criterion.title}**"
        )
        head.caption(VERDICT_HELP[criterion.verdict])
        mark.metric("", f"{criterion.score:g}/{criterion.max_score:g}")

        if criterion.rationale:
            st.write(criterion.rationale)
        if criterion.evidence_span:
            st.caption("Evidence from your submission:")
            st.info(criterion.evidence_span)

followed = [c.code for c in sheet.criteria if c.verdict is Verdict.FOLLOWED]
missing = [
    c.code
    for c in sheet.criteria
    if c.verdict in (Verdict.NOT_FOLLOWED, Verdict.NO_EVIDENCE)
]

st.divider()
if followed:
    st.success("Followed: " + ", ".join(followed), icon=":material/check_circle:")
if missing:
    st.warning("Work on next time: " + ", ".join(missing), icon=":material/target:")

if sheet.faculty_note:
    st.subheader("Note from your guide")
    st.write(sheet.faculty_note)

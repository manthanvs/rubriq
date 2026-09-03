"""Reports — faculty.

Score distribution and the criterion-level weak-spot chart (§8).

Every figure is an aggregate of persisted score sheets, so this page cannot
disagree with the Review Grid — it recomputes nothing. Absences are counted
separately rather than folded in as zeroes, because §5.1 exists to keep those
two apart and an average that merges them destroys the distinction.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.context import current_actor, db
from core.academics.milestones import list_milestones
from core.academics.subjects import list_subjects
from core.errors import RubriQError
from core.reports.service import attendance_mix, build_report

actor = current_actor()

st.title("Reports")

with db() as session:
    subjects = list_subjects(actor, session)

if not subjects:
    st.info(
        "No subjects yet — create one on the Subjects page.", icon=":material/school:"
    )
    st.stop()

subject = st.selectbox(
    "Subject", options=subjects, format_func=lambda s: f"{s.label} (sem {s.semester})"
)

with db() as session:
    milestones = list_milestones(actor, session, subject_id=subject.id)

if not milestones:
    st.info("No milestones yet.", icon=":material/event_busy:")
    st.stop()

milestone = st.selectbox(
    "Milestone", options=milestones, format_func=lambda m: f"Review {m.index} — {m.title}"
)

try:
    with db() as session:
        report = build_report(actor, session, milestone_id=milestone.id)
        mix = attendance_mix(actor, session, milestone_id=milestone.id)
except RubriQError as exc:
    st.error(str(exc), icon=":material/error:")
    st.stop()

if not report.has_marks:
    st.info(
        "Nothing scored for this milestone yet. Charts appear once the first "
        "score sheet is saved on the Review Grid.",
        icon=":material/bar_chart:",
    )
    st.stop()

a, b, c, d = st.columns(4)
a.metric("Enrolled", report.enrolled)
b.metric("Scored", report.scored)
c.metric("Approved", report.approved)
d.metric("Absent", report.absent)

if report.not_submitted:
    st.caption(f"{report.not_submitted} student(s) did not submit at all.")

st.divider()
st.subheader("Score distribution")

st.caption(
    f"Out of {report.max_marks:g}. Absent students are excluded — an absence is "
    "a status, not a mark of zero."
)

left, right = st.columns([2, 1])

with left:
    frame = pd.DataFrame(
        {
            "Band": [band.label for band in report.bands],
            "Students": [band.count for band in report.bands],
        }
    ).set_index("Band")
    st.bar_chart(frame, height=260)

with right:
    st.metric("Mean", f"{report.mean:g}")
    st.metric("Median", f"{report.median:g}")
    st.caption(f"Range {report.lowest:g} — {report.highest:g}")

st.subheader("Where the cohort struggled")

st.caption(
    "Mean score per criterion, as a share of what that criterion is out of. "
    "The lowest bar is the part of the rubric to talk about in the next review."
)

weak = pd.DataFrame(
    {
        "Criterion": [f"{c.code}" for c in report.criteria],
        "Mean %": [float(c.mean_percent) for c in report.criteria],
    }
).set_index("Criterion")
st.bar_chart(weak, height=240)

weakest = report.weakest
if weakest is not None:
    st.warning(
        f"**{weakest.code} — {weakest.title}** is the weakest criterion at "
        f"{weakest.mean_percent}% of its maximum"
        + (
            f", and {weakest.unevidenced} submission(s) had no evidence for it."
            if weakest.unevidenced
            else "."
        ),
        icon=":material/target:",
    )

st.dataframe(
    [
        {
            "Code": c.code,
            "Criterion": c.title,
            "Out of": float(c.max_score),
            "Mean %": float(c.mean_percent),
            "Followed": c.verdicts.get("FOLLOWED", 0),
            "Partial": c.verdicts.get("PARTIAL", 0),
            "Not followed": c.verdicts.get("NOT_FOLLOWED", 0),
            "No evidence": c.verdicts.get("NO_EVIDENCE", 0),
            "Must": "Yes" if c.is_mandatory else "",
        }
        for c in report.criteria
    ],
    hide_index=True,
    width="stretch",
)

st.subheader("How the cohort was recorded")
st.caption("Absent, reinstated and not-submitted are distinct outcomes (§5.1).")

st.dataframe(
    [{"Outcome": k, "Students": v} for k, v in mix.items()],
    hide_index=True,
    width="stretch",
)

"""Rubric Builder — faculty.

Build criteria, watch the weight total, publish to freeze. A published rubric
is read-only here because it is read-only in ``core/`` — this page cannot edit
one even if a button were wired to try (fix item 6).
"""

from __future__ import annotations

import streamlit as st

from app.components.rubric_view import (
    render_rubric,
    render_version_badge,
    render_weight_status,
)
from app.context import current_actor, db
from app.state import flash, invalidate, render_flash
from core.academics.milestones import list_milestones
from core.academics.subjects import list_subjects
from core.errors import RubriQError
from core.rubrics.dto import RubricDTO
from core.rubrics.service import (
    add_criterion,
    clone_for_edit,
    create_rubric,
    draft_rubric_for,
    list_rubrics,
    publish_rubric,
    published_rubric_for,
    remove_criterion,
)


def render_draft_editor(draft: RubricDTO) -> None:
    """The editable half: add and remove criteria, then publish."""
    render_version_badge(draft)
    render_rubric(draft, empty_message="No criteria yet — add the first below.")
    render_weight_status(draft)

    if draft.criteria:
        with st.expander("Remove a criterion"):
            code = st.selectbox(
                "Criterion",
                options=[c.code for c in draft.criteria],
                key="remove_code",
            )
            st.caption(
                "Removing deactivates it on this draft. Nothing is deleted — "
                "scores from earlier versions still reference their criteria."
            )
            if st.button("Remove", icon=":material/delete:"):
                try:
                    with db() as session:
                        remove_criterion(actor, session, rubric_id=draft.id, code=code)
                    invalidate()
                    st.rerun()
                except RubriQError as exc:
                    st.error(str(exc), icon=":material/error:")

    with st.form("add_criterion", clear_on_submit=True):
        st.write("**Add a criterion**")

        left, right = st.columns(2)
        code = left.text_input("Code", placeholder=f"C{len(draft.criteria) + 1}")
        title = right.text_input("Title", placeholder="Problem statement and objectives")

        weight_col, score_col, must_col = st.columns([2, 2, 1])
        weight = weight_col.number_input(
            "Weight",
            min_value=0.0,
            max_value=100.0,
            value=float(max(0, 100 - float(draft.total_weight))) or 10.0,
            step=5.0,
            help="Share of 100 across this rubric.",
        )
        max_score = score_col.number_input("Out of", min_value=1, max_value=100, value=10)
        is_mandatory = must_col.checkbox("Mandatory", value=False)

        expected = st.text_area(
            "What counts as evidence",
            placeholder="A stated problem, at least two objectives, and scope in/out.",
            help="Shown to the student before they submit, and used by the AI layer "
            "in Phase 5 to decide what it is looking for.",
        )

        if st.form_submit_button("Add criterion", type="primary"):
            try:
                with db() as session:
                    add_criterion(
                        actor,
                        session,
                        rubric_id=draft.id,
                        code=code,
                        title=title,
                        weight=weight,
                        max_score=max_score,
                        expected_evidence=expected,
                        is_mandatory=is_mandatory,
                    )
                invalidate()
                st.rerun()
            except RubriQError as exc:
                st.error(str(exc), icon=":material/error:")

    st.divider()

    can_publish = draft.weights_are_valid
    st.caption(
        "Publishing freezes this version. Students see it, and it becomes the "
        "rubric submissions are graded against. Editing later creates v"
        f"{draft.version + 1} and leaves this one exactly as it is."
    )

    if st.button(
        f"Publish v{draft.version}",
        type="primary",
        disabled=not can_publish,
        icon=":material/lock:",
    ):
        try:
            with db() as session:
                publish_rubric(actor, session, rubric_id=draft.id)
            invalidate()
            flash(f"Published v{draft.version} — it is now frozen.")
            st.rerun()
        except RubriQError as exc:
            st.error(str(exc), icon=":material/error:")


def render_published(published: RubricDTO) -> None:
    """The frozen half: read-only, with a route to a new version."""
    render_version_badge(published)
    render_rubric(published)

    st.caption(
        "This version is frozen. Submissions already graded against it stay "
        "valid because it cannot change."
    )

    if st.button("Edit as new version", icon=":material/content_copy:"):
        try:
            with db() as session:
                clone = clone_for_edit(actor, session, rubric_id=published.id)
            invalidate()
            flash(
                f"Created draft v{clone.version} — a copy of v{published.version}. "
                f"v{published.version} is unchanged."
            )
            st.rerun()
        except RubriQError as exc:
            st.error(str(exc), icon=":material/error:")


actor = current_actor()

st.title("Rubric Builder")

render_flash()

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
    st.info(
        "No milestones yet — add them from Subjects → Milestones.",
        icon=":material/event_busy:",
    )
    st.stop()

milestone = st.selectbox(
    "Milestone",
    options=milestones,
    format_func=lambda m: f"Review {m.index} — {m.title}",
)

with db() as session:
    published = published_rubric_for(actor, session, milestone.id)
    draft = draft_rubric_for(actor, session, milestone.id)
    history = list_rubrics(actor, session, milestone.id)

st.divider()

if published is None and draft is None:
    st.info(
        "No rubric for this milestone yet. Students cannot submit against a "
        "milestone with no published rubric.",
        icon=":material/rule:",
    )
    if st.button("Start a rubric", type="primary", icon=":material/add:"):
        try:
            with db() as session:
                create_rubric(actor, session, milestone_id=milestone.id)
            invalidate()
            st.rerun()
        except RubriQError as exc:
            st.error(str(exc), icon=":material/error:")
    st.stop()

if draft is not None and published is not None:
    draft_tab, published_tab = st.tabs(
        [f"Draft v{draft.version}", f"Published v{published.version}"]
    )
    with draft_tab:
        render_draft_editor(draft)
    with published_tab:
        render_published(published)
elif draft is not None:
    render_draft_editor(draft)
else:
    render_published(published)

if len(history) > 1:
    with st.expander(f"Version history ({len(history)} versions)"):
        st.dataframe(
            [
                {
                    "Version": r.version,
                    "State": "Published" if r.is_published else "Draft",
                    "Criteria": len(r.criteria),
                    "Total weight": float(r.total_weight),
                    "Published by": r.published_by or "—",
                }
                for r in history
            ],
            hide_index=True,
            use_container_width=True,
        )

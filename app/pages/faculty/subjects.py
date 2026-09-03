"""Subjects — faculty.

Create subjects, add project cycles and milestones, and import the class roll
from CSV. The import is a dry run first, always: see fix item 7.

The tab bodies are functions rather than inline blocks because ``st.stop()``
halts the whole script run, not the block it appears in — calling it inside
one tab would blank the others. A function can just ``return``.
"""

from __future__ import annotations

from datetime import datetime, time

import streamlit as st

from app.context import current_actor, db, get_settings
from app.state import invalidate
from core.academics.dto import SubjectDTO
from core.academics.enrollment import (
    TEMPLATE_CSV,
    ImportVerdict,
    commit_enrollment_import,
    list_enrollments,
    preview_enrollment_import,
    rejected_rows_csv,
)
from core.academics.milestones import (
    create_milestone,
    list_milestones,
    set_milestone_visibility,
)
from core.academics.subjects import (
    create_cycle,
    create_subject,
    list_cycles,
    list_subjects,
)
from core.clock import IST
from core.errors import RubriQError

VERDICT_ICON = {
    ImportVerdict.NEW: "✅",
    ImportVerdict.ALREADY_ENROLLED: "↔️",
    ImportVerdict.INVALID_DOMAIN: "🚫",
    ImportVerdict.MALFORMED: "⚠️",
    ImportVerdict.DUPLICATE_IN_FILE: "🔁",
    ImportVerdict.FACULTY_ADDRESS: "🎓",
}


def render_new_subject_form(has_subjects: bool) -> None:
    with st.expander("New subject", expanded=not has_subjects):
        with st.form("new_subject", clear_on_submit=True):
            code = st.text_input("Code", placeholder="MCA33EL03")
            name = st.text_input("Name", placeholder="Mini Project")
            semester = st.number_input("Semester", 1, 6, value=3, step=1)

            if not st.form_submit_button("Create subject", type="primary"):
                return
            try:
                with db() as session:
                    created = create_subject(
                        actor, session, code=code, name=name, semester=int(semester)
                    )
                invalidate()
                st.success(f"Created {created.label}.")
                st.rerun()
            except RubriQError as exc:
                st.error(str(exc), icon=":material/error:")


def render_roll(subject: SubjectDTO) -> None:
    with db() as session:
        roll = list_enrollments(actor, session, subject.id)

    if not roll:
        st.info(
            "Nobody enrolled yet — use the Import students tab.",
            icon=":material/group_off:",
        )
        return

    st.dataframe(
        [
            {
                "PRN": e.prn or "—",
                "Name": e.student_name or "—",
                "Email": e.student_email,
                "Batch": e.batch or "—",
                "Group": e.group_label or "—",
            }
            for e in roll
        ],
        hide_index=True,
        use_container_width=True,
    )
    st.caption(f"{len(roll)} student(s) enrolled.")


def render_cycle_form(subject: SubjectDTO) -> None:
    st.info("No project cycle yet — milestones hang off a cycle.")
    with st.form("new_cycle", clear_on_submit=True):
        title = st.text_input("Cycle title", value="Mini Project")
        year = st.text_input("Academic year", value="2026-27")

        if not st.form_submit_button("Create cycle", type="primary"):
            return
        try:
            with db() as session:
                create_cycle(
                    actor, session, subject_id=subject.id, title=title, academic_year=year
                )
            invalidate()
            st.rerun()
        except RubriQError as exc:
            st.error(str(exc), icon=":material/error:")


def render_milestones(subject: SubjectDTO) -> None:
    with db() as session:
        cycles = list_cycles(actor, session, subject.id)

    if not cycles:
        render_cycle_form(subject)
        return

    cycle = st.selectbox(
        "Cycle", options=cycles, format_func=lambda c: f"{c.title} ({c.academic_year})"
    )

    with db() as session:
        milestones = list_milestones(actor, session, subject_id=subject.id)

    for milestone in milestones:
        left, right = st.columns([5, 1])
        left.write(f"**Review {milestone.index} — {milestone.title}**")
        left.caption(f"{milestone.max_marks} marks")
        published = right.toggle(
            "Published",
            value=milestone.is_visible,
            key=f"vis_{milestone.id}",
            label_visibility="collapsed",
        )
        if published != milestone.is_visible:
            with db() as session:
                set_milestone_visibility(
                    actor, session, milestone_id=milestone.id, is_visible=published
                )
            invalidate()
            st.rerun()

    if not milestones:
        st.caption("No milestones yet.")

    st.divider()

    with st.form("new_milestone", clear_on_submit=True):
        st.write("**Add a milestone**")
        index = st.number_input("Review number", 1, 20, value=len(milestones) + 1, step=1)
        title = st.text_input("Title", placeholder="Review 1 — Synopsis & SRS")
        description = st.text_area("Description", placeholder="What to submit")
        public_notes = st.text_area(
            "Notes for students (optional)",
            placeholder="Guidance the assistant may quote when students ask.",
            help="Part of the context the Ask RubriQ assistant is allowed to "
            "use. Anything not written here is not something it can tell them.",
        )
        due_date = st.date_input("Due date (IST)")
        due_time = st.time_input("Due time (IST)", value=time(23, 59))
        max_marks = st.number_input("Max marks", 1, 100, value=25)

        if not st.form_submit_button("Add milestone", type="primary"):
            return
        try:
            # Built in IST because that is what the faculty member typed, and
            # stored as UTC. §5.1's boundary depends on this not being fudged
            # into a naive datetime somewhere along the way.
            due_at = datetime.combine(due_date, due_time).replace(tzinfo=IST)
            with db() as session:
                create_milestone(
                    actor,
                    session,
                    cycle_id=cycle.id,
                    index=int(index),
                    title=title,
                    description=description,
                    public_notes=public_notes,
                    due_at=due_at,
                    max_marks=int(max_marks),
                )
            invalidate()
            st.success(f"Added review {int(index)}.")
            st.rerun()
        except RubriQError as exc:
            st.error(str(exc), icon=":material/error:")


def render_import(subject: SubjectDTO) -> None:
    st.download_button(
        "Download CSV template",
        data=TEMPLATE_CSV,
        file_name="rubriq_enrollment_template.csv",
        mime="text/csv",
        icon=":material/download:",
    )

    uploaded = st.file_uploader("Student list (CSV)", type=["csv"])

    if uploaded is None:
        st.caption("Required columns: email, name, prn. Optional: batch, group_label.")
        return

    csv_text = uploaded.getvalue().decode("utf-8-sig", errors="replace")
    settings = get_settings()

    try:
        # Re-previewed on every rerun from the uploaded bytes, so what is on
        # screen is never a stale snapshot of an earlier database state.
        with db() as session:
            preview = preview_enrollment_import(
                actor,
                session,
                subject_id=subject.id,
                csv_text=csv_text,
                settings=settings,
            )
    except RubriQError as exc:
        st.error(str(exc), icon=":material/error:")
        return

    counts = {k: v for k, v in preview.counts.items() if v}
    st.write(" · ".join(f"{VERDICT_ICON[k]} {k} {v}" for k, v in counts.items()))

    st.dataframe(
        [
            {
                "Line": row.line_number,
                " ": VERDICT_ICON[row.verdict],
                "Verdict": str(row.verdict),
                "Email": row.email or "—",
                "Name": row.name or "—",
                "PRN": row.prn or "—",
                "Reason": row.message,
            }
            for row in preview.rows
        ],
        hide_index=True,
        use_container_width=True,
    )

    if preview.rejected:
        st.download_button(
            f"Download {len(preview.rejected)} rejected row(s)",
            data=rejected_rows_csv(preview),
            file_name="rubriq_rejected_rows.csv",
            mime="text/csv",
            icon=":material/file_download:",
        )

    if not preview.committable:
        st.warning("Nothing to import — every row was rejected.", icon=":material/block:")
        return

    st.info(
        f"**{len(preview.committable)}** student(s) will be enrolled. "
        f"**{len(preview.rejected)}** row(s) will be skipped.",
        icon=":material/info:",
    )

    if not st.button(
        f"Enrol {len(preview.committable)} student(s)",
        type="primary",
        icon=":material/group_add:",
    ):
        return

    try:
        with db() as session:
            result = commit_enrollment_import(
                actor,
                session,
                subject_id=subject.id,
                csv_text=csv_text,
                settings=settings,
            )
        invalidate()
        st.success(
            f"Enrolled {len(result.committable)}. Skipped {len(result.rejected)}.",
            icon=":material/check_circle:",
        )
    except RubriQError as exc:
        st.error(str(exc), icon=":material/error:")


actor = current_actor()

st.title("Subjects")

with db() as session:
    subjects = list_subjects(actor, session)

render_new_subject_form(bool(subjects))

if not subjects:
    st.info(
        "No subjects yet — create one above to get started.", icon=":material/school:"
    )
else:
    chosen = st.selectbox(
        "Subject",
        options=subjects,
        format_func=lambda s: (
            f"{s.label} (sem {s.semester}) — {s.enrolled_count} enrolled"
        ),
    )

    roll_tab, milestones_tab, import_tab = st.tabs(
        ["Roll", "Milestones", "Import students"]
    )

    with roll_tab:
        render_roll(chosen)
    with milestones_tab:
        render_milestones(chosen)
    with import_tab:
        render_import(chosen)

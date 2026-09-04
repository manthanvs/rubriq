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

from app.components.groups import group_table, render_pending_decisions
from app.context import current_actor, db, get_settings
from app.state import after_mutation, invalidate
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
from core.db.models import User
from core.errors import RubriQError
from core.groups.service import create_group, list_groups, set_github_username

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
                after_mutation(f"Created {created.label}.")
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
        width="stretch",
    )
    st.caption(f"{len(roll)} student(s) enrolled.")


def render_groups(subject: SubjectDTO) -> None:
    """Decision #5 — groups exist here, or they do not exist.

    Requests and outright creation land on one page because they are the same
    decision reached from two directions, and a faculty member should be able
    to see both without remembering which one a particular group came from.
    """
    with db() as session:
        groups = list_groups(actor, session, subject_id=subject.id)
        roll = list_enrollments(actor, session, subject.id)

    st.caption(
        "A group is only a group once you grant it. Until then it changes "
        "nothing: members cannot see each other's work and submissions stay "
        "individual."
    )

    st.markdown("**Waiting on you**")
    render_pending_decisions(actor, groups)

    st.divider()
    st.markdown("**All groups**")

    if not groups:
        st.info(
            "No groups in this subject yet — form one below, or wait for a "
            "student to ask.",
            icon=":material/group_off:",
        )
    else:
        st.dataframe(group_table(groups), hide_index=True, width="stretch")

    if not roll:
        st.caption("Enrol students before forming groups.")
        return

    st.divider()
    with st.form(f"new_group_{subject.id}"):
        st.markdown("**Form a group**")
        name = st.text_input("Group name", placeholder="Team Alpha")
        members = st.multiselect(
            "Members",
            options=[e.student_email for e in roll],
            format_func=lambda email: next(
                (
                    f"{e.student_name or e.student_email} ({e.prn or '—'})"
                    for e in roll
                    if e.student_email == email
                ),
                email,
            ),
            help="A group you form here is granted immediately — you are the approval.",
        )
        note = st.text_input("Note (optional)", placeholder="Why this pairing.")

        if st.form_submit_button("Create group", type="primary"):
            try:
                with db() as session:
                    created = create_group(
                        actor,
                        session,
                        subject_id=subject.id,
                        name=name,
                        member_emails=list(members),
                        note=note,
                    )
                after_mutation(f"Created and granted {created.name}.")
            except RubriQError as exc:
                st.error(str(exc), icon=":material/error:")


def render_github_register(subject: SubjectDTO) -> None:
    """Decision #6 — the accounts a repository URL is checked against.

    Faculty-only by design. The profiles are the ones students already shared
    with their guide; letting a student type their own would make the
    ownership check something the person being checked configures.
    """
    with db() as session:
        roll = list_enrollments(actor, session, subject.id)

    if not roll:
        st.info(
            "Nobody enrolled yet — use the Import students tab.",
            icon=":material/group_off:",
        )
        return

    st.caption(
        "A submitted repository link is accepted only if it belongs to the "
        "account recorded here. A student with no account on record cannot "
        "submit a link at all."
    )

    missing = [e for e in roll if not _github_of(e.student_email)]
    if missing:
        st.warning(
            f"{len(missing)} of {len(roll)} students have no GitHub account on record.",
            icon=":material/link_off:",
        )

    for entry in roll:
        current = _github_of(entry.student_email)
        cols = st.columns([3, 2, 1])
        cols[0].markdown(
            f"{entry.student_name or entry.student_email}  \
"
            f"<small>{entry.prn or '—'}</small>",
            unsafe_allow_html=True,
        )
        typed = cols[1].text_input(
            "GitHub account",
            value=current or "",
            key=f"gh_{entry.student_email}",
            label_visibility="collapsed",
            placeholder="github username",
        )
        if cols[2].button("Save", key=f"ghs_{entry.student_email}"):
            try:
                with db() as session:
                    set_github_username(
                        actor,
                        session,
                        student_email=entry.student_email,
                        username=typed,
                    )
                after_mutation(f"Recorded GitHub for {entry.student_email}.")
            except RubriQError as exc:
                st.error(str(exc), icon=":material/error:")


def _github_of(student_email: str) -> str | None:
    """The account on record, read fresh rather than cached in the widget."""
    with db() as session:
        return session.get(User, student_email).github_username


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
            after_mutation(f"Added review {int(index)}.")
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
        width="stretch",
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

    roll_tab, groups_tab, github_tab, milestones_tab, import_tab = st.tabs(
        ["Roll", "Groups", "GitHub", "Milestones", "Import students"]
    )

    with roll_tab:
        render_roll(chosen)
    with groups_tab:
        render_groups(chosen)
    with github_tab:
        render_github_register(chosen)
    with milestones_tab:
        render_milestones(chosen)
    with import_tab:
        render_import(chosen)

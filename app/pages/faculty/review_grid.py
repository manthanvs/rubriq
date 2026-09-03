"""Review Grid — faculty. The centrepiece (§7).

One row per enrolled student, needing-attention first. Selecting a row opens a
drawer to score, override with a reason, and approve.

Three things this page deliberately does **not** do:

* compute a mark — every number comes from ``core/scoring``;
* build its own export — both buttons call ``build_export_rows`` (fix item 11);
* decide who needs attention — that predicate lives on the DTO so the
  dashboard count cannot disagree with this filter (fix item 8).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.context import current_actor, db
from app.state import flash, invalidate, render_flash
from core.academics.milestones import list_milestones
from core.academics.subjects import list_subjects
from core.clock import to_ist, utc_now
from core.errors import RubriQError
from core.exports.rows import build_export_rows
from core.exports.tsv import to_tsv
from core.exports.xlsx import to_xlsx
from core.rubrics.service import published_rubric_for
from core.scoring.dto import GridRow
from core.scoring.enums import Verdict
from core.scoring.grid import list_grid_rows
from core.scoring.sheets import (
    approval_blockers,
    approve_sheet,
    override_criterion,
    override_history,
    reinstate,
    save_manual_scores,
)

VERDICT_CHOICES = [
    Verdict.FOLLOWED,
    Verdict.PARTIAL,
    Verdict.NOT_FOLLOWED,
    Verdict.NO_EVIDENCE,
]


def build_frame(rows: tuple[GridRow, ...], codes: tuple[str, ...]) -> pd.DataFrame:
    """The grid table. Verdict glyphs per criterion, totals at the end."""
    records = []
    for row in rows:
        sheet = row.sheet
        record = {
            "!": "●" if row.needs_attention else "",
            "PRN": row.prn or "—",
            "Name": row.student_name or row.student_email,
            "Ver": row.submission_version or "",
            "Days Late": sheet.days_late if sheet else "",
            "Status": row.status_label,
        }
        by_code = {c.code: c for c in (sheet.criteria if sheet else ())}
        for code in codes:
            criterion = by_code.get(code)
            record[code] = criterion.verdict.glyph if criterion else ""

        record["Base"] = float(sheet.base_total) if sheet else None
        record["Penalty"] = float(sheet.penalty) if sheet else None
        # display_total, so an absent student is never a number (fix item 10).
        record["Final"] = sheet.display_total if sheet else ""
        record["By"] = sheet.provenance if sheet else ""
        records.append(record)

    return pd.DataFrame(records)


@st.dialog("Score sheet", width="large")
def score_drawer(row: GridRow, codes: tuple[str, ...], rubric) -> None:
    """The per-student drawer: score, override, approve."""
    st.write(f"**{row.student_name or row.student_email}** · {row.prn or '—'}")

    if row.submission_id is None:
        st.warning("No submission for this milestone.", icon=":material/inbox:")
        return

    st.caption(
        f"Submission v{row.submission_version} · "
        f"{to_ist(row.submitted_at).strftime('%d %b %Y, %I:%M %p')} IST"
    )

    if row.has_newer_version:
        # Fix item 2: never silently rebind an approval to work nobody read.
        st.warning(
            "A newer submission version exists. This sheet grades the version "
            "shown above, not the newest one.",
            icon=":material/history:",
        )

    sheet = row.sheet

    if sheet is not None and sheet.reinstated:
        st.info(f"Reinstated — {sheet.reinstate_reason}", icon=":material/gavel:")

    tab_score, tab_history = st.tabs(["Score", "History"])

    with tab_score:
        if sheet is not None and sheet.is_approved:
            st.success(
                f"Approved by {sheet.approved_by} on "
                f"{to_ist(sheet.approved_at).strftime('%d %b %Y, %I:%M %p')} IST",
                icon=":material/verified:",
            )
            render_override_form(sheet)
            return

        render_score_form(row, rubric)

    with tab_history:
        if sheet is None:
            st.caption("Nothing scored yet.")
            return
        entries = []
        with db() as session:
            entries = override_history(actor, session, sheet.id)
        if not entries:
            st.caption("No overrides on this sheet.")
        else:
            st.dataframe(
                [
                    {
                        "Criterion": e["criterion"],
                        "From": float(e["from"]),
                        "To": float(e["to"]),
                        "By": e["by"],
                        "When (IST)": to_ist(e["at"]).strftime("%d %b, %I:%M %p"),
                        "Reason": e["reason"],
                    }
                    for e in entries
                ],
                hide_index=True,
                use_container_width=True,
            )


def render_score_form(row: GridRow, rubric) -> None:
    """Manual scoring, one row per criterion."""
    existing = {c.code: c for c in (row.sheet.criteria if row.sheet else ())}

    with st.form(f"score_{row.submission_id}"):
        values: dict[str, tuple[float, Verdict]] = {}

        for criterion in rubric.criteria:
            current = existing.get(criterion.code)
            st.markdown(f"**{criterion.code} — {criterion.title}**")
            if criterion.expected_evidence:
                st.caption(criterion.expected_evidence)

            score_col, verdict_col = st.columns([1, 2])
            score = score_col.number_input(
                f"Score (out of {criterion.max_score})",
                min_value=0.0,
                max_value=float(criterion.max_score),
                value=float(current.score) if current else 0.0,
                step=0.5,
                key=f"s_{row.submission_id}_{criterion.code}",
            )
            verdict = verdict_col.selectbox(
                "Verdict",
                options=VERDICT_CHOICES,
                index=VERDICT_CHOICES.index(current.verdict) if current else 0,
                format_func=lambda v: f"{v.glyph}  {v}",
                key=f"v_{row.submission_id}_{criterion.code}",
            )
            values[criterion.code] = (score, verdict)
            st.divider()

        note = st.text_area(
            "Note for the student",
            value=(row.sheet.faculty_note if row.sheet else "") or "",
        )

        if st.form_submit_button("Save scores", type="primary"):
            try:
                with db() as session:
                    save_manual_scores(
                        actor,
                        session,
                        submission_id=row.submission_id,
                        scores={k: (v[0], v[1]) for k, v in values.items()},
                        faculty_note=note,
                    )
                invalidate()
                flash("Scores saved.")
                st.rerun()
            except RubriQError as exc:
                st.error(str(exc), icon=":material/error:")

    if row.sheet is None:
        return

    blockers = approval_blockers(row.sheet)
    if blockers:
        st.warning(
            "Cannot approve — " + "; ".join(blockers) + ".", icon=":material/block:"
        )

    left, right = st.columns(2)

    if left.button(
        "Approve",
        type="primary",
        disabled=bool(blockers),
        icon=":material/verified:",
        key=f"approve_{row.sheet.id}",
    ):
        try:
            with db() as session:
                approve_sheet(actor, session, score_sheet_id=row.sheet.id)
            invalidate()
            flash(f"Approved {row.student_name or row.student_email}.")
            st.rerun()
        except RubriQError as exc:
            st.error(str(exc), icon=":material/error:")

    if row.sheet.is_absent or row.sheet.days_late > 5:
        with right.popover("Reinstate", icon=":material/gavel:"):
            reason = st.text_input("Reason", key=f"rein_{row.sheet.id}")
            if st.button("Confirm reinstatement", key=f"reinbtn_{row.sheet.id}"):
                try:
                    with db() as session:
                        reinstate(
                            actor, session, score_sheet_id=row.sheet.id, reason=reason
                        )
                    invalidate()
                    flash("Reinstated — the late penalty is zeroed.")
                    st.rerun()
                except RubriQError as exc:
                    st.error(str(exc), icon=":material/error:")


def render_override_form(sheet) -> None:
    """Changing an approved mark: reason required, approval cleared."""
    st.caption(
        "This sheet is approved. Changing a mark records an override with your "
        "reason and clears the approval, so someone has to sign it off again."
    )

    with st.form(f"override_{sheet.id}"):
        code = st.selectbox("Criterion", options=[c.code for c in sheet.criteria])
        criterion = next(c for c in sheet.criteria if c.code == code)

        new_score = st.number_input(
            f"New score (out of {criterion.max_score})",
            min_value=0.0,
            max_value=float(criterion.max_score),
            value=float(criterion.score),
            step=0.5,
        )
        new_verdict = st.selectbox(
            "Verdict",
            options=VERDICT_CHOICES,
            index=VERDICT_CHOICES.index(criterion.verdict),
            format_func=lambda v: f"{v.glyph}  {v}",
        )
        reason = st.text_area("Reason (required)")

        if st.form_submit_button("Apply override", type="primary"):
            try:
                with db() as session:
                    override_criterion(
                        actor,
                        session,
                        score_sheet_id=sheet.id,
                        criterion_code=code,
                        new_score=new_score,
                        new_verdict=new_verdict,
                        reason=reason,
                    )
                invalidate()
                flash("Override applied. The sheet needs approving again.")
                st.rerun()
            except RubriQError as exc:
                st.error(str(exc), icon=":material/error:")


def render_bulk_approve(rows: tuple[GridRow, ...]) -> None:
    """Fix item 4: show the excluded count *before* confirming, not after."""
    candidates = [
        r
        for r in rows
        if r.sheet is not None
        and not r.sheet.is_approved
        and not approval_blockers(r.sheet)
    ]
    excluded = [
        r
        for r in rows
        if r.sheet is not None and not r.sheet.is_approved and approval_blockers(r.sheet)
    ]

    if not candidates and not excluded:
        return

    with st.expander(f"Approve all eligible ({len(candidates)})"):
        st.write(
            f"**{len(candidates)}** sheet(s) will be approved. "
            f"**{len(excluded)}** will be skipped."
        )
        if excluded:
            skipped = [
                f"{r.prn or r.student_email} ({'; '.join(approval_blockers(r.sheet))})"
                for r in excluded
            ]
            st.caption("Skipped: " + ", ".join(skipped))

        if candidates and st.button(
            f"Approve {len(candidates)}", type="primary", icon=":material/done_all:"
        ):
            approved = 0
            try:
                for row in candidates:
                    with db() as session:
                        approve_sheet(actor, session, score_sheet_id=row.sheet.id)
                    approved += 1
                invalidate()
                flash(f"Approved {approved}. Skipped {len(excluded)}.")
                st.rerun()
            except RubriQError as exc:
                st.error(f"Stopped after {approved}: {exc}", icon=":material/error:")


actor = current_actor()

st.title("Review Grid")
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
    st.info("No milestones yet.", icon=":material/event_busy:")
    st.stop()

milestone = st.selectbox(
    "Milestone", options=milestones, format_func=lambda m: f"Review {m.index} — {m.title}"
)

with db() as session:
    rubric = published_rubric_for(actor, session, milestone.id)
    rows = list_grid_rows(actor, session, milestone_id=milestone.id)

if rubric is None:
    st.warning(
        "No published rubric for this milestone — publish one in the Rubric "
        "Builder before scoring.",
        icon=":material/rule:",
    )
    st.stop()

codes = tuple(c.code for c in rubric.criteria)

needing = [r for r in rows if r.needs_attention]

a, b, c, d = st.columns(4)
a.metric("Students", len(rows))
b.metric("Needs attention", len(needing))
c.metric("Approved", sum(1 for r in rows if r.sheet and r.sheet.is_approved))
d.metric("Max marks", f"{milestone.max_marks:g}")

only_attention = st.toggle("Show only rows needing attention", value=False)
visible = needing if only_attention else list(rows)

if not visible:
    st.success("Nothing needs attention here.", icon=":material/task_alt:")
else:
    st.caption(
        "Legend: ✓ followed · ~ partial · ✗ not followed · ? no evidence"
        " · ● needs attention"
    )

    event = st.dataframe(
        build_frame(tuple(visible), codes),
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "!": st.column_config.TextColumn("!", width="small"),
            "PRN": st.column_config.TextColumn(width="small"),
            "Ver": st.column_config.NumberColumn(width="small", format="v%d"),
            "Base": st.column_config.NumberColumn(width="small", format="%.2f"),
            "Penalty": st.column_config.NumberColumn(width="small", format="%.2f"),
            "Final": st.column_config.TextColumn(width="small"),
        },
    )

    selected = event.selection.rows if event and event.selection else []
    if selected:
        score_drawer(visible[selected[0]], codes, rubric)

render_bulk_approve(tuple(rows))

st.divider()
st.subheader("Export")

with db() as session:
    bundle = build_export_rows(
        actor, session, milestone_id=milestone.id, generated_at=utc_now()
    )

st.caption(
    "Both exports are built from the saved score sheets, not from this table, "
    "and carry identical numbers. Unapproved rows are marked as estimates."
)

st.download_button(
    "Download .xlsx",
    data=to_xlsx(bundle),
    file_name=f"{bundle.filename_stem}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary",
    icon=":material/download:",
)

with st.expander("Copy as TSV (paste into Excel or Sheets)"):
    st.code(to_tsv(bundle), language=None)

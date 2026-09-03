"""The shared rubric display.

Written once and called by both roles (§8). The student sees this *before*
uploading — §10 calls that "the entire point of the system", so the Submit page
renders it above the file picker, not below it.

Faculty see the same table while building, which is deliberate: the thing being
edited and the thing the student will read are the same view, so there is no
gap between what was written and what was understood.
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import streamlit as st

from core.rubrics.dto import RubricDTO


def render_rubric(
    rubric: RubricDTO | None,
    *,
    empty_message: str = "No rubric published for this milestone yet.",
    show_weights: bool = True,
) -> None:
    """Render a rubric's criteria as a table."""
    if rubric is None:
        st.info(empty_message, icon=":material/rule:")
        return

    if not rubric.criteria:
        st.warning("This rubric has no criteria yet.", icon=":material/rule:")
        return

    frame = pd.DataFrame(
        [
            {
                "Code": c.code,
                "Criterion": c.title,
                "What is expected": c.expected_evidence or c.description or "—",
                "Weight": float(c.weight),
                "Out of": float(c.max_score),
                "Must": "Yes" if c.is_mandatory else "",
            }
            for c in rubric.criteria
        ]
    )

    if not show_weights:
        frame = frame.drop(columns=["Weight"])

    st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        column_config={
            "Code": st.column_config.TextColumn(width="small"),
            "Criterion": st.column_config.TextColumn(width="medium"),
            "What is expected": st.column_config.TextColumn(width="large"),
            "Weight": st.column_config.NumberColumn(
                width="small",
                format="%.2f",
                help="Share of 100 for this milestone.",
            ),
            "Out of": st.column_config.NumberColumn(width="small", format="%.0f"),
            "Must": st.column_config.TextColumn(
                "Must",
                width="small",
                help="Mandatory — cannot be left unresolved when approving.",
            ),
        },
    )

    if rubric.mandatory_codes:
        st.caption(
            "Mandatory criteria: "
            + ", ".join(rubric.mandatory_codes)
            + " — these must be evidenced."
        )


def render_weight_status(rubric: RubricDTO) -> None:
    """Live "weights must sum to 100" feedback while building.

    Shown continuously rather than only on the publish attempt: finding out
    the weights are wrong at the moment you try to freeze the rubric is the
    worst time to find out.
    """
    total = rubric.total_weight
    target = Decimal("100")

    if not rubric.criteria:
        st.caption("Add criteria to begin. Weights must total 100 to publish.")
        return

    if total == target:
        st.success(f"Weights total {total} — ready to publish.", icon=":material/check:")
        return

    difference = target - total
    direction = "short of" if difference > 0 else "over"
    st.warning(
        f"Weights total **{total}**, which is {abs(difference)} {direction} 100. "
        "The rubric cannot be published until they sum to exactly 100.",
        icon=":material/balance:",
    )


def render_version_badge(rubric: RubricDTO) -> None:
    """One line stating which version this is and whether it is frozen."""
    if rubric.is_published:
        stamp = rubric.published_at.strftime("%d %b %Y") if rubric.published_at else ""
        st.caption(f"**v{rubric.version}** · published {stamp} · frozen")
    else:
        st.caption(f"**v{rubric.version}** · draft · not visible to students")

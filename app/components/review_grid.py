"""Table shaping for the faculty review grid (§7), pulled out of the page.

The page itself is a Streamlit script: importing it runs it. These are the
parts worth asserting on — which columns exist, in what order, and what happens
to a rubric wide enough to push the totals off the right-hand edge (fix item
12) — so they live here, where a test can import them.

Still a view module: it decides how a row *looks*, never what it is worth. Every
number it renders was computed in ``core/scoring``.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.scoring.dto import GridRow

#: Past this many criteria the glyph block leaves the main table. Eight narrow
#: verdict columns is roughly what fits alongside identity and totals before the
#: totals start scrolling off the right-hand edge — and the totals are the part
#: a faculty member is actually reading.
CRITERION_OVERFLOW = 8

LEGEND = (
    "Legend: ✓ followed · ~ partial · ✗ not followed · ? no evidence · ● needs attention"
)


def build_frame(rows: tuple[GridRow, ...], codes: tuple[str, ...]) -> pd.DataFrame:
    """The grid table. Verdict glyphs per criterion, totals at the end.

    ``codes`` is empty when the rubric is wide enough that the verdict block has
    been moved into its own table — see ``CRITERION_OVERFLOW``.
    """
    records = []
    for row in rows:
        sheet = row.sheet
        record = {
            "!": "●" if row.needs_attention else "",
            "PRN": row.prn or "—",
            "Name": row.student_name or row.student_email,
            "Ver": f"v{row.submission_version}" if row.submission_version else "",
            # Text, not a number: a row with nothing submitted has no days-late
            # at all, and a blank in a numeric column renders as a stray 0.
            "Days Late": str(sheet.days_late) if sheet else "",
            "Status": row.status_label,
        }
        by_code = {c.code: c for c in (sheet.criteria if sheet else ())}
        for code in codes:
            criterion = by_code.get(code)
            record[code] = criterion.verdict.glyph if criterion else ""

        # All three totals go through one renderer and are text, for the same
        # reason: a row with no sheet has no base and no penalty, and a null in
        # a numeric column renders as the word "None" — which reads as a value.
        # ``display_total`` also keeps ABSENT out of a number (fix item 10).
        record["Base"] = f"{sheet.base_total}" if sheet else ""
        record["Penalty"] = f"{sheet.penalty}" if sheet else ""
        record["Final"] = sheet.display_total if sheet else ""
        record["By"] = sheet.provenance if sheet else ""
        records.append(record)

    return pd.DataFrame(records)


def split_criteria(codes: tuple[str, ...]) -> tuple[tuple[str, ...], bool]:
    """Which verdict columns stay inline, and whether any were moved out.

    Fix item 12: past ``CRITERION_OVERFLOW`` the whole block moves rather than
    half of it, because a table showing C1..C8 and hiding C9 is worse than one
    that says plainly where the verdicts went.
    """
    if len(codes) > CRITERION_OVERFLOW:
        return (), True
    return codes, False


def build_criterion_frame(
    rows: tuple[GridRow, ...], codes: tuple[str, ...]
) -> pd.DataFrame:
    """Identity plus verdict glyphs only — the overflow table for a wide rubric.

    It repeats PRN and name because a table you have to read alongside another
    table is worse than one extra column.
    """
    records = []
    for row in rows:
        by_code = {c.code: c for c in (row.sheet.criteria if row.sheet else ())}
        record = {
            "PRN": row.prn or "—",
            "Name": row.student_name or row.student_email,
        }
        for code in codes:
            criterion = by_code.get(code)
            record[code] = criterion.verdict.glyph if criterion else ""
        records.append(record)

    return pd.DataFrame(records)


def grid_column_config(rubric, codes: tuple[str, ...]) -> dict:
    """Explicit widths, pinned identity, and the criterion title as a tooltip.

    Without explicit widths the table sizes itself to its contents, so adding
    one long faculty name reflows the whole grid and the totals move. Pinning
    ``!``, PRN and Name keeps the row identifiable while the verdicts scroll.
    """
    titles = {c.code: c.title for c in rubric.criteria}
    config = {
        "!": st.column_config.TextColumn(
            "!", width=44, pinned=True, help="Needs a human look — see the legend."
        ),
        "PRN": st.column_config.TextColumn(width=110, pinned=True),
        "Name": st.column_config.TextColumn(width=170, pinned=True),
        "Ver": st.column_config.TextColumn(width=60, help="Submission version graded."),
        "Days Late": st.column_config.TextColumn(width=90),
        "Status": st.column_config.TextColumn(width=130),
        "Base": st.column_config.TextColumn(width=80),
        "Penalty": st.column_config.TextColumn(width=80),
        "Final": st.column_config.TextColumn(
            width=80, help="ABSENT is a status, never a number (§5.1)."
        ),
        "By": st.column_config.TextColumn(
            width=110, help="AI, MANUAL or OVERRIDDEN — where this mark came from."
        ),
    }
    for code in codes:
        config[code] = st.column_config.TextColumn(
            code, width=52, help=titles.get(code, code)
        )
    return config

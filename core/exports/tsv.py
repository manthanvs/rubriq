"""TSV export — the `st.code` copy button path from §7.

Tab-separated rather than comma, because pasting into Excel or Sheets then
splits into columns without an import dialog, which is the whole point of
offering this alongside the .xlsx.

What it copies is the assessment sheet's table — headings, the Marks row, one
row per student — so a paste lands in the department's own sheet in the order
the printed form uses. The raw data stays in the workbook.
"""

from __future__ import annotations

from core.exports.rows import ExportBundle

#: Tabs and newlines inside a cell would break the row/column structure that
#: makes a paste land correctly.
_ESCAPES = {"\t": " ", "\r": " ", "\n": " "}


def _clean(value: str) -> str:
    for bad, good in _ESCAPES.items():
        value = value.replace(bad, good)
    return value


def to_tsv(bundle: ExportBundle) -> str:
    """Render the assessment table as tab-separated text.

    Writes ``bundle.assessment.table()`` and nothing else — the same rows the
    spreadsheet's first sheet is drawn from, so it cannot disagree with it
    (fix item 11).
    """
    if bundle.assessment is None:
        raise ValueError("The bundle was built without its assessment sheet.")
    return "\n".join(
        "\t".join(_clean(cell) for cell in row) for row in bundle.assessment.table()
    )

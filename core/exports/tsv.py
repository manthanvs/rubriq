"""TSV export — the `st.code` copy button path from §7.

Tab-separated rather than comma, because pasting into Excel or Sheets then
splits into columns without an import dialog, which is the whole point of
offering this alongside the .xlsx.
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
    """Render the bundle as tab-separated text.

    Writes ``bundle.cells()`` and nothing else — no formatting decisions of its
    own, so it cannot disagree with the spreadsheet (fix item 11).
    """
    return "\n".join("\t".join(_clean(cell) for cell in row) for row in bundle.cells())

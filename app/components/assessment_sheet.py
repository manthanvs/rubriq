"""The department's assessment sheet, drawn on the page.

The same :class:`~core.exports.assessment.AssessmentSheet` the Excel export
writes, rendered as HTML — so what a guide sees in the score drawer, what a
student sees on Feedback, and what prints from the spreadsheet are one form,
not three that happen to look alike.

It is drawn as paper — white, black rules, a serif face — in either theme,
because it is a document the department signs, not a panel of the app.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from html import escape

import streamlit as st

from core.exports.assessment import (
    ABSENT,
    INSTITUTE_LINES,
    NO_SUBMISSION,
    SIGNATORIES,
    AssessmentSheet,
)
from core.exports.xlsx import LOGO

STYLE = """
<style>
.rq-form{background:#fff;color:#000;font-family:'Times New Roman',Times,serif;
  padding:18px 20px 22px;border:1px solid #c9c9c9;border-radius:4px;
  overflow-x:auto}
.rq-form table{border-collapse:collapse;width:100%}
.rq-head td{border:1px solid #000;text-align:center;line-height:1.35;
  padding:4px 8px}
.rq-head .logo{width:96px}
.rq-head img{width:78px;height:auto;display:block;margin:0 auto}
.rq-head .big{font-size:1.25rem;font-weight:700}
.rq-band{background:#e6e6e6;border:1px solid #000;border-top:0;
  text-align:center;font-weight:700;font-size:1.05rem;padding:5px}
.rq-part{margin:10px 0 12px}
.rq-part td{padding:2px 4px;font-weight:700;vertical-align:top}
.rq-grid th,.rq-grid td{border:1px solid #000;padding:4px 6px;
  font-size:.92rem;text-align:center}
.rq-grid th{font-weight:700}
.rq-grid td.l{text-align:left}
.rq-grid tr.marks td{font-weight:700}
.rq-grid tr.est td{background:#fff3cd}
.rq-grid td.code{font-weight:700}
.rq-legend{margin-top:10px;font-size:.85rem;font-style:italic}
.rq-legend div{margin:1px 0}
.rq-sign{margin-top:46px;font-weight:700}
.rq-sign td{width:33%}
</style>
"""


@lru_cache(maxsize=1)
def _logo() -> str:
    if not LOGO.exists():
        return ""
    data = base64.b64encode(LOGO.read_bytes()).decode("ascii")
    return f'<img alt="PCCoE" src="data:image/png;base64,{data}">'


def _header(form: AssessmentSheet) -> str:
    lines = []
    for index, line in enumerate(INSTITUTE_LINES):
        css = ' class="big"' if index == 1 else ""
        lines.append(f"<div{css}>{escape(line)}</div>")
    return (
        '<table class="rq-head"><tr>'
        f'<td class="logo">{_logo()}</td>'
        f"<td>{''.join(lines)}</td>"
        "</tr></table>"
        f'<div class="rq-band">{escape(form.header.title)}</div>'
    )


def _particulars(form: AssessmentSheet) -> str:
    rows = []
    for line in form.header.particulars:
        cells = "".join(
            f"<td>{escape(label)}: {escape(value)}</td>" if label else "<td></td>"
            for label, value in line
        )
        rows.append(f"<tr>{cells}</tr>")
    return f'<table class="rq-part">{"".join(rows)}</table>'


def _table(form: AssessmentSheet) -> str:
    heads = "".join(f"<th>{escape(h)}</th>" for h in form.column_headers)
    marks = (
        '<tr class="marks"><td colspan="4" style="text-align:right">Marks</td>'
        + "".join(f"<td>{escape(m)}</td>" for m in form.criterion_max)
        + f"<td>{escape(form.max_total)}</td></tr>"
    )
    body = []
    for row in form.rows:
        cells = []
        for index, value in enumerate(row.cells()):
            css = []
            if index in (2, 3):
                css.append("l")
            if index == len(form.column_headers) - 1 and row.total in (
                ABSENT,
                NO_SUBMISSION,
            ):
                css.append("code")
            attr = f' class="{" ".join(css)}"' if css else ""
            cells.append(f"<td{attr}>{escape(value)}</td>")
        tr = ' class="est"' if row.is_estimate else ""
        body.append(f"<tr{tr}>{''.join(cells)}</tr>")
    return f'<table class="rq-grid"><tr>{heads}</tr>{marks}{"".join(body)}</table>'


def assessment_html(form: AssessmentSheet, *, signatures: bool = True) -> str:
    """The whole form as one HTML string."""
    legend = "".join(f"<div>{escape(line)}</div>" for line in form.legend)
    sign = ""
    if signatures:
        cells = "".join(
            f'<td style="text-align:{align}">{escape(name)}</td>'
            for name, align in zip(SIGNATORIES, ("left", "center", "right"), strict=True)
        )
        sign = f'<table class="rq-sign"><tr>{cells}</tr></table>'
    return (
        STYLE
        + '<div class="rq-form">'
        + _header(form)
        + _particulars(form)
        + _table(form)
        + (f'<div class="rq-legend">{legend}</div>' if legend else "")
        + sign
        + "</div>"
    )


def render_assessment(form: AssessmentSheet, *, signatures: bool = True) -> None:
    st.html(assessment_html(form, signatures=signatures))

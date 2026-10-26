"""XLSX export — the department's assessment sheet, plus what stands behind it.

Three sheets, in the order a reader needs them:

1. **Assessment Sheet** — the PCCoE form exactly as it is printed: the
   institute header, the grey title band, the particulars, the table with its
   Marks row, the legend, and the three signatures. Laid out for A4
   landscape so it prints straight from Excel.
2. **Raw Data** — every column the system holds for each student, and below
   it the evidence and rationale behind every criterion score (§7).
3. **How to Use** — what the file is, what each code on the form means, and
   how a total is arrived at.

Both the form and the copied table are drawn from one
:class:`~core.exports.assessment.AssessmentSheet`; this module only lays
values out. It never computes or reformats a number (fix item 11).
"""

from __future__ import annotations

import io
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import Workbook
from openpyxl.drawing.image import Image as SheetImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from core.exports.assessment import (
    ABSENT,
    INSTITUTE_LINES,
    NO_SUBMISSION,
    SIGNATORIES,
    AssessmentSheet,
)
from core.exports.rows import ESTIMATE_MARKER, ExportBundle

LOGO = Path(__file__).resolve().parent / "assets" / "institute_logo.png"

FONT_NAME = "Times New Roman"
THIN = Side(style="thin", color="000000")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
BAND_FILL = PatternFill("solid", fgColor="E6E6E6")
HEADER_FILL = PatternFill("solid", fgColor="2F5BD0")
ESTIMATE_FILL = PatternFill("solid", fgColor="FFF3CD")

CENTRE = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
RIGHT = Alignment(horizontal="right", vertical="center")

#: Where the table's heading row sits on Sheet 1, below the header block.
TABLE_ROW = 11

#: Widths for Sr. No., PRN, Name, Project Title; each criterion; and Total.
FIXED_WIDTHS = (7, 14, 26, 40)
CRITERION_WIDTH = 13
TOTAL_WIDTH = 10


def _value(text: str):
    """A mark as a number, so Excel neither flags it as text nor refuses to sum it.

    Only plain numerals convert. ``15.5*`` and ``AB`` stay text — they are
    statements about a mark, not marks. Read back through ``str()``, a
    converted value is the same string it started as.
    """
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        return text
    if not number.is_finite() or text != text.strip():
        return text
    return int(number) if number == number.to_integral_value() else float(number)


def _font(size: float = 11, *, bold: bool = False, italic: bool = False) -> Font:
    return Font(name=FONT_NAME, size=size, bold=bold, italic=italic, color="000000")


def _merge(sheet, row: int, first: int, last: int, value: str, *, font, align):
    sheet.merge_cells(start_row=row, start_column=first, end_row=row, end_column=last)
    cell = sheet.cell(row=row, column=first, value=value)
    cell.font = font
    cell.alignment = align
    return cell


def _outline(sheet, top: int, bottom: int, first: int, last: int) -> None:
    """A box around a block of merged cells — Excel draws borders per cell."""
    for row in range(top, bottom + 1):
        for column in range(first, last + 1):
            cell = sheet.cell(row=row, column=column)
            cell.border = Border(
                left=THIN if column == first else None,
                right=THIN if column == last else None,
                top=THIN if row == top else None,
                bottom=THIN if row == bottom else None,
            )


def _thirds(width: int) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    """Left, middle and right column spans for the particulars and signatures.

    The form puts three items across the page. Those spans have to come out of
    whatever columns this review's criteria produce, so they are computed
    rather than fixed: the left block takes the identity columns, the right
    block the last three, and the middle everything between.
    """
    left = (1, 3)
    right = (max(5, width - 2), width)
    middle = (4, right[0] - 1)
    return left, middle, right


def write_assessment(sheet, form: AssessmentSheet) -> None:
    """Lay the department's form out on a worksheet."""
    width = len(form.column_headers)
    last = width

    for index, column_width in enumerate(FIXED_WIDTHS, 1):
        sheet.column_dimensions[get_column_letter(index)].width = column_width
    for index in range(len(FIXED_WIDTHS) + 1, width):
        sheet.column_dimensions[get_column_letter(index)].width = CRITERION_WIDTH
    sheet.column_dimensions[get_column_letter(width)].width = TOTAL_WIDTH

    # -- institute header ------------------------------------------------
    sizes = (12, 16, 11, 11, 11)
    bold = (False, True, False, False, False)
    for offset, (line, size, weight) in enumerate(
        zip(INSTITUTE_LINES, sizes, bold, strict=True)
    ):
        row = 1 + offset
        _merge(sheet, row, 2, last, line, font=_font(size, bold=weight), align=CENTRE)
        sheet.row_dimensions[row].height = 21 if size > 12 else 17

    sheet.merge_cells(start_row=1, start_column=1, end_row=5, end_column=1)
    _outline(sheet, 1, 5, 1, 1)
    _outline(sheet, 1, 5, 2, last)

    if LOGO.exists():
        logo = SheetImage(str(LOGO))
        # Sized to the five header rows rather than its native pixels, so it
        # sits inside the box whatever resolution the file is.
        ratio = logo.width / logo.height
        logo.height = 84
        logo.width = int(84 * ratio)
        sheet.add_image(logo, "A1")
        sheet.column_dimensions["A"].width = max(FIXED_WIDTHS[0], 14)

    # -- the grey title band ---------------------------------------------
    band = 6
    _merge(
        sheet, band, 1, last, form.header.title, font=_font(14, bold=True), align=CENTRE
    )
    for column in range(1, last + 1):
        sheet.cell(row=band, column=column).fill = BAND_FILL
    _outline(sheet, band, band, 1, last)
    sheet.row_dimensions[band].height = 24

    # -- particulars -----------------------------------------------------
    spans = _thirds(width)
    for offset, line in enumerate(form.header.particulars):
        row = 7 + offset
        for (label, value), (first, end) in zip(line, spans, strict=True):
            text = f"{label}: {value}" if label else ""
            _merge(sheet, row, first, end, text, font=_font(12, bold=True), align=LEFT)
        sheet.row_dimensions[row].height = 18

    # -- the table -------------------------------------------------------
    head = TABLE_ROW
    table = form.table()

    for column, heading in enumerate(table[0], 1):
        cell = sheet.cell(row=head, column=column, value=heading)
        cell.font = _font(11, bold=True)
        cell.alignment = CENTRE
        cell.border = BOX
    sheet.row_dimensions[head].height = 46

    # "Marks" sits in the fourth cell, where the table model puts it, with the
    # first four drawn as one box rather than merged — so the sheet reads back
    # cell for cell as the table the TSV copies.
    marks = head + 1
    label = sheet.cell(row=marks, column=4, value=table[1][3])
    label.font = _font(11, bold=True)
    label.alignment = RIGHT
    _outline(sheet, marks, marks, 1, 4)
    for column, value in enumerate(table[1][4:], 5):
        cell = sheet.cell(row=marks, column=column, value=_value(value))
        cell.font = _font(11, bold=True)
        cell.alignment = CENTRE
        cell.border = BOX

    for offset, (values, student) in enumerate(zip(table[2:], form.rows, strict=True)):
        row = marks + 1 + offset
        for column, value in enumerate(values, 1):
            # PRN, name and title stay text: a PRN is an identifier, and
            # "125M1H071" must never be read as anything else.
            cell = sheet.cell(
                row=row, column=column, value=value if 2 <= column <= 4 else _value(value)
            )
            cell.font = _font(11)
            cell.border = BOX
            cell.alignment = LEFT if column in (3, 4) else CENTRE
        total = sheet.cell(row=row, column=last)
        if student.total in (ABSENT, NO_SUBMISSION):
            total.font = _font(11, bold=True)
        if student.is_estimate:
            # Tinted as well as starred: invariant #1 visible at a glance.
            for column in range(1, last + 1):
                sheet.cell(row=row, column=column).fill = ESTIMATE_FILL

    after = marks + len(form.rows)

    # -- legend ----------------------------------------------------------
    row = after + 2
    for line in form.legend:
        _merge(sheet, row, 1, last, line, font=_font(10, italic=True), align=LEFT)
        row += 1

    # -- signatures ------------------------------------------------------
    row += 3
    for name, (first, end) in zip(SIGNATORIES, spans, strict=True):
        align = LEFT if first == 1 else (RIGHT if end == last else CENTRE)
        _merge(sheet, row, first, end, name, font=_font(12, bold=True), align=align)

    # -- printing --------------------------------------------------------
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.print_options.horizontalCentered = True
    sheet.page_margins.left = sheet.page_margins.right = 0.4
    sheet.page_margins.top = sheet.page_margins.bottom = 0.5
    # A long class runs to a second page; repeat the headings on it.
    sheet.print_title_rows = f"{head}:{marks}"
    sheet.sheet_view.showGridLines = False


def _write_raw(sheet, bundle: ExportBundle) -> None:
    grid = bundle.cells()
    for row in grid:
        sheet.append(row)

    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    sheet.freeze_panes = "C2"

    status_column = bundle.headers.index("Status") + 1
    for row_index in range(2, len(grid) + 1):
        status = str(sheet.cell(row=row_index, column=status_column).value or "")
        if ESTIMATE_MARKER in status:
            for column in range(1, len(bundle.headers) + 1):
                sheet.cell(row=row_index, column=column).fill = ESTIMATE_FILL

    for index in range(len(grid[0])):
        widest = max((len(str(row[index])) for row in grid), default=10)
        sheet.column_dimensions[get_column_letter(index + 1)].width = min(widest + 2, 42)

    if not bundle.evidence:
        return

    # Evidence beneath the scores, so the file stays three sheets and a mark
    # is still one scroll away from the line of the student's work behind it.
    start = len(grid) + 3
    sheet.cell(row=start, column=1, value="Evidence and rationale").font = Font(
        bold=True, size=12
    )
    headers = ["PRN", "Name", "Criterion", "Verdict", "Score", "Evidence", "Rationale"]
    for column, heading in enumerate(headers, 1):
        cell = sheet.cell(row=start + 1, column=column, value=heading)
        cell.fill = HEADER_FILL
        cell.font = Font(color="FFFFFF", bold=True)
    for offset, entry in enumerate(bundle.evidence, 2):
        for column, heading in enumerate(headers, 1):
            cell = sheet.cell(
                row=start + offset, column=column, value=entry.get(heading, "")
            )
            cell.alignment = Alignment(vertical="top", wrap_text=True)


def _write_guide(sheet, form: AssessmentSheet) -> None:
    sections: list[tuple[str, list[str]]] = [
        (
            "What this file is",
            [
                f"{form.header.title} for {form.header.subject}, "
                f"{form.header.year} semester {form.header.semester}, "
                f"academic year {form.header.academic_year}.",
                f"Generated by RubriQ on {form.header.date} from the score "
                "sheets saved at that moment. Editing a cell here changes "
                "nothing in RubriQ.",
            ],
        ),
        (
            "Sheet 1 — Assessment Sheet",
            [
                "The department's form, filled in. Print it as it is: it is "
                "laid out for A4 landscape and the headings repeat if the "
                "class runs to a second page.",
                "Each criterion is marked out of the figure in the Marks row. "
                f"The Total is out of {form.max_total}.",
                "Sign it in the three places at the foot of the page.",
            ],
        ),
        (
            "Sheet 2 — Raw Data",
            [
                "Everything RubriQ holds for each student: submission time, "
                "days late, status, penalty, who approved the mark and when, "
                "and any note.",
                "Below the table, the line of the student's own work behind "
                "every criterion score, and the reason given for it.",
            ],
        ),
        ("What the codes on the form mean", list(form.legend) or ["None appear."]),
        (
            "How a total is arrived at",
            [
                "Each criterion score is divided by what it is out of, "
                "multiplied by its weight, and the results added. That "
                "percentage is then scaled onto the review's marks.",
                "A late submission loses a share of the review's marks. Under "
                "the default policy: one day 10%, two days 20%, three days "
                "35%; four days or more is recorded as absent rather than "
                "scored. A subject may set its own bands.",
                "None of this arithmetic is done by the AI. It suggests a "
                "score for each criterion with a quotation from the student's "
                "work; a named guide approves every mark.",
            ],
        ),
    ]

    sheet.column_dimensions["A"].width = 110
    row = 1
    title = sheet.cell(row=row, column=1, value="How to use this file")
    title.font = Font(bold=True, size=16)
    row += 2
    for heading, lines in sections:
        sheet.cell(row=row, column=1, value=heading).font = Font(bold=True, size=12)
        row += 1
        for line in lines:
            cell = sheet.cell(row=row, column=1, value=line)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            row += 1
        row += 1


def assessment_workbook(
    form: AssessmentSheet, bundle: ExportBundle | None = None
) -> bytes:
    """A workbook holding the form, and — given a bundle — the raw data too.

    Without a bundle it is the form alone, which is what the score drawer
    offers for a single student.
    """
    workbook = Workbook()
    write_assessment(workbook.active, form)
    workbook.active.title = "Assessment Sheet"

    if bundle is not None:
        _write_raw(workbook.create_sheet("Raw Data"), bundle)
    _write_guide(workbook.create_sheet("How to Use"), form)

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def to_xlsx(bundle: ExportBundle) -> bytes:
    """The full export: form, raw data, and guide."""
    if bundle.assessment is None:
        raise ValueError("The bundle was built without its assessment sheet.")
    return assessment_workbook(bundle.assessment, bundle)

"""Build the Mini Project Synopsis in the department's own format.

The layout follows `Miniproject_Synopsis.pdf` exactly: title page, index page,
sections 1–8 in the order the template lists them, and a student-details page
at the end. The template also states its own formatting rules — Times New
Roman, 14 pt headings, 12 pt body, 1.5 line spacing, justified text — and all
four are applied here rather than left to Word's defaults.

The prose is deliberately plain. This is read by a guide and an examiner who
want to know what the system does, not by someone looking for style.

Deliberately a script rather than a one-off conversion: the synopsis will
change before the review, and a document nobody can regenerate goes stale the
first time it does.

    make synopsis
    python scripts/build_synopsis_docx.py
    python scripts/build_synopsis_docx.py --out somewhere/else.docx
"""

from __future__ import annotations

import argparse
import shutil  # noqa: F401
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from docx import Document  # noqa: E402
from docx.enum.section import WD_SECTION  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK  # noqa: E402
from docx.oxml import OxmlElement  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.shared import Inches, Pt  # noqa: E402

from scripts.synopsis_diagram import build as build_diagram  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "docs" / "report" / "RubriQ_Synopsis.docx"
DIAGRAM = REPO_ROOT / "docs" / "report" / "flow.png"

FONT = "Times New Roman"
BODY_PT = 12
HEAD_PT = 14
LINE_SPACING = 1.5

# -- title page (template page 1) ----------------------------------------

PROJECT_TITLE = (
    "RubriQ – AI-Assisted Project Review & Rubric Evaluation System for PCCOE Mentors"
)
STUDENT_NAME = "Manthan Sankpal"
PRN = "125M1H064"
GUIDE = "Prof. Dr. Anjana Arakerimath (HOD)"
DEPARTMENT = "DEPARTMENT OF MCA"
INSTITUTE = (
    "PIMPRI CHINCHWAD COLLEGE OF ENGINEERING "
    "SECTOR NO. 26, PRADHIKARAN, NIGDI, PUNE - 44."
)
YEAR = "(2026 - 2027)"

# -- index (template page 2) ---------------------------------------------

INDEX = [
    ("1. Introduction", []),
    (
        "2. Problem Statement",
        ["Working Of Existing System", "Need Of New System"],
    ),
    ("3. Scope of proposed system", []),
    ("4. Objectives of proposed system", []),
    (
        "5. Methodology",
        [
            "a) Flow diagram followed by description of working",
            "b) Functional Requirements",
            "c) Non-functional Requirements",
        ],
    ),
    ("6. Technical Requirements", ["Software requirement"]),
    ("7. Expected Outcomes", []),
    ("8. Conclusion", []),
]

# -- 1. Introduction ------------------------------------------------------

INTRODUCTION = [
    "In every project-based course at PCCOE, a student's work is checked at a "
    "small number of review meetings. For each review there is a rubric — a "
    "list of things the work is supposed to contain, and how many marks each "
    "of them carries. In practice the student usually sees this rubric only "
    "after the review is over, when the marks are announced. By then it is "
    "too late to use it.",
    "RubriQ is a web application that moves the rubric to the beginning of "
    "this process instead of the end. The guide writes the rubric and "
    "publishes it, and the student can read it before uploading anything. "
    "When the work is submitted, the system reads the document and prepares a "
    "suggested score for each point in the rubric. Every suggestion comes with "
    "a line copied from the student's own file as proof. The guide then checks "
    "these suggestions, changes anything they disagree with, and approves the "
    "final marks.",
    "The important part is that the software only suggests. It never decides. "
    "A mark becomes final only when a faculty member approves it, and the "
    "system records who approved it and when. The name RubriQ comes from "
    "“rubric” and “IQ”: the rubric stays in charge, and the "
    "intelligence only assists.",
]

# -- 2. Problem Statement -------------------------------------------------

EXISTING_SYSTEM = [
    "At present the whole review process is manual.",
    "The guide keeps the rubric on paper or in their own notes. During the "
    "review they look at the student's report, judge it from memory against "
    "that rubric, and write a mark in a register or a spreadsheet. Feedback is "
    "given by speaking to the student for a few minutes. Late submissions are "
    "handled case by case. At the end, the marks of all students are typed "
    "into an Excel sheet by hand for department records.",
    "This works, but it depends entirely on the reviewer keeping everything in "
    "their head at the same time.",
]

EXISTING_PROBLEMS = [
    "The student does not see the rubric before submitting, so they cannot aim at it.",
    "There is no record of why a particular mark was given. Only the number survives.",
    "Two reviewers, or the same reviewer on two different days, may score "
    "similar work differently.",
    "A student who submits four days late and a student who never submits at "
    "all are usually both written down as zero, even though these are "
    "completely different situations.",
    "Verbal feedback is forgotten quickly, and the student has nothing written "
    "to improve from.",
    "Marks are copied by hand into Excel, where a typing mistake is easy to "
    "make and hard to notice.",
]

NEED_OF_NEW_SYSTEM = [
    "The new system is needed so that the review becomes fair, written down, "
    "and repeatable.",
    "It shows the rubric to the student before the deadline, so the rubric "
    "becomes a set of instructions instead of a justification for a mark. It "
    "makes the reviewer's job faster by preparing a first draft of the score "
    "sheet, and it makes that draft checkable by attaching the exact line from "
    "the report that supports each point. It applies the late-submission rules "
    "by calculation instead of by memory, and it keeps “absent” as a "
    "separate status rather than turning it into a zero.",
    "Finally, it produces the Excel file for the department automatically, "
    "using the same numbers that are shown on the screen, so nothing has to be "
    "retyped.",
]

# -- 3. Scope -------------------------------------------------------------

SCOPE_INTRO = [
    "The system is a single web application used by two kinds of users: "
    "faculty members and students. Everything runs on one computer and all "
    "data is stored locally. There is no separate server and no cloud storage.",
]

SCOPE_IN = [
    "Login with the college Google account only. An address outside "
    "@pccoepune.org is refused.",
    "The user's role (student or faculty) is decided by the system from a "
    "prepared list. A user cannot choose it.",
    "Faculty can create subjects, add students, and set review milestones "
    "with dates and marks.",
    "Faculty can build a rubric for each review, and publish it so it cannot "
    "be changed afterwards.",
    "Students can see the published rubric, upload their work as PDF, DOCX or "
    "TXT, and upload it again if they improve it. Old versions are kept.",
    "Students may also attach a GitHub repository link, which is accepted "
    "only if it belongs to the GitHub account their guide has recorded for "
    "them.",
    "Students may work in a group, but only when a faculty member approves "
    "the group. One submission then counts for all its members.",
    "The system prepares a suggested score for each rubric point, along with "
    "the supporting line from the student's document.",
    "Late marks and absence are calculated automatically from a fixed rule table.",
    "Faculty can change any score, giving a reason, and then approve the score sheet.",
    "The approved marks can be downloaded as an Excel file or copied into a spreadsheet.",
    "Students can ask questions about a review, answered from the rubric "
    "only, and passed to the guide when the answer is not there.",
    "After approval, students can see which points they followed and which they did not.",
    "The system keeps a record of every action taken by every user.",
]

SCOPE_OUT = [
    "Checking for plagiarism or copied content.",
    "Running, compiling or testing the student's program code.",
    "A mobile application.",
    "Connecting to any college ERP or learning-management system.",
    "Use by more than one college at a time.",
    "Hosting on the internet with real student data.",
    "Downloading or reading the contents of a linked GitHub repository. The "
    "link is only stored and shown; marks are given from the uploaded "
    "document.",
]

# -- 4. Objectives --------------------------------------------------------

OBJECTIVES = [
    "To let a faculty member create a rubric for each review, check that its "
    "weights add up to 100, and publish it so that it cannot be edited later.",
    "To show the published rubric to the student before the submission is made.",
    "To accept submissions in PDF, DOCX and TXT form, keep every version, and "
    "read out the text at the time of upload.",
    "To prepare a suggested score for every rubric point, with a line quoted "
    "from the student's own document as proof.",
    "To reject any quoted line that is not actually present in the document, "
    "and mark that point as having no evidence.",
    "To calculate late-submission penalties and absence by fixed rules "
    "instead of by judgement.",
    "To make sure no mark becomes final until a faculty member approves it, "
    "and to record every change with a reason.",
    "To export the approved marks to an Excel file with the same numbers "
    "shown on the screen.",
    "To answer student questions about a review using only the published "
    "rubric, and to pass the question to the guide when it cannot be "
    "answered.",
    "To allow project groups only when a faculty member has granted them.",
    "To keep a complete record of who did what, so that every mark can be "
    "traced back later.",
]

# -- 5. Methodology -------------------------------------------------------

FLOW_DESCRIPTION = [
    "The working of the system is shown in the diagram above. The steps are "
    "explained below.",
]

FLOW_STEPS = [
    (
        "Creating and publishing the rubric.",
        "The faculty member lists the points the work will be judged on, and "
        "gives each one a weight and a maximum score. The system does not "
        "allow publishing unless the weights add up to 100. Once published, "
        "the rubric is locked. If it has to be changed, the system makes a "
        "new version and leaves the old one untouched, so work already marked "
        "stays valid.",
    ),
    (
        "The student reads the rubric and submits.",
        "The rubric appears on the student's submission page above the upload "
        "box. If the deadline has passed, the page states exactly what will "
        "happen — for example, that a 20% penalty will apply, or that the "
        "submission will be recorded as absent — before the student confirms.",
    ),
    (
        "Reading the file.",
        "As soon as the file is uploaded, the system extracts its text and "
        "stores it. No later step opens the file again. If a file is a "
        "scanned image with no text inside it, the system says so instead of "
        "guessing.",
    ),
    (
        "Checking the work against the rubric.",
        "For each rubric point, the AI model is given the rubric point and "
        "the extracted text, and returns a verdict (followed, partly "
        "followed, not followed, or no evidence), a score, and a line copied "
        "from the document that supports its answer. The student's name and "
        "PRN are removed before the text is sent.",
    ),
    (
        "Checking the evidence.",
        "The system then searches for that quoted line inside the student's "
        "own text. If the line is not really there, the answer is rejected: "
        "the point is marked as having no evidence, the score is set to zero, "
        "and the faculty member is told to look at it. This step is what "
        "stops the AI from inventing things.",
    ),
    (
        "Calculating the marks.",
        "Adding up the scores, applying the weights, and subtracting the late "
        "penalty are all done by ordinary Python code, not by the AI. The "
        "same input always gives the same result.",
    ),
    (
        "Faculty review and approval.",
        "The faculty member sees all students in one table, with the ones "
        "needing attention at the top. Clicking a row opens the details, "
        "including the quoted evidence. Any score can be changed, but a "
        "reason must be typed, and the change is saved permanently. Nothing "
        "is final until the Approve button is pressed.",
    ),
    (
        "Output.",
        "After approval, the marks can be downloaded as an Excel file for the "
        "department, and the student can see which rubric points they "
        "followed and which they did not.",
    ),
]

FUNCTIONAL_REQUIREMENTS = [
    ("FR-1", "The system shall allow login only through a college Google account."),
    (
        "FR-2",
        "The system shall reject any email address that is not from the "
        "@pccoepune.org domain.",
    ),
    (
        "FR-3",
        "The system shall decide the user's role from a stored list, and shall "
        "not allow a user to select it.",
    ),
    (
        "FR-4",
        "The system shall allow a faculty member to create subjects, add "
        "students, and create review milestones.",
    ),
    (
        "FR-5",
        "The system shall allow students to be added in bulk from a CSV file, "
        "showing a preview of what will happen before saving anything.",
    ),
    (
        "FR-6",
        "The system shall allow a faculty member to create a rubric with "
        "criteria, weights and maximum scores.",
    ),
    (
        "FR-7",
        "The system shall refuse to publish a rubric whose weights do not add up to 100.",
    ),
    (
        "FR-8",
        "The system shall not allow a published rubric to be edited; editing "
        "shall create a new version instead.",
    ),
    (
        "FR-9",
        "The system shall display the published rubric to the student before "
        "the upload option.",
    ),
    (
        "FR-10",
        "The system shall accept PDF, DOCX and TXT files, and shall keep every "
        "uploaded version.",
    ),
    (
        "FR-11",
        "The system shall extract and store the text of a submission at the "
        "time of upload.",
    ),
    (
        "FR-12",
        "The system shall accept a GitHub repository link only if it belongs "
        "to the account recorded by the faculty member for that student.",
    ),
    (
        "FR-13",
        "The system shall allow a project group only after a faculty member "
        "grants it, and shall treat one submission as the work of all its "
        "members.",
    ),
    (
        "FR-14",
        "The system shall produce a suggested score and a verdict for every "
        "rubric point.",
    ),
    (
        "FR-15",
        "The system shall reject any quoted evidence that cannot be found in "
        "the student's text, and shall mark that point as having no evidence.",
    ),
    (
        "FR-16",
        "The system shall calculate the late penalty and absence status from "
        "the rule table.",
    ),
    (
        "FR-17",
        "The system shall show all students of a review in one table, with the "
        "ones needing attention first.",
    ),
    (
        "FR-18",
        "The system shall require a reason before any score is changed, and "
        "shall keep a record of the change.",
    ),
    (
        "FR-19",
        "The system shall record the name of the approver and the time of "
        "approval for every final score sheet.",
    ),
    (
        "FR-20",
        "The system shall export the approved marks to an Excel file and to a "
        "copyable text form, with identical numbers.",
    ),
    (
        "FR-21",
        "The system shall answer student questions using only the published "
        "rubric and the faculty notes, and shall forward the question to the "
        "guide when it cannot answer.",
    ),
    (
        "FR-22",
        "The system shall show feedback to a student only after the score "
        "sheet has been approved.",
    ),
    (
        "FR-23",
        "The system shall record every action performed by every user.",
    ),
]

NON_FUNCTIONAL_REQUIREMENTS = [
    (
        "NFR-1 Security",
        "A student must never be able to see another student's work or marks. "
        "This is enforced while fetching the data from the database, not by "
        "hiding buttons on the screen.",
    ),
    (
        "NFR-2 Privacy",
        "The student's name, PRN and email are removed before any text is sent "
        "to the AI service.",
    ),
    (
        "NFR-3 Reliability",
        "If the AI service is not available, the rest of the system must keep "
        "working. Manual marking, penalties, approval and export are not "
        "affected.",
    ),
    (
        "NFR-4 Correctness",
        "The same submission and the same rubric must always produce the same "
        "marks. All calculations use exact decimal arithmetic.",
    ),
    (
        "NFR-5 Traceability",
        "Every final mark must be traceable to the person who approved it, the "
        "version of the submission, and the version of the rubric used.",
    ),
    (
        "NFR-6 Data safety",
        "Nothing is permanently deleted. New submissions and new evaluations "
        "are stored as new versions.",
    ),
    (
        "NFR-7 Usability",
        "No screen may show a blank area or a technical error message. Every "
        "empty page must tell the user what to do next.",
    ),
    (
        "NFR-8 Maintainability",
        "All the logic is kept separate from the screen code, so the user "
        "interface can be replaced later without rewriting the system.",
    ),
    (
        "NFR-9 Portability",
        "The system must run on a normal laptop with only Python installed. "
        "There is no database server to set up.",
    ),
]

# -- 6. Technical requirements -------------------------------------------

SOFTWARE_REQUIREMENTS = [
    ("Operating system", "Windows 10 or 11 (also runs on Linux or macOS)"),
    ("Programming language", "Python 3.12 or above"),
    ("Web framework", "Streamlit (version 1.42 or above)"),
    ("Database", "SQLite, used through SQLAlchemy 2.0"),
    ("Database migrations", "Alembic"),
    ("Login", "Google Sign-In (OIDC), restricted to the college domain"),
    ("File reading", "pdfplumber for PDF, python-docx for Word files"),
    ("AI service", "Google Gemini, used through an internet connection"),
    ("AI workflow", "LangGraph, for the step-by-step checking process"),
    ("Data checking", "Pydantic version 2"),
    ("Text matching", "RapidFuzz, for checking quoted evidence"),
    ("Excel export", "openpyxl"),
    ("Testing", "pytest"),
    ("Editor / tools", "Visual Studio Code, Git"),
]

HARDWARE_NOTE = (
    "No special hardware is required. A normal laptop with 8 GB of RAM is "
    "enough. An internet connection is needed only for the login and for the "
    "AI checking step; every other feature works offline."
)

# -- 7. Expected outcomes -------------------------------------------------

EXPECTED_OUTCOMES = [
    "A working web application in which a faculty member can create a "
    "subject, publish a rubric, and review a whole class from one screen.",
    "A student view in which the rubric is visible before submitting, and "
    "the penalty for a late submission is stated before it is confirmed.",
    "A suggested score sheet for each submission, where every score is "
    "supported by a line taken from the student's own document.",
    "A count of how many AI answers were rejected because the quoted line was "
    "not really present. This number shows how useful the evidence check is, "
    "and will be reported.",
    "Correct handling of late and absent cases, with absence shown as a "
    "status and never as a mark of zero.",
    "An Excel file of approved marks, ready to be given to the department, "
    "containing exactly the numbers shown on the screen.",
    "A written feedback page for the student, listing what was followed and "
    "what was not.",
    "A complete activity record showing who approved or changed each mark, and when.",
    "A saving of time for the faculty member, because the first draft of the "
    "score sheet is already prepared and only needs to be checked.",
]

# -- 8. Conclusion --------------------------------------------------------

CONCLUSION = [
    "RubriQ tries to fix a small but real problem in the way project reviews "
    "are conducted. The rubric already exists in every course; the difficulty "
    "is that the student sees it too late, and that the reasons behind a mark "
    "are never written down.",
    "By publishing the rubric before submission, by attaching a line of proof "
    "to every suggested score, and by requiring a faculty member to approve "
    "the result, the system makes the review clearer for the student and "
    "faster for the guide, without taking the decision away from the guide.",
    "The design keeps a firm line between the two halves of the work. The AI "
    "reads and suggests. All calculation of marks is done by ordinary program "
    "code that can be tested and explained. This is what makes the result "
    "trustworthy: a wrong suggestion can be seen and corrected by the "
    "reviewer, whereas a wrong calculation would go unnoticed.",
    "The system is planned to be completed and demonstrated across the two "
    "scheduled reviews, and its limitations have been listed honestly rather "
    "than left to be discovered later.",
]

# -- student details page -------------------------------------------------

STUDENT_DETAILS = [
    ("Name of Student", STUDENT_NAME),
    ("PRN", PRN),
    ("Email", ""),
    ("Contact No.", ""),
]


# ------------------------------------------------------------------------
# document helpers
# ------------------------------------------------------------------------


def set_styles(document) -> None:
    """Times New Roman, 12 pt, 1.5 spacing, justified — the template says so."""
    normal = document.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(BODY_PT)
    # East-Asian font name too, or Word substitutes for some characters.
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)

    fmt = normal.paragraph_format
    fmt.line_spacing = LINE_SPACING
    fmt.space_after = Pt(6)
    fmt.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    for style_name in ("List Bullet", "List Number"):
        style = document.styles[style_name]
        style.font.name = FONT
        style.font.size = Pt(BODY_PT)
        style.paragraph_format.line_spacing = LINE_SPACING
        style.paragraph_format.space_after = Pt(4)


def page_number_footer(section) -> None:
    """A real PAGE field — python-docx has no API for it.

    The unlink matters: a new section's footer is linked to the previous one by
    default, so without this the field lands in a footer shared with the title
    page and numbers it too.
    """
    section.footer.is_linked_to_previous = False
    paragraph = section.footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    run.font.name = FONT
    run.font.size = Pt(10)

    for tag, attrs, text in (
        ("w:fldChar", {"w:fldCharType": "begin"}, None),
        ("w:instrText", {"xml:space": "preserve"}, " PAGE "),
        ("w:fldChar", {"w:fldCharType": "end"}, None),
    ):
        element = OxmlElement(tag)
        for key, value in attrs.items():
            element.set(qn(key), value)
        if text is not None:
            element.text = text
        run._r.append(element)


def centred(document, text, *, size, bold=False, space_before=0, space_after=6):
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.line_spacing = 1.0
    paragraph.paragraph_format.space_before = Pt(space_before)
    paragraph.paragraph_format.space_after = Pt(space_after)
    run = paragraph.add_run(text)
    run.font.name = FONT
    run.font.size = Pt(size)
    run.bold = bold
    return paragraph


def heading(document, text, *, level=1):
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(14 if level == 1 else 10)
    paragraph.paragraph_format.space_after = Pt(6)
    paragraph.paragraph_format.line_spacing = LINE_SPACING
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.keep_with_next = True
    paragraph.paragraph_format.page_break_before = False
    run = paragraph.add_run(text)
    run.font.name = FONT
    run.font.size = Pt(HEAD_PT)
    run.bold = True
    return paragraph


def para(document, text, *, lead=None):
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    paragraph.paragraph_format.line_spacing = LINE_SPACING
    if lead:
        run = paragraph.add_run(lead + " ")
        run.bold = True
        run.font.name = FONT
        run.font.size = Pt(BODY_PT)
    run = paragraph.add_run(text)
    run.font.name = FONT
    run.font.size = Pt(BODY_PT)
    return paragraph


def bullet(document, text, *, lead=None, indent=0.25):
    paragraph = document.add_paragraph(style="List Bullet")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    paragraph.paragraph_format.line_spacing = LINE_SPACING
    paragraph.paragraph_format.left_indent = Inches(indent + 0.25)
    if lead:
        run = paragraph.add_run(lead + " ")
        run.bold = True
        run.font.name = FONT
        run.font.size = Pt(BODY_PT)
    run = paragraph.add_run(text)
    run.font.name = FONT
    run.font.size = Pt(BODY_PT)
    return paragraph


def numbered(document, text):
    paragraph = document.add_paragraph(style="List Number")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    paragraph.paragraph_format.line_spacing = LINE_SPACING
    paragraph.paragraph_format.left_indent = Inches(0.5)
    run = paragraph.add_run(text)
    run.font.name = FONT
    run.font.size = Pt(BODY_PT)
    return paragraph


def two_column_table(document, rows, headers, widths):
    table = document.add_table(rows=0, cols=len(widths))
    table.style = "Table Grid"

    def cell_text(cell, text, *, bold=False):
        paragraph = cell.paragraphs[0]
        paragraph.paragraph_format.line_spacing = 1.0
        paragraph.paragraph_format.space_after = Pt(2)
        run = paragraph.add_run(text)
        run.font.name = FONT
        run.font.size = Pt(BODY_PT - 1)
        run.bold = bold

    if headers:
        cells = table.add_row().cells
        for cell, text in zip(cells, headers, strict=True):
            cell_text(cell, text, bold=True)

    for values in rows:
        cells = table.add_row().cells
        for index, value in enumerate(values):
            cell_text(cells[index], str(value))

    # Column widths AND cell widths, or Word ignores both.
    for row in table.rows:
        for index, width in enumerate(widths):
            row.cells[index].width = Inches(width)

    document.add_paragraph()
    return table


def page_break(document) -> None:
    document.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# ------------------------------------------------------------------------
# the document
# ------------------------------------------------------------------------


def build(out_path: Path) -> Path:
    if not DIAGRAM.exists():
        build_diagram(DIAGRAM)

    document = Document()
    set_styles(document)

    section = document.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1.1)
    section.right_margin = Inches(1)

    # ---------------- title page (template page 1) ----------------------
    for _ in range(2):
        document.add_paragraph()

    centred(document, "Mini Project Synopsis", size=22, bold=True, space_after=30)
    centred(document, PROJECT_TITLE, size=18, bold=True, space_after=36)
    centred(document, STUDENT_NAME, size=17, space_after=4)
    centred(document, f"({PRN})", size=13, space_after=30)
    centred(document, GUIDE, size=15, space_after=54)
    centred(document, DEPARTMENT, size=15, bold=True, space_after=8)
    centred(document, INSTITUTE, size=13, bold=True, space_after=18)
    centred(document, YEAR, size=13, space_after=0)

    page_break(document)

    # Page numbers start after the title page.
    document.add_section(WD_SECTION.CONTINUOUS)
    page_number_footer(document.sections[-1])

    # ---------------- index (template page 2) ---------------------------
    centred(document, "Index", size=HEAD_PT + 2, bold=True, space_after=14)

    for entry, children in INDEX:
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.line_spacing = LINE_SPACING
        paragraph.paragraph_format.space_after = Pt(2)
        paragraph.paragraph_format.left_indent = Inches(0.4)
        run = paragraph.add_run(entry)
        run.font.name = FONT
        run.font.size = Pt(BODY_PT)
        for child in children:
            bullet(document, child, indent=0.55)

    page_break(document)

    # ---------------- 1. Introduction -----------------------------------
    heading(document, "1. Introduction")
    for text in INTRODUCTION:
        para(document, text)

    # ---------------- 2. Problem Statement ------------------------------
    heading(document, "2. Problem Statement")
    para(
        document,
        "Project reviews at present depend almost entirely on the reviewer's "
        "memory and on paperwork done by hand. This creates problems for both "
        "sides.",
    )

    heading(document, "Working Of Existing System", level=2)
    for text in EXISTING_SYSTEM:
        para(document, text)
    para(document, "The difficulties with this way of working are:")
    for text in EXISTING_PROBLEMS:
        bullet(document, text)

    heading(document, "Need Of New System", level=2)
    for text in NEED_OF_NEW_SYSTEM:
        para(document, text)

    # ---------------- 3. Scope ------------------------------------------
    heading(document, "3. Scope of proposed system")
    for text in SCOPE_INTRO:
        para(document, text)

    para(document, "The following features are included in the system:")
    for text in SCOPE_IN:
        bullet(document, text)

    para(
        document,
        "The following are deliberately kept outside the scope of this "
        "project, and are stated here so that there is no confusion later:",
    )
    for text in SCOPE_OUT:
        bullet(document, text)

    # ---------------- 4. Objectives -------------------------------------
    heading(document, "4. Objectives of proposed system")
    para(document, "The objectives of the proposed system are as follows:")
    for text in OBJECTIVES:
        numbered(document, text)

    # ---------------- 5. Methodology ------------------------------------
    heading(document, "5. Methodology")
    heading(
        document,
        "a) Flow diagram followed by description of working",
        level=2,
    )

    picture = document.add_paragraph()
    picture.alignment = WD_ALIGN_PARAGRAPH.CENTER
    picture.paragraph_format.space_before = Pt(6)
    picture.paragraph_format.space_after = Pt(6)
    picture.paragraph_format.keep_with_next = True
    picture.add_run().add_picture(str(DIAGRAM), width=Inches(5.9))

    caption = document.add_paragraph()
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption.paragraph_format.line_spacing = 1.0
    caption_run = caption.add_run("Fig. 1 — Flow of work in RubriQ")
    caption_run.font.name = FONT
    caption_run.font.size = Pt(BODY_PT - 1)
    caption_run.italic = True

    document.add_paragraph()
    for text in FLOW_DESCRIPTION:
        para(document, text)
    for lead, text in FLOW_STEPS:
        para(document, text, lead=lead)

    heading(document, "b) Functional Requirements", level=2)
    para(
        document,
        "These are the things the system must be able to do. Each one is "
        "numbered so that it can be referred to during testing.",
    )
    two_column_table(
        document,
        FUNCTIONAL_REQUIREMENTS,
        headers=("No.", "Requirement"),
        widths=(0.7, 5.3),
    )

    heading(document, "c) Non-functional Requirements", level=2)
    para(
        document,
        "These describe how well the system must work, rather than what it must do.",
    )
    two_column_table(
        document,
        NON_FUNCTIONAL_REQUIREMENTS,
        headers=("Quality", "Requirement"),
        widths=(1.5, 4.5),
    )

    # ---------------- 6. Technical Requirements -------------------------
    heading(document, "6. Technical Requirements")
    heading(document, "Software requirement", level=2)
    two_column_table(
        document,
        SOFTWARE_REQUIREMENTS,
        headers=("Item", "Software used"),
        widths=(1.9, 4.1),
    )
    para(document, HARDWARE_NOTE)

    # ---------------- 7. Expected Outcomes ------------------------------
    heading(document, "7. Expected Outcomes")
    para(
        document,
        "On completion of the project, the following results are expected:",
    )
    for text in EXPECTED_OUTCOMES:
        bullet(document, text)

    # ---------------- 8. Conclusion -------------------------------------
    heading(document, "8. Conclusion")
    for text in CONCLUSION:
        para(document, text)

    # ---------------- student details page ------------------------------
    page_break(document)
    centred(document, "STUDENT DETAILS", size=HEAD_PT + 2, bold=True, space_after=20)

    for label, value in STUDENT_DETAILS:
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.line_spacing = LINE_SPACING
        paragraph.paragraph_format.space_after = Pt(10)
        paragraph.paragraph_format.left_indent = Inches(0.3)
        run = paragraph.add_run(f"{label}: ")
        run.bold = True
        run.font.name = FONT
        run.font.size = Pt(BODY_PT)
        value_run = paragraph.add_run(value if value else "_______________________")
        value_run.font.name = FONT
        value_run.font.size = Pt(BODY_PT)

    document.add_paragraph()
    document.add_paragraph()

    sign = document.add_paragraph()
    sign.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    sign.paragraph_format.line_spacing = 1.0
    sign_run = sign.add_run("Signature of the Guide: ______________________")
    sign_run.font.name = FONT
    sign_run.font.size = Pt(BODY_PT)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(out_path)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    build_diagram(DIAGRAM)
    written = build(args.out)
    try:
        shown = written.relative_to(REPO_ROOT)
    except ValueError:  # --out pointed outside the repo
        shown = written
    print(f"Wrote {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

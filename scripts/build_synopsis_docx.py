"""Build the synopsis as a Word document for submission.

``docs/synopsis.md`` is the source of truth and stays the thing that gets
edited; this renders it into the shape a department expects — a title page, a
numbered body, and real tables — because a marked-up Markdown file is not what
gets handed in.

Deliberately a script rather than a one-off conversion: the synopsis will
change before the viva, and a document nobody can regenerate goes stale the
first time it does.

    python scripts/build_synopsis_docx.py
    python scripts/build_synopsis_docx.py --out somewhere/else.docx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from docx import Document  # noqa: E402
from docx.enum.section import WD_SECTION  # noqa: E402
from docx.enum.table import WD_TABLE_ALIGNMENT  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK  # noqa: E402
from docx.oxml import OxmlElement  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.shared import Inches, Pt, RGBColor  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "docs" / "report" / "RubriQ_Synopsis.docx"

TITLE = "RubriQ — Rubric-Driven, AI-Assisted Project Review"
SUBTITLE = "A Mini Project Synopsis"

FRONT_MATTER = [
    ("Project title", "RubriQ — Rubric-Driven, AI-Assisted Project Review"),
    ("Student", "Manthan Sankpal"),
    ("PRN", "125M1H064"),
    ("Programme", "Master of Computer Applications (MCA)"),
    ("Semester", "III"),
    ("Course", "Mini Project — MCA33EL03"),
    ("Guide", "Prof. Dr. Anjana Arakerimath (HOD)"),
    ("Institute", "Pimpri Chinchwad College of Engineering, Pune"),
    ("Evaluation", "Minimum two reviews, 50 marks total"),
    ("Academic year", "2026–27"),
]

INTRODUCTION = [
    "Every project-based course at PCCOE is assessed through a small number of "
    "review milestones. A rubric exists for each of them, but it exists mostly "
    "on the reviewer's side of the table: the student finds out what was "
    "expected of them at the moment they are told their mark.",
    "RubriQ moves the rubric to the front of that sequence. Faculty author it, "
    "publish it, and it becomes visible to the student before submission "
    "opens. When work comes in, the system produces an evidence-backed "
    "estimate of the mark against that same rubric — every criterion score "
    "citing a verbatim span from the student's own document — which a faculty "
    "member then verifies, adjusts where they disagree, and approves. Only "
    "after approval does anything become a mark, and only after approval does "
    "the student see feedback.",
    "The name is rubric + IQ. The ordering is deliberate: the rubric is the "
    "authority, and the intelligence is assistive.",
]

PROBLEMS = [
    (
        "The rubric is invisible until it is too late to act on it.",
        "A student cannot aim at a target they have not been shown, so the "
        "rubric functions as a justification for a mark rather than a "
        "specification for the work.",
    ),
    (
        "Review marking is unevenly evidenced.",
        "Two reviewers, or the same reviewer on a Friday afternoon, can score "
        "the same submission differently, and neither score carries a record "
        "of what in the document produced it.",
    ),
    (
        "Late and absent are conflated.",
        "A submission four days past the deadline and a submission that never "
        "arrived are administratively different things, but both tend to be "
        "recorded as a zero, which destroys the distinction the department's "
        "own policy depends on.",
    ),
]

OBJECTIVES = [
    (
        "O1",
        "Let faculty author a rubric per review milestone, validate that its "
        "weights sum to 100, and publish it as an immutable version",
    ),
    (
        "O2",
        "Show the published rubric to the enrolled student before they upload anything",
    ),
    (
        "O3",
        "Accept versioned submissions (PDF / DOCX / TXT) and extract their "
        "text at upload time",
    ),
    (
        "O4",
        "Produce a per-criterion estimated score in which every score cites a "
        "verbatim span from the submission, or is marked NO_EVIDENCE",
    ),
    (
        "O5",
        "Apply late and absence policy as deterministic arithmetic, not as a "
        "judgement call",
    ),
    (
        "O6",
        "Require an explicit, named faculty approval before any mark is "
        "final, and record every override with a reason",
    ),
    (
        "O7",
        "Export an approved score sheet to Excel, and to a clipboard-pastable "
        "form, with identical numbers",
    ),
    (
        "O8",
        "Answer student questions about a milestone from its rubric alone, "
        "escalating to faculty rather than inventing an answer",
    ),
    (
        "O9",
        "Keep every mark traceable — who approved it, when, against which "
        "submission version, and which rubric version",
    ),
    (
        "O10",
        "Allow project groups, but only where a faculty member has granted them",
    ),
    (
        "O11",
        "Accept a repository URL as part of a submission, only when it "
        "belongs to a GitHub account the guide already has on record",
    ),
]

SYSTEM_INTRO = (
    "RubriQ is a single Streamlit application backed by SQLite, split into two "
    "layers with one hard rule between them."
)

LAYERS = [
    (
        "core/ — the domain.",
        "All logic as plain Python with zero Streamlit imports: authentication "
        "and role resolution, academics, rubric versioning, submissions, "
        "project groups, the deterministic scoring engine, the AI layer, "
        "exports, and the audit log. This is the part that is unit-tested, and "
        "the part that would survive replacing the interface.",
    ),
    (
        "app/ — the view.",
        "A thin layer of pages and components that calls core/ and renders the "
        "result. It computes no marks and writes no queries of its own.",
    ),
]

SYSTEM_NOTES = [
    "The separation is enforced by a test that searches every file under core/ "
    "for a Streamlit import and fails if it finds one, so the rule cannot "
    "erode quietly.",
    "Responsibility is split the same way. The language model reads and "
    "judges; all arithmetic that decides a mark happens in Python, in one "
    "module, with a table-driven test behind it. A wrong verdict is a "
    "disagreement a faculty member can see and override. A wrong total would "
    "be an error nobody would catch.",
]

IN_SCOPE = [
    "Google sign-in restricted to @pccoepune.org, with the role resolved "
    "server-side from a seeded faculty allow-list",
    "Subjects, project cycles, enrolment including a validated CSV import, and "
    "review milestones",
    "Rubric authoring with weight validation, publish-freezes-version "
    "semantics, and cloning a published rubric to a new draft",
    "Student submission with version history and server-side text extraction",
    "Project groups, requested by a student or formed by the guide, and active "
    "only once granted — a granted group submits once, and every member shares "
    "the version, the score sheet, and the approval",
    "GitHub repository links, accepted only when owned by an account the "
    "faculty member has recorded for that student or a granted group-mate",
    "AI evaluation against a published rubric, with a fuzzy-match evidence "
    "guard that demotes unverifiable claims to NO_EVIDENCE",
    "Deterministic late-penalty and absence policy",
    "A faculty review grid: per-criterion verdicts, an evidence drawer, "
    "override with a mandatory reason, and single or bulk approval",
    "Excel (.xlsx) and TSV export, both built from persisted score sheets",
    "A student assistant scoped to one milestone's published rubric, with "
    "escalation to a faculty inbox",
    "Post-approval student feedback showing what was and was not followed",
    "Reports: score distribution, weakest criterion, and attendance mix",
    "An append-only audit log, surfaced in the interface",
]

OUT_OF_SCOPE = [
    "Plagiarism or similarity detection",
    "Executing, compiling, or testing student code",
    "A mobile application",
    "LMS or ERP integration",
    "Multi-institution tenancy",
    "Production cloud deployment with real student data",
    "Real-time collaborative editing",
    "Deep content analysis of images or video inside a submission",
    "Fetching, cloning, or reading the contents of a linked repository. A "
    "repository URL is recorded and shown; it is never downloaded. Marks come "
    "from evidence in the submitted document, because a span the guard cannot "
    "verify is not evidence",
]

TECHNOLOGY = [
    ("Application", "Streamlit ≥ 1.42, multipage via st.navigation"),
    ("Authentication", "st.login() / st.user, Google OIDC, hd=pccoepune.org"),
    (
        "Database",
        "SQLite via SQLAlchemy 2.0 (WAL, busy_timeout, foreign_keys=ON)",
    ),
    ("Migrations", "Alembic"),
    ("Validation", "Pydantic v2"),
    ("File parsing", "pdfplumber, python-docx"),
    ("AI orchestration", "LangGraph with SqliteSaver checkpointing"),
    (
        "AI model",
        "Google Gemini (gemini-3.6-flash), behind a one-method provider protocol",
    ),
    ("Evidence guard", "rapidfuzz partial_ratio ≥ 90"),
    ("Export", "openpyxl"),
    ("Testing", "pytest — 542 tests, all passing"),
]

OUTCOME = [
    "The system can be demonstrated end to end from a single command, "
    "producing a populated cohort in which a rubric is published; submissions "
    "arrive on time, late, and not at all; a group submits as one; an "
    "evaluation runs; evidence is verified; one criterion is demoted for want "
    "of evidence; penalties apply from the policy table; a faculty member "
    "approves; and an Excel file falls out carrying the same numbers as the "
    "screen.",
    "The empirical result worth reporting is the evidence rejection rate: how "
    "often the model cited something that is not actually in the student's "
    "document and was therefore refused. That number is what distinguishes "
    "this from asking a chatbot to grade an essay.",
]

DOCUMENTS = [
    (
        "Requirement analysis",
        "docs/requirements.md",
        "66 functional and 13 non-functional requirements, each traced to a "
        "module and a test",
    ),
    (
        "SRS",
        "docs/srs.md",
        "Assumptions, constraints, external interfaces, glossary",
    ),
    (
        "Design",
        "docs/design.md",
        "Architecture reasoning, with six diagrams in docs/diagrams/",
    ),
    ("Implementation", "docs/implementation.md", "Module-wise write-up"),
    (
        "Testing",
        "docs/test-cases.md",
        "Automated coverage, a manual test-case table with actual results, "
        "and a defect log",
    ),
    (
        "Deployment",
        "docs/deployment.md",
        "Setup, configuration, and a demonstration script",
    ),
    ("Limitations", "docs/limitations.md", "Honest limits and future scope"),
]


# -- document helpers ----------------------------------------------------


def set_base_styles(document) -> None:
    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(8)
    normal.paragraph_format.line_spacing = 1.15

    for level, size in ((1, 15), (2, 12.5)):
        style = document.styles[f"Heading {level}"]
        style.font.name = "Calibri"
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor(0x1F, 0x30, 0x64)
        style.paragraph_format.space_before = Pt(16 if level == 1 else 12)
        style.paragraph_format.space_after = Pt(6)


def add_page_number_footer(section) -> None:
    """A PAGE field. python-docx has no API for it, so build the run by hand."""
    paragraph = section.footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

    run = paragraph.add_run()
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

    run.font.size = Pt(9)


def body(document, text: str, *, italic: bool = False):
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    run = paragraph.add_run(text)
    run.italic = italic
    return paragraph


def bullet(document, text: str, *, lead: str | None = None):
    paragraph = document.add_paragraph(style="List Bullet")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    if lead:
        paragraph.add_run(lead + " ").bold = True
    paragraph.add_run(text)
    return paragraph


def two_column_table(document, rows, *, headers=None, widths=(1.6, 4.4)):
    table = document.add_table(rows=0, cols=len(widths))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    if headers:
        cells = table.add_row().cells
        for cell, heading in zip(cells, headers, strict=True):
            run = cell.paragraphs[0].add_run(heading)
            run.bold = True

    for values in rows:
        cells = table.add_row().cells
        for index, value in enumerate(values):
            cells[index].paragraphs[0].add_run(str(value))

    # Both the column widths and every cell width, or Word ignores them.
    for row in table.rows:
        for index, width in enumerate(widths):
            row.cells[index].width = Inches(width)

    document.add_paragraph()
    return table


# -- the document --------------------------------------------------------


def build(out_path: Path) -> Path:
    document = Document()
    set_base_styles(document)

    section = document.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1.1)
    section.right_margin = Inches(1)

    # -- title page ------------------------------------------------------
    for _ in range(3):
        document.add_paragraph()

    heading = document.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = heading.add_run(TITLE)
    run.bold = True
    run.font.size = Pt(22)
    run.font.color.rgb = RGBColor(0x1F, 0x30, 0x64)

    sub = document.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub_run = sub.add_run(SUBTITLE)
    sub_run.font.size = Pt(13)
    sub_run.italic = True

    document.add_paragraph()
    two_column_table(document, FRONT_MATTER, widths=(2.0, 4.0))

    document.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # Page numbering starts on the body, not the title page.
    document.add_section(WD_SECTION.CONTINUOUS)
    add_page_number_footer(document.sections[-1])

    # -- 1. introduction -------------------------------------------------
    document.add_heading("1. Introduction", level=1)
    for text in INTRODUCTION:
        body(document, text)

    # -- 2. problem statement --------------------------------------------
    document.add_heading("2. Problem statement", level=1)
    body(document, "Three problems, in the order they hurt:")
    for lead, text in PROBLEMS:
        bullet(document, text, lead=lead)

    # -- 3. objectives ----------------------------------------------------
    document.add_heading("3. Objectives", level=1)
    two_column_table(document, OBJECTIVES, headers=("#", "Objective"), widths=(0.6, 5.4))

    # -- 4. proposed system ----------------------------------------------
    document.add_heading("4. Proposed system", level=1)
    body(document, SYSTEM_INTRO)
    for lead, text in LAYERS:
        bullet(document, text, lead=lead)
    for text in SYSTEM_NOTES:
        body(document, text)

    # -- 5. scope ---------------------------------------------------------
    document.add_heading("5. Scope", level=1)
    document.add_heading("5.1 In scope", level=2)
    for text in IN_SCOPE:
        bullet(document, text)

    document.add_heading("5.2 Out of scope", level=2)
    body(
        document,
        "Declared explicitly, so that it is not mistaken at the review for "
        "something the project failed to do:",
    )
    for text in OUT_OF_SCOPE:
        bullet(document, text)

    # -- 6. technology ----------------------------------------------------
    document.add_heading("6. Technology", level=1)
    two_column_table(document, TECHNOLOGY, headers=("Layer", "Choice"), widths=(1.7, 4.3))

    # -- 7. expected outcome ----------------------------------------------
    document.add_heading("7. Expected outcome", level=1)
    for text in OUTCOME:
        body(document, text)

    # -- 8. deliverables ---------------------------------------------------
    document.add_heading("8. Accompanying SDLC documents", level=1)
    body(
        document,
        "This synopsis is one of nine documents. The remainder are maintained "
        "alongside the source code, so a claim that has stopped being true is "
        "visible rather than merely plausible.",
    )
    table = document.add_table(rows=0, cols=3)
    table.style = "Table Grid"
    header = table.add_row().cells
    for cell, text in zip(header, ("Document", "File", "Covers"), strict=True):
        cell.paragraphs[0].add_run(text).bold = True
    for name, path, covers in DOCUMENTS:
        cells = table.add_row().cells
        cells[0].paragraphs[0].add_run(name)
        cells[1].paragraphs[0].add_run(path).font.name = "Consolas"
        cells[2].paragraphs[0].add_run(covers)
    for row in table.rows:
        for index, width in enumerate((1.4, 1.7, 2.9)):
            row.cells[index].width = Inches(width)

    document.add_paragraph()
    signature = document.add_paragraph()
    signature.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    signature.add_run("Guide's signature: ").bold = True
    signature.add_run("__________________________")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(out_path)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    written = build(args.out)
    print(f"Wrote {written.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

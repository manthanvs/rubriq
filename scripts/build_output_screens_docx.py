"""Build the output-screens document: one captured screen per flow stage.

The screenshots in ``docs/report/screens/`` are artifacts, not generated
output — they were captured from the running application and are checked in,
because a screenshot of a system that no longer exists in that state cannot be
regenerated. This script assembles them, with the stage each one belongs to
and what it is evidence of.

Captured in light mode: a report is printed, and a dark screenshot is a page
of black ink.

    make screens
    python scripts/build_output_screens_docx.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from docx import Document  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.shared import Inches, Pt  # noqa: E402

from scripts.build_synopsis_docx import (  # noqa: E402
    BODY_PT,
    FONT,
    LINE_SPACING,
    centred,
    heading,
    page_break,
    page_number_footer,
    para,
    set_styles,
)

SCREENS = REPO_ROOT / "docs" / "report" / "screens"
DEFAULT_OUT = REPO_ROOT / "docs" / "report" / "RubriQ_Output_Screens.docx"

#: (file, stage, title, what the screen is evidence of)
FIGURES: tuple[tuple[str, str, str, str], ...] = (
    (
        "01-sign-in.jpg",
        "Stage 1 — Signing in",
        "The authentication gate",
        "The only way into the system. Sign-in is through the institute's "
        "Google account, and the address is checked against the permitted "
        "domain on the server after Google returns it. The role — faculty or "
        "student — is then resolved from a list held by the institution, so a "
        "user cannot choose their own.",
    ),
    (
        "02-faculty-dashboard.jpg",
        "Stage 2 — Faculty dashboard",
        "What is waiting for the guide",
        "Sixty-seven enrolled students and eighty-five rows awaiting a "
        "decision across both reviews. Each line under “Waiting on you” is a "
        "link to the page that resolves it. The progress bar below reports "
        "forty-nine of sixty-seven approved for the selected review.",
    ),
    (
        "03-rubric-builder.jpg",
        "Stage 2 — Rubric builder",
        "The published rubric, frozen",
        "The department's five criteria with the evidence each expects, and "
        "the two that are mandatory. The version is marked published and "
        "frozen: it cannot be edited in place, and the only way forward is "
        "“Edit as new version”, which leaves work already graded against this "
        "version valid.",
    ),
    (
        "04-student-dashboard.jpg",
        "Stage 3 — Student dashboard",
        "The next deadline, and where each review stands",
        "The countdown answers the question the page is opened to ask. Below "
        "it, each review carries its own status — submitted at version one, or "
        "not yet submitted — so the student never has to work it out from a "
        "date.",
    ),
    (
        "05-student-submit.jpg",
        "Stage 3 — Student submission",
        "The rubric is shown before the upload box",
        "The central idea of the project, visible in one screen. “What you "
        "are being marked on” appears above “Your submission”, so the student "
        "reads the criteria before choosing a file rather than after being "
        "marked. The notice above it states the consequence of the deadline "
        "having passed before anything is confirmed.",
    ),
    (
        "06-review-grid.jpg",
        "Stage 5 — Review grid",
        "One row per student, one column per criterion",
        "The centrepiece. Sixty-seven rows, eighteen flagged as needing a "
        "decision, forty-nine already approved. The status column distinguishes "
        "an estimate awaiting approval from an absence and from a student who "
        "never submitted — a non-submitter keeps a row rather than disappearing "
        "from the list.",
    ),
    (
        "07-reports.jpg",
        "Stage 7 — Reports",
        "The cohort, and the department's grading scale",
        "The distribution of marks out of twenty-five, with absent students "
        "excluded because an absence is a status and not a mark of zero. Below "
        "it the department's published bands — Excellent, Good, Satisfactory, "
        "Needs Improvement, Poor — applied to this review's marks.",
    ),
)


def figure(document, path: Path, number: str, caption: str) -> None:
    picture = document.add_paragraph()
    picture.alignment = WD_ALIGN_PARAGRAPH.CENTER
    picture.paragraph_format.space_before = Pt(4)
    picture.paragraph_format.space_after = Pt(4)
    picture.paragraph_format.keep_with_next = True
    picture.add_run().add_picture(str(path), width=Inches(5.9))

    label = document.add_paragraph()
    label.alignment = WD_ALIGN_PARAGRAPH.CENTER
    label.paragraph_format.line_spacing = 1.0
    label.paragraph_format.space_after = Pt(10)
    run = label.add_run(f"{number} — {caption}")
    run.font.name = FONT
    run.font.size = Pt(BODY_PT - 1)
    run.italic = True


def build(out_path: Path = DEFAULT_OUT) -> Path:
    missing = [name for name, *_ in FIGURES if not (SCREENS / name).is_file()]
    if missing:
        raise SystemExit(f"missing screenshots: {missing}")

    document = Document()
    set_styles(document)
    section = document.sections[0]
    section.top_margin = section.bottom_margin = Inches(0.8)
    section.left_margin = section.right_margin = Inches(0.9)
    page_number_footer(section)

    centred(document, "RubriQ — Output Screens", size=18, bold=True, space_after=6)
    centred(
        document,
        "Captured from the running system, one screen per stage of the flow",
        size=11,
        space_after=16,
    )
    para(
        document,
        "The screens below follow the order in which the system is used: a "
        "user signs in, a guide sets up a subject and publishes a rubric, a "
        "student reads that rubric and submits against it, the submission is "
        "evaluated, the guide reviews and approves, and the result is "
        "reported and exported. Each figure names the stage it belongs to and "
        "what it is evidence of.",
    )

    contents = document.add_paragraph()
    contents.paragraph_format.space_after = Pt(4)
    run = contents.add_run("Figures")
    run.bold = True
    run.font.name = FONT
    run.font.size = Pt(BODY_PT)
    for index, (_, stage, title, _note) in enumerate(FIGURES, 1):
        line = document.add_paragraph()
        line.paragraph_format.line_spacing = LINE_SPACING
        line.paragraph_format.space_after = Pt(1)
        line.paragraph_format.left_indent = Inches(0.35)
        entry = line.add_run(f"Fig. {index}  {title}  ·  {stage}")
        entry.font.name = FONT
        entry.font.size = Pt(BODY_PT - 1)

    page_break(document)

    for index, (name, stage, title, note) in enumerate(FIGURES, 1):
        heading(document, f"{index}. {title}")
        para(document, stage)
        para(document, note)
        figure(document, SCREENS / name, f"Fig. {index}", title)
        if index != len(FIGURES):
            page_break(document)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(out_path)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out = args.out if args.out.is_absolute() else REPO_ROOT / args.out
    print(f"Wrote {build(out).relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

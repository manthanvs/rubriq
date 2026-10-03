"""Build the Mini Project report as a Word document.

The department supplied a template for the *synopsis*, not for the report, so
this follows a conventional MCA project-report structure and reuses the
synopsis template's own formatting rules — Times New Roman, 14 pt headings,
12 pt body, 1.5 line spacing, justified — on the reasonable assumption that the
department wants both documents to look alike.

**Reformat the front matter if your department's certificate wording differs.**
That page is the one part of a report every institute words its own way, and
guessing it exactly is not possible from here; the text below is deliberately
plain so that replacing it is a small edit.

Content is drawn from the eight documents in ``docs/``, which stay the source of
truth. This is an assembly step, not a second copy: when a requirement changes,
change it in ``docs/requirements.md`` and rebuild.

    make report
    python scripts/build_report_docx.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from docx import Document  # noqa: E402
from docx.enum.section import WD_SECTION  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.shared import Inches, Pt  # noqa: E402

from scripts.build_synopsis_docx import (  # noqa: E402
    BODY_PT,
    FONT,
    GUIDE,
    INSTITUTE,
    PRN,
    STUDENT_NAME,
    YEAR,
    bullet,
    centred,
    heading,
    numbered,
    page_break,
    page_number_footer,
    para,
    set_styles,
    table_of_contents,
    two_column_table,
    update_fields_on_open,
)
from scripts.report_diagrams import (  # noqa: E402
    build_architecture,
    build_dfd_l0,
    build_dfd_l1,
    build_er,
    build_eval_state,
    build_use_case,
)
from scripts.synopsis_diagram import build as build_flow  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "docs" / "report" / "RubriQ_Report.docx"
REPORT_DIR = REPO_ROOT / "docs" / "report"

TITLE = "RubriQ – AI-Assisted Project Review & Rubric Evaluation System for PCCOE Mentors"

TESTS_TOTAL = 657

#: Shown on the title page and in §1.3. Private at the time of writing; make
#: the repository public before handing the report in, or the link is dead
#: for whoever reads it.
REPO_URL = "https://github.com/manthanvs/rubriq"

CERTIFICATE = (
    f"This is to certify that the Mini Project entitled “{TITLE}” has been "
    f"carried out by {STUDENT_NAME} (PRN {PRN}) in partial fulfilment of the "
    "requirements for the award of the degree of Master of Computer "
    "Applications, Semester III, during the academic year 2026–27."
)

ACKNOWLEDGEMENT = [
    "I would like to thank my guide, Prof. Dr. Anjana Arakerimath, Head of the "
    "Department of MCA, for her guidance throughout this project, and for the "
    "discussions that shaped what the system does and, just as usefully, what "
    "it deliberately does not do.",
    "I am grateful to the Department of MCA at Pimpri Chinchwad College of "
    "Engineering for providing the environment and the facilities that made "
    "this work possible.",
]

ABSTRACT = [
    "Project reviews in a college depend on a rubric that the student usually "
    "does not see until after they have been marked. The rubric therefore "
    "explains a mark rather than guiding the work, and the reasons behind a "
    "particular score are rarely written down anywhere.",
    "RubriQ is a web application that moves the rubric to the start of the "
    "process. A faculty member writes the rubric and publishes it, after which "
    "it cannot be edited; the student reads it before uploading anything. When "
    "work is submitted the system reads its text and produces a suggested "
    "score for each rubric point, and every suggestion carries a line copied "
    "from the student's own document as evidence. Any quoted line that is not "
    "actually present in the document is rejected and the point is recorded as "
    "having no evidence.",
    "All arithmetic that decides a mark — weights, totals, late penalties and "
    "absence — is performed by ordinary program code rather than by the "
    "language model, and no mark becomes final until a faculty member approves "
    "it by name. The system supports project groups that a faculty member has "
    "granted, allows a member of such a group to be marked apart from it with "
    "a recorded reason, and exports approved marks to Excel with the same "
    "numbers shown on screen.",
    f"The implementation is a single Streamlit application backed by SQLite, "
    f"organised so that all domain logic is free of interface code, and is "
    f"covered by {TESTS_TOTAL} automated tests.",
]

CHAPTERS = [
    "1. Introduction",
    "2. Problem Statement and Existing System",
    "3. Requirement Analysis",
    "4. System Design",
    "5. Implementation",
    "6. Testing",
    "7. Results",
    "8. Conclusion and Future Scope",
    "References",
]

# -- 1. Introduction ------------------------------------------------------

INTRO_BACKGROUND = [
    "Every project-based course at PCCOE is assessed at a small number of "
    "review meetings. For each review there is a rubric: a list of what the "
    "work should contain and how many marks each part carries. The rubric "
    "exists, but it exists mostly on the reviewer's side of the table.",
    "This project asks a narrow question. If the rubric already exists, what "
    "changes when the student can read it before they submit, and when every "
    "mark carries the line of text that justified it?",
]

INTRO_OBJECTIVES = [
    "Let a faculty member write a rubric for each review, check that its "
    "weights total 100, and publish it so that it cannot be edited afterwards.",
    "Show the published rubric to the student before submission opens.",
    "Accept versioned submissions and read their text at the time of upload.",
    "Produce a suggested score for each rubric point, quoting the student's "
    "own document as evidence, and reject any quotation that is not really "
    "there.",
    "Apply late-submission and absence rules by calculation rather than by judgement.",
    "Require an explicit, named faculty approval before any mark is final.",
    "Export approved marks to Excel with the numbers shown on screen.",
    "Answer student questions from the published rubric alone, and pass on "
    "anything it cannot answer.",
    "Allow project groups only where a faculty member has granted them, and "
    "allow a member of a granted group to be marked apart from it with a "
    "recorded reason.",
]

INTRO_ORGANISATION = (
    "Chapter 2 describes how reviews are conducted at present and why a new "
    "system is needed. Chapter 3 sets out the requirements. Chapter 4 gives "
    "the design and the diagrams. Chapter 5 describes the implementation "
    "module by module. Chapter 6 covers testing, including the defects found "
    "during development. Chapter 7 reports the results obtained, and Chapter 8 "
    "concludes with the limitations and the scope for future work."
)

# -- 2. Problem statement -------------------------------------------------

EXISTING = [
    "At present the review process is carried out by hand. The guide keeps the "
    "rubric on paper or in their own notes. During the review they read the "
    "student's report, judge it against that rubric from memory, and write a "
    "mark in a register or a spreadsheet. Feedback is given by speaking to the "
    "student for a few minutes. Late submissions are handled case by case. At "
    "the end, every student's marks are typed into an Excel sheet for the "
    "department's records.",
    "This works, and it has worked for years. Its weaknesses are not failures "
    "of effort but consequences of everything depending on one person holding "
    "the whole rubric in mind at once, with nothing written down afterwards.",
]

EXISTING_PROBLEMS = [
    "The student cannot see the rubric before submitting, so they cannot aim at it.",
    "Only the mark survives the review. The reasons behind it do not.",
    "Two reviewers, or one reviewer on two different days, may score similar "
    "work differently, and there is no record against which to check.",
    "A student four days late and a student who never submitted are usually "
    "both recorded as zero, although they are administratively different.",
    "Spoken feedback is forgotten, leaving the student nothing written to improve from.",
    "Marks are copied by hand into a spreadsheet, where a typing error is easy "
    "to make and hard to notice.",
]

NEED = [
    "The proposed system addresses each of these directly. It publishes the "
    "rubric before the deadline, so the rubric becomes a specification rather "
    "than a justification. It prepares a first draft of the score sheet so the "
    "reviewer checks rather than composes, and it attaches to every suggested "
    "score the exact sentence from the report that supports it, so the draft "
    "can be checked rather than trusted.",
    "It applies the late-submission table by calculation, keeps “absent” "
    "as a status distinct from a mark of zero, records every change with its "
    "reason and its author, and produces the department's Excel file "
    "automatically from the same figures shown on screen.",
]

RELATED = [
    "Learning-management systems such as Moodle and Google Classroom provide "
    "rubric-based grading, and both allow a rubric to be attached to an "
    "assignment. What they do not provide is an evidence-backed first draft of "
    "the marks, or a guarantee that a machine-suggested score is traceable to "
    "a specific sentence in the student's own submission.",
    "Automated essay-scoring research has produced systems that predict a "
    "grade from text, but a predicted grade with no visible justification is "
    "not usable in a review where the mark has to be defended to the student. "
    "RubriQ deliberately takes the opposite position: the model never produces "
    "a final mark, and anything it claims must be checkable against the "
    "document it claims to have read.",
]

# -- 3. Requirement analysis ---------------------------------------------

FUNCTIONAL = [
    (
        "Authentication",
        "Sign-in restricted to institute Google accounts; the role is "
        "decided from a stored list and cannot be chosen by the user.",
    ),
    (
        "Academics",
        "Subjects, project cycles, enrolment including a validated CSV "
        "import, and review milestones with dates and marks.",
    ),
    (
        "Rubrics",
        "Criteria with weights and maximum scores; publishing is refused "
        "unless the weights total 100; a published rubric is read-only and "
        "editing it creates a new version.",
    ),
    (
        "Submissions",
        "PDF, DOCX and TXT uploads with full version history; text "
        "extracted at upload; an optional GitHub link accepted only if it "
        "belongs to a registered account.",
    ),
    (
        "Groups",
        "A student may request a group and a faculty member may form one; "
        "only a granted group has any effect, and it submits once for all "
        "its members.",
    ),
    (
        "Evaluation",
        "A verdict, a score, a confidence and a quoted line for each rubric "
        "point; any quotation not found in the submission is rejected and "
        "recorded as having no evidence.",
    ),
    (
        "Scoring",
        "Weighted totals, late penalties and absence computed from a fixed "
        "rule table, in program code rather than by the model.",
    ),
    (
        "Approval",
        "No mark is final until approved by a named faculty member; any "
        "change requires a reason and clears an existing approval.",
    ),
    (
        "Per-member marks",
        "A member of a granted group may be marked apart from it by a "
        "recorded difference, with a reason the student can read.",
    ),
    (
        "Export",
        "Excel and clipboard-pastable exports carrying identical numbers, "
        "built from stored score sheets.",
    ),
    (
        "Student assistant",
        "Questions answered from the published rubric alone, escalated to "
        "the guide when they cannot be answered.",
    ),
    (
        "Feedback and audit",
        "Per-criterion feedback shown after approval; every action recorded.",
    ),
]

NON_FUNCTIONAL = [
    (
        "Security",
        "A student can never read another student's work or marks. This is "
        "enforced while the data is fetched from the database, not by "
        "hiding controls.",
    ),
    (
        "Privacy",
        "The student's name, PRN and email are removed before any text is "
        "sent to the AI service.",
    ),
    (
        "Reliability",
        "If the AI service is unavailable, manual marking, penalties, "
        "approval and export continue to work.",
    ),
    (
        "Correctness",
        "The same submission and rubric always produce the same marks; all "
        "money-like values use exact decimal arithmetic.",
    ),
    (
        "Traceability",
        "Every final mark traces to an approver, a submission version and a "
        "rubric version.",
    ),
    (
        "Data safety",
        "Nothing is permanently deleted; new submissions and evaluations "
        "are stored as new versions.",
    ),
    (
        "Usability",
        "No screen shows a blank area or a technical error; every empty "
        "page states the next action.",
    ),
    ("Maintainability", "Domain logic is kept entirely separate from interface code."),
    (
        "Portability",
        "Runs on a normal laptop with only Python installed; there is no "
        "database server to configure.",
    ),
]

SOFTWARE = [
    ("Operating system", "Windows 10 or 11; also runs on Linux and macOS"),
    ("Language", "Python 3.12 or above"),
    ("Web framework", "Streamlit 1.42 or above"),
    ("Database", "SQLite, accessed through SQLAlchemy 2.0"),
    ("Migrations", "Alembic"),
    ("Authentication", "Google Sign-In (OIDC), restricted to the college domain"),
    ("File reading", "pdfplumber (PDF), python-docx (Word)"),
    ("AI service", "Google Gemini (gemini-3.6-flash)"),
    ("AI workflow", "LangGraph, with SQLite checkpointing"),
    ("Validation", "Pydantic 2"),
    ("Text matching", "RapidFuzz"),
    ("Spreadsheet export", "openpyxl"),
    ("Testing", "pytest"),
]

HARDWARE = (
    "No special hardware is required. A laptop with 8 GB of RAM is sufficient. "
    "An internet connection is needed for sign-in and for AI evaluation; every "
    "other feature works without one."
)

# -- 4. Design ------------------------------------------------------------
DESIGN_USE_CASES = [
    "Two people use the system and they use it for different things. A student "
    "reads a rubric, submits work against it, asks a question about it, and "
    "later reads the feedback. A faculty member creates the subject, enrols the "
    "class, writes and publishes the rubric, runs the evaluation, corrects it, "
    "approves it, and exports the result. Signing in is the only thing both do.",
    "The seven shaded cases on the right of the diagram are not features. They "
    "are steps that other use cases always include and can never skip: "
    "asserting the institute domain before a role is resolved, checking that "
    "rubric weights sum to 100 before a version can be published, removing the "
    "student's identity before any text reaches the model, checking a quoted "
    "span against the submission before a score is stored, applying the "
    "lateness rules before a total is written, and recording an audit row for "
    "every change. Drawing them separately is deliberate: each one is an "
    "invariant, and an invariant that is merely described in prose is one that "
    "a later change can quietly remove.",
]

DESIGN_DATA_FLOW = [
    "At the context level the system is a single process with four things "
    "outside it: the student, the faculty member, Google's sign-in service, and "
    "the language model. Two properties of that boundary are worth stating "
    "because they are design decisions rather than consequences. Nothing "
    "identifying crosses it on the way to the model — the arrow carries rubric "
    "text and submission text with the name, PRN and email already removed. And "
    "everything that comes back is an estimate; it becomes a mark only after a "
    "named person approves it inside the boundary.",
    "Opening that process up gives seven sub-processes and six data stores. "
    "The evaluation process, 5.0, is the one to read closely. It reads the "
    "rubric store and the submission store and writes to neither, and it has no "
    "path at all to the user store or the subject store. That is what the "
    "constraint “the graph has no tools” means in practice: the evaluation "
    "receives a rubric and a block of text as input and returns structured "
    "output, and there is no route by which it could query the database for "
    "anything else. Process 6.0 is likewise the only writer of a total — the "
    "others produce verdicts and answers, and the arithmetic happens in one "
    "place.",
]


DESIGN_PRINCIPLE = [
    "The system is built on one architectural rule: all domain logic lives in "
    "a package named core, written as plain Python with no interface code in "
    "it at all, and the Streamlit application is a thin layer that calls it. "
    "The rule is enforced by an automated test which searches every file under "
    "core for a Streamlit import and fails if it finds one.",
    "The rule is worth the discipline for three reasons. The domain becomes "
    "testable without a browser, which is why 589 of the project's "
    f"{TESTS_TOTAL} tests need no interface at all. Access control becomes a "
    "property of a function signature — every service function takes the "
    "acting user as its first argument and filters the database query by it — "
    "rather than something the interface is trusted to do. And if Streamlit "
    "ever became the limiting factor, the interface could be replaced without "
    "rewriting the system.",
]

DESIGN_SCORING = [
    "Marks are computed in one module and nowhere else. The weighted total is "
    "the sum, over the rubric's criteria, of the score obtained divided by the "
    "criterion maximum and multiplied by the criterion weight; this is scaled "
    "onto the milestone's own maximum marks. The late penalty is a percentage "
    "of that maximum, taken from a rule table, and is applied to the total "
    "rather than to any individual criterion. The final mark is the base total "
    "less the penalty, and never falls below zero.",
    "Two properties of this arrangement matter. It is deterministic, so the "
    "same inputs always produce the same mark. And it is separate from the "
    "language model, which is never asked to perform arithmetic that decides a "
    "mark.",
]

LATE_TABLE = [
    ("0", "No penalty"),
    ("1", "10% of the milestone's maximum marks deducted"),
    ("2", "20% deducted"),
    ("3", "35% deducted"),
    ("4 – 5", "Recorded ABSENT; the work is still stored and still receives feedback"),
    (
        "More than 5",
        "Recorded ABSENT, and requires explicit faculty reinstatement "
        "before it can be scored",
    ),
]

DESIGN_AI = [
    "The AI layer is confined to a single package. Everything outside it calls "
    "three ordinary Python functions and never sees a model, a prompt or a "
    "workflow object.",
    "Evaluation is expressed as a small state machine rather than a straight "
    "line of code, because it genuinely has two failure loops: a response that "
    "does not match the required format is sent back once for repair, and a "
    "quotation that cannot be found in the student's text causes that rubric "
    "point to be demoted. Expressing this as a diagram makes the retry policy "
    "explicit rather than hidden inside nested error handling.",
    "The state machine is also checkpointed. Streamlit re-runs the whole script "
    "on every interaction, so an evaluation interrupted by a page refresh would "
    "otherwise start again from the beginning and call the model a second time. "
    "With checkpointing it resumes from the last completed step; this was "
    "verified against the live service, where a resumed run made no model calls "
    "at all.",
]

DESIGN_GUARD = [
    "Every quoted line returned by the model is checked against the text "
    "extracted from the student's submission, using approximate string "
    "matching with a threshold of 90. A quotation that cannot be found is "
    "rejected: the rubric point is recorded as having no evidence, its score "
    "is set to zero, and the faculty member is required to look at it.",
    "Both sides of the comparison are normalised — spacing collapsed, case "
    "folded, line-break hyphenation joined — because PDF extraction reflows "
    "text and a genuine quotation would otherwise fail to match. The model's "
    "original wording is stored untouched, so a quotation shown to a faculty "
    "member is exactly what the model produced.",
    "There is no way past this check. It is not skipped at high confidence and "
    "not skipped in a batch run, because a confidence value reported by a "
    "language model is a self-assessment and not a probability.",
]

# -- 5. Implementation ----------------------------------------------------

MODULES = [
    (
        "core/auth",
        "Domain assertion, role resolution from a stored list, and the page "
        "policy that decides which pages exist for which role.",
    ),
    (
        "core/academics",
        "Subjects, project cycles, enrolment and milestones. The CSV import "
        "is a dry run first: every row is given a verdict and shown before "
        "anything is written, and the commit is all-or-nothing.",
    ),
    (
        "core/rubrics",
        "Rubric versioning. A published rubric is read-only at the service "
        "layer; editing clones it to the next version and leaves the "
        "published one untouched, so work already marked stays valid.",
    ),
    (
        "core/submissions",
        "Storage, text extraction and versioning. Text is read at upload so "
        "that no later stage opens a file. Repository links are parsed and "
        "checked against the account the faculty member recorded.",
    ),
    (
        "core/groups",
        "Group requests, grants and refusals. Only a granted group has any "
        "effect; this is the single deliberate exception to the rule that a "
        "student sees only their own data.",
    ),
    (
        "core/scoring",
        "The arithmetic, the late-policy table, the score sheets, and the "
        "review-grid query. Nothing outside this package computes a mark.",
    ),
    (
        "core/ai",
        "The only package permitted to import a language-model library. It "
        "contains the response schema, the evidence guard, the prompts and "
        "the evaluation workflow.",
    ),
    (
        "core/queries",
        "The student assistant: its context is the published rubric and the "
        "milestone description, and nothing else.",
    ),
    (
        "core/exports",
        "One row builder feeding both the Excel and the clipboard exports, "
        "so the two can differ in formatting but never in numbers.",
    ),
    (
        "app/",
        "Pages and shared components. It computes no marks and writes no "
        "database queries of its own.",
    ),
]

IMPL_NOTES = [
    (
        "Storing time correctly.",
        "Timestamps are stored in UTC through a custom column type that refuses "
        "to accept a value with no timezone attached. This was written in "
        "response to a real defect: SQLite discarded the offset on an "
        "India-time value, so a submission made at 23:59 was read back as "
        "23:59 UTC and displayed as 05:29 the next morning, turning an on-time "
        "submission into a late one.",
    ),
    (
        "Deciding lateness.",
        "Days late are computed from the calendar date in India Standard Time "
        "on both sides of the comparison. Comparing timestamps in UTC would "
        "make a submission at a quarter to midnight count as a day late, which "
        "is both wrong and impossible to explain to a student.",
    ),
    (
        "Keeping the reviewer honest about groups.",
        "A group's submission is stored once and every member resolves to it, "
        "but each member keeps their own row in the review grid. Collapsing a "
        "group into a single row would leave individual members with no record "
        "of their own.",
    ),
    (
        "Marking a member apart.",
        "A per-member adjustment is stored as a signed difference from the "
        "group's total rather than as a replacement mark. The group's work was "
        "assessed once; what differs between members is contribution. A "
        "replacement would detach from that assessment, so that correcting a "
        "criterion later would move the group's total while the replacement "
        "sat unchanged, explaining nothing.",
    ),
]

# -- 6. Testing -----------------------------------------------------------

TEST_AREAS = [
    (
        "Scoring engine",
        "30",
        "The late-penalty table row by row, boundary days, midnight "
        "in India Standard Time, and a round-trip check that a stored mark "
        "equals a fresh recomputation.",
    ),
    (
        "Score sheets",
        "25",
        "Approval refused while an evaluation is still running, an "
        "empty override reason refused, totals recomputed after an "
        "override.",
    ),
    (
        "Evidence guard",
        "22",
        "A fabricated quotation is rejected; a genuine but reflowed "
        "one is accepted; no identifying information appears in the "
        "outgoing prompt.",
    ),
    (
        "Response schema",
        "22",
        "The required response format, including the rule that a "
        "point with no evidence must score zero.",
    ),
    (
        "Evaluation workflow",
        "20",
        "The repair limit, batch demotion, checkpoint resume and the "
        "absence of duplicate model calls.",
    ),
    (
        "Student assistant",
        "34",
        "Scope rules, escalation, and refusal to predict a mark.",
    ),
    (
        "Groups",
        "32",
        "A pending request confers nothing; a granted group shares "
        "one submission; a non-member sees nothing.",
    ),
    (
        "Repository links",
        "48",
        "URL parsing, lookalike hosts, ownership against the "
        "register, and a refused link leaving no submission behind.",
    ),
    (
        "Per-member marks",
        "39",
        "Reasons required, both clamps enforced, approval cleared, "
        "and an absent row staying absent.",
    ),
    (
        "Rubric versioning",
        "18",
        "A published rubric cannot be edited; publishing with weights "
        "that do not total 100 is refused.",
    ),
    (
        "Submission versioning",
        "19",
        "Version 1 remains retrievable and bound to its own text after version 2 exists.",
    ),
    (
        "Export parity",
        "17",
        "The two export formats agree cell for cell; absence exports as a status.",
    ),
    (
        "Isolation and access",
        "74",
        "Cross-user negative cases, the domain assertion, and the page-list policy.",
    ),
    (
        "Interface",
        "78",
        "All thirteen pages against an empty database; grid layout; "
        "the wording shown for each late-penalty band.",
    ),
]

ARCHITECTURE_TESTS = [
    "One test searches every file in the domain package for an interface "
    "import and fails if it finds one.",
    "One test uses reflection over every public function in the domain package "
    "and fails any whose signature does not begin with the acting user. "
    "Exemptions must be listed with a written reason.",
    "One test asserts the page-list builder directly, so the claim that a "
    "student cannot reach a faculty page is proved by a unit test rather than "
    "by clicking.",
]

DEFECTS = [
    (
        "Timezone discarded on storage",
        "A submission at 23:59 India time was read back as the following "
        "morning, turning an on-time submission late.",
        "A column type that refuses a value with no timezone and normalises to UTC.",
    ),
    (
        "Confirmation messages discarded",
        "A success message shown immediately before the page refreshed was "
        "drawn and thrown away, so the student was told nothing.",
        "Messages are queued and shown after the refresh.",
    ),
    (
        "Resumed evaluation overwrote its own checkpoint",
        "The workflow was resumed by passing it a fresh starting state, which "
        "is exactly the duplicate call the design forbids.",
        "Resume passes no state, so the checkpoint is replayed.",
    ),
    (
        "Provider failure recorded as zeroes",
        "A service outage was written to the database as a page of zero "
        "scores instead of a failure.",
        "The failure status and its reason are preserved.",
    ),
    (
        "Mark-prediction refusal too narrow",
        "The assistant refused “what marks will I get” but answered "
        "“how many marks will I get”.",
        "The check no longer assumes the words appear in a particular order.",
    ),
    (
        "Empty totals displayed as a word",
        "A student with no score sheet showed the word None in the marks "
        "column, which reads as a value.",
        "All three totals render through one path and show nothing when there "
        "is nothing.",
    ),
    (
        "Late-penalty wording understated the outcome",
        "Ten days late was described as a late penalty applying, when the "
        "policy records it as absent and requires reinstatement.",
        "The wording names the band that actually applies.",
    ),
    (
        "Version collision after a group was granted",
        "A student who had already submitted individually, then had their "
        "group granted, caused a database constraint violation on their next "
        "upload.",
        "Version numbering takes the union of the group's submissions and the "
        "uploader's own.",
    ),
    (
        "Export crashed on a non-submitter",
        "Adding the group columns updated only the branch for scored rows, so "
        "exporting any milestone containing a student who never submitted "
        "raised an error.",
        "Both branches updated, with a test that exports a cohort containing "
        "an empty row.",
    ),
]

# -- 7. Results -----------------------------------------------------------

RESULTS = [
    "The system was demonstrated end to end against a seeded cohort of eight "
    "students, built by a single command and deliberately uneven: one "
    "submission on time, one a day late, one two days late, one four days late "
    "and therefore absent, one student who never submitted, one blocked by a "
    "mandatory rubric point with no evidence, one with a version history, one "
    "granted group submitting as a single entry, and one group request still "
    "waiting for approval.",
]

RESULT_TABLE = [
    (
        "Deterministic marking",
        "The late-penalty table produces the documented deduction at every "
        "band, including the boundary between three days and four.",
    ),
    (
        "Absence kept distinct",
        "An absent submission is displayed and exported as ABSENT and never "
        "as a number, and is excluded from the class average.",
    ),
    (
        "Evidence checking",
        "Live evaluation completed for every submission attempted, with "
        "each score carrying a quotation checked against the submitted "
        "text.",
    ),
    (
        "Resumable evaluation",
        "A completed run re-entered with the same identifier executed no "
        "further steps and made no model calls.",
    ),
    (
        "Group marking",
        "Two members of one granted group hold different marks (11.63 and "
        "9.13 out of 25) from a single submission, with the difference and "
        "its reason recorded.",
    ),
    (
        "Export agreement",
        "The spreadsheet carries the same figures as the screen, including "
        "a member's adjusted mark rather than the group's.",
    ),
    (
        "Behaviour without AI",
        "With the model unavailable, manual marking, penalties, approval "
        "and export continue to work.",
    ),
]

RESULTS_HONEST = [
    "One result expected at the outset was not obtained. The rate at which the "
    "system rejects fabricated quotations was intended as the project's "
    "principal empirical finding, and across the runs performed it was zero. "
    "This is a weak result rather than a good one: the seeded documents are "
    "short and clean, and most rubric points returned no evidence — a verdict "
    "that carries no quotation to check. Establishing a meaningful rejection "
    "rate requires longer, genuine submissions, and is stated here as an open "
    "measurement rather than a finding.",
]

# -- 8. Conclusion --------------------------------------------------------

CONCLUSION = [
    "RubriQ addresses a small but real problem in the way project reviews are "
    "conducted. The rubric already exists in every course; the difficulty is "
    "that the student sees it too late to act on, and that the reasoning "
    "behind a mark is never written down.",
    "Publishing the rubric before submission, attaching a quotation to every "
    "suggested score, and requiring a named faculty approval before anything "
    "becomes final makes the review clearer for the student and quicker for "
    "the guide, without moving the decision away from the guide.",
    "The design keeps a firm line between the two halves of the work. The "
    "language model reads and judges; all arithmetic that decides a mark is "
    "performed by program code that can be tested and explained. This is what "
    "makes the result defensible: a wrong judgement is visible to the reviewer "
    "and can be corrected, whereas a wrong calculation would pass unnoticed.",
]

LIMITATIONS = [
    (
        "Concurrency",
        "SQLite permits one writer at a time. This is adequate for a single "
        "guide reviewing a cohort, but would not survive an entire class "
        "submitting simultaneously.",
    ),
    (
        "Single process",
        "A long evaluation occupies the session that started it, and there "
        "is no background worker.",
    ),
    (
        "Confidence is not a probability",
        "A confidence figure reported by a language model is a self- "
        "assessment. No decision in the system depends on it alone.",
    ),
    (
        "Evidence checking is lexical",
        "The guard detects a fabricated quotation. It cannot detect a "
        "genuine quotation used to support a conclusion it does not "
        "actually support.",
    ),
    (
        "Extraction depends on the file",
        "A scanned PDF with no text layer yields nothing, and diagrams are "
        "invisible to the system. It records this rather than guessing.",
    ),
    (
        "No plagiarism detection",
        "The system reports whether a submission evidences a rubric point, "
        "not whether it is the student's own work.",
    ),
    (
        "Group splits are judgements",
        "A per-member adjustment records that a guide decided a member "
        "contributed less, and their stated reason, but the system has no "
        "evidence of contribution to check it against.",
    ),
    (
        "Reproducibility is recorded, not guaranteed",
        "Every evaluation stores the model name, prompt version and raw "
        "response, so a result can be explained later; it cannot "
        "necessarily be reproduced, because the service is non- "
        "deterministic and models are withdrawn on the vendor's schedule.",
    ),
]

FUTURE = [
    "Reading a linked repository, so that a commit history can serve as "
    "evidence a document cannot provide.",
    "Rubric templates, to remove the largest piece of manual work for faculty.",
    "Comparing reviewers against each other and against the model, using "
    "data the system already stores.",
    "Checking that a quoted line actually supports the verdict drawn from "
    "it, rather than merely existing.",
    "Evaluating diagrams as well as text, which for a project report is "
    "where much of the substance lies.",
    "Moving to a client–server database and a real deployment.",
    "Measuring contribution within a group rather than recording a judgement about it.",
    "A rubric self-check for students before the deadline, letting them "
    "see which rubric points their own draft does not yet evidence.",
]

REFERENCES = [
    f"RubriQ source code and commit history. {REPO_URL}",
    "Streamlit documentation. https://docs.streamlit.io",
    "SQLAlchemy 2.0 documentation. https://docs.sqlalchemy.org",
    "Alembic documentation. https://alembic.sqlalchemy.org",
    "Pydantic documentation. https://docs.pydantic.dev",
    "LangGraph documentation. https://langchain-ai.github.io/langgraph/",
    "Google Gemini API documentation. https://ai.google.dev/gemini-api/docs",
    "RapidFuzz documentation. https://rapidfuzz.github.io/RapidFuzz/",
    "openpyxl documentation. https://openpyxl.readthedocs.io",
    "pdfplumber. https://github.com/jsvine/pdfplumber",
    "pytest documentation. https://docs.pytest.org",
]


def figure(document, path: Path, caption: str, width: float = 5.9) -> None:
    picture = document.add_paragraph()
    picture.alignment = WD_ALIGN_PARAGRAPH.CENTER
    picture.paragraph_format.space_before = Pt(6)
    picture.paragraph_format.space_after = Pt(4)
    picture.paragraph_format.keep_with_next = True
    picture.add_run().add_picture(str(path), width=Inches(width))

    label = document.add_paragraph()
    label.alignment = WD_ALIGN_PARAGRAPH.CENTER
    label.paragraph_format.line_spacing = 1.0
    label.paragraph_format.space_after = Pt(10)
    run = label.add_run(caption)
    run.font.name = FONT
    run.font.size = Pt(BODY_PT - 1)
    run.italic = True


def build(out_path: Path) -> Path:
    diagrams = {
        "flow": build_flow,
        "architecture": build_architecture,
        "er": build_er,
        "use-case": build_use_case,
        "dfd-l0": build_dfd_l0,
        "dfd-l1": build_dfd_l1,
        "eval-state": build_eval_state,
    }
    figures = {}
    for name, builder in diagrams.items():
        path = REPORT_DIR / f"{name}.png"
        if not path.exists():
            builder(path)
        figures[name] = path
    flow = figures["flow"]
    architecture = figures["architecture"]
    er = figures["er"]

    document = Document()
    set_styles(document)

    section = document.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1.2)
    section.right_margin = Inches(1)

    # ---- title page ----------------------------------------------------
    document.add_paragraph()
    centred(document, "A Mini Project Report on", size=14, space_after=24)
    centred(document, TITLE, size=19, bold=True, space_after=30)
    centred(document, "Submitted by", size=13, space_after=10)
    centred(document, STUDENT_NAME, size=16, bold=True, space_after=4)
    centred(document, f"({PRN})", size=13, space_after=26)
    centred(document, "Under the guidance of", size=13, space_after=10)
    centred(document, GUIDE, size=15, space_after=40)
    centred(document, "DEPARTMENT OF MCA", size=15, bold=True, space_after=8)
    centred(document, INSTITUTE, size=12, bold=True, space_after=16)
    centred(document, YEAR, size=13, space_after=16)
    centred(document, f"Source code: {REPO_URL}", size=11, space_after=0)
    page_break(document)

    document.add_section(WD_SECTION.CONTINUOUS)
    page_number_footer(document.sections[-1])

    # ---- certificate ---------------------------------------------------
    centred(document, "CERTIFICATE", size=16, bold=True, space_after=22)
    para(document, CERTIFICATE)
    document.add_paragraph()
    document.add_paragraph()
    para(
        document,
        "The work is original and has been carried out under my supervision.",
    )
    for _ in range(3):
        document.add_paragraph()
    row = document.add_paragraph()
    row.paragraph_format.line_spacing = 1.0
    run = row.add_run("Guide\t\t\t\t\t\tHead of the Department")
    run.font.name = FONT
    run.font.size = Pt(BODY_PT)
    run.bold = True
    page_break(document)

    # ---- acknowledgement -----------------------------------------------
    centred(document, "ACKNOWLEDGEMENT", size=16, bold=True, space_after=20)
    for text in ACKNOWLEDGEMENT:
        para(document, text)
    document.add_paragraph()
    signature = document.add_paragraph()
    signature.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    signature.paragraph_format.line_spacing = 1.0
    run = signature.add_run(f"{STUDENT_NAME}\n({PRN})")
    run.font.name = FONT
    run.font.size = Pt(BODY_PT)
    page_break(document)

    # ---- abstract ------------------------------------------------------
    centred(document, "ABSTRACT", size=16, bold=True, space_after=20)
    for text in ABSTRACT:
        para(document, text)
    page_break(document)

    # ---- contents ------------------------------------------------------
    centred(document, "CONTENTS", size=16, bold=True, space_after=18)
    table_of_contents(document, CHAPTERS)
    page_break(document)

    # ---- 1. Introduction -----------------------------------------------
    heading(document, "1. Introduction")
    heading(document, "1.1 Background", level=2)
    for text in INTRO_BACKGROUND:
        para(document, text)

    heading(document, "1.2 Objectives", level=2)
    for text in INTRO_OBJECTIVES:
        numbered(document, text)

    heading(document, "1.3 Organisation of the report", level=2)
    para(document, INTRO_ORGANISATION)
    para(
        document,
        "The complete source code, its commit history, and the eight "
        "supporting documents this report is assembled from are available "
        f"at {REPO_URL}. The commit history is itself part of the record: "
        "each phase of the build is a separate commit, and the defects "
        "listed in Chapter 6 can be traced to the commits that fixed them.",
    )

    # ---- 2. Problem statement ------------------------------------------
    heading(document, "2. Problem Statement and Existing System")
    heading(document, "2.1 The existing system", level=2)
    for text in EXISTING:
        para(document, text)
    para(document, "Its difficulties are:")
    for text in EXISTING_PROBLEMS:
        bullet(document, text)

    heading(document, "2.2 Need for the proposed system", level=2)
    for text in NEED:
        para(document, text)

    heading(document, "2.3 Related work", level=2)
    for text in RELATED:
        para(document, text)

    # ---- 3. Requirement analysis ----------------------------------------
    heading(document, "3. Requirement Analysis")
    heading(document, "3.1 Functional requirements", level=2)
    para(
        document,
        "The requirements are summarised by area below. The full numbered list "
        "— 74 functional and 13 non-functional requirements, each naming the "
        "module that implements it and the test that proves it — is maintained "
        "alongside the source code in docs/requirements.md.",
    )
    two_column_table(
        document, FUNCTIONAL, headers=("Area", "Requirement"), widths=(1.5, 4.4)
    )

    heading(document, "3.2 Non-functional requirements", level=2)
    two_column_table(
        document, NON_FUNCTIONAL, headers=("Quality", "Requirement"), widths=(1.4, 4.5)
    )

    heading(document, "3.3 Software requirements", level=2)
    two_column_table(
        document, SOFTWARE, headers=("Item", "Software used"), widths=(1.8, 4.1)
    )
    para(document, HARDWARE)

    # ---- 4. Design -------------------------------------------------------
    heading(document, "4. System Design")
    heading(document, "4.1 Architecture", level=2)
    for text in DESIGN_PRINCIPLE:
        para(document, text)
    figure(document, architecture, "Fig. 4.1 — System architecture")

    heading(document, "4.2 Use cases", level=2)
    for text in DESIGN_USE_CASES:
        para(document, text)
    figure(document, figures["use-case"], "Fig. 4.2 — Use-case diagram", width=5.1)

    heading(document, "4.3 Data flow", level=2)
    for text in DESIGN_DATA_FLOW:
        para(document, text)
    figure(
        document,
        figures["dfd-l0"],
        "Fig. 4.3 — Data flow diagram, level 0 (context)",
    )
    figure(
        document,
        figures["dfd-l1"],
        "Fig. 4.4 — Data flow diagram, level 1",
        width=5.2,
    )

    heading(document, "4.4 Data model", level=2)
    para(
        document,
        "The database holds twenty tables. Three properties of the model carry "
        "the design decisions. An evaluation records the submission version "
        "and the rubric version it ran against as values, so re-evaluating "
        "cannot retroactively change what an approved mark was measured "
        "against. A score sheet always refers to a specific evaluation rather "
        "than to a submission. And the verdict for each rubric point is stored "
        "in its own column rather than being derived from the score when the "
        "page is drawn, which is what makes “what has the student followed, "
        "and what have they not” answerable.",
    )
    figure(document, er, "Fig. 4.5 — Entity–relationship overview", width=5.9)

    heading(document, "4.5 Flow of work", level=2)
    figure(document, flow, "Fig. 4.6 — Flow of work in RubriQ", width=5.4)

    heading(document, "4.6 Scoring", level=2)
    for text in DESIGN_SCORING:
        para(document, text)
    para(document, "The late-submission policy is as follows:")
    two_column_table(
        document, LATE_TABLE, headers=("Days late", "Outcome"), widths=(1.3, 4.6)
    )

    heading(document, "4.7 The AI layer", level=2)
    for text in DESIGN_AI:
        para(document, text)
    figure(
        document,
        figures["eval-state"],
        "Fig. 4.7 — Evaluation state machine, with both failure loops",
        width=5.6,
    )

    heading(document, "4.8 The evidence guard", level=2)
    for text in DESIGN_GUARD:
        para(document, text)

    # ---- 5. Implementation ----------------------------------------------
    heading(document, "5. Implementation")
    heading(document, "5.1 Module structure", level=2)
    two_column_table(
        document, MODULES, headers=("Module", "Responsibility"), widths=(1.4, 4.5)
    )

    heading(document, "5.2 Implementation notes", level=2)
    para(
        document,
        "Four decisions are worth recording, because each was made in response "
        "to something that went wrong rather than in advance.",
    )
    for lead, text in IMPL_NOTES:
        para(document, text, lead=lead)

    # ---- 6. Testing ------------------------------------------------------
    heading(document, "6. Testing")
    heading(document, "6.1 Automated tests", level=2)
    para(
        document,
        f"The project has {TESTS_TOTAL} automated tests, all passing. They are "
        "summarised by area below; the complete run is kept with the source "
        "code in docs/test-report.txt.",
    )
    two_column_table(
        document,
        [(area, count, what) for area, count, what in TEST_AREAS],
        headers=("Area", "Tests", "What it checks"),
        widths=(1.5, 0.7, 3.7),
    )

    heading(document, "6.2 Tests that protect the design", level=2)
    para(
        document,
        "Three tests check the structure of the project rather than its "
        "behaviour. They exist because the design erodes quietly otherwise.",
    )
    for text in ARCHITECTURE_TESTS:
        bullet(document, text)

    heading(document, "6.3 Defects found and corrected", level=2)
    para(
        document,
        "The following defects were found during development and are recorded "
        "here rather than omitted, since a project that reports no failures is "
        "less credible than one that shows them.",
    )
    two_column_table(
        document,
        DEFECTS,
        headers=("Defect", "Effect", "Correction"),
        widths=(1.5, 2.4, 2.0),
    )

    # ---- 7. Results ------------------------------------------------------
    heading(document, "7. Results")
    for text in RESULTS:
        para(document, text)
    two_column_table(
        document, RESULT_TABLE, headers=("Result", "Observation"), widths=(1.6, 4.3)
    )

    heading(document, "7.1 A result not obtained", level=2)
    for text in RESULTS_HONEST:
        para(document, text)

    # ---- 8. Conclusion ---------------------------------------------------
    heading(document, "8. Conclusion and Future Scope")
    heading(document, "8.1 Conclusion", level=2)
    for text in CONCLUSION:
        para(document, text)

    heading(document, "8.2 Limitations", level=2)
    two_column_table(
        document, LIMITATIONS, headers=("Limitation", "Detail"), widths=(1.7, 4.2)
    )

    heading(document, "8.3 Future scope", level=2)
    para(document, "In the order in which it would be worth doing:")
    for text in FUTURE:
        numbered(document, text)

    # ---- references ------------------------------------------------------
    heading(document, "References")
    for text in REFERENCES:
        numbered(document, text)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    update_fields_on_open(document)
    document.save(out_path)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    build_flow(REPORT_DIR / "flow.png")
    build_architecture(REPORT_DIR / "architecture.png")
    build_er(REPORT_DIR / "er.png")

    written = build(args.out)
    try:
        shown = written.relative_to(REPO_ROOT)
    except ValueError:
        shown = written
    print(f"Wrote {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

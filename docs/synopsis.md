# RubriQ — Project Synopsis

**Rubric-driven, AI-assisted project review for PCCOE.**

| Field | Value |
|---|---|
| Student | Manthan Sankpal |
| PRN | 125M1H064 |
| Programme / Semester | MCA, Semester III |
| Course | Mini Project — MCA33EL03 |
| Guide | Prof. Dr. Anjana Arakerimath (HOD) |
| Evaluation | Minimum 2 reviews, 50 marks total |

---

## 1. Introduction

Every project-based course at PCCOE is assessed through a small number of
review milestones. A rubric exists for each of them, but it exists mostly on
the reviewer's side of the table: the student finds out what was expected of
them when they are told their mark.

RubriQ moves the rubric to the front of that sequence. Faculty author it,
publish it, and it becomes visible to the student *before* submission opens.
When work comes in, the system produces an evidence-backed **estimate** of the
mark against that same rubric — every criterion score citing a verbatim span
from the student's own document — which a faculty member then verifies,
adjusts where they disagree, and approves. Only after approval does anything
become a mark, and only after approval does the student see feedback.

The name is *rubric* + *IQ*. The ordering is deliberate: the rubric is the
authority, the intelligence is assistive.

## 2. Problem statement

Three problems, in the order they hurt:

1. **The rubric is invisible until it is too late to act on it.** A student
   cannot aim at a target they have not been shown, so the rubric functions as
   a justification for a mark rather than a specification for the work.
2. **Review marking is unevenly evidenced.** Two reviewers, or the same
   reviewer on a Friday afternoon, can score the same submission differently,
   and neither score carries a record of what in the document produced it.
3. **Late and absent are conflated.** A submission four days past the deadline
   and a submission that never arrived are administratively different things,
   but both tend to be recorded as a zero, which destroys the distinction the
   department's own policy depends on.

## 3. Objectives

| # | Objective |
|---|---|
| O1 | Let faculty author a rubric per review milestone, validate that its weights sum to 100, and publish it as an immutable version |
| O2 | Show the published rubric to the enrolled student **before** they upload anything |
| O3 | Accept versioned submissions (PDF / DOCX / TXT) and extract their text at upload time |
| O4 | Produce a per-criterion estimated score in which every score cites a verbatim span from the submission, or is marked `NO_EVIDENCE` |
| O5 | Apply late and absence policy as deterministic arithmetic, not as a judgement call |
| O6 | Require an explicit, named faculty approval before any mark is final, and record every override with a reason |
| O7 | Export an approved score sheet to Excel, and to a clipboard-pastable form, with identical numbers |
| O8 | Answer student questions about a milestone from its rubric alone, escalating to faculty rather than inventing an answer |
| O9 | Keep every mark traceable — who approved it, when, against which submission version and which rubric version |
| O10 | Allow project groups, but only where a faculty member has granted them |
| O11 | Accept a repository URL as part of a submission, only when it belongs to a GitHub account the guide already has on record |
| O12 | Let a faculty member mark one member of a granted group apart from it, with a recorded reason |

## 4. Proposed system

A single Streamlit application, backed by SQLite, split into two layers:

* **`core/`** — all domain logic as plain Python with **zero Streamlit
  imports**: authentication and role resolution, academics, rubric versioning,
  submissions, the deterministic scoring engine, the AI layer, exports, and
  the audit log. This is the part that is unit-tested, and the part that would
  survive replacing the interface.
* **`app/`** — a thin view layer of pages and components that calls `core/`
  and renders the result.

The separation is enforced by a test that greps `core/` for the string
`import streamlit` and fails if it finds one.

Scoring is split the same way the responsibility is: the language model reads
and judges, and **all arithmetic that decides a mark happens in Python**, in
one module, with a table-driven test behind it.

## 5. Scope

### In scope

* Google sign-in restricted to `@pccoepune.org`, with the role resolved
  server-side from a seeded faculty allow-list
* Subjects, project cycles, enrolment (including validated CSV import), and
  review milestones
* Rubric authoring with weight validation, publish-freezes-version semantics,
  and cloning a published rubric to a new draft
* Student submission with version history and server-side text extraction
* Project groups, requested by a student or formed by the guide, and
  active only once granted — a granted group submits once and every
  member shares the version, the sheet and the approval
* GitHub repository links, accepted only when owned by an account the
  faculty member recorded for that student or a granted group-mate
* AI evaluation against a published rubric, with a fuzzy-match evidence guard
  that demotes unverifiable claims to `NO_EVIDENCE`
* Deterministic late-penalty and absence policy
* A faculty review grid: per-criterion verdicts, evidence drawer, override
  with mandatory reason, single and bulk approval
* Excel (`.xlsx`) and TSV export, built from persisted score sheets
* A student assistant scoped to one milestone's published rubric, with
  escalation to a faculty inbox
* Post-approval student feedback showing what was and was not followed
* Reports: score distribution, weakest criterion, attendance mix
* An append-only audit log, surfaced in the interface

### Out of scope

Declared here so it is not ambushed in the viva:

* Plagiarism or similarity detection
* Executing, compiling, or testing student code
* A mobile application
* LMS / ERP integration
* Multi-institution tenancy
* Production cloud deployment with real student data
* Real-time collaborative editing
* Reels-style deep content analysis of images or video inside a submission
* **Fetching, cloning, or reading the contents of a linked repository.**
  A repository URL is recorded and shown; it is never downloaded. Marks
  come from evidence in the submitted document, because a span the
  guard cannot verify is not evidence

## 6. Technology

| Layer | Choice |
|---|---|
| Application | Streamlit ≥ 1.42, multipage via `st.navigation` |
| Authentication | `st.login()` / `st.user`, Google OIDC, `hd=pccoepune.org` |
| Database | SQLite via SQLAlchemy 2.0 (WAL, `busy_timeout`, `foreign_keys=ON`) |
| Migrations | Alembic |
| Validation | Pydantic v2 |
| File parsing | `pdfplumber`, `python-docx` |
| AI orchestration | LangGraph with `SqliteSaver` checkpointing |
| AI model | Google Gemini (`gemini-3.6-flash`) behind a one-method provider protocol |
| Evidence guard | `rapidfuzz.partial_ratio` |
| Export | `openpyxl` |
| Tests | `pytest` — 692 tests |

## 7. Expected outcome

A system that can be demonstrated end to end from a single command:

```
make seed && make run
```

producing a populated cohort in which a rubric is published, submissions
arrive on time and late and not at all, an evaluation runs, evidence is
verified, one criterion is demoted for want of evidence, penalties apply from
the policy table, a faculty member approves, and an Excel file falls out with
the same numbers as the screen.

The empirical result worth reporting is the **evidence rejection rate**: how
often the model cited something that is not actually in the student's
document, and was therefore refused. That number is what distinguishes this
from asking a chatbot to grade an essay.

## 8. Structure of the report

| Document | Covers |
|---|---|
| [`requirements.md`](requirements.md) | Functional and non-functional requirements, numbered and traceable |
| [`srs.md`](srs.md) | Assumptions, constraints, interfaces |
| [`design.md`](design.md) | Architecture, and an index of the diagrams |
| [`diagrams/`](diagrams/) | ER, DFD L0 and L1, use case, architecture, evaluation state machine |
| [`implementation.md`](implementation.md) | Module-wise write-up |
| [`test-cases.md`](test-cases.md) | Automated suite plus a manual test-case table |
| [`deployment.md`](deployment.md) | Local setup and the deployment question |
| [`limitations.md`](limitations.md) | Honest limits and future scope |

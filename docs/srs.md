# RubriQ — Software Requirements Specification

Companion to [`requirements.md`](requirements.md), which carries the numbered
requirements themselves. This document covers what surrounds them: what the
system assumes, what it is constrained by, and what it talks to.

---

## 1. Purpose and audience

This SRS describes a rubric-driven, AI-assisted review system for
project-based courses at PCCOE. It is written for the project guide, the
examiners at the two reviews, and whoever picks the code up afterwards.

## 2. Product perspective

RubriQ is a self-contained application. It is not a module of an existing LMS,
it does not synchronise with one, and it holds its own copy of the small
amount of academic data it needs (users, subjects, enrolments, milestones).
The only external service it depends on at runtime is the language-model API,
and it is designed to remain useful when that service is unavailable.

```
        ┌──────────────┐        ┌──────────────────┐
        │  Google      │        │  Gemini API      │
        │  OIDC        │        │  (optional)      │
        └──────┬───────┘        └────────┬─────────┘
               │ identity                │ evaluation
               ▼                         ▼
        ┌──────────────────────────────────────────┐
        │              RubriQ (one process)        │
        │   app/  ──calls──▶  core/  ──▶  SQLite   │
        └──────────────────────────────────────────┘
                              │
                              ▼
                    uploads/ (app-local files)
```

## 3. User classes

| Class | Who | Characteristics |
|---|---|---|
| Student | An enrolled MCA student | Sees only their own work. Cannot reach any faculty page — the page object is never constructed for their role |
| Faculty | A subject owner, seeded into the allow-list | Sees only subjects they own. Authors rubrics, approves marks, answers escalated questions |
| Admin | Reserved | Currently resolves to the same page set as Faculty. Kept as a distinct role so a future departmental view has somewhere to attach |

There is no self-registration and no role selection. A user's class is derived
server-side, on every request, from configuration.

## 4. Assumptions

| # | Assumption | If it turns out to be false |
|---|---|---|
| A1 | Every participant has an `@pccoepune.org` Google account | Nobody can sign in; the domain assertion is the gate |
| A2 | The faculty allow-list is maintained by whoever deploys the app | A faculty member is resolved as a student and sees no teaching pages |
| A3 | Submissions are text-bearing PDF, DOCX, or TXT | A scanned PDF extracts to little or nothing; the system stores it and says so, and the criteria fall to `NO_EVIDENCE` rather than being silently guessed |
| A4 | One faculty member reviews a cohort at a time | SQLite permits one writer at a time; simultaneous approval by two reviewers would serialise, and a genuine cohort submitting at once would contend. See [`limitations.md`](limitations.md) |
| A5 | The deadline is meaningful in IST | All lateness is computed on the `Asia/Kolkata` calendar date |
| A6 | The rubric is authored before submissions open | Evaluation requires a published rubric; without one the grid says so and stops |
| A7 | The language model may be slow, rate-limited, or absent | Everything deterministic still works; evaluation queues and is retryable (NFR-3) |

## 5. Constraints

### 5.1 Imposed by the brief

* **Streamlit only.** One process, one language, no separate API service, no
  frontend build.
* Two reviews, 50 marks. The build sequence is ordered so that Phase 4 is a
  complete demonstrable system on its own, and everything after it is an
  improvement rather than a prerequisite.

### 5.2 Imposed by Streamlit

| Constraint | Consequence in this design |
|---|---|
| The whole script reruns on every interaction | No work at module top level; state in `st.session_state`; database reads cached with an actor-scoped key |
| No URL routing or deep links | `st.navigation` with role-filtered page lists. "Share a link to this student's review" is out of scope |
| A long call blocks the session | Evaluation is chunked per submission inside `st.status`, and each result is persisted before the next begins |
| A rerun mid-run loses in-flight progress | The LangGraph `SqliteSaver` checkpoints per `thread_id`, so a refresh resumes at the last completed node |
| Client-side permission checks are weak | Scoping happens in SQL. A student's query never selects another student's row in the first place |

### 5.3 Self-imposed, and load-bearing

* **No Streamlit import inside `core/`.** Enforced by a test. This is what
  makes the domain testable and the view layer replaceable.
* **No LangGraph import outside `core/ai/`.** Graphs are an implementation
  detail of that package; callers see three plain functions.
* **The graph has no tools.** It receives rubric text and submission text and
  returns structured output. It cannot query the database, read a file, or
  search. Giving it tools would breach both the isolation and the
  identity-stripping requirements in one move.
* **No mark arithmetic outside `core/scoring/`.** Not in the UI, not in the
  exporters, not in the reports page.

## 6. External interfaces

### 6.1 User interface

Thirteen pages, built from a role-filtered list (`core/auth/pages.py`):

**Faculty** — Dashboard, Subjects, Rubric Builder, Calendar, Review Grid,
Query Inbox, Reports, Activity.
**Student** — Dashboard, Calendar, Submit, Feedback, Ask RubriQ.

The calendar and the rubric display are shared components called by both
roles, so the two sides cannot show different information about the same
milestone.

### 6.2 Google OIDC

| Item | Value |
|---|---|
| Mechanism | `st.login()` / `st.user`, configured under `[auth]` in `secrets.toml` |
| Client hint | `hd=pccoepune.org` — a convenience for the account chooser |
| Server-side check | The `email` claim's domain is asserted in `core/auth/domain.py`. The `hd` hint is **not** the check |
| Claims used | `email`, `name`. Nothing else is read or stored |

### 6.3 Language-model provider

| Item | Value |
|---|---|
| Interface | `LLMProvider` — a one-method Protocol in `core/ai/provider.py` |
| Default | Google Gemini, model from `[llm] model`, default `gemini-3.6-flash` |
| Alternate | Groq, implemented behind the same protocol; switching is a secrets change plus an install |
| Request | System prompt + rubric + de-identified submission text, `response_mime_type="application/json"` |
| Response | JSON conforming to `core/ai/schemas.py`; anything else triggers one repair attempt |
| Failure | Transient errors back off and retry; a hard failure marks the evaluation `FAILED` and is surfaced per row with a Retry |
| Absent key | The app reports that AI evaluation is unavailable; every deterministic path continues to work |

### 6.4 Database

SQLite through SQLAlchemy 2.0. Configured in `core/db/engine.py` with WAL
journalling, a busy timeout, `synchronous=NORMAL`, and `foreign_keys=ON` —
the defaults are not sufficient for even a single-process Streamlit app.
Schema changes ship as Alembic migrations in the same commit as the model
change.

Nothing outside `core/db/` knows the dialect, so changing engines is a URL
change.

### 6.5 File storage

Uploaded files are written under an app-local `uploads/` root, one directory
per submission version. Text is extracted at upload and stored in the
database, so no later stage — including the AI layer — reads a file.

### 6.6 Exports

| Format | Produced by | Notes |
|---|---|---|
| `.xlsx` | `openpyxl` | Frozen header row, per-criterion columns, second sheet carrying evidence and rationale |
| TSV | `core/exports/tsv.py` | Rendered with `st.code`, so the built-in copy button pastes into Excel or Sheets |

Both consume the same row builder over persisted score sheets, and a parity
test asserts the two cell grids are equal value for value.

## 7. Data requirements

The entities and their relationships are in [`diagrams/er.md`](diagrams/er.md).
Three properties matter more than the field list:

1. **Versioning is pinned, not inferred.** An `Evaluation` records the
   `submission_version` and `rubric_version` it ran against, and a
   `ScoreSheet` references a specific `evaluation_id`. Re-evaluating cannot
   silently change an approved mark.
2. **`verdict` is a stored column**, not something derived from the score at
   render time. It is what answers "what has the student followed, and what
   have they not".
3. **Nothing is hard-deleted.** Re-submission, re-evaluation, and rubric
   editing all create new versions.

## 8. Quality attributes

Covered as NFR-1 … NFR-12 in [`requirements.md`](requirements.md), each with
the test that proves it.

## 9. Glossary

| Term | Meaning |
|---|---|
| **Criterion** | One scoreable line of a rubric, with a weight and a maximum score |
| **Verdict** | `FOLLOWED` / `PARTIAL` / `NOT_FOLLOWED` / `NO_EVIDENCE` — what the submission did about a criterion |
| **Evidence span** | A verbatim quotation from the submission that justifies a criterion score |
| **Demotion** | Rewriting a criterion to `NO_EVIDENCE` with score 0 because its cited span could not be found in the submission |
| **Estimate** | A computed score sheet that no faculty member has approved. Never a mark |
| **Absent** | A status recorded when a submission is four or more days late. Not a mark of zero |
| **Reinstatement** | An explicit faculty decision to score an absent submission anyway, carrying a reason |
| **Thread id** | The deterministic key a graph run is checkpointed under: `eval:<submission_id>:<evaluation_version>` |

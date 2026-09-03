# CLAUDE.md — RubriQ

*Rubric-driven, AI-assisted project review for PCCOE.*
The name is rubric + IQ: the rubric stays the authority, the intelligence is assistive.

---

## 0. Context

| Field | Value |
|---|---|
| Student | Manthan Sankpal |
| PRN | 125M1H064 |
| Program / Sem | MCA, Semester III |
| Course | Mini Project — MCA33EL03 |
| Guide | Prof. Dr. Anjana Arakerimath (HOD) |
| Evaluation | Minimum 2 reviews, 50 marks total |
| Stack | **Streamlit only** (single Python app) |

**Pitch:** A domain-restricted Streamlit panel where PCCOE faculty define per-subject rubrics and review milestones, students submit work against them, and an AI layer produces an evidence-backed *estimated* score sheet that faculty verify, adjust, and export to Excel.

---

## 1. The Streamlit decision — read this first

Streamlit-only is a legitimate choice here and it will get you to a demo far faster. But it has real constraints, and the architecture below exists specifically to contain them.

**What Streamlit gives you:** one language, one process, no API layer, no CORS, no frontend build, native file upload, native dataframe editing, one-command deploy. For a two-review mini project, that is a large amount of removed risk.

**What it costs you, and the mitigation:**

| Constraint | Mitigation (already baked into this plan) |
|---|---|
| Whole script reruns on every interaction | All state in `st.session_state`; all DB reads through `@st.cache_data` with explicit invalidation; never do work at module top level |
| No URL routing or deep links | `st.navigation` with role-filtered page lists; accept that "share a link to this student's review" is out of scope |
| No native calendar widget | A sorted agenda table, shared by both roles (decision #3). No third-party component |
| Grid + detail drawer UX is awkward | `st.data_editor` for the grid, `st.dialog` for the evidence drawer. Do not attempt a custom component |
| Long AI calls block the session | Chunk into per-submission calls inside `st.status`, persist each result immediately so a refresh never loses work |
| Weak client-side permission story | **All scoping happens in SQL queries, never in the UI.** A student's query never selects another student's row in the first place |

**The one rule that keeps this reversible:** every piece of logic lives in `core/` as plain Python with zero Streamlit imports. `app/` is a thin view layer that calls `core/`. If Streamlit becomes the bottleneck, you swap the view layer and keep 80% of the codebase — and you can say exactly that in the viva when someone asks "why not a real web framework?"

---

## 2. Hard invariants — never violate these

If a task appears to require breaking one, stop and ask.

1. **AI never publishes a final mark.** It produces an *estimate* with evidence. A faculty member must explicitly approve or override before a score is final. Every published row carries `approved_by` and `approved_at`.
2. **Deterministic rules run in Python, not in the LLM.** Late penalties, absence thresholds, weight arithmetic, totals — pure functions with unit tests. The LLM is never asked to do arithmetic that decides marks.
3. **Every AI criterion score must cite evidence** — a verbatim span from the submission. No span means `NO_EVIDENCE`, not a number.
4. **Auth is restricted to `@pccoepune.org`**, verified server-side from the OIDC email claim. The `hd` hint passed to Google is a convenience, not the check.
5. **Role is assigned server-side** from a seeded faculty allow-list. A user can never self-select "faculty".
6. **Students never see another student's data.** Enforced in the query layer with a mandatory `actor` argument, not by hiding UI.
7. **Nothing is hard-deleted.** Submissions, evaluations and overrides are append-only and versioned. Re-evaluating creates a new version.
8. **The AI never receives identity data.** Strip name/PRN before the call; send submission text + rubric only. Reattach after.
9. **No Streamlit imports inside `core/`.** Ever. This is the load-bearing rule of the whole design.
10. **Offline degradation.** If the LLM is unreachable, everything else still works — deterministic penalties, manual scoring, calendar, exports. AI evaluation queues as `PENDING` and is retryable.

---

## 3. Tech stack

| Layer | Choice | Why |
|---|---|---|
| App | Streamlit ≥ 1.42 | Single-process, multipage via `st.navigation`; 1.42 is the floor for native OIDC |
| Auth | `st.login()` / `st.user` with Google OIDC | No password handling; `hd=pccoepune.org` as client kwarg + server-side email-domain assertion |
| DB | **SQLite** via SQLAlchemy 2.0 | Decision #8. No server to install, no credentials, and the database is a file you can copy into the report appendix. Configured with WAL + `busy_timeout` + `foreign_keys=ON` in `core/db/engine.py` — the defaults are not enough for a multi-user Streamlit app. Swapping engines later is a URL change because nothing outside `core/db/` knows the dialect |
| Migrations | Alembic | Migration history is an SDLC artifact — do not skip it |
| Validation | Pydantic v2 | AI response schema enforcement |
| File parsing | `pdfplumber`, `python-docx` | Text extraction at upload time |
| AI orchestration | **LangGraph** (+ `langgraph-checkpoint-sqlite`) | The evaluation flow is genuinely a graph with conditional retry edges; the checkpointer also solves Streamlit's rerun-loses-progress problem. `SqliteSaver`, not `PostgresSaver` — see §6.2 |
| AI model | **Gemini** (`gemini-2.0-flash`) behind `core/ai/provider.py` | Decision #4. Groq stays implemented behind the same one-method protocol, so switching is config plus an install. Never import an SDK outside this module |
| Export | `openpyxl` | Real `.xlsx`, not a CSV rename |
| Calendar | Agenda table in `app/components/calendar.py` | Decision #3. No dependency; both roles call one function |
| Tests | `pytest` | Testing `core/` is easy precisely because it has no Streamlit in it |

**Do not add:** Celery, Redis, Docker orchestration, custom React components, a separate FastAPI service, a vector store, or LangChain retrievers/agents/tools. LangGraph is in for orchestration only — pulling in the wider LangChain ecosystem is how this project doubles in size without getting better.

---

## 4. Domain model

```
User (email PK, role: STUDENT|FACULTY|ADMIN, name, department, prn?, employee_id?)

Subject (code, name, semester, owner_email → User)
  └── Enrollment (student_email, subject_id, batch, group_label?)

ProjectCycle (subject_id, title, academic_year)
  ├── ReviewMilestone (cycle_id, index, title, description,
  │                    due_at, max_marks, is_visible)
  │     └── Rubric (milestone_id, version, published_at)     ← immutable once published
  │           └── Criterion (rubric_id, code, title, description,
  │                          weight, max_score, expected_evidence, is_mandatory)
  │
  └── Submission (milestone_id, student_email, submitted_at,
                  files[], text_extract, version, status)
        └── Evaluation (submission_id, version, engine: AI|MANUAL, status,
                        model_name, prompt_version, raw_response JSON, created_at)
              └── CriterionScore (evaluation_id, criterion_id, score, confidence,
                                  evidence_span, verdict, rationale)

ScoreSheet (submission_id, base_total, penalty, final_total, attendance_status,
            approved_by, approved_at, faculty_note)
  └── ScoreOverride (score_sheet_id, criterion_id, old, new, reason, by, at)

LatePolicy (scope: SUBJECT|MILESTONE, scope_id, rules JSON, version)

StudentQuery (student_email, milestone_id?, question, ai_answer, sources[],
              escalated: bool, faculty_reply?, replied_by?, replied_at?)

AuditLog (actor_email, action, entity, entity_id, payload JSON, at)
```

**Notes**
- `verdict ∈ {FOLLOWED, PARTIAL, NOT_FOLLOWED, NO_EVIDENCE}` is a first-class column — it powers the "what the student **has** vs **has not** followed" view the requirement asks for. Do not derive it from the score at render time.
- `Rubric` is versioned. Editing a published rubric creates v+1 so already-graded submissions stay valid.
- `text_extract` is populated at upload so the AI layer never touches files.
- `AuditLog` exists because Streamlit gives you no request log worth reading. Every mutation writes one row.

---

## 5. Scoring engine — deterministic core

`core/scoring/engine.py`. Pure functions, zero DB access, fully unit-tested.

```python
base_total = Σ (score / criterion.max_score) * criterion.weight
```

### 5.1 Late & absence policy

Default, overridable per subject or milestone via `LatePolicy.rules`:

| Days late (calendar days past `due_at`) | Outcome |
|---|---|
| 0 | No penalty |
| 1 | −10% of milestone max marks |
| 2 | −20% |
| 3 | −35% |
| 4–5 | **ABSENT** — recorded 0, submission still stored and evaluated for feedback |
| > 5 | **ABSENT**, needs explicit faculty reinstatement to be scored at all |

Rules:
- Penalty applies to the milestone total, never to individual criteria.
- `final_total = max(0, base_total − penalty)`. Never negative.
- Absence is a **status**, not a zero. Reports must distinguish "absent" from "attempted, scored 0".
- Days-late computed on `date` in `Asia/Kolkata` — makes the 11:59 PM boundary unambiguous and easy to demonstrate.
- Faculty reinstatement zeroes the penalty, requires a reason, writes an `AuditLog` row.

Write a table-driven test covering every row above **before** any UI touches this.

---

## 6. AI layer (LangGraph)

### 6.1 Boundary

`core/ai/` is the only place any LLM SDK or LangGraph import may appear. Everything outside it calls three plain Python functions:

```python
evaluate_submission(rubric: RubricDTO, text: str, thread_id: str) -> EvaluationResult
answer_student_query(question: str, context: QueryContext, thread_id: str) -> QueryAnswer
summarise_feedback(scores: list[CriterionScoreDTO]) -> str
```

These are **synchronous wrappers** over compiled LangGraph graphs. Callers never see a graph, a state dict, or a checkpointer. If you ever need `graph.invoke()` outside `core/ai/`, the boundary has leaked — fix it rather than working around it.

### 6.2 Why LangGraph here (and where it must not go)

LangGraph earns its place for exactly two reasons, and you should be able to say both in the viva:

1. **The evaluation flow has real conditional edges.** Parse → validate schema → verify evidence → repair-and-retry → aggregate is a state machine with two failure loops, not a linear chain. Expressing it as a graph makes the retry policy explicit and inspectable instead of buried in nested `try/except`.
2. **Checkpointing solves a Streamlit problem.** `SqliteSaver` persists graph state per `thread_id`. When Streamlit reruns the script mid-evaluation, the graph resumes from its last completed node instead of restarting. This is the cleanest available answer to Streamlit's biggest weakness in this app. Keep the checkpointer's database file separate from `rubriq.db` so a corrupt graph checkpoint can be deleted without touching a single mark.

**Where LangGraph must not go — non-negotiable:**

- **Never inside `core/scoring/`.** Penalties, weights and totals stay pure functions. If a graph node ever computes a mark, invariant #2 is broken.
- **Never as an "agent with tools" that can query the database.** The graph receives rubric + submission text as input and returns structured output. It has no DB access, no file access, no search. Giving it tools would break invariants #6 and #8 in one move.
- **Never for CRUD flows.** Subjects, rubrics, submissions and exports are ordinary service functions. Do not graph-ify them because the dependency is already installed.

### 6.3 Evaluation graph

`core/ai/graphs/evaluation.py`

```
                    ┌──────────────┐
                    │   prepare    │  strip identity, chunk rubric,
                    └──────┬───────┘  build criterion batches
                           ▼
                    ┌──────────────┐
              ┌────▶│   evaluate   │  LLM call for one criterion batch
              │     └──────┬───────┘
              │            ▼
              │     ┌──────────────┐
              │     │ parse_schema │  Pydantic validation
              │     └──────┬───────┘
              │       fail │  ok
              │     ┌──────┴───────┐
              └─────│    repair    │  repair prompt, max 1 attempt
       (≤1 retry)   └──────┬───────┘
                    fail   │
                     │     ▼
                     │  ┌──────────────────┐
                     │  │ verify_evidence  │  rapidfuzz ≥ 90 against text_extract
                     │  └──────┬───────────┘
                     │    fail │  ok
                     │  ┌──────┴───────────┐
                     │  │ demote_criterion │  → NO_EVIDENCE, score 0, log rejection
                     │  └──────┬───────────┘
                     │         ▼
                     │  ┌──────────────┐
                     └─▶│   aggregate  │  assemble EvaluationResult
                        └──────┬───────┘   (arithmetic happens OUTSIDE, in scoring)
                               ▼
                            [ END ]
```

State:

```python
class EvalState(TypedDict):
    rubric: RubricDTO
    text: str
    batches: list[list[CriterionDTO]]
    cursor: int
    raw_responses: list[dict]
    parsed: list[CriterionResult]
    rejections: list[EvidenceRejection]
    repair_attempts: int
    status: Literal["RUNNING", "COMPLETE", "FAILED"]
```

Rules:
- `repair_attempts` is capped at 1 per batch. On second failure the batch resolves to `NO_EVIDENCE` for its criteria and the run continues — one bad batch never fails the whole submission.
- `demote_criterion` is the anti-hallucination guard from §6.5. It is a graph node, not a post-processing step, so rejections are checkpointed and visible.
- `aggregate` produces verdicts and per-criterion raw scores only. **It does not compute totals.** `core/scoring/engine.py` does that afterwards, from the persisted rows.
- `thread_id = f"eval:{submission_id}:{evaluation_version}"` — deterministic, so a resumed run is provably the same run.

### 6.4 Query graph

`core/ai/graphs/query.py` — smaller, but the routing is the point:

```
classify ──▶ in_scope? ──yes──▶ answer ──▶ confidence_check ──▶ END
                │                                  │ low
                no                                 ▼
                └──────────────▶ escalate ◀────────┘
```

- `classify` decides whether the question is answerable from the rubric context alone.
- `escalate` returns a `QueryAnswer` with `escalated=True` and no invented answer — the faculty inbox picks it up.
- Uses `MemorySaver` per chat session so follow-up questions keep context within one milestone. Session memory is **never** persisted across milestones or shared between students.

### 6.5 Response contract & guards

`core/ai/schemas.py` and `core/ai/guards.py`. Unchanged by LangGraph — the graph calls these, it does not replace them.

```json
{
  "criteria": [
    {
      "code": "C1",
      "verdict": "FOLLOWED | PARTIAL | NOT_FOLLOWED | NO_EVIDENCE",
      "score": 0,
      "max_score": 0,
      "confidence": 0.0,
      "evidence": "verbatim span from the submission, max 40 words",
      "rationale": "one plain-language sentence"
    }
  ],
  "overall_observations": ["..."],
  "missing_items": ["..."]
}
```

- System prompt: return **only** JSON, no prose, no code fences.
- `NO_EVIDENCE` forces `score = 0` **and** flags the criterion for mandatory faculty attention.
- **Anti-hallucination guard:** reject any `evidence` that doesn't fuzzy-match (`rapidfuzz.partial_ratio ≥ 90`) into `text_extract`. Log every rejection. The rejection rate is your strongest empirical result and belongs in the report.
- Store `raw_response` verbatim in the JSON column whatever happens.
- Tag every `Evaluation` with `prompt_version` **and** `graph_version` so results are reproducible.

### 6.6 Running it inside Streamlit

Stream graph node transitions into `st.status` so the demo shows the machine thinking, not a frozen spinner:

```python
with st.status("Evaluating submissions…", expanded=True) as status:
    for sub in pending:
        st.write(f"**Submission v{sub.version}**")
        for node, _ in stream_evaluation(sub):      # yields node names
            st.write(f"  · {node}")
        persist(sub)                                 # commit per submission
    status.update(label="Done", state="complete")
```

- Persist after **every** submission, not at the end of the loop.
- On re-entry after a refresh, resume by `thread_id`; the checkpointer skips completed nodes. Verify this manually in Phase 5 — refresh the browser mid-run and confirm no duplicate LLM calls in the log.
- `stream_evaluation` is a generator in `core/ai/` that yields plain strings. Streamlit still never touches a graph object.

### 6.7 Student query assistant — scope rules

- Context = published rubric for that milestone + milestone description + faculty public notes. **Nothing else.**
- Never sees other students' work, scores, or unpublished rubrics.
- If the answer isn't in context, it escalates. It does not invent policy.
- Never predicts a mark. "What will I score?" → redirect to the rubric criteria.
- Direct context stuffing, no vector store. Only reach for embeddings if a subject's notes actually overflow the context budget.

## 7. Faculty review grid (the core requirement)

Rendered with `st.data_editor`, one row per student per milestone:

| PRN | Name | Submitted | Days Late | Status | C1 | C2 | C3 | … | Base | Penalty | Final | Conf. | Approved |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

- Criterion columns use `column_config` with verdict-based text (`✓ / ~ / ✗ / ?`) plus a colour-coded `Styler` on a read-only preview.
- Row selection opens an `st.dialog` drawer showing the evidence span, rationale, and an override input that **requires a reason**.
- Computed columns (`Base`, `Penalty`, `Final`) are `disabled=True` in the editor — they are never hand-edited, only recomputed from criterion scores.
- "Approve all rows above confidence X" bulk action, showing the affected count before confirming.
- **Two export paths, both required:**
  - `st.code(tsv_string)` → the built-in copy button pastes cleanly into Excel/Sheets.
  - `st.download_button` → real `.xlsx` from `openpyxl`, frozen header row, per-criterion columns, second sheet with evidence + rationale text.
- Filename: `RubriQ_<SubjectCode>_Review<N>_<YYYYMMDD>.xlsx`

---

## 8. Pages (`st.navigation`)

Build the page list from `st.user` role. A student's page objects are never constructed.

**Faculty**
1. `Dashboard` — owned subjects, upcoming due dates, pending-approval count
2. `Subjects` — create subject, enroll students (CSV upload), manage cycles
3. `Rubric Builder` — criteria, weights, max scores, expected evidence, mandatory flag; live "weights must sum to 100" validation; publish button that freezes the version
4. `Calendar` — milestones across subjects
5. `Review Grid` — §7. The centrepiece; demo this first in both reviews
6. `Query Inbox` — escalated student questions
7. `Reports` — score distribution, criterion-level weak-spot chart

**Student**
1. `Dashboard` — my subjects, next deadline with countdown, submission status chips
2. `Calendar` — read-only, own milestones only
3. `Submit` — rubric shown **before** upload (this is the entire point of the system), file upload, version history
4. `Feedback` — post-approval only: followed / not followed per criterion, plus faculty note
5. `Ask RubriQ` — chat scoped to one milestone, with an escalate button

Calendar and rubric-display are shared functions in `app/components/`, called by both roles. Write once.

---

## 9. Repo structure

```
rubriq/
├── CLAUDE.md                  ← this file
├── Makefile                   ← run, test, seed, migrate, lint
├── requirements.txt           ← one-line "why" comment per dependency
├── .env.example
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example   ← OIDC client id/secret, DB URL, LLM key
├── docs/
│   ├── synopsis.md
│   ├── srs.md
│   ├── diagrams/              ← ER, DFD L0/L1, use-case, sequence
│   ├── test-cases.md
│   └── report/
├── core/                      ← ZERO streamlit imports. This is the rule.
│   ├── db/                    ← engine, session, models.py
│   ├── auth/                  ← domain assertion, role resolution
│   ├── academics/             ← subject, enrollment, milestone services
│   ├── rubrics/               ← rubric versioning, weight validation
│   ├── submissions/           ← storage, text extraction, versioning
│   ├── scoring/               ← engine.py (pure), policy.py, sheets.py
│   ├── ai/                    ← the ONLY place langgraph/LLM SDKs may be imported
│   │   ├── provider.py        ← sync wrappers; the public face of this package
│   │   ├── graphs/            ← evaluation.py, query.py, state.py
│   │   ├── checkpoint.py      ← SqliteSaver setup, thread_id helpers
│   │   ├── prompts/           ← versioned, one file per prompt
│   │   ├── schemas.py         ← Pydantic response models
│   │   └── guards.py          ← evidence verification, rejection logging
│   ├── queries/
│   ├── exports/               ← xlsx.py, tsv.py
│   └── audit.py
├── app/                       ← thin Streamlit view layer
│   ├── main.py                ← auth gate + st.navigation
│   ├── pages/
│   │   ├── faculty/
│   │   └── student/
│   ├── components/            ← calendar, rubric_view, review_grid, dialogs
│   └── state.py               ← session_state keys, cache invalidation helpers
├── alembic/
├── scripts/
│   └── seed_demo.py
└── tests/                     ← tests/core/** mirrors core/**
```

---

## 10. Build sequence

Ordered so **Phase 4 is a complete, demonstrable Review 1** and **Phase 7 is Review 2**. Don't start a phase until the previous one's exit criteria pass.

### Phase 0 — Foundation
- Streamlit app boots, SQLite connection, Alembic initialised, settings from `st.secrets`
- `core/` package with the no-Streamlit rule enforced by a test that greps for the import
- `pytest` wired, one passing smoke test
- **Exit:** `make run` serves a hello page; `make test` green; the no-Streamlit-in-core test exists and passes

### Phase 1 — Auth & roles
- `st.login()` with Google OIDC, `hd` client kwarg
- Server-side domain assertion in `core/auth/` — non-pccoe email is rejected with a clear message even if Google lets it through
- Faculty allow-list seeded by a management script; role resolution on first login
- `st.navigation` builds role-filtered page lists
- **Exit:** a personal Gmail account is rejected; a student session cannot construct or reach any faculty page (proved by a test on the page-list builder, not by clicking around)

### Phase 2 — Subjects, enrollment, calendar
- Subject + Enrollment CRUD, CSV student import
- Milestone CRUD; calendar component (decide `streamlit-calendar` vs agenda table here and record it)
- **Exit:** faculty creates a subject with two milestones; the enrolled student sees exactly those two and nothing else

### Phase 3 — Rubrics & submissions
- Rubric/Criterion CRUD, weight-sum validation, publish freezes version
- Student upload, text extraction (PDF/DOCX/TXT), submission versioning
- Rubric rendered to the student **before** they submit
- **Exit:** a published rubric cannot be edited in place; a re-upload creates v2 and v1 is still retrievable

### Phase 4 — Deterministic scoring ⟵ **REVIEW 1 DEMO**
- `core/scoring/engine.py` with the full §5.1 test table passing
- Manual scoring UI, review grid rendering, ScoreSheet + approval
- TSV copy + `.xlsx` download working
- **Exit:** full manual round trip — rubric → student submits 2 days late → faculty scores → 20% penalty applied → exported to Excel and opened. **This alone is a passing project.** Everything after is upside.

### Phase 5 — AI evaluation (LangGraph)
Split into two sub-phases. Do not build the graph first.

**5a — logic before orchestration**
- `core/ai/schemas.py`, `core/ai/guards.py`, prompt v1
- A single direct LLM call, no graph, proving the response contract and the evidence guard work
- Unit tests for the guard using fixture responses, including a deliberately hallucinated one
- **Exit:** guard correctly rejects fabricated evidence on a fixture, with no LangGraph installed yet

**5b — graph, checkpointing, UI**
- `core/ai/graphs/evaluation.py` per §6.3, `SqliteSaver` wired, `thread_id` scheme
- `stream_evaluation` generator; `st.status` runner with per-submission persistence
- Evidence dialog, override-with-reason, approval workflow, `FAILED` state surfaced
- **Exit:** run over 10 seeded submissions; refresh the browser mid-run and confirm the resumed run makes **no duplicate LLM calls**; rejection count logged and reportable; every score traces to a span in the source text

If 5b runs into trouble, 5a alone still gives you working AI evaluation — the graph is an upgrade to an already-functioning path, not a prerequisite.

### Phase 6 — Student assistant & feedback
- Scoped query context, escalation, faculty reply
- Student feedback view gated on approval
- **Exit:** the assistant correctly refuses an out-of-scope question and offers escalation instead of guessing

### Phase 7 — Reports & hardening ⟵ **REVIEW 2 DEMO**
- Distribution and weak-criterion charts
- Empty states, spinners, error handling on every DB and AI call
- `make seed` produces a realistic demo dataset in one command
- SDLC document set finalised (§11)
- **Exit:** clone → `make seed && make run` → a populated, browsable system, no manual setup

---

## 11. SDLC deliverables checklist

The guidelines demand all SDLC components. These are tasks, not afterthoughts.

- [ ] **Synopsis** — introduction, objectives, problem statement, scope with explicit in/out lists
- [ ] **Requirement analysis** — functional + non-functional, numbered and traceable
- [ ] **SRS** — assumptions, constraints, interfaces
- [ ] **Design** — ER diagram, DFD L0 & L1, use-case diagram, architecture diagram showing the `core/` ↔ `app/` split, **and the evaluation state-transition diagram from §6.3** (this replaces a plain sequence diagram and is a stronger artifact — state machines with retry loops read well in a report)
- [ ] **Implementation** — module-wise write-up; if this becomes a group project, the `core/` module boundaries are already your independent-module split
- [ ] **Testing** — pytest report + a manual test-case table with expected vs actual
- [ ] **Deployment** — local setup guide; note Streamlit Community Cloud as the deployment path and why it wasn't used for real data
- [ ] **Report** — institute template
- [ ] **Limitations & future scope** — be honest about AI confidence limits and Streamlit's single-process ceiling

**Declare out of scope in the synopsis** so it isn't ambushed in the viva: plagiarism detection, executing/compiling student code, mobile app, LMS integration, multi-institution tenancy, production cloud deployment, real-time collaborative editing.

---

## 12. Working rules for the agent

- **Read this file before every task.** If a request contradicts §2, stop and ask.
- **Check §14 before declaring a phase done.** Every P0 item that phase touched must be closed, with its named test passing, before you move on.
- One phase at a time. Do not scaffold Phase 5 while working on Phase 2.
- **Never import `streamlit` inside `core/`.** If you need config or user identity there, pass it in as an argument.
- **Never import `langgraph` outside `core/ai/`.** Graphs are an implementation detail of that package.
- Do not add a graph node that touches the database, the filesystem, or does mark arithmetic.
- Every service function takes an explicit `actor: User` and scopes its query by it. No implicit "current user".
- Every model change ships with its Alembic migration in the same commit.
- Every pure function in `core/scoring/` and every guard in `core/ai/` ships with tests in the same commit.
- Wrap every mutation in a transaction and write one `AuditLog` row.
- Cache DB reads with `@st.cache_data` in `app/`, never in `core/`; invalidate explicitly after mutations.
- No secrets in code. Keep `.streamlit/secrets.toml.example` current.
- Prefer boring, readable code. This gets read aloud in a viva.
- Commit format: `phase<N>: <module>: <what>`.

---

## 13. Open decisions

| # | Decision | Options | Status |
|---|---|---|---|
| 1 | Project title | — | ✅ **RubriQ** |
| 2 | Stack | — | ✅ **Streamlit only** |
| 3 | Calendar widget | `streamlit-calendar` vs agenda table | ✅ **Agenda table** — decided in Phase 2. The calendar is a supporting page, not the centrepiece, so a third-party FullCalendar wrapper is dependency risk spent in the wrong place. An agenda also answers the question students actually have ("when is my next deadline" is a sorted list, not a month grid), and sorting soonest-first makes lateness legible before it matters (fix item 10). Both roles call one function in `app/components/calendar.py`, so swapping it later touches one file. Reason recorded in that module's docstring. |
| 4 | LLM provider | Gemini vs Groq | ✅ **Gemini** — decided in Phase 5a. Both are implemented behind the one-method `LLMProvider` protocol in `core/ai/provider.py` with their SDKs imported lazily, so switching is a `secrets.toml` change plus a `pip install`, not a code change. Model: `gemini-2.0-flash`, with `response_mime_type="application/json"` set so the §6.5 contract is enforced by the API as well as by the Pydantic schema. The key lives only in gitignored `.streamlit/secrets.toml`; with no key configured the app says AI evaluation is unavailable and everything deterministic still works (invariant #10). |
| 4b | Criterion batching | one LLM call per criterion vs batched | start batched (cheaper, fewer rate-limit hits); split only if per-criterion accuracy is visibly worse |
| 5 | Individual or group | solo vs modular split | affects §11 module-ownership section |
| 6 | Submission types | PDF/DOCX only, or also GitHub URL | PDF/DOCX for Phase 3; URL is a Phase 7 stretch |
| 7 | Guide approval | title + synopsis sign-off from Dr. Arakerimath | **do before Phase 1** |
| 8 | Database engine | PostgreSQL 16 vs SQLite | ✅ **SQLite** — decided during Phase 2, superseding §3's original choice. Postgres bought real concurrency and JSONB, neither of which this project needs: a single-guide review panel has no write contention worth a server, and every JSON column is read by primary key rather than searched by content. Against that, it cost an install, a service, and credentials on every machine the project has to run on — including whichever one the viva happens on. SQLite makes the database a file that can be copied, inspected, and shipped with the report. The engine is tuned rather than left on defaults (WAL, `busy_timeout`, `foreign_keys=ON`); see `core/db/engine.py`. **Limits, stated honestly:** one writer at a time, so this would not survive a real cohort submitting simultaneously — that belongs in §11's limitations, not hidden. Reversing it is a URL change plus reinstating `psycopg`, because nothing outside `core/db/` knows the dialect. |

---

## 14. Fix priority order

Nothing is built yet, so these are not bug reports. They are the **defect classes this design is most likely to produce**, pre-registered and ranked. Each one names how it breaks, what closes it, and the check that proves it closed.

**The rule:** a phase does not exit with an open P0 that its own code created. A P1 may cross one phase boundary if it is written down. P2 collects in Phase 7.

**Do not fix upward.** If a P2 fix (a nicer grid, a cache tweak) would touch scoring, approval, or scoping code, it stops being P2 — reopen the P0 item it belongs to and do it there.

### Where each item lands

| # | Item | Guards | Owning phase | Proof lives in |
|---|---|---|---|---|
| 1 | Score/penalty integrity | inv #2 | 4 | `tests/core/scoring/test_engine.py` |
| 2 | Submission/evaluation versioning | inv #7 | 3 (schema) → 4/5b (enforced) | `tests/core/submissions/test_versioning.py` |
| 3 | Student/faculty isolation | inv #4, #5, #6 | 1–2 | `tests/core/test_actor_contract.py` |
| 4 | Approval/override integrity | inv #1 | 4 | `tests/core/scoring/test_sheets.py` |
| 5 | AI evidence validation | inv #3, #8 | 5a | `tests/core/ai/test_guards.py` |
| 6 | Rubric immutability | §4 note | 3 | `tests/core/rubrics/test_versioning.py` |
| 7 | Enrollment/import validation | — | 2 | `tests/core/academics/test_import.py` |
| 8 | Faculty review workflow clarity | — | 4, extended 5b | manual test-case table |
| 9 | AI failure/retry | inv #10 | 5b | provider-stub test |
| 10 | Submission-status clarity | §5.1 | 4 | shared-renderer test |
| 11 | Export consistency | §7 | 4 | `tests/core/exports/test_parity.py` |
| 12 | Review-grid readability | — | 7 | manual |
| 13 | Empty/error states | — | 7 | manual checklist |
| 14 | Session/cache invalidation | §1 | 1 (keying) → 7 (rest) | see item |
| 15 | Audit/history presentation | §4 note | 7 | manual |

---

### P0 — correctness/security

A P0 defect here produces a **wrong mark on a real student's record**, or shows one student another student's work. Neither is recoverable by an apology in the viva.

#### 1. Score/penalty calculation integrity

**Breaks as:** penalty subtracted per-criterion instead of from the milestone total. Weights that don't sum to 100, so `base_total` is silently not out of `max_marks`. `days_late` computed from a UTC timestamp, so an 11:45 PM IST submission counts as next-day late. Float drift rendering 19.999999. The grid displaying a recomputed number that disagrees with the stored `ScoreSheet`.

**Fix:** one entry point — `compute_score_sheet(criterion_scores, criteria, policy, due_at, submitted_at) -> ScoreSheetDTO`. Nothing outside `core/scoring/` does mark arithmetic, including the UI, the exporters, and the reports page. `days_late` derives from `date` in `Asia/Kolkata` on both sides. Round once, at the persistence boundary, half-up. `final_total = max(0, base_total − penalty)` is asserted, not assumed.

**Proof:** the §5.1 table driven row by row, plus boundary rows — exactly `due_at`, 23:59:59 IST on the due date, 00:00:01 the next day, and the 3 → 4 day ABSENT transition. Plus a round-trip test: `stored.final_total == compute_score_sheet(persisted_rows).final_total`.

#### 2. Submission/evaluation version consistency

**Breaks as:** the student uploads v2 while faculty is mid-grade on v1, and the approval lands on whichever row the query happened to return. A `ScoreSheet` points at `submission_id` with no evaluation version, so re-evaluating silently changes an approved mark. `CriterionScore` rows reference criteria from a rubric that has since moved to v2.

**Fix:** every evaluation pins its inputs — `Evaluation(submission_id, submission_version, rubric_version)`. `ScoreSheet` references a specific `evaluation_id`, never a bare submission. Unique constraint on `(submission_id, version)` and on `(submission_id, evaluation_version)`. The grid shows a stale banner when a newer submission version exists than the one being graded, and approving a non-latest evaluation requires explicit confirmation.

**Proof:** submit v1 → evaluate → submit v2 → assert the v1 evaluation is still retrievable, still bound to v1's text, and that approving it is either blocked or flagged. Never silently rebound.

#### 3. Student/faculty data isolation

**Breaks as:** a service function that forgot its `actor`. A query that fetches all rows and filters in pandas afterwards — the data already left the database, so the invariant is already broken. Faculty seeing a subject they don't own. A role cached in `session_state` at login and never re-derived.

**Fix:** `actor: User` is the first positional argument of every public function in `core/`, and scoping happens in the `WHERE` clause. Role resolves server-side from the allow-list on each rerun, never from client-held state. Domain assertion re-runs at the auth gate, not once per session.

**Proof:** a reflection test over `core/**` that fails any public service function whose signature lacks `actor`. Plus negative tests — student A requesting student B's submission raises `NotAuthorized`; faculty X listing subject Y's grid gets zero rows; a `@gmail.com` claim is rejected server-side even with a valid Google token.

#### 4. Approval/override integrity

**Breaks as:** approval writes `final_total` but not `approved_by` / `approved_at`, so invariant #1 becomes unprovable. An override changes a criterion score and the total is never recomputed. Approval succeeds on an evaluation still `RUNNING`. Re-approval overwrites the first approval with no history. The bulk "approve above confidence X" sweeps up rows with mandatory criteria sitting at `NO_EVIDENCE`.

**Fix:** approval is one transaction — recompute → write `ScoreSheet` → stamp `approved_by`/`approved_at` → write `AuditLog`, all or nothing. Overrides are append-only `ScoreOverride` rows carrying old, new, reason, actor, timestamp; an empty or whitespace-only reason is rejected in `core/`, not merely marked required on the widget. Approval is blocked while any mandatory criterion is unresolved or the evaluation is not `COMPLETE`. The bulk action excludes ineligible rows and **shows the excluded count before confirming**, not after.

**Proof:** approving a `RUNNING` evaluation raises. An override with `reason=""` raises. After an override, the stored `final_total` equals a fresh recompute. Two sequential approvals produce two audit rows and never mutate the first.

#### 5. AI evidence validation

**Breaks as:** the guard normalises a string, matches on it, and stores the normalised version — so the "verbatim span" isn't verbatim. PDF extraction inserts soft hyphens and line breaks, the fuzzy match fails on genuine evidence, and the rejection rate becomes noise instead of a result. The guard is skipped when confidence is high. `NO_EVIDENCE` arrives with a nonzero score. The student's name and PRN ride along inside `text_extract` into the prompt.

**Fix:** the guard is the **only** path to persisting a `CriterionScore` — there is no bypass branch, at any confidence. Normalise both sides identically (collapse whitespace, casefold, strip hyphenation) for comparison; store the model's original span untouched. `NO_EVIDENCE ⇒ score == 0` is a Pydantic validator, so it cannot be enforced in the UI and skipped in a batch run. Identity is stripped in `prepare`, before the first token leaves the process.

**Proof:** a fixture with fabricated evidence is rejected; a fixture with real-but-reflowed evidence is accepted. A fixture whose `text_extract` contains the PRN pattern and the student's name asserts neither appears in the outgoing prompt. Every rejection is logged with the fabricated span — that log is §6.5's empirical result, so losing it costs you a report section.

#### 6. Rubric immutability

**Breaks as:** a published rubric edited in place, retroactively changing what already-graded submissions were graded against. Publishing without the weight-sum check. Deleting a criterion that `CriterionScore` rows still reference. A submission evaluated against an unpublished draft.

**Fix:** `published_at IS NOT NULL` makes the rubric and its criteria read-only at the service layer — edits clone to v+1, and the new version starts unpublished. Publish is the only transition into the frozen state and validates Σweight == 100 with at least one criterion. Only published rubrics are selectable for evaluation. Nothing is deleted (inv #7); criteria are deactivated on the new version instead.

**Proof:** update and delete against a published rubric both raise. Publishing with weights summing to 95 raises. Editing a published rubric yields v2 while v1 stays byte-identical and still resolves for its graded submissions.

---

### P1 — management usability

These don't corrupt data. They make the system untrustworthy to operate, which in a live review reads the same.

#### 7. Enrollment/import validation

**Breaks as:** a 40-row CSV imports 31 rows and reports success. A typo'd email creates a ghost enrollment nobody can ever log in as. Duplicate PRNs. Non-`@pccoepune.org` addresses enrolled. Re-running the import doubles everyone.

**Fix:** dry-run first — parse, validate, and show a preview table with a per-row verdict (`NEW` / `ALREADY_ENROLLED` / `INVALID_DOMAIN` / `MALFORMED`) before anything commits. Commit is all-or-nothing in one transaction. Required headers checked explicitly; a template CSV is downloadable from the page. Re-import is idempotent. Rejected rows come back as a downloadable CSV so the faculty member can fix and re-upload rather than hunt.

#### 8. Faculty review workflow clarity

**Breaks as:** thirty rows in the grid and no way to see which four need a human. Approved and pending look identical. An overridden score looks like an AI score. The dashboard's pending count disagrees with the grid.

**Fix:** one "needs attention" predicate in `core/` — mandatory criterion at `NO_EVIDENCE`, confidence below threshold, evaluation `FAILED`, or not yet approved — used by the grid filter *and* the dashboard count, so the two cannot drift. Default sort: unapproved first, then ascending confidence. A provenance chip per row (`AI` / `MANUAL` / `OVERRIDDEN`) so a hand-corrected mark is never mistaken for a model output.

#### 9. AI failure/retry handling

**Breaks as:** the provider 429s mid-batch and the run looks like an app crash. A `FAILED` evaluation sits invisible and gets approved as a zero. Retry resumes the same poisoned checkpoint forever. Retry creates a duplicate evaluation for the same version.

**Fix:** `Evaluation.status ∈ {PENDING, RUNNING, COMPLETE, FAILED}` is surfaced in the grid with a per-row Retry. **Retry increments `evaluation_version`, producing a new `thread_id`** — a genuine retry starts clean, while a browser refresh still resumes the existing run. That distinction is the whole point of §6.3's deterministic thread id; don't collapse it. Bounded backoff on rate limits. When the provider is unreachable, a banner states that manual scoring, penalties, and exports still work (inv #10) rather than showing a traceback.

**Proof:** the app renders end to end with the provider stubbed to raise on every call.

#### 10. Submission-status clarity

**Breaks as:** `ABSENT` rendered as `0`, which is exactly the distinction §5.1 exists to preserve. The student's page says "submitted" while the faculty grid shows nothing. Lateness only becomes visible after the fact. A reinstatement leaves no visible trace.

**Fix:** one status enum, one shared renderer in `app/components/`, called by both roles and both exporters — status is never re-derived per page. `ABSENT` never renders as a number anywhere, Excel included. At upload time the student sees the consequence *before* confirming: "2 days late — 20% penalty will apply." Reinstatement shows as a badge carrying its reason.

#### 11. Export consistency

**Breaks as:** the TSV and the XLSX disagree because each formats its own numbers. The export is built from grid widget state rather than the persisted `ScoreSheet`, so an uncommitted edit ships. Unapproved AI estimates export looking final — invariant #1 broken at the last step. Absent students export as 0.

**Fix:** both exporters consume one `build_export_rows(actor, milestone) -> list[ExportRow]` built from persisted rows. Formatting may differ; numbers never do. Unapproved rows carry an explicit `ESTIMATE — NOT APPROVED` marker in a status column, or are excluded — decide once and state which in the report. Filename exactly per §7.

**Proof:** a parity test asserting the TSV cell grid equals the XLSX cell grid, value for value.

---

### P2 — polish

Do these in Phase 7. They are what makes the Review 2 demo feel finished, and none of them justify touching P0 code.

#### 12. Review-grid readability
Freeze the identity columns. Criterion columns stay narrow with verdict glyphs (`✓ ~ ✗ ?`) and a visible legend — detail belongs in the `st.dialog`, not the grid. Set explicit widths in `column_config`; past roughly eight criteria, collapse the criterion block behind an expander rather than letting the table scroll sideways past the totals.

#### 13. Empty/error states
Every list gets a zero-state naming the next action ("No subjects yet — create one"). Every DB and AI call is wrapped and fails to a readable message, never a traceback. No page renders a blank region. Walk all twelve pages of §8 against an empty database as a checklist.

#### 14. Session/cache invalidation
One `invalidate(*keys)` helper in `app/state.py`, called explicitly after every mutation; caching stays out of `core/` entirely. Long-running dialogs re-read before writing rather than trusting `session_state`.

> **Split priority:** the *cache-key* half of this item is not polish. Every `@st.cache_data` key must include the actor's email — a cache shared across users is a cross-user data leak, which is item 3, P0, Phase 1. Only the invalidation ergonomics belong down here.

#### 15. Audit/history presentation
`AuditLog` is written from Phase 1 but read by nobody until here. Surface it: a history panel inside the score-sheet dialog (who changed what, when, and why), submission version history on the student's Submit page, and a filterable admin view. Render timestamps in IST. This is cheap to build and it is the artifact that answers "how do you know the faculty member, not the AI, decided this mark?"

# RubriQ — Implementation

Module-wise write-up. If this becomes a group project, the `core/` package
boundaries below are already the independent-module split — each row is
separately testable and has a named test file.

---

## 1. Package map

```
core/                     ← domain. ZERO streamlit imports.
├── config.py             settings from st.secrets or the environment
├── clock.py              IST, utc_now(), to_ist(), ist_date()
├── errors.py             RubriQError, NotAuthorized, AuthError, ValidationError
├── audit.py              record() — one row per mutation
├── audit_read.py         reading it back (fix item 15)
├── db/                   engine (pragmas), models (16 tables), types
├── auth/                 domain assertion, roles, actor, page policy
├── academics/            subjects, enrolment + CSV import, milestones, access
├── rubrics/              versioning, weight validation, publish/clone
├── submissions/          storage, text extraction, versioning, status
├── scoring/              engine (pure), policy, sheets, grid, ai_runs
├── ai/                   the only place langgraph or an LLM SDK is imported
├── queries/              student assistant context, escalation, reply
├── reports/              distribution, weak criterion, attendance mix
└── exports/              rows → tsv + xlsx

app/                      ← view. Thin.
├── main.py               auth gate + st.navigation
├── navigation.py         PageSpec → st.Page, for the resolved role only
├── context.py            current_actor(), db()
├── state.py              cache scoping, flash, after_mutation
├── components/           calendar, rubric_view, review_grid, ai_runner
└── pages/                faculty/ (8) and student/ (5)
```

---

## 2. Foundation

### `core/config.py`

A frozen `Settings` dataclass built either from a mapping (`st.secrets`) or
from the environment, so Alembic and pytest — which have no `st.secrets` —
read the same configuration. `redacted()` exists so settings can be printed in
a diagnostic without leaking the API key.

### `core/db/engine.py`

SQLite is configured rather than accepted on defaults. Four pragmas on every
connection:

| Pragma | Why |
|---|---|
| `journal_mode=WAL` | A reader does not block the writer, which matters when a Streamlit rerun overlaps an approval |
| `busy_timeout` | Turns a momentary lock into a wait rather than an immediate `database is locked` |
| `synchronous=NORMAL` | Adequate durability under WAL, without an fsync per commit |
| `foreign_keys=ON` | SQLite does not enforce foreign keys unless asked. Without this the schema's referential integrity is decorative |

`check_connection()` returns a `DbHealth` value and never raises, so a page can
report an unreachable database instead of showing a traceback.

### `core/db/types.py`

`UtcDateTime` is a `TypeDecorator` that **refuses to store a naive datetime**
and normalises everything to UTC on the way in. This was written in response
to a real bug: SQLite discarded the offset on an IST-aware timestamp, so a
23:59 IST submission came back as 23:59 UTC and rendered as 05:29 the
following morning — turning an on-time submission into a late one.

### `core/clock.py`

IST as a fixed `timezone(timedelta(hours=5, minutes=30))` rather than a
`zoneinfo` lookup, so the project carries no `tzdata` dependency on Windows.
India has no DST, so a fixed offset is correct rather than merely convenient.

---

## 3. Auth and roles

| File | Responsibility |
|---|---|
| `core/auth/domain.py` | Asserts the email claim's domain. The `hd` hint sent to Google is a convenience; this is the check |
| `core/auth/roles.py` | `Role` enum and allow-list resolution |
| `core/auth/actor.py` | The `Actor` value passed as the first argument to every service function |
| `core/auth/service.py` | `authenticate()` and `sign_in()` |
| `core/auth/pages.py` | `PageSpec` list and `pages_for(role)` — access-control policy as data |

Page policy lives in `core/` on purpose. It means "a student cannot reach a
faculty page" is provable by a unit test on the page-list builder rather than
by clicking around, which is what the phase exit criterion asked for.

`app/navigation.py` constructs `st.Page` objects only for the specs returned
for the signed-in role, so a faculty page is not merely hidden from a student —
it does not exist in their session.

---

## 4. Academics

`core/academics/enrollment.py` is the largest single service, because a CSV
import that half-succeeds is worse than one that fails:

1. **`preview_enrollment_import`** parses and validates without writing,
   returning a per-row verdict: `NEW`, `ALREADY_ENROLLED`, `INVALID_DOMAIN`,
   `MALFORMED`, `DUPLICATE_IN_FILE`, `FACULTY_ADDRESS`.
2. The page renders that preview with counts before offering a commit.
3. **`commit_enrollment_import`** writes in one transaction, all or nothing,
   and only rows whose verdict is `NEW`.
4. **`rejected_rows_csv`** hands back the failures as a CSV so the faculty
   member fixes and re-uploads rather than hunting through 40 rows.

Because the only committable verdict is `NEW` and enrolment is unique on
`(student_email, subject_id)`, re-running the same import is idempotent.

One implementation note worth recording: the two-phase write here is manual.
The models deliberately declare no `relationship()`, so SQLAlchemy has no
mapper dependency to order the flush by — and an enrolment row was being
inserted before the user row it referenced. The service writes users first,
flushes, then enrolments.

---

## 5. Rubrics

`published_at IS NOT NULL` is the frozen flag. `_load_editable()` is the
single gate: it raises if the rubric is published, so every mutating function
inherits immutability rather than each remembering to check.

* `publish_rubric` validates Σweight == 100 with at least one criterion, then
  stamps `published_at` and `published_by`.
* `clone_for_edit` copies criteria into version *v+1*, unpublished. Version
  *v* is untouched and still resolves for the submissions already graded
  against it.
* `remove_criterion` deactivates rather than deletes, because
  `criterion_score` rows reference it.

---

## 6. Submissions

`submit()` does five things in one transaction: allocate the next version,
store the files, extract their text, write the submission row, and record an
audit entry.

`core/submissions/extract.py` handles PDF (`pdfplumber`), DOCX
(`python-docx`, including table cells, because requirement tables are usually
tables), and plain text. When extraction yields little or nothing — a scanned
PDF — it records an `extract_note` rather than failing. The consequence is
visible downstream: criteria fall to `NO_EVIDENCE` instead of being guessed
at.

Text is extracted **at upload**, so nothing later in the pipeline — the AI
layer included — ever opens a file.

---

## 7. Scoring

### `core/scoring/engine.py` — pure, no database

The single entry point is `compute_score_sheet(...)`. Nothing outside this
module does mark arithmetic: not the grid, not the exporters, not the reports
page.

### `core/scoring/policy.py`

The §5.1 table as data, overridable per subject or milestone:

| Days late | Outcome |
|---|---|
| 0 | No penalty |
| 1 | −10 % of milestone max marks |
| 2 | −20 % |
| 3 | −35 % |
| 4–5 | `ABSENT`, recorded as a status; the submission is still stored and still evaluated for feedback |
| > 5 | `ABSENT`, and needs explicit faculty reinstatement to be scored at all |

### `core/scoring/sheets.py`

The transactional layer: `save_manual_scores`, `approval_blockers`,
`approve_sheet`, `override_criterion`, `reinstate`, `override_history`.

Three properties are enforced here rather than in the UI:

* `approve_sheet` recomputes, writes, stamps, and audits in **one**
  transaction — all or nothing.
* `override_criterion` rejects a whitespace-only reason in `core/`, writes an
  append-only row, recomputes the total, and **clears the approval**, so
  someone has to sign it off again.
* Approval is refused while any mandatory criterion is unresolved or the
  evaluation is not `COMPLETE`.

### `core/scoring/grid.py`

Builds one `GridRow` per **enrolled** student, whether or not they submitted.
`GridRow.needs_attention` is fix item 8's single predicate, consumed by the
grid filter and the dashboard count so the two cannot disagree.

---

## 8. The AI layer

| File | Responsibility |
|---|---|
| `provider.py` | `LLMProvider` protocol, `StubProvider`, `RetryingProvider`, and lazily-imported Gemini and Groq implementations |
| `schemas.py` | The §6.5 response contract as Pydantic models. `NO_EVIDENCE ⇒ score == 0` is a validator |
| `guards.py` | Normalisation, `verify_evidence`, `demote`, `apply_guard` |
| `identity.py` | `scrub_identity`, `assert_scrubbed`, PRN and email patterns |
| `graphs/evaluation.py` | The state machine — see [`diagrams/evaluation-state.md`](diagrams/evaluation-state.md) |
| `graphs/query.py` | classify → answer → confidence check, or escalate |
| `checkpoint.py` | `SqliteSaver` setup and `thread_id` helpers |
| `prompts/` | Versioned, one file per prompt |

The public surface is three synchronous functions plus a generator. No caller
ever sees a graph, a state dict, or a checkpointer.

Both SDKs are imported **lazily**, inside the function that needs them, so a
missing package or key produces a readable message rather than an import error
at startup.

### The model choice

`gemini-2.0-flash`, named in the original plan, was already returning 404 by
the time the provider was wired up. The model is therefore configuration
(`[llm] model`, default `gemini-3.6-flash`), not a constant.
`response_mime_type="application/json"` is set so the response contract is
enforced by the API as well as by the schema.

---

## 9. Student assistant

`core/queries/service.py::build_context` assembles exactly three things: the
published rubric for that milestone, the milestone description, and the
faculty public notes. Nothing else — no other student's work, no scores, no
unpublished rubrics.

The refusal logic for "what will I score?" is worth a note, because the first
version of it was wrong. It originally assumed the verb precedes the noun, so
*"how many marks will I get"* slipped through and was answered. It now matches
a mark noun and a self-directed future reference independently of their order.

---

## 10. Exports

`core/exports/rows.py::build_export_rows` is the single source. `tsv.py` and
`xlsx.py` are formatters over its output, and
`tests/core/exports/test_parity.py` asserts the two cell grids are equal value
for value.

The XLSX carries a frozen header row, per-criterion columns, and a second
sheet with evidence and rationale text. Filename:
`RubriQ_<SubjectCode>_Review<N>_<YYYYMMDD>.xlsx`.

---

## 11. The view layer

`app/state.py` carries three things:

* **`cache_scope(actor_email, version)`** — every `@st.cache_data` key begins
  with the actor's email. A cache keyed only on a milestone id would be shared
  by every user in the process, which is a cross-user data leak wearing a
  cache's clothing.
* **`flash` / `render_flash`** — `st.success()` immediately before
  `st.rerun()` is drawn and discarded, so a confirmation has to survive the
  rerun. `render_flash()` is called once by `main.py`, above whichever page
  runs.
* **`after_mutation(message)`** — invalidate, flash, rerun. Three lines that
  every mutating branch repeated, and whose ordering is not visibly wrong when
  you get it backwards.

---

## 12. Development-only sign-in

`[dev] impersonate` in the gitignored `secrets.toml` supplies claims in place
of Google, so pages could be built before OIDC credentials existed. It routes
through `authenticate()` like a real response, so the domain assertion and the
allow-list still apply — a `@gmail.com` address put there is still refused.

It is absent from the committed example, and the app renders a persistent
warning banner while it is active.

---

## 13. Migrations

Five Alembic revisions, one per schema-bearing phase. Two were hand-repaired
after autogenerate emitted `NameError`s (an unimported `Text`, then an
unimported `core`); `alembic/env.py` now carries a `render_item` hook that
emits the custom type correctly, plus `render_as_batch=True` because SQLite
cannot `ALTER` a column in place.

---

## 14. Demo data

`scripts/seed_demo.py` builds the demo dataset through the same services a
faculty member uses — so seeded rows are indistinguishable from real ones and
every total came from the scoring engine. No LLM is called.

The cohort is deliberately uneven: on time, one day late, two days late,
absent, never submitted, one blocked on a mandatory criterion at
`NO_EVIDENCE`, one with a version history, and one escalated question waiting.
A dataset where every row is approved and every mark is the same demonstrates
none of the behaviour that matters.

# RubriQ — Design

The diagrams are in [`diagrams/`](diagrams/); this document is the reasoning
that produced them.

| Diagram | File |
|---|---|
| Entity–Relationship | [`diagrams/er.md`](diagrams/er.md) |
| DFD Level 0 (context) | [`diagrams/dfd-l0.md`](diagrams/dfd-l0.md) |
| DFD Level 1 | [`diagrams/dfd-l1.md`](diagrams/dfd-l1.md) |
| Use case | [`diagrams/use-case.md`](diagrams/use-case.md) |
| Architecture (`core/` ↔ `app/`) | [`diagrams/architecture.md`](diagrams/architecture.md) |
| Evaluation state machine | [`diagrams/evaluation-state.md`](diagrams/evaluation-state.md) |

---

## 1. The one architectural decision

Everything else follows from this: **all logic lives in `core/` as plain
Python with zero Streamlit imports, and `app/` is a thin view layer that calls
it.**

Streamlit is a fine way to reach a working system quickly, and a poor thing to
have load-bearing logic inside. The whole script reruns on every click, there
is no request boundary to hang authorisation on, and nothing in it is testable
without a browser. Putting the domain on the other side of a hard line gets
the benefits without accepting the costs:

* The domain is unit-testable. 614 of the 653 tests need no Streamlit runtime
  at all.
* Authorisation is a property of a function signature — `actor` first,
  scoping in SQL — rather than something the UI is trusted to do.
* If Streamlit becomes the bottleneck, the view layer is replaceable and
  roughly 80 % of the codebase survives. That is a real answer to *"why not a
  real web framework?"* rather than a defensive one.

The rule is enforced by a test that greps `core/` for `import streamlit`, so
it cannot erode quietly.

## 2. Layering

```
app/pages/*        →  app/components/*  →  core/<domain>/  →  core/db/  →  SQLite
                                            core/ai/       →  Gemini
```

Four rules keep the arrows pointing one way:

1. `core/` never imports `app/`.
2. `app/` never does mark arithmetic.
3. Only `core/ai/` imports LangGraph or an LLM SDK.
4. Only `core/db/` knows which database dialect is in use.

## 3. Where each concern is decided

| Concern | Decided in | Not decided in |
|---|---|---|
| Who you are, and what you may see | `core/auth/`, and the `WHERE` clause of every query | The UI. A page a student may not open is never constructed |
| What a criterion is worth | `core/rubrics/`, frozen at publish | The evaluation run, which reads a rubric version and cannot change it |
| Whether a submission is late | `core/scoring/engine.py::days_late`, from the IST calendar date | The database, which stores no `is_late` column that could drift from `due_at` |
| What a mark is | `core/scoring/engine.py` | The grid, the exporters, the reports page, and the model |
| Whether evidence is real | `core/ai/guards.py`, on the only path to persistence | A confidence threshold — there is no bypass at any confidence |
| Whether a mark is final | An explicit approval that stamps `approved_by` and `approved_at` | Anything automatic |

## 4. Scoring design

```
weighted_percent = Σ (score / criterion.max_score) × criterion.weight     # 0…100
base_total       = weighted_percent × max_marks ÷ 100
penalty          = band_percent    × max_marks ÷ 100
final_total      = max(0, base_total − penalty)
```

Four decisions inside those four lines:

* **Weights are a percentage, marks are marks.** The rubric is authored in
  percentages that must sum to 100; the milestone carries its own
  `max_marks`. Keeping them separate means changing a milestone from 25 marks
  to 50 does not require rewriting the rubric.
* **The penalty applies to the total, never to a criterion.** A per-criterion
  penalty would interact with weights and produce a different answer depending
  on which criteria happened to score well.
* **`Decimal` throughout, rounded once, half-up, at the persistence
  boundary.** Floats render 19.999999 eventually, and the first person to see
  it will be an examiner.
* **`days_late` compares two calendar dates in `Asia/Kolkata`.** A UTC
  comparison makes an 11:45 PM IST submission count as next-day late, which is
  both wrong and impossible to explain.

Absence is a *status*, not a mark. `AttendanceStatus.ABSENT` renders as the
string `ABSENT` through one shared property (`ScoreSheetDTO.display_total`)
used by the grid and both exporters, so it cannot become a `0` in one of the
three.

## 5. AI design

### 5.1 What the model is asked to do, and what it is not

The model reads and judges. It is asked for a verdict, a score out of a
criterion's maximum, a confidence, a verbatim evidence span, and one sentence
of rationale. It is never asked to add anything up.

That division is what makes the system defensible. A wrong verdict is a
disagreement a faculty member can see and override; a wrong total would be an
error nobody would catch.

### 5.2 The evidence guard

Every criterion score must cite a span that fuzzy-matches
(`rapidfuzz.partial_ratio ≥ 90`) into the stored `text_extract`. A span that
does not is demoted to `NO_EVIDENCE` with score 0, and the fabricated span is
logged.

Two details matter:

* **Both sides are normalised identically for comparison** — NFKC, invisible
  characters removed, line-break hyphenation joined, whitespace collapsed,
  casefolded — because PDF extraction reflows text and a genuine quotation
  would otherwise fail the match. **The model's original span is stored
  untouched**, so "verbatim" stays verbatim.
* **There is no bypass.** Not at high confidence, not in a batch run. The
  `NO_EVIDENCE ⇒ score == 0` rule is a Pydantic validator, so it cannot be
  enforced in the UI and skipped elsewhere.

The rejection rate this produces is the project's strongest empirical result.

### 5.3 Identity

The student's name, PRN, and email are stripped in the graph's `prepare` node,
before the first token leaves the process, and the outgoing prompt is asserted
clean. The model is given a rubric and an anonymous document.

### 5.4 Why a graph

Two reasons, both defensible aloud:

1. **The flow has real conditional edges.** Parse → validate → verify →
   repair-and-retry → aggregate is a state machine with two failure loops.
   Drawing it as one makes the retry policy explicit and inspectable.
2. **Checkpointing solves a Streamlit problem.** `SqliteSaver` persists graph
   state per `thread_id`, so a rerun mid-evaluation resumes at the last
   completed node instead of re-calling the model.

And three places it deliberately does not go: not inside `core/scoring/`, not
as an agent with database tools, and not over CRUD flows.

## 6. The review grid

The centrepiece, and the page that decides whether the system is usable.

* One row per **enrolled** student, including students who never submitted —
  a grid that omits non-submitters is how someone gets missed.
* Default order puts rows needing attention first, from **one predicate** in
  `core/`, used by the grid filter *and* the dashboard count, so the two
  cannot drift.
* Criterion columns carry verdict glyphs (`✓ ~ ✗ ?`) with a visible legend;
  detail belongs in the row dialog, not the table.
* Identity columns are pinned and every width is explicit, so a long name does
  not reflow the grid. Past eight criteria the verdict block moves into its
  own table rather than pushing the totals off the right-hand edge.
* `Base`, `Penalty`, and `Final` are never hand-edited — they are recomputed
  from criterion scores.
* The dialog re-reads its row on every rerun instead of trusting the one
  captured when the grid rendered.

## 7. Export design

Both exporters consume one `build_export_rows(actor, milestone)` over
persisted score sheets — never grid widget state, so an uncommitted edit
cannot ship. Formatting may differ between TSV and XLSX; numbers may not, and
a parity test asserts the two cell grids are equal value for value.

An unapproved row exports carrying `ESTIMATE — NOT APPROVED` in its status
column. Invariant #1 would otherwise be broken at the last possible step.

## 8. Failure design

| Failure | What the user sees |
|---|---|
| No LLM key configured | A note that AI evaluation is unavailable. Everything deterministic works |
| Provider rate-limits or 503s | Bounded backoff, then the row is marked `FAILED` with a per-row Retry |
| Schema violation | One repair attempt; then that batch resolves to `NO_EVIDENCE` and the run continues |
| Fabricated evidence | Demotion to `NO_EVIDENCE`, logged, and flagged for mandatory faculty attention |
| Browser refresh mid-run | The run resumes from its checkpoint; no duplicate model calls |
| Empty database | Every page names the next action instead of rendering a blank region |
| Database unreachable | A sidebar message, not a traceback |

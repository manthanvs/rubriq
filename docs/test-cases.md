# RubriQ — Testing

Two halves. The automated suite carries anything expressible as a function
call; the manual table carries what genuinely needs a browser and a person.

Where a case in the manual table could be checked without a person, it is —
several rows below were executed headlessly through Streamlit's `AppTest`
against the seeded database, and say so. A "manual" test nobody re-runs is
worth less than an assertion.

---

## 1. Automated suite

```bash
make test
```

**657 tests, all passing.** The full verbose run is checked in at
[`test-report.txt`](test-report.txt); regenerate it with:

```bash
python -m pytest -o addopts="--strict-markers" -v --tb=short > docs/test-report.txt
```

### Coverage by area

| Test file | Tests | What it guards |
|---|---:|---|
| `tests/core/scoring/test_engine.py` | 30 | Fix item 1 — §5.1's table row by row, boundary days, IST midnight, `final_total ≥ 0`, round-trip against persisted rows |
| `tests/core/scoring/test_sheets.py` | 25 | Fix item 4 — approval blocked while `RUNNING`, empty override reason refused, recompute after override, two approvals produce two audit rows |
| `tests/core/scoring/test_ai_runs.py` | 16 | Fix item 9 — evaluation status, retry increments the version, raw response stored on failure |
| `tests/core/ai/test_guards.py` | 22 | Fix item 5 — fabricated evidence rejected, reflowed evidence accepted, identity never in the outgoing prompt |
| `tests/core/ai/test_schemas.py` | 22 | The §6.5 contract; `NO_EVIDENCE ⇒ score == 0` as a validator |
| `tests/core/ai/test_graph.py` | 20 | The state machine — repair cap, batch demotion, checkpoint resume, no duplicate calls |
| `tests/core/ai/test_provider.py` | 19 | Backoff on transient errors only; the app renders end to end with the provider stubbed to raise |
| `tests/core/queries/test_assistant.py` | 34 | Scope rules, escalation, mark-prediction refusal |
| `tests/core/rubrics/test_versioning.py` | 18 | Fix item 6 — published rubric immutable, weight-sum validation, clone to v+1 |
| `tests/core/submissions/test_versioning.py` | 19 | Fix item 2 — v1 stays retrievable and bound to its own text after v2 |
| `tests/core/submissions/test_extract.py` | 17 | PDF, DOCX including table cells, TXT, and a file that extracts to nothing |
| `tests/core/academics/test_isolation.py` | 16 | Fix item 3 — cross-actor negative cases |
| `tests/core/academics/test_import.py` | 13 | Fix item 7 — per-row verdicts, all-or-nothing commit, idempotent re-import |
| `tests/core/exports/test_parity.py` | 14 | Fix item 11 — TSV and XLSX equal cell for cell; absent exports as `ABSENT` |
| `tests/core/reports/test_reports.py` | 12 | An absence is not a zero, anywhere in a chart |
| `tests/core/auth/*` | 53 | Domain assertion, role resolution, page-list policy |
| `tests/core/db/*` | 11 | Pragmas, and the naive-datetime refusal |
| `tests/core/test_actor_contract.py` | 5 | Reflection over `core/**`: every public service function takes `actor` first |
| `tests/core/test_no_streamlit_in_core.py` | 3 | The architectural rule, enforced |
| `tests/app/test_empty_states.py` | 39 | Fix item 13 — all 13 pages against an empty schema |
| `tests/app/test_review_grid.py` | 23 | Fix item 12 — column order, pinning, overflow, `ABSENT` never a number; the group column |
| `tests/core/groups/test_groups.py` | 32 | Decision #5 — a pending request grants nothing, a granted group shares one submission |
| `tests/core/submissions/test_links.py` | 35 | Decision #6 — URL parsing, lookalike hosts, ownership against the register |
| `tests/core/submissions/test_link_submission.py` | 13 | Decision #6 end to end — a refused link writes no submission |
| `tests/app/test_lateness_copy.py` | 11 | Fix item 10 — the student is told the band, not a generic penalty |
| `tests/app/test_state.py` | 5 | Fix item 14 (P0 half) — no cache key without the actor's email |
| `tests/test_smoke.py` | 11 | Settings, engine, session scope |

### The three tests that guard architecture rather than behaviour

These are worth pointing at, because they are what stops the design eroding:

1. **`test_no_streamlit_in_core.py`** greps every file under `core/` for a
   Streamlit import and fails if it finds one.
2. **`test_actor_contract.py`** reflects over every public function in `core/`
   and fails any whose signature does not start with `actor`. Exemptions must
   be listed explicitly with a reason.
3. **`test_pages.py::test_a_student_gets_no_faculty_page`** asserts the
   page-list builder, which is what the Phase 1 exit criterion demanded — the
   proof is a unit test, not clicking around.

---

## 2. Manual test cases

Executed against the seeded demo dataset (`make reseed`) on 3 September 2026;
MT-17 and MT-18 re-run live against Gemini on 5 September 2026.

| # | Case | Steps | Expected | Actual | Result |
|---|---|---|---|---|---|
| MT-01 | Non-institute account is refused | Sign in as `someone@gmail.com` | Rejected with a clear message; no page is reachable | `Sign-in is restricted to @pccoepune.org accounts. You signed in as someone@gmail.com.` | **Pass** — executed via `AppTest` on `app/main.py` |
| MT-02 | A lookalike domain is refused | Sign in as `attacker@pccoepune.org.evil.com` | Rejected — the check is the domain, not a substring | Same rejection message | **Pass** — executed via `AppTest` |
| MT-03 | An institute account is admitted | Sign in as `manthan.sankpal@pccoepune.org` | Reaches the app with role STUDENT | No error, app rendered | **Pass** — executed via `AppTest` |
| MT-04 | A student cannot reach a faculty page | Sign in as a student, inspect the navigation | No faculty page is listed or constructed | Student page list is Dashboard, Calendar, Submit, Feedback, Ask RubriQ | **Pass** — also asserted in `test_pages.py` |
| MT-05 | Empty database | Point the app at a fresh schema and open all 13 pages | Every page names a next action; no traceback, no blank region | e.g. Faculty Dashboard: *"No subjects yet — create one on the Subjects page to get started."* | **Pass** — automated as `test_empty_states.py` |
| MT-06 | Rubric visible before upload | Open Submit as an enrolled student | The rubric renders above the file uploader | Element order: deadline (3) → rubric block (6–9) → file uploader (14) | **Pass** — executed via `AppTest` element ordering |
| MT-07 | Lateness consequence stated before confirming | Open Submit for a milestone 10 days past due | The message names the actual §5.1 band, not a generic penalty | *"This deadline passed 10 day(s) ago… It will be recorded as ABSENT, and your guide has to reinstate it explicitly before it can be scored at all."* | **Pass** — the earlier wording said only "a late penalty will apply"; corrected and covered by `test_lateness_copy.py` |
| MT-08 | Grid shows every §5.1 outcome distinctly | Open Review Grid on the seeded milestone | Estimate, Absent, Not scored, No submission and Approved are visibly different, and `ABSENT` is not a number | Rows read `Estimate / Absent / Not scored / Estimate / No submission / Approved …`; `Final` shows `ABSENT` for the absent row | **Pass** — verified in the browser |
| MT-09 | Non-submitters appear in the grid | Same page | Neha Pawar (never submitted) has a row | Row present, status `No submission`, totals blank | **Pass** — verified in the browser |
| MT-10 | Score drawer opens with fresh data | Select a row in the grid | The dialog opens showing the current sheet and the criteria | Drawer opened for Rahul Deshmukh v2 with C1–C3 and Save/Approve | **Pass** — verified in the browser |
| MT-11 | Bulk approve names exclusions *before* confirming | Expand "Approve all eligible" | The counts and the reason for each exclusion appear before the button | *"**2** sheet(s) will be approved. **1** will be skipped."* / *"Skipped: 125M1H076 (mandatory criteria unevidenced: C1)"* | **Pass** — executed via `AppTest` |
| MT-12 | Reports exclude absences from the mean | Open Reports on the seeded milestone | Mean is over scored, non-absent sheets only | `mean 16.08 · median 15.38 · range 9.88–21.88`, absent excluded, `1 student did not submit at all` | **Pass** — verified in the browser |
| MT-13 | Weakest criterion is identified | Same page | The lowest-scoring criterion is named with its share | *"C1 — Problem statement and objectives is the weakest criterion at 66.0 % of its maximum, and 1 submission(s) had no evidence for it."* | **Pass** — verified in the browser |
| MT-14 | Escalated question reaches the inbox | Open the faculty Dashboard | The waiting count is surfaced | *"1 student question(s) the assistant could not answer are waiting in your Query Inbox."* | **Pass** — verified in the browser |
| MT-19 | `make reseed` is repeatable | Run it twice in succession | The second run succeeds | Passed after a fix — see D10 in the defect log. Now guarded by `tests/test_seed_reset.py` |  **Pass** |
| MT-20 | The system works with no AI key | Remove the `[llm]` section and open every faculty page | Nothing raises; deterministic features unaffected | All eight faculty pages render with no exception | **Pass** — invariant #10, executed via `AppTest` |
| MT-21 | Reports agree with the grid and the export | Compare the class mean against the exported marks | The same numbers appear everywhere | Passed after a fix — see D11 |  **Pass** |
| MT-15 | Clone to populated system in one command | `make seed && make run` | A browsable, populated system with no manual setup | `students 8, submissions 8, approved 3, questions 3`; app served and browsed | **Pass** — Phase 7 exit criterion |
| MT-16 | Export opens in Excel | Build the `.xlsx` and inspect the workbook | Frozen header, per-criterion columns, second sheet with evidence | Filename `RubriQ_MCA33EL03_Review1_20260905`; sheets `Scores`, `Evidence`, `About`; freeze pane at `A2`; 19 columns including `Group`, `Adjustment`, `Adjustment Reason`; `ABSENT` as a status; the adjusted member exporting 9.13 rather than the group's 11.63 | **Pass (structure)** — opening it in Excel itself is still a human step |
| MT-17 | Refresh mid-evaluation makes no duplicate model call | Run an evaluation to completion, then re-enter the same `thread_id` | The resumed run replays from the checkpoint and calls the model zero times | Run 1: full node path, **1** live Gemini call, COMPLETE. Run 2 on `eval:3:8`: no nodes re-executed, **0** live calls, identical result | **Pass (live API)** |
| MT-18 | Live Gemini evaluation, in-scope answer | Run evaluations against the seeded cohort with a real key | Criteria scored, evidence verified against the submitted text | 4/4 submissions completed on `gemini-3.6-flash`, 15–33 s each. Verdicts matched the seeded content: the one student whose file contains the SRS section scored C2 FOLLOWED; the rest returned C2/C3 `NO_EVIDENCE`, and the absent student rendered `ABSENT` rather than a number | **Pass (live API)** |

### Notes on the remaining unverified row

Listed rather than quietly dropped.

* **MT-16** is now verified as far as it can be without Excel. The workbook is
  built and read back: the filename, the three sheets, the frozen pane, the
  column list and the individual values are all checked, including that a group
  member marked apart from their group exports their own mark. What remains
  unverified is only that Excel itself renders the file — that needs Excel and
  a person, and it is a two-minute check rather than a risk.

### What the live run did and did not establish

MT-17 and MT-18 were both closed against the real Gemini API, so it is worth
being exact about what that bought.

**It established:** the model returns content conforming to §6.5's contract;
the graph completes on real responses; verdicts track the seeded content
rather than being uniform; `ABSENT` survives an AI run untouched; and a
resumed run genuinely replays from the checkpoint rather than re-calling the
provider — the claim §6.2 makes for LangGraph, which until now had only been
checked against a stub.

**It did not establish a rejection rate.** Across these runs the guard rejected
nothing, which is a weak result rather than a good one: the seeded submissions
are short, clean text, and most criteria came back `NO_EVIDENCE` — a verdict
that carries no span to check. A meaningful rejection rate needs longer, real
documents where the model has room to paraphrase. The guard's *behaviour* is
covered either way by `tests/core/ai/test_guards.py`, which rejects a
fabricated span and accepts a reflowed genuine one.

**Two failed runs happened first, and both were my instrument, not the system.**
A provider wrapper written to count calls omitted an attribute the graph reads,
so `evaluate` raised and the run was correctly marked `FAILED`. Worth recording
because the failure looked exactly like a provider outage from the outside, and
the first reading of it was wrong.

---

## 3. Defect log

Defects found during the build and fixed, kept because a report that claims a
clean run is less credible than one that shows its failures.

| # | Defect | Where found | Fix |
|---|---|---|---|
| D1 | SQLite discarded the timezone offset, so a 23:59 IST submission read back as 05:29 the next morning — turning an on-time submission late | Phase 2, manual check | `UtcDateTime` type decorator that refuses naive datetimes and normalises to UTC |
| D2 | Enrolment rows were inserted before the user rows they reference | Phase 2 | The models declare no `relationship()`, so there is no mapper dependency to order the flush by — the service now writes users, flushes, then enrolments |
| D3 | `st.success()` immediately before `st.rerun()` was drawn and discarded, so a student was never told their submission landed | Phase 3 | `flash` / `render_flash`, later folded into `after_mutation` |
| D4 | A resumed evaluation overwrote its own checkpoint by passing an initial state instead of `None` — the exact duplicate call the exit criterion forbids | Phase 5b | Pass `None` on resume so the checkpointer replays |
| D5 | `aggregate` clobbered a `FAILED` status and wiped `last_error`, so a provider outage looked like a page of zeroes | Phase 5b | `aggregate` preserves the failure status and its reason |
| D6 | The mark-refusal regex assumed the verb precedes the noun, so *"how many marks will I get"* was answered instead of refused | Phase 6 | Matched order-independently |
| D7 | A null in a numeric grid column rendered as the word `None`, which reads as a value | Phase 7 | `Base`, `Penalty`, and `Final` render as text through one path; nothing scored shows blank |
| D8 | The Submit page said "a late penalty will apply" at ten days late, where §5.1 actually records ABSENT and requires reinstatement | Phase 7, MT-07 | The band is looked up and described; covered by `test_lateness_copy.py` |
| D9 | `use_container_width` is deprecated and past its removal date | Phase 7 | Replaced with `width="stretch"` in all 16 call sites |
| D10 | `make reseed` failed on its **second** run — a foreign key error, because `MemberAdjustment` was deleted after the `ScoreSheet` it references. Step 1 of the demonstration script | Viva rehearsal | Delete order corrected, extracted to `RESET_ORDER`, and checked against the schema by `tests/test_seed_reset.py`. That test immediately found a second gap: `late_policy` was never cleared at all, so a policy override would have survived a reseed and silently changed the marks |
| D11 | The Reports page averaged the **group's** total for every member, so a member marked apart from their group counted at the wrong figure and the class mean disagreed with the exported file | Viva rehearsal | `GridRow.member_mark` — the numeric counterpart of `display_total` — is what the report averages |
| D12 | A metric on the student Feedback page had an empty label. Streamlit warns this may become an exception, and a screen reader announced a bare score with no idea what it measured | Viva rehearsal | A real label, hidden with `label_visibility="collapsed"` |

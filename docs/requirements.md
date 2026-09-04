# RubriQ — Requirement Analysis

Every requirement below is numbered, and every one names the module that
implements it and the test that proves it. A requirement with no test named is
a requirement nobody has checked, so the third column is not decoration.

Paths are relative to the repository root.

---

## 1. Functional requirements

### 1.1 Authentication and roles

| # | Requirement | Implemented in | Proved by |
|---|---|---|---|
| FR-1 | The system shall authenticate users through Google OIDC and shall not store or handle passwords | `app/main.py`, `core/auth/service.py` | manual — MT-01 |
| FR-2 | The system shall reject any account whose email domain is not `pccoepune.org`, asserted server-side from the email claim rather than trusting the `hd` hint | `core/auth/domain.py` | `tests/core/auth/test_domain.py` |
| FR-3 | The system shall assign a role from a seeded faculty allow-list; a user shall not be able to select their own role | `core/auth/roles.py`, `core/auth/service.py` | `tests/core/auth/test_roles.py`, `tests/core/auth/test_service.py` |
| FR-4 | The system shall re-resolve the role on every rerun from settings, never from client-held session state | `app/context.py::current_actor` | `tests/core/auth/test_service.py` |
| FR-5 | The system shall build the navigation from the resolved role, constructing no page object a student may not open | `core/auth/pages.py`, `app/navigation.py` | `tests/core/auth/test_pages.py` |

### 1.2 Academics

| # | Requirement | Implemented in | Proved by |
|---|---|---|---|
| FR-6 | Faculty shall create subjects and project cycles they own | `core/academics/subjects.py` | `tests/core/academics/test_isolation.py` |
| FR-7 | Faculty shall enrol students individually and by CSV import | `core/academics/enrollment.py` | `tests/core/academics/test_import.py` |
| FR-8 | A CSV import shall be previewed with a per-row verdict (`NEW`, `ALREADY_ENROLLED`, `INVALID_DOMAIN`, `MALFORMED`, `DUPLICATE_IN_FILE`, `FACULTY_ADDRESS`) before anything is written | `core/academics/enrollment.py::preview_enrollment_import` | `tests/core/academics/test_import.py` |
| FR-9 | An import shall commit all-or-nothing, shall be idempotent on re-run, and shall return rejected rows as a downloadable CSV | `core/academics/enrollment.py::commit_enrollment_import`, `::rejected_rows_csv` | `tests/core/academics/test_import.py` |
| FR-10 | Faculty shall create review milestones with a title, description, due date, maximum marks, and a visibility flag | `core/academics/milestones.py` | `tests/core/academics/test_isolation.py` |
| FR-11 | Both roles shall see a milestone agenda sorted soonest-first, from one shared renderer | `app/components/calendar.py` | `tests/app/test_empty_states.py` (both calendar pages) |

### 1.2a Project groups (decision #5)

| # | Requirement | Implemented in | Proved by |
|---|---|---|---|
| FR-53 | A student shall be able to request a project group, naming its members | `core/groups/service.py::request_group` | `tests/core/groups/test_groups.py` |
| FR-54 | A faculty member shall be able to form a group outright, granted on creation | `core/groups/service.py::create_group` | `tests/core/groups/test_groups.py` |
| FR-55 | A group shall confer nothing until a faculty member who owns the subject grants it | `core/groups/service.py::grant_group`, `::granted_group_ids_for` | `tests/core/groups/test_groups.py` |
| FR-56 | A refusal shall require a reason, which the student can read | `core/groups/service.py::reject_group` | `tests/core/groups/test_groups.py` |
| FR-57 | A granted group's submission shall be visible to every member, and to nobody else | `core/submissions/service.py::_assert_can_see`, `::_belongs_to` | `tests/core/groups/test_groups.py` |
| FR-58 | Submission versions shall be numbered per group, so two members cannot each create a v1 | `core/submissions/service.py::submit` | `tests/core/groups/test_groups.py` |
| FR-59 | No student shall be in two granted groups for one subject | `core/groups/service.py::_assert_no_double_grant` | `tests/core/groups/test_groups.py` |
| FR-60 | The review grid shall keep one row per student, naming the group on it | `core/scoring/grid.py`, `app/components/review_grid.py` | `tests/app/test_review_grid.py` |

### 1.2b Repository links (decision #6)

| # | Requirement | Implemented in | Proved by |
|---|---|---|---|
| FR-61 | A submission shall accept GitHub repository URLs alongside or instead of files | `core/submissions/service.py::submit` | `tests/core/submissions/test_link_submission.py` |
| FR-62 | A URL shall be accepted only when its owner matches a GitHub account recorded by faculty for the submitter or a granted group-mate | `core/submissions/links.py::assert_owned` | `tests/core/submissions/test_links.py`, `test_link_submission.py` |
| FR-63 | Only a faculty member shall be able to record a student's GitHub account | `core/groups/service.py::set_github_username` | `tests/core/groups/test_groups.py` |
| FR-64 | A non-GitHub host, including a lookalike or credential-disguised one, shall be refused | `core/submissions/links.py::parse_github_url` | `tests/core/submissions/test_links.py` |
| FR-65 | A refused URL shall leave no submission behind | `core/submissions/service.py::submit` | `tests/core/submissions/test_link_submission.py` |
| FR-66 | The system shall not fetch, clone, or read a linked repository | `core/submissions/links.py` (no network code) | `tests/core/submissions/test_link_submission.py` |

### 1.3 Rubrics

| # | Requirement | Implemented in | Proved by |
|---|---|---|---|
| FR-12 | Faculty shall define criteria with a code, title, description, weight, maximum score, expected evidence, and a mandatory flag | `core/rubrics/service.py::add_criterion` | `tests/core/rubrics/test_versioning.py` |
| FR-13 | Publishing shall be refused unless the criterion weights sum to exactly 100 and at least one criterion exists | `core/rubrics/service.py::publish_rubric` | `tests/core/rubrics/test_versioning.py` |
| FR-14 | A published rubric shall be read-only; editing it shall create version *v+1* in an unpublished state and leave *v* unchanged | `core/rubrics/service.py::clone_for_edit` | `tests/core/rubrics/test_versioning.py` |
| FR-15 | Only a published rubric shall be selectable for evaluation | `core/rubrics/service.py::published_rubric_for` | `tests/core/rubrics/test_versioning.py` |
| FR-16 | The published rubric shall be rendered to the student before the upload control | `app/pages/student/submit.py`, `app/components/rubric_view.py` | manual — MT-06 |

### 1.4 Submissions

| # | Requirement | Implemented in | Proved by |
|---|---|---|---|
| FR-17 | A student shall upload PDF, DOCX, or TXT files against a visible milestone | `core/submissions/service.py::submit` | `tests/core/submissions/test_versioning.py` |
| FR-18 | Text shall be extracted at upload time and stored, so no later stage reads a file | `core/submissions/extract.py` | `tests/core/submissions/test_extract.py` |
| FR-19 | A re-upload shall create a new version; every previous version shall stay retrievable with its own text | `core/submissions/service.py` | `tests/core/submissions/test_versioning.py` |
| FR-20 | The consequence of submitting late shall be shown before the student confirms, naming the §5.1 band rather than a generic penalty | `app/pages/student/submit.py`, `app/components/lateness.py`, `core/scoring/sheets.py::policy_for_milestone` | `tests/app/test_lateness_copy.py`, manual — MT-07 |
| FR-21 | Files shall be stored outside the database under a per-submission path | `core/submissions/storage.py` | `tests/core/submissions/test_versioning.py` |

### 1.5 Scoring

| # | Requirement | Implemented in | Proved by |
|---|---|---|---|
| FR-22 | `base_total` shall be the weighted sum of `score / max_score × weight`, scaled onto the milestone's maximum marks | `core/scoring/engine.py` | `tests/core/scoring/test_engine.py` |
| FR-23 | Late penalty shall follow the policy table (0 %, 10 %, 20 %, 35 %, then ABSENT), applied to the milestone total and never to a criterion | `core/scoring/policy.py`, `core/scoring/engine.py` | `tests/core/scoring/test_engine.py` |
| FR-24 | Days late shall be computed from the calendar date in `Asia/Kolkata` on both sides of the comparison | `core/clock.py`, `core/scoring/engine.py::days_late` | `tests/core/scoring/test_engine.py`, `tests/core/db/test_utc_datetime.py` |
| FR-25 | `final_total` shall equal `max(0, base_total − penalty)` and shall never be negative | `core/scoring/engine.py` | `tests/core/scoring/test_engine.py` |
| FR-26 | Absence shall be recorded as a status, never as a mark of zero, and shall render as `ABSENT` in the grid and in both exports | `core/scoring/policy.py`, `core/scoring/dto.py::display_total` | `tests/core/scoring/test_engine.py`, `tests/app/test_review_grid.py`, `tests/core/exports/test_parity.py` |
| FR-27 | Faculty shall be able to reinstate a student past the absence threshold, with a mandatory reason and an audit entry | `core/scoring/sheets.py::reinstate` | `tests/core/scoring/test_sheets.py` |

### 1.6 Approval and overrides

| # | Requirement | Implemented in | Proved by |
|---|---|---|---|
| FR-28 | No score shall become final without an explicit approval stamping `approved_by` and `approved_at` | `core/scoring/sheets.py::approve_sheet` | `tests/core/scoring/test_sheets.py` |
| FR-29 | Approval shall be blocked while any mandatory criterion is unresolved or the evaluation is not `COMPLETE` | `core/scoring/sheets.py::approval_blockers` | `tests/core/scoring/test_sheets.py` |
| FR-30 | An override shall require a non-empty reason, rejected in `core/` rather than only marked required on the widget | `core/scoring/sheets.py::override_criterion` | `tests/core/scoring/test_sheets.py` |
| FR-31 | An override shall be an append-only row carrying old value, new value, reason, actor, and timestamp; it shall recompute the total and clear the approval | `core/scoring/sheets.py::override_criterion` | `tests/core/scoring/test_sheets.py` |
| FR-32 | A bulk approval shall show the excluded count and the reason for each exclusion **before** it is confirmed | `app/pages/faculty/review_grid.py::render_bulk_approve` | manual — MT-11 |

### 1.7 AI evaluation

| # | Requirement | Implemented in | Proved by |
|---|---|---|---|
| FR-33 | The model shall return only JSON conforming to the §6.5 contract; a `NO_EVIDENCE` verdict shall force a score of zero | `core/ai/schemas.py` | `tests/core/ai/test_schemas.py` |
| FR-34 | Every criterion score shall cite a verbatim span that fuzzy-matches (`partial_ratio ≥ 90`) into the stored text; a span that does not shall be demoted to `NO_EVIDENCE` and logged | `core/ai/guards.py` | `tests/core/ai/test_guards.py` |
| FR-35 | The guard shall be the only path to persisting a criterion score — there shall be no confidence threshold that bypasses it | `core/ai/guards.py::apply_guard`, `core/scoring/ai_runs.py` | `tests/core/ai/test_guards.py`, `tests/core/scoring/test_ai_runs.py` |
| FR-36 | Student identity (name, PRN, email) shall be stripped before any text leaves the process | `core/ai/identity.py` | `tests/core/ai/test_guards.py` |
| FR-37 | A schema failure shall trigger at most one repair attempt per batch; a second failure shall resolve that batch to `NO_EVIDENCE` and let the run continue | `core/ai/graphs/evaluation.py` | `tests/core/ai/test_graph.py` |
| FR-38 | A graph run shall be checkpointed by a deterministic `thread_id`, so a browser refresh resumes rather than re-calling the model | `core/ai/checkpoint.py`, `core/ai/graphs/evaluation.py` | `tests/core/ai/test_graph.py` |
| FR-39 | A retry shall increment the evaluation version and start a new thread, so it does not resume a poisoned checkpoint | `core/scoring/ai_runs.py::next_evaluation_version` | `tests/core/scoring/test_ai_runs.py` |
| FR-40 | The raw model response shall be stored verbatim whatever happens, tagged with `model_name`, `prompt_version`, and `graph_version` | `core/scoring/ai_runs.py` | `tests/core/scoring/test_ai_runs.py` |

### 1.8 Student assistant

| # | Requirement | Implemented in | Proved by |
|---|---|---|---|
| FR-41 | The assistant's context shall be the published rubric, the milestone description, and faculty public notes — nothing else | `core/queries/service.py::build_context` | `tests/core/queries/test_assistant.py` |
| FR-42 | An out-of-scope question shall be escalated rather than answered | `core/ai/graphs/query.py` | `tests/core/queries/test_assistant.py` |
| FR-43 | The assistant shall refuse to predict a mark and shall redirect to the rubric criteria | `core/ai/graphs/query.py` | `tests/core/queries/test_assistant.py` |
| FR-44 | An escalated question shall appear in the faculty inbox and shall accept a reply visible to that student only | `core/queries/service.py::list_escalated`, `::reply` | `tests/core/queries/test_assistant.py` |

### 1.9 Feedback, exports, reports, audit

| # | Requirement | Implemented in | Proved by |
|---|---|---|---|
| FR-45 | A student shall see per-criterion feedback only after the score sheet is approved | `app/pages/student/feedback.py`, `core/scoring/sheets.py` | `tests/core/scoring/test_sheets.py` |
| FR-46 | Both exporters shall consume one row builder over persisted score sheets, never grid widget state | `core/exports/rows.py` | `tests/core/exports/test_parity.py` |
| FR-47 | The TSV and the XLSX shall agree cell for cell | `core/exports/tsv.py`, `core/exports/xlsx.py` | `tests/core/exports/test_parity.py` |
| FR-48 | An unapproved row shall export carrying an explicit `ESTIMATE — NOT APPROVED` marker | `core/exports/rows.py` | `tests/core/exports/test_parity.py` |
| FR-49 | The export filename shall be `RubriQ_<SubjectCode>_Review<N>_<YYYYMMDD>` | `core/exports/rows.py` | `tests/core/exports/test_parity.py` |
| FR-50 | Reports shall show a score distribution, a per-criterion weak-spot chart, and an attendance mix, excluding absences from the mean | `core/reports/service.py` | `tests/core/reports/test_reports.py` |
| FR-51 | Every mutation shall write one audit row naming actor, action, entity, and payload | `core/audit.py` | `tests/core/scoring/test_sheets.py`, `tests/core/rubrics/test_versioning.py` |
| FR-52 | The audit log shall be readable in the interface, filtered, with timestamps in IST | `core/audit_read.py`, `app/pages/faculty/activity.py` | `tests/app/test_empty_states.py` |

---

## 2. Non-functional requirements

| # | Requirement | How it is met | Proved by |
|---|---|---|---|
| NFR-1 | **Isolation.** A student shall never be able to read another student's data | `actor: Actor` is the first positional argument of every public function in `core/`, and scoping happens in the SQL `WHERE` clause | `tests/core/test_actor_contract.py` (reflection over `core/**`), `tests/core/academics/test_isolation.py` |
| NFR-2 | **Portability of the view layer.** The domain shall not depend on Streamlit | A test greps every file under `core/` for a Streamlit import | `tests/core/test_no_streamlit_in_core.py` |
| NFR-3 | **Offline degradation.** With the model unreachable, manual scoring, penalties, the calendar, and exports shall still work | The provider is behind a protocol; a missing key produces a message, not a startup failure | `tests/core/ai/test_provider.py` (stub raising on every call) |
| NFR-4 | **Determinism.** Identical inputs shall produce an identical score sheet | All mark arithmetic is in pure functions over `Decimal`, rounded once at the persistence boundary | `tests/core/scoring/test_engine.py` |
| NFR-5 | **Auditability.** Every published mark shall trace to an approver, a submission version, and a rubric version | `Evaluation` pins both versions; `ScoreSheet` references an `evaluation_id` | `tests/core/scoring/test_sheets.py`, `tests/core/submissions/test_versioning.py` |
| NFR-6 | **No hard deletes.** Submissions, evaluations, and overrides shall be append-only | Re-evaluation creates a new version; criteria are deactivated, not removed | `tests/core/rubrics/test_versioning.py`, `tests/core/submissions/test_versioning.py` |
| NFR-7 | **Cache safety.** No cached read shall be shared between users | Every `@st.cache_data` key begins with the actor's email | `tests/app/test_state.py` |
| NFR-8 | **Usability under an empty database.** No page shall show a traceback or a blank region | Every page names a next action on a zero state | `tests/app/test_empty_states.py` (13 pages × 3 assertions) |
| NFR-9 | **Time correctness.** Stored timestamps shall be unambiguous | A `UtcDateTime` column type refuses to store a naive datetime and normalises to UTC; display converts to IST | `tests/core/db/test_utc_datetime.py` |
| NFR-10 | **Reproducibility of a run.** An evaluation shall record what produced it | `model_name`, `prompt_version`, `graph_version`, and the verbatim raw response | `tests/core/scoring/test_ai_runs.py` |
| NFR-11 | **Setup cost.** A clone shall reach a populated system in one command | `make seed && make run`; SQLite means no server and no credentials | manual — MT-15 |
| NFR-12 | **Privacy of student text.** No identity shall reach the model | Identity is stripped in the graph's `prepare` node, before the first token leaves the process | `tests/core/ai/test_guards.py` |
| NFR-13 | **Scoping helpers are scoped too.** A public function that *builds* a query decides access as much as one that runs it | The actor-contract test flags any public `core/` function returning a `Select` without an actor; exemptions must state a reason | `tests/core/test_actor_contract.py` |

---

## 3. Traceability to objectives

| Objective | Requirements |
|---|---|
| O1 | FR-12, FR-13, FR-14 |
| O2 | FR-15, FR-16 |
| O3 | FR-17, FR-18, FR-19, FR-21 |
| O4 | FR-33, FR-34, FR-35, FR-37, FR-40 |
| O5 | FR-22 – FR-27, NFR-4 |
| O6 | FR-28 – FR-32, FR-51 |
| O7 | FR-46 – FR-49 |
| O8 | FR-41 – FR-44 |
| O9 | FR-40, FR-51, FR-52, NFR-5 |
| O10 | FR-53 – FR-60 |
| O11 | FR-61 – FR-66 |

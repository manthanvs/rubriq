# RubriQ

**Rubric-driven, AI-assisted project review for PCCOE.**

The rubric already exists in every project course. The problem is that the
student usually sees it *after* they have been marked, and the reasoning behind
a mark is never written down. RubriQ moves the rubric to the front: faculty
publish it before submission opens, the system drafts a score against it with a
line quoted from the student's own document as evidence, and a faculty member
checks and approves before anything becomes a mark.

The name is *rubric* + *IQ*. The ordering is deliberate — the rubric is the
authority, the intelligence is assistive.

| | |
|---|---|
| Student | Manthan Sankpal (PRN 125M1H064) |
| Course | MCA Semester III — Mini Project, MCA33EL03 |
| Guide | Prof. Dr. Anjana Arakerimath (HOD) |
| Institute | Pimpri Chinchwad College of Engineering, Pune |
| Tests | 646, all passing |

---

## Running it

Needs Python 3.12+. Nothing else — no database server, no Docker, no
credentials to obtain before it will start.

```bash
python -m venv .venv
.\.venv\Scripts\activate          # Windows;  source .venv/bin/activate elsewhere
pip install -r requirements.txt

make seed && make run             # or:  .\make.ps1 seed  then  .\make.ps1 run
```

`make seed` creates the config, runs the migrations, and builds a demo cohort.
`make run` serves the app at <http://localhost:8501>.

Sign-in needs Google OIDC configured — see
[`docs/deployment.md`](docs/deployment.md) §4. To look around before setting
that up, uncomment the `[dev]` block in `.streamlit/secrets.toml`; it still
goes through the real domain and role checks, and the app shows a warning
banner the whole time it is on.

## What it does

- Faculty author a rubric per review, validated to sum to 100, and **publish it
  so it freezes** — editing a published rubric creates v2 and leaves v1 intact
- Students see that rubric **before** uploading, and are told what submitting
  late will cost **before** they confirm
- Submissions are versioned; text is extracted at upload so nothing downstream
  reads a file
- AI drafts a per-criterion score, each one quoting the submission. **Any quote
  that is not actually in the document is rejected** and recorded as having no
  evidence
- Late penalties and absence come from a rule table, computed in Python — the
  model is never asked to do arithmetic that decides a mark
- Nothing is final until a named faculty member approves it; every override
  carries a reason and clears the approval
- Groups exist only where faculty granted them, and a member can be marked
  apart from their group with a recorded reason
- Export to Excel and to a pasteable form, carrying the same numbers as the
  screen

## The one architectural rule

All domain logic lives in `core/` as plain Python with **zero Streamlit
imports**. `app/` is a thin view layer that calls it.

```
app/     pages, components       may import streamlit · computes no marks
core/    auth · academics · rubrics · submissions · scoring · ai · exports
         ZERO streamlit imports · every function takes `actor` first
```

It is enforced by a test that searches every file under `core/` for a Streamlit
import and fails if it finds one. That rule is why 607 of the 646 tests need no
browser at all, why access control is a property of a function signature rather
than something the UI is trusted to do, and why the answer to *"why not a real
web framework?"* is "swap `app/` and keep the rest" rather than a shrug.

Two more tests guard the design rather than the behaviour: one reflects over
every public function in `core/` and fails any whose signature does not begin
with the acting user, and one asserts the page-list builder directly — so "a
student cannot reach a faculty page" is proved by a unit test, not by clicking.

## Layout

```
core/      domain logic, no interface code
app/       Streamlit pages and shared components
tests/     mirrors core/, plus interface and documentation checks
docs/      the SDLC document set
alembic/   migrations, one per schema-bearing phase
scripts/   seed the demo, build the synopsis and report
```

## Documentation

Everything in [`docs/`](docs/) is kept in step with the code — the requirement
tables name the module *and* the test for each row, and
`tests/test_docs_claims.py` fails the build when a document names a file that
no longer exists or quotes a test count that no longer matches.

| | |
|---|---|
| [Synopsis](docs/synopsis.md) | Problem, objectives, scope with explicit in/out lists |
| [Requirements](docs/requirements.md) | 74 functional, 13 non-functional, each traced to code and a test |
| [SRS](docs/srs.md) | Assumptions, constraints, interfaces |
| [Design](docs/design.md) | The reasoning, plus six diagrams in [`docs/diagrams/`](docs/diagrams/) |
| [Implementation](docs/implementation.md) | Module-by-module |
| [Testing](docs/test-cases.md) | Coverage, a manual table with real results, and a defect log |
| [Deployment](docs/deployment.md) | Setup, and why it is not hosted |
| [Limitations](docs/limitations.md) | Honest limits and future scope |

[`CLAUDE.md`](CLAUDE.md) is the working specification the code was written
against — invariants, build phases, and the design decisions with their
reasoning.

## Commands

```bash
make test          # 646 tests
make lint          # ruff
make seed          # build the demo cohort
make reseed        # wipe and rebuild it
make migrate       # alembic upgrade head
make synopsis      # docs/report/RubriQ_Synopsis.docx
make report        # docs/report/RubriQ_Report.docx
```

On Windows without `make`, `.\make.ps1 <target>` mirrors every one of them.

## What it deliberately does not do

Stated here so it is not mistaken for an omission: no plagiarism detection, no
executing or compiling student code, no mobile app, no LMS integration, no
multi-institution tenancy, no hosted deployment with real student data, and
**nothing fetches a linked repository** — a GitHub URL is recorded and checked
against an account the guide registered, never downloaded.

The reasoning for each is in [`docs/limitations.md`](docs/limitations.md).

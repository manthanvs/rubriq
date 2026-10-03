# Architecture Diagram

One Streamlit process, split in two. The dividing line is the only
architectural rule in the project, and it is enforced by a test
([`tests/core/test_no_streamlit_in_core.py`](../../tests/core/test_no_streamlit_in_core.py))
that greps every file under `core/` for a Streamlit import.

```mermaid
flowchart TB
    subgraph browser["Browser"]
        UI["Streamlit UI"]
    end

    subgraph app["app/ — view layer (may import streamlit)"]
        direction TB
        MAIN["main.py<br/><i>auth gate · st.navigation</i>"]
        NAV["navigation.py"]
        CTX["context.py<br/><i>current_actor() · db()</i>"]
        STATE["state.py<br/><i>cache scope · flash</i>"]

        subgraph pages["pages/"]
            FP["faculty/<br/>dashboard · subjects · rubric_builder<br/>calendar · review_grid · query_inbox<br/>reports · activity"]
            SP["student/<br/>dashboard · calendar · submit<br/>feedback · ask"]
        end

        subgraph comps["components/"]
            CMP["calendar · rubric_view<br/>review_grid · ai_runner"]
        end
    end

    subgraph core["core/ — domain (ZERO streamlit imports)"]
        direction TB
        AUTH["auth/<br/><i>domain assertion · role resolution · page policy</i>"]
        ACAD["academics/<br/><i>subjects · enrolment · milestones</i>"]
        RUB["rubrics/<br/><i>versioning · weight validation</i>"]
        SUB["submissions/<br/><i>storage · extraction · versioning</i>"]
        SCORE["scoring/<br/><b>engine.py — all mark arithmetic</b><br/>policy · sheets · grid · ai_runs"]
        AI["ai/<br/><i>the only place langgraph or an<br/>LLM SDK may be imported</i>"]
        QRY["queries/"]
        REP["reports/"]
        EXP["exports/<br/><i>rows → tsv + xlsx</i>"]
        AUD["audit.py · audit_read.py"]
        DB["db/<br/><i>engine · models · types</i>"]
    end

    subgraph outside["Outside the process"]
        SQLITE[("rubriq.db<br/>SQLite + WAL")]
        CKPT[("ai_checkpoints.db<br/>LangGraph SqliteSaver")]
        FILES[("uploads/")]
        GOOGLE[/"Google OIDC"/]
        GEMINI[/"Gemini API"/]
    end

    UI <--> MAIN
    MAIN --> NAV --> pages
    pages --> comps
    pages --> CTX
    pages --> STATE
    CTX --> AUTH

    pages --> ACAD
    pages --> RUB
    pages --> SUB
    pages --> SCORE
    pages --> QRY
    pages --> REP
    pages --> EXP
    comps --> AI

    ACAD --> DB
    RUB --> DB
    SUB --> DB
    SCORE --> DB
    QRY --> DB
    REP --> DB
    EXP --> SCORE
    QRY --> AI
    SCORE -.->|"persists results of"| AI

    ACAD --> AUD
    RUB --> AUD
    SUB --> AUD
    SCORE --> AUD
    QRY --> AUD
    AUD --> DB

    DB --> SQLITE
    SUB --> FILES
    AI --> CKPT
    AI --> GEMINI
    MAIN --> GOOGLE
```

## Why the split is drawn here

| Rule | Consequence |
|---|---|
| `core/` may not import Streamlit | The domain is unit-testable without a browser or a session, which is why 606 of the 645 tests need no Streamlit runtime |
| `app/` may not do mark arithmetic | There is one place a total can be computed, so the grid, the exporters, and the reports page cannot disagree |
| Only `core/ai/` may import LangGraph or an LLM SDK | Callers see three plain functions; the graph is an implementation detail that can be replaced without touching a page |
| Only `core/db/` knows the dialect | Changing database engine is a URL change |
| Every public function in `core/` takes `actor` first | Scoping is a signature-level requirement, checked by reflection, not a convention people remember |

## The two databases

They are deliberately separate files.

* `rubriq.db` holds marks. It is the artifact that would be copied into the
  report appendix.
* `ai_checkpoints.db` holds LangGraph's per-thread graph state.

A corrupt checkpoint can be deleted outright — the worst case is that an
evaluation re-runs — without touching a single mark. Putting both in one file
would make that recovery impossible.

## Request path, end to end

1. Streamlit reruns the script. `main.py` loads settings from `st.secrets`.
2. Claims arrive from Google OIDC (or the gitignored local dev stand-in).
3. `authenticate()` asserts the `@pccoepune.org` domain and resolves the role
   from the allow-list. **This happens on every rerun**, from settings, never
   from `session_state`.
4. `build_navigation(actor)` constructs `st.Page` objects for that role only.
   A page a student may not open is never built, so there is nothing to reach.
5. The page calls into `core/` with `actor` as the first argument. Scoping
   happens in the SQL `WHERE` clause.
6. Mutations run inside one transaction that also writes an audit row.
7. The page invalidates the actor-scoped cache and reruns.

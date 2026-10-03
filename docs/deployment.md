# RubriQ — Deployment and Setup

---

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12+ | Developed on 3.14 |
| `git` | To clone |
| Nothing else | No database server, no Docker, no Node, no credentials to obtain before it will run |

The last row is a design decision, not a coincidence — see
[decision #8](../CLAUDE.md#13-open-decisions). SQLite makes the database a file
that can be copied, inspected, and shipped with the report.

---

## 2. Local setup

```bash
git clone <repo-url> rubriq
cd rubriq

python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Then, in one command:

```bash
make seed && make run
```

`make seed` creates `.streamlit/secrets.toml` if it is missing, runs
`alembic upgrade head`, and builds the demo dataset. `make run` starts the app
at <http://localhost:8501>.

`make` is not installed on the Windows development machine, so a PowerShell
mirror with the same target names is checked in:

```powershell
.\make.ps1 seed
.\make.ps1 run
```

Both files must be kept in step.

### Available targets

| Target | Does |
|---|---|
| `install` | `pip install -r requirements.txt` |
| `run` | Start the Streamlit app |
| `test` | Run pytest |
| `lint` | `ruff check` over `core app tests alembic scripts` |
| `fmt` | `ruff check --fix` then `ruff format` |
| `migrate` | `alembic upgrade head` |
| `revision` | `alembic revision --autogenerate -m "…"` |
| `seed-faculty` | Seed only the faculty allow-list into `users` |
| `seed` | Build the demo dataset |
| `reseed` | Wipe demo rows and rebuild |

---

## 3. Configuration

Everything lives in `.streamlit/secrets.toml`, which is **gitignored**.
`.streamlit/secrets.toml.example` is the committed template.

```toml
[database]
# Omitted on purpose: RubriQ defaults to a SQLite file at the repo root.
echo_sql = false

[rubriq]
allowed_email_domain = "pccoepune.org"
faculty_allowlist = [
    "guide@pccoepune.org",
]

[auth]                       # Google OIDC — see §4
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "…"
client_id = "…"
client_secret = "…"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
client_kwargs = { hd = "pccoepune.org" }

[llm]                        # optional — everything else works without it
provider = "gemini"
api_key = "…"
model = "gemini-3.6-flash"
```

**No secret belongs in the repository.** Fill these in locally. If a key is
ever pasted anywhere it could be logged — a terminal, a chat window, a commit —
rotate it rather than assuming it was not captured.

### Without an LLM key

The app runs. AI evaluation reports that it is unavailable, and manual
scoring, penalties, approval, the calendar, reports, and both exports work
unchanged. This is invariant #10 and it is worth demonstrating deliberately:
pull the key, reload, and show the system still doing its job.

### Local development sign-in

Before Google credentials exist, an optional block supplies claims directly:

```toml
[dev]
impersonate = "guide@pccoepune.org"
name = "Dr. Anjana Arakerimath"
```

It routes through `authenticate()` like a real Google response, so the domain
assertion and the allow-list still apply — a `@gmail.com` address here is
still refused. The app shows a persistent warning banner while it is active.

**Delete this section before any demo.** It is absent from the committed
example and `scripts/seed_demo.py` writes it commented out.

---

## 4. Google OIDC setup

1. In the Google Cloud console, create an OAuth 2.0 **Web application** client.
2. Add `http://localhost:8501/oauth2callback` as an authorised redirect URI.
3. Copy the client id and secret into `[auth]`.
4. Generate a `cookie_secret` — any long random string.
5. `client_kwargs = { hd = "pccoepune.org" }` pre-filters the account chooser.

The `hd` hint is a convenience only. The actual restriction is asserted
server-side from the returned `email` claim in `core/auth/domain.py`, so a
user who works around the hint is still refused.

---

## 5. Database and migrations

The schema is created by Alembic, never by `create_all` outside tests.

```bash
make migrate                          # alembic upgrade head
make revision M="what changed"        # autogenerate a new revision
```

Two notes learned the hard way:

* **Check the exit code.** Piping `alembic` through `grep` takes the
  pipeline's exit status from `grep`, so a broken migration can look applied.
* **Never run `alembic downgrade` against the development database** to test a
  migration. Point it at a throwaway file. Doing otherwise cost a rebuild of
  the Phase 2 demo data.

`alembic/env.py` carries a `render_item` hook so autogenerate emits the custom
`UtcDateTime` type correctly, and `render_as_batch=True` because SQLite cannot
`ALTER` a column in place.

---

## 6. Files on disk

| Path | Contents | In git? |
|---|---|---|
| `rubriq.db` | The application database | No — `*.db` is ignored |
| `ai_checkpoints.db` | LangGraph graph state | No |
| `uploads/` | Submitted files, one directory per submission version | No |
| `.streamlit/secrets.toml` | Configuration and keys | No |
| `.streamlit/secrets.toml.example` | The template | Yes |
| `docs/test-report.txt` | The pytest run | Yes |

Uploaded files live outside the database on purpose: SQLite handles the
metadata well and multi-megabyte blobs badly, and a file on disk can be opened
during a viva without a query.

---

## 7. Deployment

**Streamlit Community Cloud** is the natural host: point it at the repository,
paste the secrets into its UI, and it serves the app.

There are two different questions here, and collapsing them produces a bad
answer to both.

### 7.1 Production, with real student data — not done, deliberately

Three reasons, worth stating plainly rather than glossing:

1. **SQLite on Community Cloud is ephemeral.** The filesystem is not durable
   across restarts or redeploys. Marks would disappear, which for a system
   whose entire purpose is recording marks is disqualifying. Real deployment
   would mean a managed Postgres — a URL change, since nothing outside
   `core/db/` knows the dialect, plus reinstating `psycopg`.
2. **Real student data.** Names, PRNs, and submitted work are personal data.
   Putting them on a free tier of a third-party host without an institutional
   decision is not the student's call to make.
3. **The LLM key.** A key in a public deployment's secrets is a key with a
   billing account attached to it.

What production would take: provision managed Postgres and set
`[database] url`; `pip install psycopg[binary]`; `alembic upgrade head`
against it; move uploads to object storage, where
`core/submissions/storage.py` is the only module that touches the filesystem;
register the deployed callback URL with the Google OAuth client.

### 7.2 A demo deployment, with seeded data — supported

Every objection above is an objection to hosting *real marks*. A deployment
carrying only the seeded demo cohort meets none of them: there is no personal
data to leak, an ephemeral filesystem is no loss when the database is rebuilt
from seed anyway, and the LLM key can simply be omitted — AI evaluation then
reports that it is unavailable and everything deterministic still works, which
is invariant #10 demonstrated rather than described.

One thing had to be built for this to work at all. The host runs
`streamlit run app/main.py` and nothing else: there is no shell, so `make seed`
never happens and the app would start against a database that does not exist.
`app/bootstrap.py` closes that — it migrates on first boot and seeds the demo
cohort if no user exists yet.

It is **off unless `[deploy] bootstrap` is true**, and it refuses to touch a
database that already holds a user. Both guards matter and neither is
redundant: the emptiness check is what stops a redeploy dropping demo rows
onto real marks, and the flag is what stops that check from being the only
thing standing in the way. `tests/app/test_bootstrap.py` asserts both
negatives.

**Steps**

1. Push to GitHub — Community Cloud deploys from a repository, not an upload.
2. At <https://share.streamlit.io>, sign in with GitHub and create an app from
   `manthanvs/rubriq`, branch `main`, main file path `app/main.py`.
3. Paste the contents of `.streamlit/secrets.toml` into **Advanced settings →
   Secrets**, with these changes:
   - add `[deploy]` with `bootstrap = true`
   - set `[auth] redirect_uri` to `https://<your-app>.streamlit.app/oauth2callback`
   - omit the `[llm]` section unless a throwaway key with a spend cap is used
   - keep `[rubriq] faculty_allowlist` — its first address owns the seeded
     subject
4. In the Google Cloud console, add that same `https://…/oauth2callback` as an
   authorised redirect URI on the OAuth client. The deployed URL is a second
   URI, not a replacement: keep `http://localhost:8501/oauth2callback` so local
   development still works.
5. While the OAuth consent screen is in **Testing**, add every address that
   will sign in under **Audience → Test users**. An address that is not listed
   fails with `access_denied` before RubriQ sees it, so this looks like an app
   bug and is not one.
6. Open the app. The first load migrates and seeds, which takes a few seconds
   and shows a toast saying what it created.

**Set `bootstrap = false` again once it has run.** It is idempotent, so leaving
it on is survivable, but a flag that only needed to be true once should not
stay true.

---

## 8. Demonstration script

The order that shows the most in the least time.

| Step | Do | Shows |
|---|---|---|
| 1 | `make reseed && make run` | Setup cost is one command |
| 2 | Faculty Dashboard | Owned subjects, needs-attention count, waiting question |
| 3 | Rubric Builder — try to edit the published rubric | Immutability; the clone-to-v2 path |
| 4 | Review Grid | The centrepiece: verdicts, penalties, `ABSENT` as a status, a non-submitter with a row |
| 5 | Open a row's drawer | Evidence span, rationale, override-with-reason, approval blocked on an unevidenced mandatory criterion |
| 6 | "Approve all eligible" | The excluded count and its reason, *before* confirming |
| 7 | Download the `.xlsx`, open it | A real spreadsheet with the same numbers as the screen |
| 8 | Reports | Distribution, weakest criterion, absence excluded from the mean |
| 9 | Sign in as a student | Rubric before upload, lateness consequence, feedback gated on approval |
| 10 | Ask RubriQ an out-of-scope question | Escalation instead of invention |
| 11 | Activity | Who changed what, when, and why |

If the network is unavailable, steps 1–11 all still work. Only a live AI
evaluation would not, and its absence is itself a demonstration of
invariant #10.

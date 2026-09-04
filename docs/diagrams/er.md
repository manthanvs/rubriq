# Entity–Relationship Diagram

Nineteen tables, defined in [`core/db/models.py`](../../core/db/models.py) and
created by the migrations in [`alembic/versions/`](../../alembic/versions/).
Attribute lists below are the columns that carry meaning; timestamps and
`is_active` flags are omitted where they say nothing about the relationship.

Three things in this diagram are load-bearing and are easy to miss:

* **`evaluation` pins its inputs.** It stores `submission_version` and
  `rubric_version` as values, not just foreign keys, so re-evaluating cannot
  retroactively change what an approved mark was measured against.
* **`score_sheet` references an `evaluation`, never a bare submission.** A
  sheet is always the consequence of one specific evaluation run.
* **`verdict` lives on `criterion_score` as its own column.** It is stored,
  not derived from the score when rendering — that is what makes "followed
  versus not followed" answerable.

```mermaid
erDiagram
    USERS ||--o{ SUBJECT : owns
    USERS ||--o{ ENROLLMENT : "is enrolled by"
    USERS ||--o{ SUBMISSION : submits
    USERS ||--o{ STUDENT_QUERY : asks
    USERS ||--o{ AUDIT_LOG : acts

    SUBJECT ||--o{ ENROLLMENT : has
    SUBJECT ||--o{ PROJECT_CYCLE : runs
    PROJECT_CYCLE ||--o{ REVIEW_MILESTONE : contains
    REVIEW_MILESTONE ||--o{ RUBRIC : "is graded by"
    REVIEW_MILESTONE ||--o{ SUBMISSION : receives
    REVIEW_MILESTONE ||--o{ STUDENT_QUERY : "is asked about"

    RUBRIC ||--o{ CRITERION : contains
    SUBMISSION ||--o{ SUBMISSION_FILE : stores
    SUBMISSION ||--o{ EVALUATION : "is evaluated by"
    RUBRIC ||--o{ EVALUATION : "is applied in"

    EVALUATION ||--o{ CRITERION_SCORE : produces
    CRITERION ||--o{ CRITERION_SCORE : "is scored as"
    EVALUATION ||--|| SCORE_SHEET : "totals into"
    SCORE_SHEET ||--o{ SCORE_OVERRIDE : "is corrected by"
    CRITERION ||--o{ SCORE_OVERRIDE : "is corrected on"

    USERS {
        string  email PK
        string  role "STUDENT | FACULTY | ADMIN"
        string  name
        string  department
        string  prn
        string  employee_id
    }

    SUBJECT {
        int     id PK
        string  code
        string  name
        int     semester
        string  owner_email FK
    }

    ENROLLMENT {
        int     id PK
        string  student_email FK
        int     subject_id FK
        string  batch
        string  group_label
    }

    PROJECT_CYCLE {
        int     id PK
        int     subject_id FK
        string  title
        string  academic_year
    }

    REVIEW_MILESTONE {
        int      id PK
        int      cycle_id FK
        int      index
        string   title
        text     description
        text     public_notes
        datetime due_at
        decimal  max_marks
        bool     is_visible
    }

    RUBRIC {
        int      id PK
        int      milestone_id FK
        int      version
        datetime published_at "NULL until frozen"
        string   published_by FK
    }

    CRITERION {
        int     id PK
        int     rubric_id FK
        string  code
        string  title
        decimal weight
        decimal max_score
        text    expected_evidence
        bool    is_mandatory
        int     order_index
    }

    SUBMISSION {
        int      id PK
        int      milestone_id FK
        string   student_email FK
        int      version
        string   status
        datetime submitted_at
        text     text_extract
    }

    SUBMISSION_FILE {
        int    id PK
        int    submission_id FK
        string filename
        string stored_path
        string sha256
        int    extracted_chars
        string extract_note
    }

    EVALUATION {
        int    id PK
        int    submission_id FK
        int    submission_version "pinned"
        int    rubric_id FK
        int    rubric_version "pinned"
        int    version
        string engine "AI | MANUAL"
        string status "PENDING|RUNNING|COMPLETE|FAILED"
        string model_name
        string prompt_version
        string graph_version
        json   raw_response "stored verbatim"
        text   failure_reason
    }

    CRITERION_SCORE {
        int     id PK
        int     evaluation_id FK
        int     criterion_id FK
        decimal score
        string  verdict "FOLLOWED|PARTIAL|NOT_FOLLOWED|NO_EVIDENCE"
        decimal confidence
        text    evidence_span
        text    rationale
    }

    SCORE_SHEET {
        int      id PK
        int      evaluation_id FK
        int      submission_id FK
        decimal  max_marks
        decimal  weighted_percent
        decimal  base_total
        decimal  penalty
        decimal  final_total
        int      days_late
        string   attendance_status
        bool     reinstated
        text     reinstate_reason
        string   approved_by FK
        datetime approved_at
        text     faculty_note
    }

    SCORE_OVERRIDE {
        int      id PK
        int      score_sheet_id FK
        int      criterion_id FK
        decimal  old_score
        decimal  new_score
        string   old_verdict
        string   new_verdict
        text     reason "non-empty, enforced in core"
        string   overridden_by FK
        datetime overridden_at
    }

    LATE_POLICY {
        int    id PK
        string scope "SUBJECT | MILESTONE"
        int    scope_id
        json   rules
        int    version
    }

    STUDENT_QUERY {
        int      id PK
        string   student_email FK
        int      milestone_id FK
        text     question
        text     ai_answer
        json     sources
        bool     escalated
        text     faculty_reply
        string   replied_by FK
        datetime replied_at
    }

    AUDIT_LOG {
        int      id PK
        string   actor_email
        string   action
        string   entity
        string   entity_id
        json     payload
        datetime at
    }
```

## Key constraints

These are the ones that carry a rule rather than tidiness.

| Constraint | Table | Why it exists |
|---|---|---|
| `UNIQUE (milestone_id, student_email, version)` | `submission` | Two v2s from the same student would make "which one was graded" unanswerable |
| `UNIQUE (submission_id, version)` | `evaluation` | A retry must produce a *new* version, not a second row at the same one |
| `UNIQUE (evaluation_id)` | `score_sheet` | One evaluation totals into exactly one sheet |
| `UNIQUE (evaluation_id, criterion_id)` | `criterion_score` | One score per criterion per run |
| `UNIQUE (milestone_id, version)` | `rubric` | Version numbering is the immutability mechanism |
| `UNIQUE (rubric_id, code)` | `criterion` | `C1` must mean one thing within a rubric version |
| `UNIQUE (student_email, subject_id)` | `enrollment` | Makes re-running a CSV import idempotent |
| `UNIQUE (cycle_id, index)` | `review_milestone` | "Review 1" is a single milestone |
| `UNIQUE (code, semester)` | `subject` | A subject code is unique within a semester |
| `UNIQUE (scope, scope_id, version)` | `late_policy` | One policy version per scope |
| `FOREIGN KEYS = ON` | connection pragma | SQLite does not enforce foreign keys by default; without this the referential structure above is decorative |

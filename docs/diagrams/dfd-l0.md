# Data Flow Diagram — Level 0 (Context)

RubriQ as a single process, and everything outside it.

```mermaid
flowchart LR
    STUDENT([Student])
    FACULTY([Faculty])
    GOOGLE[/"Google OIDC"/]
    LLM[/"Gemini API"/]

    SYSTEM(("0<br/>RubriQ<br/>Review System"))

    STUDENT -->|"submission files,<br/>questions"| SYSTEM
    SYSTEM -->|"published rubric, deadline,<br/>approved feedback,<br/>assistant answer"| STUDENT

    FACULTY -->|"subjects, enrolment CSV,<br/>rubrics, scores, overrides,<br/>approvals, replies"| SYSTEM
    SYSTEM -->|"review grid, estimates,<br/>evidence, reports,<br/>Excel and TSV export"| FACULTY

    GOOGLE -->|"email and name claims"| SYSTEM
    SYSTEM -->|"sign-in request<br/>(hd=pccoepune.org)"| GOOGLE

    SYSTEM -->|"rubric + de-identified<br/>submission text"| LLM
    LLM -->|"per-criterion JSON:<br/>verdict, score,<br/>evidence, rationale"| SYSTEM
```

## Notes on the flows

* **Nothing identifying crosses the boundary to the model.** The arrow to the
  Gemini API carries rubric text and submission text with the student's name,
  PRN, and email removed (`core/ai/identity.py`). The mapping back is held
  inside the process.
* **The model returns a proposal, never a mark.** Everything on that return
  arrow is an estimate until a faculty member approves it.
* **Google is asked for identity, not for authorisation.** The domain check
  and the role lookup both happen inside the system, from the returned email
  claim.
* **The Gemini arrow is optional.** Remove it and the diagram still describes
  a working system: manual scoring, penalties, approval, and export are
  untouched.

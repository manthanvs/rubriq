# Data Flow Diagram — Level 1

Process 0 from [`dfd-l0.md`](dfd-l0.md), opened up. Seven processes and six
data stores.

```mermaid
flowchart TB
    STUDENT([Student])
    FACULTY([Faculty])
    GOOGLE[/"Google OIDC"/]
    LLM[/"Gemini API"/]

    P1(("1.0<br/>Authenticate<br/>& resolve role"))
    P2(("2.0<br/>Manage subjects,<br/>enrolment,<br/>milestones"))
    P3(("3.0<br/>Author &<br/>publish rubric"))
    P4(("4.0<br/>Accept<br/>submission"))
    P5(("5.0<br/>Evaluate<br/>against rubric"))
    P6(("6.0<br/>Score, approve<br/>& export"))
    P7(("7.0<br/>Answer<br/>student query"))

    D1[("D1  users")]
    D2[("D2  subjects · enrolment · milestones")]
    D3[("D3  rubrics · criteria")]
    D4[("D4  submissions · files · text")]
    D5[("D5  evaluations · criterion scores · sheets · overrides")]
    D6[("D6  audit log")]

    GOOGLE -->|claims| P1
    P1 -->|"upsert user"| D1
    D1 -->|"role"| P1
    P1 -->|"actor"| P2
    P1 -->|"actor"| P4

    FACULTY --> P2
    P2 <--> D2
    P2 -->|"enrolment preview<br/>and verdicts"| FACULTY

    FACULTY --> P3
    P3 <--> D3
    D2 -->|"milestone"| P3

    STUDENT -->|"files"| P4
    D3 -->|"published rubric,<br/>shown before upload"| STUDENT
    P4 -->|"extracted text,<br/>new version"| D4
    D2 -->|"due_at"| P4
    P4 -->|"days late and<br/>the penalty it implies"| STUDENT

    D4 -->|"text_extract"| P5
    D3 -->|"criteria"| P5
    P5 -->|"de-identified<br/>rubric + text"| LLM
    LLM -->|"criterion JSON"| P5
    P5 -->|"verified scores,<br/>rejections,<br/>raw response"| D5

    D5 --> P6
    D2 -->|"due_at, max_marks"| P6
    FACULTY -->|"manual scores,<br/>overrides, approval"| P6
    P6 -->|"score sheet,<br/>approved_by/at"| D5
    P6 -->|"grid, xlsx, tsv"| FACULTY
    P6 -->|"feedback,<br/>after approval only"| STUDENT

    STUDENT -->|"question"| P7
    D3 -->|"published rubric"| P7
    D2 -->|"description,<br/>public notes"| P7
    P7 -->|"answer or escalation"| LLM
    P7 -->|"query row"| D5
    P7 -->|"escalated queue"| FACULTY

    P2 --> D6
    P3 --> D6
    P4 --> D6
    P5 --> D6
    P6 --> D6
    P7 --> D6
```

## Reading the diagram

**Every process writes to D6.** That is not diagram clutter — it is invariant:
every mutation writes exactly one audit row inside the same transaction as the
change. Streamlit gives no request log worth reading, so this store is the
only record of who did what.

**Process 5.0 reads D4 and D3 but never writes to them.** The evaluation
process consumes a submission's text and a rubric's criteria and produces
scores. It cannot modify either, and it has no path to D1 or D2 at all — which
is what "the graph has no tools" means concretely.

**Process 6.0 is the only writer of a total.** Processes 5.0 and 7.0 produce
verdicts and answers; the arithmetic that turns criterion scores into a mark
happens in one place, fed by D5 and by the milestone's `due_at` and
`max_marks` from D2.

**The rubric reaches the student from D3 before 4.0 accepts anything.** That
arrow is the whole thesis of the system, so it is drawn even though it is a
read rather than a process output.

**D5 holds student queries** alongside evaluation rows. They are grouped here
because both are per-student outputs of an AI process with a faculty
follow-up; in the schema they are separate tables.

# Use-Case Diagram

Two human actors and two external systems. The dashed `<<include>>` arrows are
the ones worth pointing at in a viva: they are where the invariants sit.

```mermaid
flowchart LR
    subgraph actors[" "]
        direction TB
        S([Student])
        F([Faculty])
    end

    subgraph system["RubriQ"]
        direction TB

        UC1(["Sign in with<br/>institute account"])
        UC2(["Create subject<br/>and cycle"])
        UC3(["Import enrolment<br/>from CSV"])
        UC4(["Define review<br/>milestone"])
        UC5(["Author rubric"])
        UC6(["Publish rubric"])
        UC7(["View published<br/>rubric"])
        UC8(["Submit work"])
        UC9(["Run AI<br/>evaluation"])
        UC10(["Review and<br/>override scores"])
        UC11(["Approve<br/>score sheet"])
        UC12(["Export to<br/>Excel / TSV"])
        UC13(["Ask about<br/>a milestone"])
        UC14(["Answer escalated<br/>question"])
        UC15(["View feedback"])
        UC16(["View reports"])
        UC17(["Reinstate an<br/>absent student"])
        UC18(["Browse<br/>activity log"])

        UCa(["Assert institute<br/>domain & role"])
        UCb(["Validate weights<br/>sum to 100"])
        UCc(["Extract text<br/>from files"])
        UCd(["Verify evidence<br/>against text"])
        UCe(["Strip student<br/>identity"])
        UCf(["Apply late /<br/>absence policy"])
        UCg(["Write audit row"])
    end

    GOOGLE[/Google OIDC/]
    LLM[/Gemini API/]

    S --- UC1
    S --- UC7
    S --- UC8
    S --- UC13
    S --- UC15

    F --- UC1
    F --- UC2
    F --- UC3
    F --- UC4
    F --- UC5
    F --- UC6
    F --- UC9
    F --- UC10
    F --- UC11
    F --- UC12
    F --- UC14
    F --- UC16
    F --- UC17
    F --- UC18

    UC1 -.->|include| UCa
    UC1 --- GOOGLE
    UC6 -.->|include| UCb
    UC8 -.->|include| UCc
    UC9 -.->|include| UCe
    UC9 -.->|include| UCd
    UC9 --- LLM
    UC13 --- LLM
    UC11 -.->|include| UCf
    UC11 -.->|include| UCg
    UC10 -.->|include| UCg
    UC17 -.->|include| UCg
    UC6 -.->|include| UCg
    UC3 -.->|include| UCg
```

## Principal use cases

| Use case | Actor | Precondition | Postcondition |
|---|---|---|---|
| Publish rubric | Faculty | Draft exists, weights sum to 100, at least one criterion | The version is frozen and becomes selectable for evaluation; an audit row is written |
| Submit work | Student | The milestone is visible and the student is enrolled | A new submission version exists with its text extracted; the student has been told the lateness consequence |
| Run AI evaluation | Faculty | A published rubric and at least one submission exist; a provider key is configured | Each criterion has a verdict and a verified evidence span, or is `NO_EVIDENCE`; the raw response is stored |
| Approve score sheet | Faculty | The evaluation is `COMPLETE` and no mandatory criterion is unresolved | `final_total`, `approved_by`, and `approved_at` are stamped in one transaction; the student's feedback becomes visible |
| Override a score | Faculty | A score sheet exists and a non-empty reason is supplied | An append-only override row is written, the total is recomputed, and the approval is cleared so someone must sign it off again |
| Reinstate an absent student | Faculty | The sheet is `ABSENT` or more than five days late, and a reason is supplied | The penalty is zeroed, a badge carrying the reason is shown, and an audit row is written |
| Ask about a milestone | Student | The milestone has a published rubric | Either an answer sourced from the rubric context, or an escalation with no invented answer |

## Excluded by design

These are not missing; they are refused.

| Not a use case | Why |
|---|---|
| Student selects their own role | Role is resolved server-side from an allow-list (invariant #5) |
| Student views another student's submission or mark | Scoped in SQL, and asserted by a reflection test over `core/**` (invariant #6) |
| AI publishes a mark | Approval is a separate, human, named act (invariant #1) |
| Faculty edits a published rubric in place | Editing clones to v+1; v stays byte-identical (invariant #7) |
| Anyone hard-deletes a submission or evaluation | Everything is append-only and versioned (invariant #7) |

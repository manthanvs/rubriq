# RubriQ — Documentation

The SDLC document set for the Mini Project (MCA33EL03). Every document here is
generated from, and kept in step with, the code in this repository — the
requirement tables name the module and the test for each row, so a claim that
has stopped being true is visible rather than plausible.

| Document | Covers |
|---|---|
| [`synopsis.md`](synopsis.md) | Introduction, problem statement, objectives, scope with explicit in/out lists |
| [`requirements.md`](requirements.md) | 74 functional and 13 non-functional requirements, numbered, each traced to code and to a test |
| [`srs.md`](srs.md) | Assumptions, constraints, external interfaces, glossary |
| [`design.md`](design.md) | The reasoning behind the diagrams |
| [`implementation.md`](implementation.md) | Module-wise write-up |
| [`test-cases.md`](test-cases.md) | Automated coverage, a manual test-case table with actual results, and a defect log |
| [`test-report.txt`](test-report.txt) | The verbatim `pytest -v` run |
| [`deployment.md`](deployment.md) | Setup, configuration, the deployment question, and a demonstration script |
| [`limitations.md`](limitations.md) | Honest limits and future scope |

## Diagrams

All in [Mermaid](https://mermaid.js.org), so they render on GitHub and stay
diffable in version control rather than being screenshots nobody can edit.

| Diagram | File |
|---|---|
| Entity–Relationship | [`diagrams/er.md`](diagrams/er.md) |
| DFD Level 0 (context) | [`diagrams/dfd-l0.md`](diagrams/dfd-l0.md) |
| DFD Level 1 | [`diagrams/dfd-l1.md`](diagrams/dfd-l1.md) |
| Use case | [`diagrams/use-case.md`](diagrams/use-case.md) |
| Architecture — the `core/` ↔ `app/` split | [`diagrams/architecture.md`](diagrams/architecture.md) |
| Evaluation state machine | [`diagrams/evaluation-state.md`](diagrams/evaluation-state.md) |

The evaluation state machine stands in for a sequence diagram, deliberately:
the flow has two conditional retry loops, which a state diagram draws exactly
and a sequence diagram draws badly.

## The specification itself

[`../CLAUDE.md`](../CLAUDE.md) is the working specification — invariants,
architecture rules, build phases, the recorded design decisions, and the
pre-registered defect classes in §14. It is the document the code was written
against, and it is worth reading before any of the above.

## Report assembly

`report/` is where the institute-template document goes. The material for it
is the eight documents above, in this order:

1. Introduction, problem statement, objectives, scope → `synopsis.md`
2. Requirement analysis → `requirements.md`
3. SRS → `srs.md`
4. System design → `design.md` and `diagrams/`
5. Implementation → `implementation.md`
6. Testing → `test-cases.md` and `test-report.txt`
7. Deployment → `deployment.md`
8. Limitations and future scope → `limitations.md`

# Report

Both documents here are **generated, never hand-edited**. The eight documents in
[`../`](..) are the source of truth; edit those and rebuild.

| File | Built by | Command |
|---|---|---|
| `RubriQ_Synopsis.docx` | `scripts/build_synopsis_docx.py` | `make synopsis` |
| `RubriQ_Report.docx` | `scripts/build_report_docx.py` | `make report` |

Both use the formatting the department specified for the synopsis — Times New
Roman, 14 pt headings, 12 pt body, 1.5 line spacing, justified.

## Synopsis

Follows the department's own template (`Miniproject_Synopsis.pdf`): title page,
index, sections 1–8, student-details page. **Email** and **Contact No.** are
left blank to be filled in.

## Report

A conventional MCA report structure: title page, certificate, acknowledgement,
abstract, contents, eight chapters and references.

**Check the certificate wording against your department's.** That page is the
one part every institute words its own way; the text in the generator is
deliberately plain so replacing it is a small edit.

## Diagrams

`flow.png`, `architecture.png` and `er.png` are drawn by
`scripts/synopsis_diagram.py` and `scripts/report_diagrams.py` and regenerate
with either command above. The Mermaid originals stay in
[`../diagrams/`](../diagrams) — they diff, and GitHub renders them; Word cannot.

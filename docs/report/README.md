# Report

## Synopsis

[`RubriQ_Synopsis.docx`](RubriQ_Synopsis.docx) — written in the department's own
template (`Miniproject_Synopsis.pdf`): title page, index, sections 1–8, and a
student-details page, set in Times New Roman with 14 pt headings, 12 pt body,
1.5 line spacing and justified text.

It is **generated, never hand-edited**. Regenerate with:

```bash
make synopsis
```

`scripts/build_synopsis_docx.py` holds the text and the layout;
`scripts/synopsis_diagram.py` draws the flow diagram (`flow.png`) that section 5
embeds. Editing the `.docx` directly means the next regeneration silently
discards the change.

Two fields are deliberately left blank for you to fill in by hand or in the
script: **Email** and **Contact No.** on the student-details page.

## The full report

The institute-template report document goes here (`.docx` and its exported
`.pdf`), assembled from the eight documents in [`../`](..) in the order given
in [`../README.md`](../README.md#report-assembly).

# RubriQ — Limitations and Future Scope

An honest account is worth more than a defensive one. Everything below is a
real limit of the system as built, and most of them are consequences of
decisions that were right for the project's constraints.

---

## 1. Concurrency: SQLite permits one writer

**The limit.** SQLite in WAL mode allows many readers alongside one writer.
Two faculty members approving simultaneously will serialise, and a whole
cohort submitting in the same minute would contend. A `busy_timeout` turns a
brief collision into a wait rather than an error, but it does not create
concurrency that the engine does not have.

**Why it was accepted.** A single-guide review panel has no write contention
worth a database server. Postgres would have bought real concurrency and
JSONB, and cost an install, a service, and credentials on every machine the
project has to run on — including whichever one the viva happens on. SQLite
makes the database a file that can be copied, inspected, and shipped with the
report.

**What it would take to lift.** A URL change in `core/db/engine.py` and
reinstating `psycopg`. Nothing outside `core/db/` knows the dialect, so the
change is genuinely that small.

## 2. Streamlit's single-process ceiling

**The limit.** One process serves every session. A long AI evaluation blocks
the session that started it. There is no URL routing, so "send me a link to
this student's review" is not expressible. There is no background worker, so
nothing runs when nobody is looking at the screen.

**Mitigations already in place.** Evaluation is chunked per submission and
persisted after each one; graph state is checkpointed so a rerun resumes
rather than restarting; all reads are cached with an actor-scoped key.

**What it would take to lift.** Replace `app/` with a real web framework.
`core/` is untouched by that change, which is the point of the split — and a
better answer to *"why not a real web framework?"* than a shrug.

## 3. The AI is an estimator, and its confidence is not a probability

**The limit.** The `confidence` a model reports is a self-assessment, not a
calibrated probability. A confident wrong answer and a confident right answer
look identical in that field. Any threshold built on it — including the "bulk
approve above confidence X" action — is a heuristic, not a guarantee.

**Why the system is still defensible.** Confidence is never load-bearing on
its own. The evidence guard runs at *every* confidence with no bypass, no mark
is published without a named human approval, and a mandatory criterion at
`NO_EVIDENCE` blocks approval regardless of how confident anything was.

**Honest framing for the report.** The system does not claim the AI grades
correctly. It claims that every AI-proposed score is traceable to a span in
the student's own document, and that a human decided.

## 4. Evidence verification is lexical, not semantic

**The limit.** `rapidfuzz.partial_ratio ≥ 90` catches a *fabricated* quotation.
It does not catch a real quotation used to support a conclusion it does not
actually support. A model can cite a genuine sentence and draw the wrong
inference from it, and the guard will pass it.

**What the guard does buy.** The most common and most damaging failure —
inventing text that is not in the document — is caught mechanically, and the
rejection rate is measurable. That number is the project's strongest empirical
result precisely because it is measurable.

**Future scope.** Entailment checking: a second pass asking whether the cited
span supports the verdict. That is a research problem, not a feature.

## 5. Text extraction is only as good as the file

**The limit.** A scanned PDF with no text layer extracts to nothing. Diagrams,
screenshots, tables rendered as images, and handwritten annexures are
invisible to the system. For a project report — where the ER diagram and the
DFD are often images — this is not a corner case.

**How it degrades.** Extraction records an `extract_note` rather than failing,
and the affected criteria resolve to `NO_EVIDENCE` and are flagged for
mandatory faculty attention. It does not guess.

**Future scope.** OCR for scanned pages, and a multimodal call that can see a
diagram. The second is the more interesting one for this domain, and the
architecture already allows it — a provider is one method behind a protocol.

## 6. No plagiarism or similarity detection

Out of scope and declared as such. The system says whether a submission
evidences a criterion; it says nothing about whether the submission is the
student's own work. Two identical submissions score identically and the system
will not notice.

### 6a. A repository link is checked for ownership, not for content

Decision #6 verifies that a submitted URL belongs to a GitHub account the guide
recorded. It verifies nothing else. Nothing is fetched, so the system cannot
tell whether the repository contains the project, contains anything at all, or
was created five minutes before the deadline. A student who registers an
account and links an empty repository under it passes the check and is scored
on their document — the intended behaviour rather than a gap, but worth saying
plainly, because "the link was verified" is easy to hear as a stronger claim
than it is.

## 7. Group marking is per-member, but the split is a judgement

Phase 9 closed the original limitation here. A faculty member can now mark one
member of a granted group apart from the rest, as a signed difference from the
group's total, with a reason the student sees. The group's own assessment is
untouched, the adjustment is append-only, and adjusting an approved sheet
clears the approval so someone has to sign it off again.

**What remains a limitation** is that the split is a human judgement with
nothing behind it. The system records *that* a guide decided one member
contributed less, and *why they said* they decided it, but it has no evidence
of contribution to check that against — no commit attribution, no per-section
authorship, nothing. A repository link is recorded but never read (§6a), so
even the obvious source of that evidence is unused. The honest position is that
this feature makes an existing judgement auditable, not measurable.

## 8. One institute, one deployment

There is no tenancy model. Every user in a deployment belongs to one domain,
set by a single configuration key.

## 9. Reproducibility is recorded, not guaranteed

Every evaluation stores `model_name`, `prompt_version`, `graph_version`, and
the verbatim raw response, so a result can be *explained* later. It cannot
necessarily be *reproduced*: the provider is non-deterministic, and models are
retired on the vendor's schedule — `gemini-2.0-flash` was already returning
404 by the time the provider was wired up, which is why the model is
configuration rather than a constant.

## 10. What the tests do and do not prove

584 tests pass, and it is worth being precise about what that means.

**They do prove:** the scoring arithmetic matches §5.1 row by row and at every
boundary; a published rubric cannot be edited; a student cannot reach another
student's data, and a group-mate cannot either until the group is granted;
approval cannot happen without a name; the evidence guard rejects fabricated
spans and accepts reflowed genuine ones; a repository URL owned by anybody but
a registered account is refused before a file is written; the TSV and the XLSX
agree cell for cell; every page renders on an empty database.

**They do not prove:** that a language model's judgement is any good; that
Excel renders the exported file the way it looks in the test; that the system
behaves under a real cohort's concurrent load; that the interface is pleasant
to use. Those need a person, a spreadsheet, a load generator, and users
respectively.

One manual case remains unverified in [`test-cases.md`](test-cases.md): MT-16,
opening the exported `.xlsx` in Excel itself, which needs Excel and a person.
MT-17 and MT-18 were closed against the live Gemini API on 5 September 2026 —
a resumed run made zero model calls, and four seeded submissions evaluated
end to end. What that run did *not* produce is a meaningful evidence-rejection
rate: the seeded documents are short and clean, so the guard had almost
nothing to reject. That number needs real submissions, and is listed here as
an open measurement rather than a result.

---

## Future scope, in the order it would be worth doing

| # | Feature | Why it is next |
|---|---|---|
| 1 | Reading a linked repository | Decision #6 records the URL; the next step is reading a README or a commit history from it, which is evidence a PDF is not. It needs a network call at upload time and an answer for what the evidence guard verifies against |
| 2 | Rubric templates and a library | Faculty currently author every rubric from scratch. Templates per subject type would remove the largest piece of manual work |
| 3 | Calibration across reviewers | With two reviewers on one cohort, the interesting question is where they disagree with each other and with the model. The data to answer it is already stored |
| 4 | Entailment checking on evidence | Closes limitation §4 — the cited span *supports* the verdict, not merely exists |
| 5 | Multimodal evaluation | Closes limitation §5 for diagrams, which for a project report is where a lot of the substance is |
| 6 | Postgres and a real deployment | Closes limitations §1 and, partly, §2. Small change, real consequences |
| 7 | Per-member contribution weighting within a group | Closes what remains of limitation §7 |
| 8 | A student-facing rubric self-check before submission | The natural extension of showing the rubric first: let the student run the evidence guard against their own draft and see which criteria have nothing pointing at them |

Item 8 is the one most in the spirit of the project. Everything RubriQ does
for a faculty member after the deadline could be done for the student before
it, and that is where it would actually change an outcome rather than measure
one.

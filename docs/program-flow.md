# Program Flow — and the AI question

Two things, in one place: how the program actually works end to end, and how
to answer the question your guide is most likely to ask.

---

## Part 1 — How the program works

Seven stages. Follow them in this order and the whole system makes sense.

```
 Sign in  →  Set up  →  Submit  →  Evaluate  →  Review  →  Approve  →  Export
 (Google)   (faculty)  (student)    (AI)      (faculty)  (faculty)   (faculty)
                                                              ↓
                                                          Feedback
                                                          (student)
```

### Stage 1 · Signing in

1. You click **Sign in with Google**.
2. Google returns your email address to the app.
3. The app checks the address ends in `@pccoepune.org`. **This check happens
   on the server**, not in the browser, so it cannot be bypassed.
4. The app looks your address up in a list of faculty addresses. If it is
   there you are faculty; otherwise you are a student. **You cannot choose
   your own role.**
5. The menu is then built from your role. A student's faculty pages are never
   created — there is no hidden page to find.

*Files: `core/auth/`, `app/main.py`, `app/navigation.py`*

### Stage 2 · Faculty sets up

1. Create a subject, and enrol the class from a CSV file.
2. The import is checked **before** anything is saved — it shows you each row
   as `NEW`, `ALREADY ENROLLED`, `INVALID DOMAIN` or `MALFORMED`, and you
   confirm. Either all rows are saved or none are.
3. Create a review with a deadline and a maximum mark.
4. Write the rubric: five criteria, each with a weight, a maximum score and a
   description of what evidence it expects.
5. **Publish it.** From that moment the rubric is frozen. Editing it makes
   version 2 and leaves version 1 untouched, so work already marked stays
   marked against what it was actually marked against.

*Files: `core/academics/`, `core/rubrics/`*

### Stage 3 · Student submits

1. The student opens **Submit** and picks a review.
2. **The rubric appears before the upload box.** This is the whole idea of
   the project — the student reads what they will be marked on first.
3. They upload a PDF, DOCX or text file, and optionally a repository link.
4. The app reads the text out of the file immediately and stores it. Nothing
   later in the system ever opens the file again.
5. If they are late, the app says what the penalty will be **before** they
   confirm.
6. Re-uploading makes version 2. Version 1 is still there.

*Files: `core/submissions/`*

### Stage 4 · AI evaluation — covered in detail in Part 2

In one line: the system removes the student's identity, asks the model to
score each criterion with a quotation, checks every quotation is really in
the document, and throws away the ones that are not.

### Stage 5 · Faculty reviews

1. The **Review Grid** shows one row per student and one column per
   criterion.
2. Each cell shows a verdict — followed, partly followed, not followed, or no
   evidence.
3. Clicking a row opens a drawer with the quotation and the reason behind
   each score.
4. The guide can change any score, but **must type a reason**. The change is
   saved with their name and the time.

*Files: `core/scoring/grid.py`, `app/components/review_grid.py`*

### Stage 6 · Faculty approves

1. The totals are worked out by ordinary program code: each score is divided
   by its maximum, multiplied by its weight, and the result scaled onto the
   review's marks.
2. The late penalty is taken off the total — never off individual criteria.
3. Being absent is recorded as a **status**, not as a zero. Absent and
   "attempted and scored nothing" are different facts.
4. Approval is **blocked** while any required criterion has no evidence.
5. Approving stamps the guide's name and the time. That is the moment a
   suggestion becomes a mark.

*Files: `core/scoring/engine.py`, `core/scoring/sheets.py`*

### Stage 7 · Feedback and export

1. The student can see feedback **only after approval**. They never see a
   draft score.
2. The guide exports to Excel, or copies a table to paste into a spreadsheet.
3. Both exports are built from the same saved data, so they cannot disagree.
4. Every change made anywhere is written to an audit log: who, what, when,
   why.

*Files: `core/exports/`, `core/audit.py`*

---

## Part 2 — "How have you used AI?"

This is the question. Answer it as a **pipeline with guardrails**, not as
"I called an API".

### The short answer

> "The AI reads a submission and suggests a score for each rubric criterion,
> and for every suggestion it must quote the line from the student's own
> document that supports it. I then check those quotes mechanically. If a
> quote isn't really in the document, I throw the score away. And the AI
> never does any arithmetic that decides a mark — that's all ordinary code.
> No mark exists until a teacher approves it by name."

### The six steps, if she wants detail

**1 · Remove the identity.**
Before anything is sent, the student's name, PRN and email address are
stripped out of the text — by name, and also by pattern, so a PRN or an email
the system wasn't told about is caught too. The system then *asserts* they are
gone and refuses to continue if they are not. The model never learns whose
work it is marking.

**2 · Build the prompt.**
The rubric and the cleaned text go in. The instruction is strict: return only
JSON, and for each criterion give a verdict, a score, a confidence, a quotation
of at most forty words, and a one-sentence reason.

**3 · Call the model.**
Through one small function with a single method. Three providers are
supported — Gemini, OpenRouter and NVIDIA — and switching is a settings
change, not a code change. The API is also told to return JSON, so the format
is enforced at both ends.

**4 · Check the shape.**
The reply is validated against a schema. One rule is built into the schema
itself: **"no evidence" forces the score to zero**, so no part of the program
can set one without the other.

**5 · Check the evidence — this is the important one.**
Every quotation is compared back against the student's actual text using
fuzzy matching, set at 90% similarity. Fuzzy rather than exact because PDF
extraction inserts stray line breaks and hyphens, and a genuine quote
shouldn't fail on formatting.

- Quote found → the score stands.
- Quote **not** found → the score is thrown away, the criterion becomes **no
  evidence**, and the made-up quote is written to a log.

**There is no way around this check.** It is not skipped when the model is
confident. It is the only route by which a score reaches the database.

**6 · A person decides.**
Everything so far is a *suggestion*. The guide reviews it, changes what they
disagree with — with a written reason — and approves. Approval is what makes
it a mark.

### The three sentences to memorise

> **The AI never decides a mark.** It suggests; a named person approves.

> **Every score must quote the student's own words**, and the quote is checked
> mechanically. No quote, no score.

> **No arithmetic goes near the AI.** Weights, totals, penalties and absence
> are ordinary code with tests.

### Why it is built this way

Because a language model will produce a confident, well-written, completely
invented quotation if you let it. The evidence check exists because that is
the failure everybody worries about, and checking is cheap: the student's text
is right there.

### If she asks "what if the AI is wrong?"

> "Then the guide changes it, and the change is recorded with their name and
> their reason. The system is built assuming the AI will sometimes be wrong —
> that's why nothing it produces is final, and why every number it gives has a
> quote attached that you can check yourself in two seconds."

### If she asks "what if there's no internet?"

> "Everything except the AI suggestions still works — marking by hand,
> penalties, approval, reports and the Excel export. The AI part says it's
> unavailable. That was a design requirement, not an accident."

---

## Part 3 — "Did you use AI to write the code?"

**Be ready for this one.** The source code link is on the title page of your
report, the repository is public, and 41 of its 42 commits say
`Co-Authored-By: Claude`. If she opens it, she will see that immediately.

Do not be caught out by it, and do not volunteer a confession either. Have a
straight answer ready if it comes.

### A straight answer

> "Yes — I used an AI coding assistant throughout, and the commit history says
> so on every commit rather than hiding it.
>
> What I wrote first was the specification: the rules the system is not
> allowed to break, the architecture, and the order the work had to happen in.
> Every significant design decision is written down with the reasoning behind
> it — why SQLite instead of PostgreSQL, why no third-party calendar, why the
> AI is not allowed to touch the database.
>
> Then I used AI the same way my own system uses it: it proposes, I check and
> approve. The test suite is how I checked. And three bugs still got past the
> tests and only showed up when I deployed it — which is in the report, with
> what each one taught me."

That last part is the strongest thing you can say, because it is specific, it
is checkable, and it is not flattering.

### What makes this defensible

- The **specification came first** and the build followed it, which the commit
  history shows phase by phase.
- Every **decision is recorded with its reasoning**, not just its outcome.
- The **honesty is built in**: your own row in the demo scores itself 23 out of
  25, and the two marks held back are explained.
- Nothing was **hidden** — the attribution is on every commit.

### What you must actually do

**Be able to explain any part of it she points at.** That is the real test,
and it is a fair one. Before the viva, make sure you can explain, in your own
words and without notes:

1. How the domain check stops a Gmail address signing in.
2. How a total is calculated from the five criterion scores.
3. What the evidence check does, and why fuzzy matching rather than exact.
4. Why a published rubric cannot be edited.
5. What happens when the AI provider is unreachable.

If you can explain those five, you understand the system. If you cannot
explain one of them, go and read that file before the viva rather than hoping
it does not come up.

### What not to say

- Don't say "I wrote every line myself." The repository contradicts it.
- Don't say "the AI did it." You specified it, you checked it, you can explain
  it — that is the work.
- Don't get defensive. It is a reasonable question and you have a good answer.

---

### One-line summary

**Inside the project:** AI suggests a score and must quote the student's own
words; the quote is verified; a teacher approves. **Building the project:** the
same shape — AI proposed, I specified, tested and approved.

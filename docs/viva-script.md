# Viva Script — RubriQ

A step-by-step guide for presenting. Each step says **what to click** and
**what to say**. The "say" lines are written to be spoken, not read out — use
your own words once you know the shape.

Keep this open on a second screen or print it.

---

## Part A — Before she arrives

Ten minutes, not two.

| # | Do | Why |
|---|---|---|
| 1 | Open a terminal in the project folder | |
| 2 | Run `make reseed` (or `.\make.ps1 reseed`) | Rebuilds the demo class with fresh dates. **Do this every time.** A database seeded last week shows deadlines that closed ages ago |
| 3 | Run `make run` (or `.\make.ps1 run`) | Starts the app at <http://localhost:8501> |
| 4 | Sign in as the **faculty** account and leave it open | Signing in while she watches wastes a minute |
| 5 | Open <https://rubriq.streamlit.app> in a second tab | Your backup, and proof it is deployed |
| 6 | Open your Downloads folder in a window | You will download a spreadsheet in step 8 |
| 7 | Close every other tab | |

**If the wifi is bad, use the local one.** Everything except the AI step works
with no internet at all. That is deliberate and it is worth saying out loud.

---

## Part B — The opening

Before you click anything. About sixty seconds.

> "In every project review, the student is marked against a rubric. The
> problem is the student usually sees that rubric *after* they have been
> marked — and the reasoning behind the mark is never written down anywhere.
>
> RubriQ turns that around. The teacher publishes the rubric first. The
> student reads it before they submit. The system then drafts a score against
> that rubric and, for every point, quotes the line from the student's own
> document that justifies it. The teacher checks it, changes anything they
> disagree with, and approves.
>
> The one rule the whole system is built on: **the AI never decides a mark.**
> It proposes, with evidence. A person approves. Nothing becomes a mark until
> a named teacher has signed it."

Then: *"Let me show you."*

---

## Part C — The walkthrough

Twelve steps. Roughly fifteen minutes if nobody interrupts, and they will.

### 1 · Setup — 20 seconds

**Do:** show the terminal where you ran `make reseed && make run`.

> "The whole system starts with one command. No database to install, no
> server. That was a deliberate choice — it has to run on whichever laptop
> the review happens on."

---

### 2 · Faculty Dashboard — 1 minute

**Do:** point at the four cards along the top.

> "This is what a guide sees. One subject, sixty-seven students, one review
> published, and eighteen rows that need a decision from me."

**Do:** point at the **Waiting on you** box, then click one of its links.

> "These are links, not notices. If the system tells me eighteen rows need
> attention, clicking that sentence takes me to them. It shouldn't tell me
> about a problem and then make me go and find it."

**Do:** come back, and use the **review picker** dropdown.

> "I can pick any review and see how far through it I am."

---

### 3 · Rubric Builder — 2 minutes · *important*

**Do:** open **Rubric Builder** and show the five criteria.

> "This is the actual rubric for this subject — the same five criteria you
> mark us against. Problem Definition, Requirements Analysis, Technology
> Stack, System Design, Synopsis Submission. Each one out of five, each one
> worth twenty percent."

**Do:** expand a criterion to show the descriptor text.

> "And each one carries the full wording — what a five looks like, what a
> three looks like. The student reads exactly the same words you mark from."

**Do:** try to edit the published rubric. It will refuse.

> "Now watch this. Once a rubric is published it can't be edited. If I change
> it, the system makes version 2 and leaves version 1 exactly as it was.
> Otherwise a rubric could change after students were marked against it, and
> nobody would know."

---

### 4 · Review Grid — 3 minutes · **the centrepiece**

**Do:** open **Review Grid**. Let her look at it for a moment.

> "This is the main screen. One row per student, one column per criterion."

Point at four things, in this order:

1. **A tick or cross in a criterion column** —
   > "At a glance: what each student did and didn't follow."
2. **A row with a penalty** —
   > "This one submitted two days late, so twenty percent came off the total.
   > The system worked that out, not me."
3. **The row that says ABSENT** —
   > "This one is marked absent, and notice it says ABSENT, not zero. They're
   > different things — absent means they didn't attend, zero means they tried
   > and scored nothing. The reports keep them apart too."
4. **A row with no submission** —
   > "And this student never submitted. They still get a row. If they
   > disappeared from the list, they'd be easy to forget."

---

### 5 · Your own row — 1 minute · *this one lands well*

**Do:** click your own row to open the drawer.

> "This is my project, marked against the same rubric. Twenty-three out of
> twenty-five."

**Do:** read the note.

> "And I gave myself four, not five, on two of them. Technology Stack, because
> I changed the database choice halfway through the project rather than
> getting it right first. And Synopsis Submission, because the synopsis was
> signed off after I'd built most of it rather than before.
>
> Both are in my records. Giving myself full marks wouldn't have been an
> assessment."

---

### 6 · The drawer and the evidence — 2 minutes · *important*

**Do:** open a different student's row.

> "For each criterion the system shows the quote from the student's document
> that justifies the score. If it can't find a real quote, it doesn't give a
> score — it says NO EVIDENCE and flags it for me."

**Do:** try to approve a row that has an unevidenced mandatory criterion.

> "This row can't be approved. One of the required criteria has no evidence
> behind it, so the system won't let me sign it off until a human has looked.
> That's the safety rule: the AI can't quietly give someone a mark."

**Do:** show the override box.

> "If I disagree with a score I change it, but I have to type a reason. It's
> recorded with my name and the time."

---

### 7 · Approve in bulk — 30 seconds

**Do:** click **Approve all eligible**.

> "I can approve many at once — but it tells me how many it's leaving out and
> why, *before* I confirm. Not after."

---

### 8 · Export to Excel — 1 minute

**Do:** download the `.xlsx` and open it.

> "And this is a real Excel file, not a renamed CSV. Same numbers as the
> screen — there's a test that checks the two can't disagree. The absent
> student still says ABSENT here, not zero."

---

### 9 · Reports — 1 minute

**Do:** open **Reports**.

> "Across the class: how the marks are spread, and the same grading scale the
> department uses — Excellent, Good, Satisfactory, and so on."

**Do:** point at the weakest criterion.

> "And this tells me which criterion the class did worst on. That's useful for
> teaching, not just marking."

---

### 10 · The student side — 2 minutes · **the whole point**

**Do:** sign out, sign in as the student account.

> "Now the other side."

**Do:** show the dashboard countdown.

> "The next deadline, and how long is left."

**Do:** open **Submit** and pick the open review.

> "Here's the important part. **Before I upload anything, I can see exactly
> what I'm going to be marked on** — all five criteria and the full wording.
> That's the whole idea of the project. Normally you see this afterwards."

**Do:** point out the lateness warning if one shows.

> "And if I'm late, it tells me the penalty before I confirm, not after."

**Do:** open **Feedback**.

> "Feedback only appears after the teacher has approved it. Students never see
> a draft mark."

---

### 11 · Ask RubriQ — 1 minute

**Do:** open **Ask RubriQ** and ask something off-topic, e.g.
*"What marks will I get?"* or *"When is the college holiday?"*

> "There's an assistant, but it only answers from the rubric for this review.
> Ask it anything outside that and it refuses and offers to send the question
> to the guide instead. It won't guess, and it will never predict a mark."

---

### 12 · Activity — 30 seconds

**Do:** sign back in as faculty, open **Activity**.

> "And every change is logged — who did it, when, and why. If anyone asks
> whether the teacher or the AI decided a mark, this is the answer."

**Close with:**

> "So: rubric first, evidence for every score, and a person approves
> everything. That's RubriQ."

---

## Part D — Questions she may ask

Short answers. Say the first sentence; the rest only if she wants more.

**"Why Streamlit and not a proper web framework?"**
> "All the actual logic is in a separate package with no Streamlit in it at
> all — there's a test that fails if anyone imports Streamlit there. So the
> interface could be swapped without touching the rest. Most of the tests run
> with no browser at all."

**"Did the AI mark these?"**
> "It drafted them. Every score here was approved by a person, and the
> approval has a name and a timestamp against it. The AI never writes a final
> mark."

**"What if the AI makes something up?"**
> "It's checked. Every quote the model gives is matched back against the
> student's actual document. If the quote isn't really in there, the score is
> thrown away and the criterion is marked as having no evidence. The rejected
> ones are logged."

**"What if the internet is down?"**
> "Everything except AI drafting still works — marking, penalties, approval,
> the reports and the export. The AI part just says it's unavailable."

**"Did you choose the right technology first time?"**
> "No, and that's why I gave myself four out of five on that criterion. I
> started with PostgreSQL and switched to SQLite partway through. It was a
> small change because only one folder knows what database is being used — but
> I'd have preferred to decide it properly at the start."

**"How do you know it works?"**
> "There are automated tests, and they run every time. But the more honest
> answer is that three bugs got past them and only showed up when I deployed
> it — the database setup, the way the app starts, and some missing diagrams
> in the report. Each of those now has a test. Knowing *how* my tests were
> blind was more useful than the number of them."

**"Can two students work as a group?"**
> "Yes, but only if the guide approves it. A student can request a group, and
> until the guide grants it, it does nothing. And even in a group, each member
> keeps their own row — the guide can give one member a different mark with a
> recorded reason."

**"Is this deployed anywhere?"**
> "Yes — it runs online, with college Google sign-in. Only @pccoepune.org
> accounts can get in, and that's checked on the server, not in the browser."

---

## Part E — If something goes wrong

| Problem | Do this |
|---|---|
| App won't start | Use the online version: <https://rubriq.streamlit.app> |
| Online version slow to load | It sleeps when unused. Wait ~30 seconds, it wakes up |
| Sign-in fails | Use the local one with the other account; don't debug live |
| A page looks empty | You're probably signed in as the wrong role. Sign out, sign in again |
| AI step fails | Say so plainly: *"That's the offline case — everything else still works."* It's a designed behaviour, not a crash |
| Something you can't explain | *"I'd have to check that properly rather than guess."* It's a better answer than inventing one |

---

## The one-line version

If she only has two minutes: **show the Review Grid, then open one row's
drawer.** The grid is what the project had to build; the drawer is the rule
the whole thing is built on.

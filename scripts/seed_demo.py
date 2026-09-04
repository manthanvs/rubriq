"""Build a realistic demo dataset in one command — §10's Phase 7 exit.

*"clone → ``make seed && make run`` → a populated, browsable system, no manual
setup."*

The dataset is deliberately **uneven**. A demo where every row is approved and
every mark is 20/25 proves nothing: it cannot show the late-penalty bands, the
approval gate, an unevidenced mandatory criterion, or an escalated question. So
this seeds a cohort that exercises the interesting states —

* one student on time, one a day late, one two days late, one absent;
* one submission re-uploaded, so a version history exists;
* some sheets approved, some left as estimates, one blocked by a mandatory
  criterion at ``NO_EVIDENCE``;
* one student who never submitted, because that row must appear in the grid;
* an escalated question waiting in the faculty inbox;
* one **granted** project group and one request still **waiting** for the
  guide, so decision #5's gate is visible from both sides at once;
* GitHub accounts on record, and one submission carrying a repository link,
  so decision #6 can be demonstrated — including the refusal, by trying a
  link the register does not cover.

No LLM is called. Scores are written through the same manual-scoring service a
faculty member uses, so the seeded data is indistinguishable from real use and
every total came from ``core/scoring/engine.py``.

    python scripts/seed_demo.py            # build it
    python scripts/seed_demo.py --reset    # wipe demo rows first
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import delete, select  # noqa: E402

from core.academics.enrollment import commit_enrollment_import  # noqa: E402
from core.academics.milestones import create_milestone  # noqa: E402
from core.academics.subjects import create_cycle, create_subject  # noqa: E402
from core.audit import record  # noqa: E402
from core.auth.actor import Actor  # noqa: E402
from core.auth.roles import Role  # noqa: E402
from core.clock import utc_now  # noqa: E402
from core.config import Settings  # noqa: E402
from core.db.engine import (  # noqa: E402
    build_engine,
    build_session_factory,
    session_scope,
)
from core.db.models import (  # noqa: E402
    AuditLog,
    Criterion,
    CriterionScore,
    Enrollment,
    Evaluation,
    GroupMember,
    ProjectCycle,
    ProjectGroup,
    ReviewMilestone,
    Rubric,
    ScoreOverride,
    ScoreSheet,
    StudentQuery,
    Subject,
    Submission,
    SubmissionFile,
    SubmissionLink,
    User,
)
from core.groups.service import (  # noqa: E402
    create_group,
    request_group,
    set_github_username,
)
from core.queries.dto import QueryAnswer  # noqa: E402
from core.queries.service import ask, reply  # noqa: E402
from core.rubrics.service import (  # noqa: E402
    add_criterion,
    create_rubric,
    publish_rubric,
)
from core.scoring.enums import Verdict  # noqa: E402
from core.scoring.sheets import approve_sheet, save_manual_scores  # noqa: E402
from core.submissions.service import submit  # noqa: E402

SECRETS = REPO_ROOT / ".streamlit" / "secrets.toml"

FACULTY = "guide@pccoepune.org"
FACULTY_NAME = "Dr. Anjana Arakerimath"

#: (name, prn, days late relative to the deadline, or None for "never submitted")
COHORT: tuple[tuple[str, str, int | None], ...] = (
    ("Manthan Sankpal", "125M1H064", 0),
    ("Rahul Deshmukh", "125M1H071", 1),
    ("Priya Kulkarni", "125M1H072", 2),
    ("Aditi Joshi", "125M1H073", 0),
    ("Kunal Patil", "125M1H074", 4),  # absent under §5.1
    ("Sneha More", "125M1H075", 0),
    ("Rohit Jadhav", "125M1H076", 0),
    ("Neha Pawar", "125M1H077", None),  # never submitted
)

#: The GitHub accounts faculty have on record (decision #6). Deliberately not
#: everyone: a student with no account on record cannot submit a link at all,
#: and that refusal is worth being able to show.
GITHUB = {
    "Manthan Sankpal": "manthan-vs",
    "Rahul Deshmukh": "rahul-d",
    "Priya Kulkarni": "priya-k",
    "Aditi Joshi": "aditi-j",
}

#: Granted by the guide. Both members submit as one.
GRANTED_GROUP = ("Team Synapse", ("Priya Kulkarni", "Aditi Joshi"))

#: Asked for, and still waiting — so the gate is visible, not just described.
PENDING_GROUP = ("Team Lumen", ("Sneha More", "Rohit Jadhav"))

SYNOPSIS = """\
RubriQ — Mini Project Synopsis

1. Problem statement
Faculty currently mark project reviews from memory against a rubric that
students never see before they submit. Marks vary between reviewers, and a
student cannot tell what was expected of them until after they are marked.

2. Objectives
- Let faculty define a rubric per milestone and publish it to students before
  submission opens.
- Produce an evidence-backed estimated score sheet that a faculty member
  verifies and approves.
- Export an approved score sheet to Excel for departmental records.

3. Scope
In scope: rubric authoring, submission with versioning, deterministic scoring
with late penalties, faculty approval, and export.
Out of scope: plagiarism detection, executing student code, mobile app, LMS
integration, multi-institution tenancy.

4. System design
The application is a single Streamlit process. All domain logic lives in a
core package with no Streamlit imports, so the view layer is replaceable.
"""

SRS_EXTRA = """\

5. Requirements
FR-1 The system shall restrict sign-in to institute accounts.
FR-2 The system shall publish a rubric to students before submission opens.
FR-3 The system shall record every submission version without overwriting.
FR-4 The system shall apply late penalties from a documented policy table.
NFR-1 A faculty member shall be able to approve a cohort in one sitting.
NFR-2 No mark shall be published without a named approver.
"""


def _actor(email: str, role: Role, name: str) -> Actor:
    return Actor(email=email, role=role, name=name)


def _handle(name: str) -> str:
    return name.lower().replace(" ", ".") + "@pccoepune.org"


def load_settings() -> Settings:
    if SECRETS.exists():
        with SECRETS.open("rb") as handle:
            return Settings.from_mapping(tomllib.load(handle))
    return Settings.from_env()


def ensure_secrets() -> bool:
    """Write a starter secrets file if none exists. Returns True if written.

    The faculty allow-list has to exist for role resolution to work at all
    (invariant #5), so a fresh clone with no secrets file cannot show the
    faculty side. The ``[dev]`` block is written **commented out** — a demo
    dataset is worth shipping, an enabled auth bypass is not.
    """
    if SECRETS.exists():
        return False

    SECRETS.parent.mkdir(parents=True, exist_ok=True)
    SECRETS.write_text(
        "# Written by scripts/seed_demo.py. Gitignored.\n"
        "\n"
        "[rubriq]\n"
        'allowed_email_domain = "pccoepune.org"\n'
        "faculty_allowlist = [\n"
        f'    "{FACULTY}",\n'
        "]\n"
        "\n"
        "# Uncomment ONE line below to browse without Google OIDC configured.\n"
        "# Local development only — delete before any demo.\n"
        "# [dev]\n"
        f'# impersonate = "{FACULTY}"                    # the faculty side\n'
        '# impersonate = "manthan.sankpal@pccoepune.org"  # the student side\n',
        encoding="utf-8",
    )
    return True


def migrate() -> None:
    """Bring the database up to head, so a fresh clone needs no extra step."""
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )


def reset(factory) -> None:
    """Remove seeded rows, newest table first so foreign keys stay satisfied."""
    with session_scope(factory) as session:
        for model in (
            ScoreOverride,
            ScoreSheet,
            CriterionScore,
            Evaluation,
            StudentQuery,
            SubmissionLink,
            SubmissionFile,
            Submission,
            GroupMember,
            ProjectGroup,
            Criterion,
            Rubric,
            ReviewMilestone,
            ProjectCycle,
            Enrollment,
            Subject,
            AuditLog,
        ):
            session.execute(delete(model))
        session.execute(delete(User))


def build(settings: Settings) -> dict[str, int]:
    """Create the dataset. Returns a summary for printing."""
    factory = build_session_factory(build_engine(settings))
    faculty = _actor(FACULTY, Role.FACULTY, FACULTY_NAME)
    counts = {
        "students": 0,
        "groups_granted": 0,
        "groups_pending": 0,
        "github": 0,
        "submissions": 0,
        "links": 0,
        "approved": 0,
        "queries": 0,
    }

    # -- faculty, subject, cycle -------------------------------------
    with session_scope(factory) as session:
        if session.get(User, FACULTY) is None:
            session.add(User(email=FACULTY, role=Role.FACULTY, name=FACULTY_NAME))
            session.flush()
            record(
                session,
                actor_email="system:seed_demo",
                action="user.seeded",
                entity="User",
                entity_id=FACULTY,
                payload={"role": "FACULTY"},
            )

        subject = create_subject(
            faculty, session, code="MCA33EL03", name="Mini Project", semester=3
        )
        cycle = create_cycle(
            faculty,
            session,
            subject_id=subject.id,
            title="Mini Project 2026",
            academic_year="2026-27",
        )
        subject_id, cycle_id = subject.id, cycle.id

    # -- milestones ---------------------------------------------------
    deadline = utc_now().replace(hour=18, minute=29, second=0, microsecond=0) - timedelta(
        days=10
    )

    with session_scope(factory) as session:
        review_one = create_milestone(
            faculty,
            session,
            cycle_id=cycle_id,
            index=1,
            title="Review 1 — Synopsis & SRS",
            description=(
                "Submit the synopsis, the SRS and an ER diagram as a single PDF "
                "or DOCX. The rubric below is what you will be marked against."
            ),
            public_notes=(
                "Number your requirements (FR-1, FR-2, …) so they can be traced. "
                "The ER diagram must show cardinality. Objectives should be "
                "measurable — 'improve the process' is not."
            ),
            due_at=deadline,
            max_marks=25,
            is_visible=True,
        )
        review_two = create_milestone(
            faculty,
            session,
            cycle_id=cycle_id,
            index=2,
            title="Review 2 — Implementation & Testing",
            description="A working system, the test report, and a demo video.",
            public_notes="Bring a laptop that can run the system offline.",
            due_at=deadline + timedelta(days=45),
            max_marks=25,
            is_visible=False,  # still a draft, so the grid shows both states
        )
        milestone_one, milestone_two = review_one.id, review_two.id

    # -- rubric for review 1 -------------------------------------------
    with session_scope(factory) as session:
        rubric = create_rubric(faculty, session, milestone_id=milestone_one)
        for code, title, weight, evidence, mandatory in (
            (
                "C1",
                "Problem statement and objectives",
                40,
                "A stated problem, its consequence, and at least two "
                "measurable objectives.",
                True,
            ),
            (
                "C2",
                "SRS completeness",
                35,
                "Numbered functional and non-functional requirements.",
                False,
            ),
            (
                "C3",
                "ER diagram and design",
                25,
                "An ER diagram showing entities, relationships and cardinality.",
                False,
            ),
        ):
            add_criterion(
                faculty,
                session,
                rubric_id=rubric.id,
                code=code,
                title=title,
                weight=weight,
                max_score=10,
                expected_evidence=evidence,
                is_mandatory=mandatory,
            )
        publish_rubric(faculty, session, rubric_id=rubric.id)

    # -- enrolment ------------------------------------------------------
    rows = ["email,name,prn,batch,group_label"]
    for name, prn, _late in COHORT:
        rows.append(f"{_handle(name)},{name},{prn},A,G{1 + (len(rows) % 2)}")
    csv_text = "\n".join(rows) + "\n"

    with session_scope(factory) as session:
        result = commit_enrollment_import(
            faculty, session, subject_id=subject_id, csv_text=csv_text, settings=settings
        )
        counts["students"] = len(result.committable)

    # -- GitHub register and groups (decisions #6 and #5) ----------------
    with session_scope(factory) as session:
        for name, handle in GITHUB.items():
            set_github_username(
                faculty, session, student_email=_handle(name), username=handle
            )
        counts["github"] = len(GITHUB)

    with session_scope(factory) as session:
        granted_name, granted_members = GRANTED_GROUP
        create_group(
            faculty,
            session,
            subject_id=subject_id,
            name=granted_name,
            member_emails=[_handle(n) for n in granted_members],
            note="Shared implementation, agreed at the proposal stage.",
        )
        counts["groups_granted"] = 1

    with session_scope(factory) as session:
        pending_name, pending_members = PENDING_GROUP
        asker = _actor(_handle(pending_members[0]), Role.STUDENT, pending_members[0])
        request_group(
            asker,
            session,
            subject_id=subject_id,
            name=pending_name,
            member_emails=[_handle(n) for n in pending_members],
        )
        counts["groups_pending"] = 1

    # -- submissions ----------------------------------------------------
    uploads = settings.uploads_root

    #: Whoever submits first for the granted group submits for both, so the
    #: second member must not create a second row.
    group_submitted = False

    _, granted_members = GRANTED_GROUP

    for name, _prn, late in COHORT:
        if late is None:
            continue

        # One submission per group, not one per member: the second member's
        # upload would be v2 of the same work rather than a second row, and
        # seeding that would make the demo look like a duplicate.
        if name in granted_members:
            if group_submitted:
                continue
            group_submitted = True

        student = _actor(_handle(name), Role.STUDENT, name)
        body = SYNOPSIS if name != "Rahul Deshmukh" else SYNOPSIS + SRS_EXTRA

        # One submission carries a repository link, so the faculty drawer and
        # the student history both have one to show.
        handle = GITHUB.get(name)
        links = (
            [f"https://github.com/{handle}/rubriq-mini-project"]
            if handle and name == "Manthan Sankpal"
            else []
        )

        with session_scope(factory) as session:
            created = submit(
                student,
                session,
                milestone_id=milestone_one,
                files={"synopsis.txt": body.encode()},
                uploads_root=uploads,
                note=None if late == 0 else "Sorry this is late.",
                links=links,
            )
            counts["submissions"] += 1
            counts["links"] += len(links)
            submission_id = created.id

        # A version history for one student, so the stale-version banner and
        # the Submit page's history table both have something to show.
        if name == "Rahul Deshmukh":
            with session_scope(factory) as session:
                created = submit(
                    student,
                    session,
                    milestone_id=milestone_one,
                    files={"synopsis_v2.txt": (body + SRS_EXTRA).encode()},
                    uploads_root=uploads,
                    note="Added the literature survey after feedback.",
                )
                counts["submissions"] += 1
                submission_id = created.id

        # Date the submission relative to the deadline, so §5.1's bands apply.
        with session_scope(factory) as session:
            row = session.get(Submission, submission_id)
            row.submitted_at = deadline + timedelta(days=late, hours=-2)

    # -- scoring --------------------------------------------------------
    marks = {
        "Manthan Sankpal": {"C1": 9, "C2": 8, "C3": 9},
        "Rahul Deshmukh": {"C1": 8, "C2": 7, "C3": 6},
        "Priya Kulkarni": {"C1": 7, "C2": 6, "C3": 7},
        "Aditi Joshi": {"C1": 9, "C2": 9, "C3": 8},
        "Kunal Patil": {"C1": 6, "C2": 5, "C3": 5},
        # Left unscored on purpose, so the grid has rows needing attention.
        "Sneha More": None,
        # Mandatory C1 unevidenced: approval must be blocked (fix item 4).
        "Rohit Jadhav": {"C1": 0, "C2": 7, "C3": 6},
    }
    approve_for = {"Manthan Sankpal", "Aditi Joshi", "Priya Kulkarni"}

    for name, scores in marks.items():
        if scores is None:
            continue

        with session_scope(factory) as session:
            submission = session.scalars(
                select(Submission)
                .where(
                    Submission.milestone_id == milestone_one,
                    Submission.student_email == _handle(name),
                )
                .order_by(Submission.version.desc())
                .limit(1)
            ).first()
            if submission is None:
                continue
            submission_id = submission.id

        verdicts = {
            code: (
                value,
                Verdict.NO_EVIDENCE
                if value == 0
                else (Verdict.FOLLOWED if value >= 8 else Verdict.PARTIAL),
            )
            for code, value in scores.items()
        }

        with session_scope(factory) as session:
            sheet = save_manual_scores(
                faculty,
                session,
                submission_id=submission_id,
                scores=verdicts,
                faculty_note=(
                    "Objectives are clear. Number the requirements next time."
                    if name != "Rohit Jadhav"
                    else "C1 is not evidenced anywhere in the document."
                ),  # noqa: E501
            )
            sheet_id = sheet.id

        if name in approve_for:
            with session_scope(factory) as session:
                approve_sheet(faculty, session, score_sheet_id=sheet_id)
                counts["approved"] += 1

    # -- student questions ----------------------------------------------
    student = _actor(_handle("Manthan Sankpal"), Role.STUDENT, "Manthan Sankpal")

    with session_scope(factory) as session:
        ask(
            student,
            session,
            milestone_id=milestone_one,
            question="What does C1 expect me to include?",
            answer=QueryAnswer(
                answer=(
                    "C1 asks for a stated problem with its consequence, and at "
                    "least two measurable objectives. It is mandatory and worth "
                    "40% of the milestone."
                ),
                escalated=False,
                sources=("C1", "notes from the guide"),
                confidence=0.91,
            ),
        )
        counts["queries"] += 1

        escalated = ask(
            student,
            session,
            milestone_id=milestone_one,
            question="Can I have an extension until next Monday?",
            answer=QueryAnswer(
                answer="",
                escalated=True,
                reason="Only your guide can change a deadline or grant an exception.",
            ),
        )
        counts["queries"] += 1
        escalated_id = escalated.id

    # One answered and one still waiting, so the inbox shows both states.
    with session_scope(factory) as session:
        ask(
            _actor(_handle("Aditi Joshi"), Role.STUDENT, "Aditi Joshi"),
            session,
            milestone_id=milestone_one,
            question="Does the ER diagram need to show cardinality?",
            answer=QueryAnswer(
                answer="",
                escalated=True,
                reason="The assistant was not confident enough to answer this.",
            ),
        )
        counts["queries"] += 1

    with session_scope(factory) as session:
        reply(
            faculty,
            session,
            query_id=escalated_id,
            message=(
                "No extension for Review 1 — submit what you have and we will "
                "discuss the gaps at the review."
            ),
        )

    counts["milestones"] = 2
    counts["milestone_one"] = milestone_one
    counts["milestone_two"] = milestone_two
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete existing rows before seeding (demo databases only)",
    )
    args = parser.parse_args()

    print("Migrating…")
    migrate()

    wrote_secrets = ensure_secrets()
    settings = load_settings()

    print(f"Database: {settings.redacted()['database_url']}")

    factory = build_session_factory(build_engine(settings))

    if args.reset:
        print("Resetting existing rows…")
        reset(factory)

    try:
        counts = build(settings)
    except Exception as exc:
        print(f"\nSeeding failed: {exc}", file=sys.stderr)
        print("If the database already has demo data, try --reset.", file=sys.stderr)
        return 1

    print()
    print(f"  students    {counts['students']}")
    print(f"  github      {counts['github']} accounts on record")
    print(
        f"  groups      {counts['groups_granted']} granted, "
        f"{counts['groups_pending']} awaiting approval"
    )
    print(f"  submissions {counts['submissions']} ({counts['links']} with a repo link)")
    print(f"  approved    {counts['approved']}")
    print(f"  questions   {counts['queries']}")
    print()
    print("Seeded: one on-time, one late, one two days late, one absent,")
    print("one never submitted, one blocked on a mandatory criterion,")
    print("one version history, one granted group submitting as one, one")
    print("group request still waiting on the guide, one repository link on")
    print("record, and an escalated question awaiting a reply.")
    print()

    if wrote_secrets:
        print("Wrote .streamlit/secrets.toml with the faculty allow-list.")
        print("To browse without Google OIDC, uncomment a [dev] line in it.")
        print()

    print("Next:  make run     (or  .\\make.ps1 run  on Windows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

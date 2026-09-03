"""The student assistant — §6.4, §6.7, and the Phase 6 exit criterion.

*"Exit: the assistant correctly refuses an out-of-scope question and offers
escalation instead of guessing."* :class:`TestExitCriterion` is that, through
the public function, for each of the refusal categories §6.7 names.

The other half of this file is the scoping story. §6.7 limits the context to
the published rubric, the milestone description and the guide's public notes —
so :class:`TestContextIsNarrow` asserts what is *absent* from it, which is the
part that would leak.
"""

from __future__ import annotations

import json

import pytest

from core.ai.graphs.query import MINIMUM_CONFIDENCE, deterministic_refusal
from core.ai.provider import answer_student_query
from core.db.engine import session_scope
from core.errors import NotAuthorized, ValidationError
from core.queries.dto import QueryAnswer
from core.queries.service import (
    ask,
    build_context,
    escalated_count,
    list_escalated,
    list_my_queries,
    reply,
)


class ScriptedProvider:
    """Answers classify and answer calls from a script."""

    name = "scripted"
    model = "scripted-1"

    def __init__(
        self,
        *,
        in_scope: bool = True,
        answer: str = "",
        confidence: float = 0.9,
        sources: list[str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._in_scope = in_scope
        self._answer = answer or "The rubric asks for a stated problem and objectives."
        self._confidence = confidence
        self._sources = sources if sources is not None else ["C1"]
        self._error = error
        self.calls: list[str] = []

    def complete(self, *, system: str, user: str) -> str:
        if self._error is not None:
            raise self._error

        if "decide whether" in system.lower():
            self.calls.append("classify")
            return json.dumps({"in_scope": self._in_scope, "reason": "scripted"})

        self.calls.append("answer")
        return json.dumps(
            {
                "answer": self._answer,
                "sources": self._sources,
                "confidence": self._confidence,
            }
        )


@pytest.fixture
def context(db_factory, world, graded):
    """A real context built through the service, for the student's milestone."""
    with session_scope(db_factory) as session:
        return build_context(world.student_1, session, world.milestone_visible)


class TestExitCriterion:
    """Out-of-scope questions escalate, and carry no invented answer."""

    @pytest.mark.parametrize(
        "question",
        [
            "What will I score on this review?",
            "How many marks will I get for this submission?",
            "What percentage do you think I will score?",
            "Will I pass this review?",
        ],
    )
    def test_mark_prediction_is_always_refused(self, context, question: str) -> None:
        """§6.7: "Never predicts a mark." Policy, not model judgment."""
        provider = ScriptedProvider(in_scope=True, confidence=1.0)

        result = answer_student_query(question, context, provider=provider)

        assert result.escalated
        assert result.answer == "", "an escalation must carry no invented answer"
        assert "never predicts" in result.reason.lower()
        assert provider.calls == [], "refused before any model was asked"

    @pytest.mark.parametrize(
        ("question", "expected"),
        [
            ("How did other students score on this?", "anyone else"),
            ("Can I get an extension on the deadline?", "deadline"),
            ("I want this re-marked, it was unfair.", "re-mark"),
        ],
    )
    def test_the_other_policy_refusals(self, context, question, expected) -> None:
        provider = ScriptedProvider(in_scope=True)

        result = answer_student_query(question, context, provider=provider)

        assert result.escalated
        assert result.answer == ""
        assert expected in result.reason.lower()

    def test_the_model_may_also_decide_a_question_is_out_of_scope(self, context) -> None:
        """Policy catches the obvious; the classifier catches the rest."""
        provider = ScriptedProvider(in_scope=False)

        result = answer_student_query(
            "What is the college attendance policy?", context, provider=provider
        )

        assert result.escalated
        assert result.answer == ""
        assert provider.calls == ["classify"], "it never reached the answer node"

    def test_a_low_confidence_answer_escalates_rather_than_hedging(self, context) -> None:
        """§6.4's confidence_check. A half-believed answer reads as a real one."""
        provider = ScriptedProvider(in_scope=True, confidence=MINIMUM_CONFIDENCE - 0.1)

        result = answer_student_query(
            "What should the SRS contain?", context, provider=provider
        )

        assert result.escalated
        assert result.answer == ""

    def test_an_in_scope_question_is_answered(self, context) -> None:
        """The refusals must not swallow the questions it exists to answer."""
        provider = ScriptedProvider(
            in_scope=True,
            answer="C1 asks for a stated problem and at least two objectives.",
            confidence=0.92,
        )

        result = answer_student_query(
            "What does C1 want from me?", context, provider=provider
        )

        assert not result.escalated
        assert "objectives" in result.answer
        assert result.sources == ("C1",)
        assert provider.calls == ["classify", "answer"]


class TestDeterministicRefusals:
    def test_ordinary_questions_are_not_caught(self) -> None:
        """A refusal list that swallows real questions is worse than none."""
        for question in (
            "What does C2 expect in the SRS?",
            "When is this review due?",
            "Do I need an ER diagram?",
            "How should I structure the objectives section?",
        ):
            assert deterministic_refusal(question) == "", question

    def test_mark_questions_are_caught_however_phrased(self) -> None:
        for question in (
            "what marks will i get",
            "How much will I score here?",
            "will i pass",
        ):
            assert deterministic_refusal(question), question


class TestContextIsNarrow:
    """§6.7: the rubric, the description, the notes. Nothing else."""

    def test_it_contains_the_published_rubric(self, context) -> None:
        text = context.as_prompt_text()

        assert "C1" in text and "C2" in text
        assert "Problem statement" in text

    def test_it_never_contains_another_students_work(
        self, db_factory, world, graded
    ) -> None:
        with session_scope(db_factory) as session:
            built = build_context(world.student_1, session, world.milestone_visible)

        text = built.as_prompt_text()

        assert world.student_2.email not in text
        assert "synopsis" not in text.lower(), "no submission text in the context"

    def test_it_never_contains_scores_or_approvals(
        self, db_factory, world, graded
    ) -> None:
        from core.scoring.enums import Verdict
        from core.scoring.sheets import approve_sheet, save_manual_scores

        with session_scope(db_factory) as session:
            sheet = save_manual_scores(
                world.faculty_a,
                session,
                submission_id=graded.submission_id,
                scores={"C1": (9, Verdict.FOLLOWED), "C2": (7, Verdict.FOLLOWED)},
            )
        with session_scope(db_factory) as session:
            approve_sheet(world.faculty_a, session, score_sheet_id=sheet.id)

        with session_scope(db_factory) as session:
            text = build_context(
                world.student_1, session, world.milestone_visible
            ).as_prompt_text()

        assert "19.50" not in text
        assert "approved" not in text.lower()

    def test_a_student_cannot_build_a_context_for_a_draft_milestone(
        self, db_factory, world
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                build_context(world.student_1, session, world.milestone_hidden)

    def test_a_student_cannot_build_a_context_for_another_subject(
        self, db_factory, world, graded
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                build_context(world.student_2, session, world.milestone_visible)

    def test_source_labels_only_offer_what_the_context_holds(self, context) -> None:
        labels = context.source_labels()

        assert "C1" in labels and "due date" in labels
        assert "C99" not in labels


class TestSourcesAreNotInvented:
    def test_a_cited_source_outside_the_context_is_dropped(self, context) -> None:
        """Inventing provenance is worse than offering none."""
        provider = ScriptedProvider(
            in_scope=True,
            confidence=0.9,
            sources=["C1", "the institute handbook", "another student's report"],
        )

        result = answer_student_query("What does C1 want?", context, provider=provider)

        assert result.sources == ("C1",)


class TestOfflineDegradation:
    def test_a_dead_provider_escalates_rather_than_erroring(self, context) -> None:
        """Invariant #10: the question still reaches a human."""
        provider = ScriptedProvider(error=TimeoutError("provider gone"))

        result = answer_student_query("What does C1 want?", context, provider=provider)

        assert result.escalated
        assert result.answer == ""
        assert "guide" in result.reason.lower()

    def test_a_milestone_with_no_rubric_says_so_in_the_context(
        self, db_factory, world
    ) -> None:
        """Not the same as escalating.

        With no rubric there is still a due date and a description, so "when is
        this due" remains answerable. What must not happen is the model
        inventing a rubric, so the context states plainly that none exists.
        """
        with session_scope(db_factory) as session:
            built = build_context(world.student_1, session, world.milestone_visible)

        assert not built.has_rubric
        assert "No rubric has been published yet." in built.as_prompt_text()
        assert "C1" not in built.as_prompt_text()


class TestStorageAndInbox:
    def test_asking_records_the_question(self, db_factory, world, graded) -> None:
        with session_scope(db_factory) as session:
            stored = ask(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                question="What does C1 want?",
                answer=QueryAnswer(
                    answer="A stated problem.",
                    escalated=False,
                    sources=("C1",),
                    confidence=0.9,
                ),
            )

        assert stored.question == "What does C1 want?"
        assert stored.escalated is False
        assert stored.sources == ("C1",)

    def test_an_escalated_question_reaches_the_faculty_inbox(
        self, db_factory, world, graded
    ) -> None:
        with session_scope(db_factory) as session:
            ask(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                question="Can I have an extension?",
                answer=QueryAnswer(
                    answer="", escalated=True, reason="Only your guide can decide."
                ),
            )

        with session_scope(db_factory) as session:
            inbox = list_escalated(world.faculty_a, session)

        assert len(inbox) == 1
        assert inbox[0].awaiting_reply
        assert inbox[0].student_email == world.student_1.email

    def test_an_answered_question_does_not_reach_the_inbox(
        self, db_factory, world, graded
    ) -> None:
        with session_scope(db_factory) as session:
            ask(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                question="What does C1 want?",
                answer=QueryAnswer(answer="A stated problem.", escalated=False),
            )

        with session_scope(db_factory) as session:
            assert list_escalated(world.faculty_a, session) == ()

    def test_replying_closes_it(self, db_factory, world, graded) -> None:
        with session_scope(db_factory) as session:
            stored = ask(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                question="Can I have an extension?",
                answer=QueryAnswer(answer="", escalated=True, reason="Ask your guide."),
            )

        with session_scope(db_factory) as session:
            answered = reply(
                world.faculty_a,
                session,
                query_id=stored.id,
                message="No extension, but submit what you have by Friday.",
            )

        assert answered.faculty_reply.startswith("No extension")
        assert answered.replied_by == world.faculty_a.email
        assert not answered.awaiting_reply

        with session_scope(db_factory) as session:
            assert escalated_count(world.faculty_a, session) == 0

    def test_an_empty_reply_is_refused(self, db_factory, world, graded) -> None:
        with session_scope(db_factory) as session:
            stored = ask(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                question="Extension?",
                answer=QueryAnswer(answer="", escalated=True, reason="Ask."),
            )

        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError):
                reply(world.faculty_a, session, query_id=stored.id, message="   ")


class TestScoping:
    def test_a_student_sees_only_their_own_questions(
        self, db_factory, world, graded
    ) -> None:
        with session_scope(db_factory) as session:
            ask(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                question="Mine.",
                answer=QueryAnswer(answer="ok", escalated=False),
            )

        with session_scope(db_factory) as session:
            assert len(list_my_queries(world.student_1, session)) == 1
            assert list_my_queries(world.student_2, session) == ()

    def test_faculty_cannot_read_another_faculty_members_inbox(
        self, db_factory, world, graded
    ) -> None:
        with session_scope(db_factory) as session:
            ask(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                question="Extension?",
                answer=QueryAnswer(answer="", escalated=True, reason="Ask."),
            )

        with session_scope(db_factory) as session:
            assert list_escalated(world.faculty_b, session) == ()

    def test_a_student_cannot_read_the_inbox(self, db_factory, world) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                list_escalated(world.student_1, session)

    def test_faculty_cannot_ask(self, db_factory, world, graded) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError):
                ask(
                    world.faculty_a,
                    session,
                    milestone_id=world.milestone_visible,
                    question="Testing.",
                    answer=QueryAnswer(answer="x", escalated=False),
                )

    def test_a_student_cannot_ask_about_a_draft_milestone(
        self, db_factory, world
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                ask(
                    world.student_1,
                    session,
                    milestone_id=world.milestone_hidden,
                    question="What is this?",
                    answer=QueryAnswer(answer="x", escalated=False),
                )

    def test_an_empty_question_is_refused(self, db_factory, world, graded) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError):
                ask(
                    world.student_1,
                    session,
                    milestone_id=world.milestone_visible,
                    question="   ",
                    answer=QueryAnswer(answer="x", escalated=False),
                )


class TestSessionMemoryIsolation:
    def test_threads_are_keyed_by_student_and_milestone(self, context) -> None:
        """§6.4: memory is never shared between students or across milestones.

        The thread id is built from both, so two students asking the same
        question on the same milestone occupy different threads, and one
        student on two milestones does too.
        """
        provider = ScriptedProvider(in_scope=True, confidence=0.9)

        first = answer_student_query(
            "What does C1 want?",
            context,
            provider=provider,
            student_email="a@pccoepune.org",
        )
        second = answer_student_query(
            "What does C1 want?",
            context,
            provider=provider,
            student_email="b@pccoepune.org",
        )

        # Both answered independently; neither short-circuited from the other's
        # memory, which is what sharing a thread would have caused.
        assert not first.escalated and not second.escalated
        assert provider.calls.count("classify") == 2

    def test_the_result_is_stamped(self, context) -> None:
        result = answer_student_query(
            "What does C1 want?", context, provider=ScriptedProvider()
        )

        assert result.prompt_version == "query-v1"
        assert result.graph_version == "query-graph-v1"

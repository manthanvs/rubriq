"""The student-query graph — §6.4.

    classify ──in scope?──yes──▶ answer ──▶ confidence_check ──▶ END
                  │                                │ low
                  no                                ▼
                  └──────────────────▶ escalate ◀───┘

§6.4 says the routing is the point, and it is: three different ways of
declining converge on one ``escalate`` node, so there is exactly one place that
decides what an unanswerable question looks like.

**Some refusals are policy, not judgment.** §6.7 forbids the assistant ever
predicting a mark. Leaving that to the model would make it a matter of how the
question was phrased, so :data:`ALWAYS_ESCALATE` catches it deterministically
before any model sees it. The model's classification then handles everything
that genuinely requires reading the context.
"""

from __future__ import annotations

import re
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from core.ai.prompts.query_v1 import (
    ANSWER_SYSTEM,
    CLASSIFY_SYSTEM,
    build_answer_prompt,
    build_classify_prompt,
)
from core.ai.schemas import AIResponseError, parse_classification, parse_query_response

QUERY_GRAPH_VERSION = "query-graph-v1"

#: Below this the answer goes to the guide instead of the student. §6.4's
#: ``confidence_check``: an answer the model half-believes is worse than an
#: honest hand-off, because the student cannot tell the difference.
MINIMUM_CONFIDENCE = 0.55

#: Words naming a mark, and words meaning "me, in the future". A mark question
#: is the two together **in either order** — "what will I score" and "how many
#: marks will I get" are the same question, and an ordered pattern catches only
#: one of them. That hole was live until a test found it.
_MARK_NOUNS = re.compile(
    r"\b(marks?|score[sd]?|scoring|grade[sd]?|percentage|cgpa|gpa|result)\b",
    re.IGNORECASE,
)

#: A first-person reading of the future: "will I", "I will get", "am I going to".
_SELF_FUTURE = re.compile(
    r"\b(i|me|my|we|our)\b[^.?!]{0,60}\b(get|getting|will|would|expect|likely|"
    r"chance|deserve|going)\b"
    r"|\b(will|would|do|does|can|could|am|are|is)\b[^.?!]{0,40}\b(i|me|my|we)\b",
    re.IGNORECASE,
)

_PASS_FAIL = re.compile(
    r"\b(pass|fail|passing|failing)\b",
    re.IGNORECASE,
)

MARK_REFUSAL = "The assistant never predicts marks — only your guide decides those."

#: Refused regardless of what any model thinks, with the reason the student is
#: shown. These are §6.7's rules, and a rule a model can talk itself out of is
#: not a rule.
ALWAYS_ESCALATE: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\b(other|others|another|classmates?|everyone else|rest of the class"
            r"|compared to|comparison|average|topper|rank)\b",
            re.IGNORECASE,
        ),
        "The assistant can only see your milestone, never anyone else's work.",
    ),
    (
        re.compile(
            r"\b(extension|extend|postpone|deadline change|reschedul\w*|waive"
            r"|exemption|defer)\b",
            re.IGNORECASE,
        ),
        "Only your guide can change a deadline or grant an exception.",
    ),
    (
        re.compile(
            r"\b(re-?mark(ed|ing)?|re-?evaluat\w*|reassess\w*|appeal|dispute"
            r"|unfair|recheck|revaluation)\b",
            re.IGNORECASE,
        ),
        "A re-mark or an appeal has to go to your guide.",
    ),
)


class QueryState(TypedDict, total=False):
    """State for one question. Small, because the context is small."""

    question: str
    context_text: str
    source_labels: list[str]

    in_scope: bool
    classification_reason: str

    answer: str
    sources: list[str]
    confidence: float

    escalated: bool
    escalation_reason: str
    last_error: str

    status: Literal["ANSWERED", "ESCALATED"]


def deterministic_refusal(question: str) -> str:
    """The reason this question is refused outright, or an empty string.

    Mark questions need a mark word *and* a first-person future reading, in
    either order. Requiring both is what keeps "what counts as evidence for the
    C1 score band" answerable while "what score will I get" is not.
    """
    text = question or ""

    if _MARK_NOUNS.search(text) and _SELF_FUTURE.search(text):
        return MARK_REFUSAL
    if _PASS_FAIL.search(text) and _SELF_FUTURE.search(text):
        return MARK_REFUSAL

    for pattern, reason in ALWAYS_ESCALATE:
        if pattern.search(text):
            return reason

    return ""


def build_query_graph(provider):
    """Compile the query graph against a provider."""

    def classify(state: QueryState) -> dict[str, Any]:
        """Policy first, then the model."""
        refusal = deterministic_refusal(state["question"])
        if refusal:
            return {"in_scope": False, "classification_reason": refusal}

        if not state["context_text"].strip():
            return {
                "in_scope": False,
                "classification_reason": (
                    "There is no published rubric or guidance for this milestone yet."
                ),
            }

        prompt = build_classify_prompt(state["question"], state["context_text"])

        try:
            raw = provider.complete(system=CLASSIFY_SYSTEM, user=prompt)
            verdict = parse_classification(raw)
        except (AIResponseError, Exception) as exc:
            # A classifier that cannot answer escalates. Guessing "in scope"
            # here would let a broken call become an invented answer.
            return {
                "in_scope": False,
                "classification_reason": (
                    "The assistant could not check this question, so it has "
                    "gone to your guide."
                ),
                "last_error": str(exc),
            }

        return {
            "in_scope": verdict.in_scope,
            "classification_reason": verdict.reason,
        }

    def answer(state: QueryState) -> dict[str, Any]:
        prompt = build_answer_prompt(state["question"], state["context_text"])

        try:
            raw = provider.complete(system=ANSWER_SYSTEM, user=prompt)
            response = parse_query_response(raw)
        except Exception as exc:
            return {
                "answer": "",
                "confidence": 0.0,
                "last_error": str(exc),
                "classification_reason": (
                    "The assistant could not produce an answer, so this has "
                    "gone to your guide."
                ),
            }

        # Only labels the context actually offers. A model citing a source it
        # was never given is inventing provenance, which is worse than none.
        allowed = {label.casefold() for label in state.get("source_labels", [])}
        sources = [s for s in response.sources if s.casefold() in allowed]

        return {
            "answer": response.answer,
            "sources": sources,
            "confidence": response.confidence,
        }

    def confidence_check(state: QueryState) -> dict[str, Any]:
        """A pass-through node; the routing after it does the work."""
        return {}

    def escalate(state: QueryState) -> dict[str, Any]:
        """Hand the question to the guide, carrying no invented answer.

        §6.4: *"escalate returns a QueryAnswer with escalated=True and no
        invented answer"*. The answer field is cleared here rather than merely
        being ignored downstream, so there is nothing for a caller to render by
        mistake.
        """
        reason = state.get("classification_reason") or (
            "This needs your guide rather than the assistant."
        )
        return {
            "answer": "",
            "sources": [],
            "escalated": True,
            "escalation_reason": reason,
            "status": "ESCALATED",
        }

    def finish(state: QueryState) -> dict[str, Any]:
        return {"escalated": False, "status": "ANSWERED"}

    def after_classify(state: QueryState) -> str:
        return "answer" if state.get("in_scope") else "escalate"

    def after_confidence(state: QueryState) -> str:
        if not state.get("answer", "").strip():
            return "escalate"
        if state.get("confidence", 0.0) < MINIMUM_CONFIDENCE:
            return "escalate"
        return "finish"

    graph = StateGraph(QueryState)

    graph.add_node("classify", classify)
    graph.add_node("answer", answer)
    graph.add_node("confidence_check", confidence_check)
    graph.add_node("escalate", escalate)
    graph.add_node("finish", finish)

    graph.set_entry_point("classify")
    graph.add_conditional_edges("classify", after_classify)
    graph.add_edge("answer", "confidence_check")
    graph.add_conditional_edges("confidence_check", after_confidence)
    graph.add_edge("escalate", END)
    graph.add_edge("finish", END)

    return graph

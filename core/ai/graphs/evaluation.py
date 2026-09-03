"""The evaluation graph — §6.3.

    prepare → evaluate → parse_schema ──ok──▶ verify_evidence ──ok──┐
                  ▲          │ fail                │ fail           │
                  │          ▼                     ▼                ▼
                  └────── repair ──fail──▶ demote_criterion ──▶ aggregate ──▶ END
                          (≤1)

Why a graph rather than nested try/except (§6.2): the flow has two genuine
failure loops, and expressing them as edges makes the retry policy inspectable
instead of buried. The checkpointer then gets resumability for free.

Three rules from §6.3 that the code below is shaped around:

* ``repair_attempts`` is capped at 1 **per batch**. On the second failure the
  batch resolves to ``NO_EVIDENCE`` for its criteria and the run continues —
  one bad batch never fails the whole submission.
* ``demote_criterion`` is a node, not post-processing, so rejections are
  checkpointed and visible rather than recomputed on resume.
* ``aggregate`` produces verdicts and per-criterion raw scores **only**. It
  does not compute totals. ``core/scoring/engine.py`` does that afterwards,
  from the persisted rows — otherwise invariant #2 is broken by a graph node
  deciding a mark.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from core.ai.graphs.state import MAX_REPAIR_ATTEMPTS, EvalState
from core.ai.guards import apply_guard
from core.ai.identity import assert_scrubbed, scrub_identity
from core.ai.prompts.evaluation_v1 import SYSTEM_PROMPT, build_user_prompt
from core.ai.schemas import AIResponseError, CriterionResult, parse_response
from core.rubrics.dto import CriterionDTO, RubricDTO
from core.scoring.enums import Verdict

#: Bumped whenever the node set or edges change, and stamped onto every
#: Evaluation row so a result is reproducible (§6.5).
GRAPH_VERSION = "eval-graph-v1"

#: Decision #4b: batched, because it is cheaper and hits rate limits less
#: often. Split only if per-criterion accuracy is visibly worse.
DEFAULT_BATCH_SIZE = 4


def _rubric_from_state(state: EvalState) -> RubricDTO:
    payload = state["rubric"]
    return RubricDTO(
        id=payload["id"],
        milestone_id=payload["milestone_id"],
        version=payload["version"],
        published_at=None,
        published_by=None,
        criteria=tuple(CriterionDTO(**c) for c in payload["criteria"]),
    )


def _batch_rubric(state: EvalState, batch: list[dict[str, Any]]) -> RubricDTO:
    """A rubric view containing only this batch's criteria."""
    full = _rubric_from_state(state)
    codes = {c["code"] for c in batch}
    return RubricDTO(
        id=full.id,
        milestone_id=full.milestone_id,
        version=full.version,
        published_at=None,
        published_by=None,
        criteria=tuple(c for c in full.criteria if c.code in codes),
    )


def build_graph(provider, *, batch_size: int = DEFAULT_BATCH_SIZE):
    """Compile the graph. ``provider`` is closed over by the calling nodes.

    Taking the provider as an argument rather than constructing one keeps the
    graph testable with a stub, which is how the retry and repair paths are
    exercised without spending tokens.
    """

    # -- nodes -----------------------------------------------------------

    def prepare(state: EvalState) -> dict[str, Any]:
        """Strip identity, then split the rubric into batches.

        Identity goes here, at the first node, so nothing downstream can send
        it even by mistake (invariant #8, fix item 5).
        """
        rubric = _rubric_from_state(state)

        scrubbed, _report = scrub_identity(
            state["text"],
            name=state.get("student_name", ""),
            prn=state.get("student_prn", ""),
            email=state.get("student_email", ""),
        )
        assert_scrubbed(
            scrubbed,
            name=state.get("student_name", ""),
            prn=state.get("student_prn", ""),
            email=state.get("student_email", ""),
        )

        criteria = [
            {
                "id": c.id,
                "code": c.code,
                "title": c.title,
                "description": c.description,
                "weight": str(c.weight),
                "max_score": str(c.max_score),
                "expected_evidence": c.expected_evidence,
                "is_mandatory": c.is_mandatory,
                "order_index": c.order_index,
            }
            for c in rubric.criteria
        ]

        batches = [
            criteria[i : i + batch_size] for i in range(0, len(criteria), batch_size)
        ]

        return {
            "text": scrubbed,
            "batches": batches,
            "cursor": 0,
            "raw_responses": [],
            "parsed": [],
            "rejections": [],
            "observations": [],
            "missing_items": [],
            "repair_attempts": 0,
            "last_error": "",
            "status": "RUNNING",
        }

    def evaluate(state: EvalState) -> dict[str, Any]:
        """One LLM call for the batch under the cursor."""
        batch = state["batches"][state["cursor"]]
        prompt = build_user_prompt(_batch_rubric(state, batch), state["text"])

        try:
            raw = provider.complete(system=SYSTEM_PROMPT, user=prompt)
        except Exception as exc:
            # A provider failure is not a schema failure; repairing would just
            # call the same broken provider again.
            return {
                "last_error": f"provider: {exc}",
                "status": "FAILED",
                "raw_responses": [*state["raw_responses"], ""],
            }

        return {
            "raw_responses": [*state["raw_responses"], raw],
            "last_error": "",
        }

    def parse_schema(state: EvalState) -> dict[str, Any]:
        """Validate the last response against §6.5's contract."""
        if state.get("status") == "FAILED":
            return {}

        raw = state["raw_responses"][-1]

        try:
            response = parse_response(raw)
        except AIResponseError as exc:
            return {"last_error": str(exc)}

        return {
            "last_error": "",
            "_batch_results": [c.model_dump(mode="json") for c in response.criteria],
            "observations": [*state["observations"], *response.overall_observations],
            "missing_items": [*state["missing_items"], *response.missing_items],
        }

    def repair(state: EvalState) -> dict[str, Any]:
        """One corrective call, quoting the validation error back.

        Capped at :data:`MAX_REPAIR_ATTEMPTS` per batch by the edge that routes
        here; this node only performs the attempt and counts it.
        """
        batch = state["batches"][state["cursor"]]
        prompt = build_user_prompt(_batch_rubric(state, batch), state["text"])

        corrective = (
            f"{prompt}\n\n"
            "## Your previous response was rejected\n\n"
            f"{state['last_error']}\n\n"
            "Return the corrected JSON object only. Do not explain the error."
        )

        try:
            raw = provider.complete(system=SYSTEM_PROMPT, user=corrective)
        except Exception as exc:
            return {
                "repair_attempts": state["repair_attempts"] + 1,
                "last_error": f"provider during repair: {exc}",
                "raw_responses": [*state["raw_responses"], ""],
            }

        return {
            "repair_attempts": state["repair_attempts"] + 1,
            "raw_responses": [*state["raw_responses"], raw],
        }

    def verify_evidence(state: EvalState) -> dict[str, Any]:
        """The guard — §6.5. No bypass, at any confidence."""
        results = [
            CriterionResult.model_validate(item)
            for item in state.get("_batch_results", [])
        ]

        outcome = apply_guard(
            results, state["text"], submission_ref=state.get("submission_ref", "")
        )

        return {
            "_batch_results": [c.model_dump(mode="json") for c in outcome.results],
            "_batch_rejections": [
                {
                    "code": r.code,
                    "span": r.span,
                    "match_score": r.match_score,
                    "reason": r.reason,
                }
                for r in outcome.rejections
            ],
        }

    def demote_criterion(state: EvalState) -> dict[str, Any]:
        """Resolve a batch that could not be parsed even after repair.

        Every criterion in it becomes ``NO_EVIDENCE`` at 0, and the reason is
        recorded as a rejection so it shows up in the report rather than
        vanishing as a silent zero.
        """
        batch = state["batches"][state["cursor"]]
        reason = state.get("last_error") or "The model's response could not be parsed."

        results = []
        rejections = []

        for criterion in batch:
            results.append(
                {
                    "code": criterion["code"],
                    "verdict": str(Verdict.NO_EVIDENCE),
                    "score": "0.00",
                    "max_score": criterion["max_score"],
                    "confidence": 0.0,
                    "evidence": "",
                    "rationale": f"Not evaluated: {reason}",
                }
            )
            rejections.append(
                {
                    "code": criterion["code"],
                    "span": "",
                    "match_score": 0.0,
                    "reason": reason,
                }
            )

        return {"_batch_results": results, "_batch_rejections": rejections}

    def aggregate(state: EvalState) -> dict[str, Any]:
        """Fold the batch into the run and advance the cursor.

        Produces verdicts and per-criterion scores only. **No totals** — that
        is ``core/scoring/engine.py``'s job, from the persisted rows, so a
        graph node never decides a mark (invariant #2).
        """
        cursor = state["cursor"] + 1
        done = cursor >= len(state["batches"])

        # A run the provider killed stays FAILED. Overwriting it here would
        # turn a dead provider into a silent set of zeroes, which is precisely
        # the failure fix item 9 names.
        if state.get("status") == "FAILED":
            status = "FAILED"
        else:
            status = "COMPLETE" if done else "RUNNING"

        return {
            "parsed": [*state["parsed"], *state.get("_batch_results", [])],
            "rejections": [*state["rejections"], *state.get("_batch_rejections", [])],
            "cursor": cursor,
            # Reset per batch, so one repaired batch does not consume the
            # allowance of the next — but keep the reason a FAILED run failed,
            # or the grid has nothing to show the faculty member.
            "repair_attempts": 0,
            "last_error": state.get("last_error", "") if status == "FAILED" else "",
            "_batch_results": [],
            "_batch_rejections": [],
            "status": status,
        }

    # -- edges -----------------------------------------------------------

    def after_parse(state: EvalState) -> str:
        if state.get("status") == "FAILED":
            return "aggregate"
        if not state.get("last_error"):
            return "verify_evidence"
        if state.get("repair_attempts", 0) < MAX_REPAIR_ATTEMPTS:
            return "repair"
        # Out of attempts: resolve the batch rather than failing the run.
        return "demote_criterion"

    def after_aggregate(state: EvalState) -> str:
        if state.get("status") == "FAILED":
            return END
        return "evaluate" if state["cursor"] < len(state["batches"]) else END

    graph = StateGraph(EvalState)

    graph.add_node("prepare", prepare)
    graph.add_node("evaluate", evaluate)
    graph.add_node("parse_schema", parse_schema)
    graph.add_node("repair", repair)
    graph.add_node("verify_evidence", verify_evidence)
    graph.add_node("demote_criterion", demote_criterion)
    graph.add_node("aggregate", aggregate)

    graph.set_entry_point("prepare")
    graph.add_edge("prepare", "evaluate")
    graph.add_edge("evaluate", "parse_schema")
    graph.add_conditional_edges("parse_schema", after_parse)
    # A repair loops back through validation, which is what enforces the cap:
    # the second failure finds repair_attempts already at the limit.
    graph.add_edge("repair", "parse_schema")
    graph.add_edge("verify_evidence", "aggregate")
    graph.add_edge("demote_criterion", "aggregate")
    graph.add_conditional_edges("aggregate", after_aggregate)

    return graph

"""The evaluation graph's state — §6.3.

Plain JSON-serialisable types throughout. The checkpointer has to write this to
SQLite and read it back after a Streamlit rerun, so Pydantic models and DTOs
are dumped to dicts at the boundary and rebuilt on use. A state holding live
objects checkpoints badly and resumes worse.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

#: §6.3: capped at one repair per batch. On the second failure the batch
#: resolves to NO_EVIDENCE for its criteria and the run continues — one bad
#: batch never fails a whole submission.
MAX_REPAIR_ATTEMPTS = 1


class EvalState(TypedDict, total=False):
    """§6.3's state, with the fields the nodes actually need to pass along."""

    # Inputs, fixed for the run.
    rubric: dict[str, Any]
    text: str
    submission_ref: str

    # Identity, consumed by ``prepare`` and never sent onward (invariant #8).
    student_name: str
    student_prn: str
    student_email: str

    # Work queue: criteria are evaluated in batches (decision #4b).
    batches: list[list[dict[str, Any]]]
    cursor: int

    # Accumulated output.
    raw_responses: list[str]
    parsed: list[dict[str, Any]]
    rejections: list[dict[str, Any]]
    observations: list[str]
    missing_items: list[str]

    # Per-batch retry bookkeeping, reset when the cursor advances.
    repair_attempts: int
    last_error: str

    # Scratch for the batch in flight. Underscored because it is internal to
    # one lap of the loop; ``aggregate`` folds it into ``parsed`` and clears it.
    _batch_results: list[dict[str, Any]]
    _batch_rejections: list[dict[str, Any]]

    status: Literal["RUNNING", "COMPLETE", "FAILED"]

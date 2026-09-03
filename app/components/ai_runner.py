"""The AI evaluation runner — §6.6.

Streams graph node transitions into ``st.status`` so the demo shows the machine
thinking rather than a frozen spinner, and **persists after every submission,
not at the end of the loop**. That is §6.6's instruction and it is what makes a
mid-run refresh cost you nothing: the submissions already finished are on disk,
and the one in flight resumes from its checkpoint.

Invariant #10 is the first thing this module does: if no provider is
configured, it says so, names what still works, and returns. It never shows a
traceback and never blocks the deterministic half of the page.
"""

from __future__ import annotations

import streamlit as st

from app.context import current_actor, db, get_settings
from app.state import flash, invalidate
from core.ai.provider import (
    AIUnavailable,
    RetryingProvider,
    build_provider,
    stream_evaluation,
)
from core.errors import RubriQError
from core.rubrics.dto import RubricDTO
from core.scoring.ai_runs import (
    finish_ai_evaluation,
    mark_evaluation_failed,
    start_ai_evaluation,
)
from core.scoring.dto import GridRow
from core.scoring.enums import EvaluationStatus
from core.submissions.service import get_submission_text

#: Nodes worth naming in the UI. The rest are plumbing.
NODE_LABELS = {
    "prepare": "stripping identity, batching criteria",
    "evaluate": "asking the model",
    "parse_schema": "validating the response",
    "repair": "response rejected — asking again",
    "verify_evidence": "checking every quote against the submission",
    "demote_criterion": "discarding unusable answers",
    "aggregate": "collecting results",
}


def needs_evaluation(row: GridRow) -> bool:
    """Rows an AI run would help with.

    A completed sheet is left alone: re-running it would create a second
    evaluation version and leave the grader wondering which one they read.
    """
    if not row.has_submitted:
        return False
    if row.sheet is None:
        return True
    return row.sheet.evaluation_status is EvaluationStatus.FAILED


def render_ai_runner(rows: tuple[GridRow, ...], rubric: RubricDTO) -> None:
    """The run button, the status stream, and the offline banner."""
    actor = current_actor()
    settings = get_settings()

    try:
        provider = RetryingProvider(build_provider(settings))
    except AIUnavailable as exc:
        # Invariant #10: say what still works rather than showing a failure.
        st.info(str(exc), icon=":material/smart_toy:")
        return

    pending = [row for row in rows if needs_evaluation(row)]
    failed = [
        row
        for row in rows
        if row.sheet is not None
        and row.sheet.evaluation_status is EvaluationStatus.FAILED
    ]

    if failed:
        st.warning(
            f"{len(failed)} evaluation(s) failed and can be retried. A retry "
            "starts a fresh run rather than resuming the one that failed.",
            icon=":material/error:",
        )

    if not pending:
        st.caption("Every submission here has been evaluated.")
        return

    st.caption(
        f"{len(pending)} submission(s) have no score sheet yet. The AI produces "
        "an estimate with evidence; you approve or override it before anything "
        "is final."
    )

    if not st.button(
        f"Evaluate {len(pending)} submission(s)",
        type="primary",
        icon=":material/smart_toy:",
    ):
        return

    completed = 0
    rejections = 0
    problems: list[str] = []

    with st.status("Evaluating submissions…", expanded=True) as status:
        for row in pending:
            label = row.student_name or row.student_email
            st.write(f"**{label}** · submission v{row.submission_version}")

            try:
                with db() as session:
                    evaluation = start_ai_evaluation(
                        actor, session, submission_id=row.submission_id
                    )
                    evaluation_id = evaluation.id
                    evaluation_version = evaluation.version
                    text = get_submission_text(actor, session, row.submission_id)
            except RubriQError as exc:
                problems.append(f"{label}: {exc}")
                st.write(f"  · skipped — {exc}")
                continue

            result = None
            try:
                for node, payload in stream_evaluation(
                    rubric,
                    text,
                    provider=provider,
                    submission_id=row.submission_id,
                    evaluation_version=evaluation_version,
                    student_name=row.student_name,
                    student_prn=row.prn or "",
                    student_email=row.student_email,
                ):
                    if payload is not None:
                        result = payload
                    elif node in NODE_LABELS:
                        st.write(f"  · {NODE_LABELS[node]}")
            except Exception as exc:
                # Never let one bad submission end the batch.
                with db() as session:
                    mark_evaluation_failed(
                        actor, session, evaluation_id=evaluation_id, reason=str(exc)
                    )
                problems.append(f"{label}: {exc}")
                st.write(f"  · failed — {exc}")
                continue

            # §6.6: persist after EVERY submission, not at the end of the loop.
            try:
                with db() as session:
                    sheet = finish_ai_evaluation(
                        actor, session, evaluation_id=evaluation_id, result=result
                    )
                completed += 1
                rejections += len(result.rejections) if result else 0
                st.write(
                    f"  · estimate {sheet.display_total} / {sheet.max_marks:g}"
                    + (
                        f" — {len(result.rejections)} quote(s) rejected"
                        if result and result.rejections
                        else ""
                    )
                )
            except RubriQError as exc:
                problems.append(f"{label}: {exc}")
                st.write(f"  · not recorded — {exc}")

        state = "complete" if not problems else "error"
        status.update(
            label=f"Done — {completed} evaluated, {len(problems)} problem(s)",
            state=state,
        )

    invalidate()

    if completed:
        flash(
            f"Evaluated {completed} submission(s). "
            f"{rejections} fabricated quote(s) were discarded. "
            "Nothing is final until you approve it."
        )

    if problems:
        st.error(
            "Some submissions did not complete:\n\n"
            + "\n".join(f"- {p}" for p in problems),
            icon=":material/error:",
        )
    else:
        st.rerun()

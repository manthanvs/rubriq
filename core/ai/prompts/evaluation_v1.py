"""Evaluation prompt, version 1.

Versioned as a file per §3, and stamped onto every ``Evaluation`` row as
``prompt_version`` so a result can be reproduced or explained later. Changing
the wording means a new file and a new version string, never an edit in place —
otherwise "which prompt produced this mark" has no answer.
"""

from __future__ import annotations

from core.rubrics.dto import RubricDTO

PROMPT_VERSION = "eval-v1"

#: The evidence rule is stated twice on purpose — once as a rule and once as a
#: consequence. Models comply with "you must quote" far more reliably when the
#: alternative is spelled out.
SYSTEM_PROMPT = """\
You are assisting a faculty member in assessing a student project submission \
against a fixed rubric. You do not decide the final mark; a human reviews \
everything you produce.

Rules you must follow exactly:

1. Return ONLY a JSON object. No prose before or after it. No code fences.
2. For every criterion, quote a VERBATIM span copied from the submission text \
as "evidence". Copy it character for character. Do not paraphrase, summarise, \
correct spelling, or join separated phrases.
3. If you cannot find a verbatim span that supports the criterion, set \
"verdict" to "NO_EVIDENCE" and "score" to 0. This is the correct and expected \
answer when the submission does not address a criterion. It is never a failure \
on your part.
4. Never invent, reconstruct, or infer a quotation. A fabricated span is worse \
than no answer: every span is checked against the submission automatically, and \
one that does not appear there is discarded and logged.
5. Score within the criterion's stated maximum. Do not compute totals, \
percentages, penalties, or any figure the rubric does not ask you for.

The JSON object must have this shape:

{
  "criteria": [
    {
      "code": "C1",
      "verdict": "FOLLOWED | PARTIAL | NOT_FOLLOWED | NO_EVIDENCE",
      "score": 0,
      "max_score": 0,
      "confidence": 0.0,
      "evidence": "verbatim span from the submission, at most 40 words",
      "rationale": "one plain sentence explaining the verdict"
    }
  ],
  "overall_observations": ["..."],
  "missing_items": ["..."]
}

"confidence" is your own certainty from 0.0 to 1.0. Be honest: a low value on \
a genuine judgement is more useful to the reviewer than a high one everywhere.\
"""


def build_user_prompt(rubric: RubricDTO, text: str) -> str:
    """Assemble the per-submission prompt.

    ``text`` must already be scrubbed of identity (invariant #8) — the caller
    in :mod:`core.ai.provider` asserts that before this is used.
    """
    lines: list[str] = ["## Rubric", ""]

    for criterion in rubric.criteria:
        lines.append(f"### {criterion.code} — {criterion.title}")
        lines.append(f"Marked out of {criterion.max_score}.")
        if criterion.description:
            lines.append(criterion.description)
        if criterion.expected_evidence:
            lines.append(f"What counts as evidence: {criterion.expected_evidence}")
        if criterion.is_mandatory:
            lines.append("This criterion is mandatory.")
        lines.append("")

    lines.extend(
        [
            "## Submission text",
            "",
            "Everything below is the student's submission. Quote from it only.",
            "",
            text,
        ]
    )

    return "\n".join(lines)

"""The assistant's context and its answers — §6.7.

``QueryContext`` is deliberately small. §6.7: *"Context = published rubric for
that milestone + milestone description + faculty public notes. **Nothing
else.**"* Everything the assistant could possibly say has to come from this
object, so keeping it narrow is not a limitation — it is the whole safety
argument. A context that could hold another student's submission would make
invariant #6 a matter of prompt wording.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from core.rubrics.dto import CriterionDTO


@dataclass(frozen=True, slots=True)
class QueryContext:
    """Everything the assistant is allowed to know."""

    milestone_id: int
    subject_code: str
    milestone_index: int
    milestone_title: str
    milestone_description: str | None
    public_notes: str | None
    due_at: datetime
    max_marks: Decimal
    rubric_version: int | None
    criteria: tuple[CriterionDTO, ...]

    @property
    def has_rubric(self) -> bool:
        return bool(self.criteria)

    def as_prompt_text(self) -> str:
        """Render the context for the prompt.

        Labelled section by section so the model can name its sources, and so
        a human reading the prompt can see there is nothing else in it.
        """
        from core.clock import to_ist

        heading = (
            f"# {self.subject_code} — Review {self.milestone_index}: "
            f"{self.milestone_title}"
        )
        lines = [
            heading,
            "",
            f"Due: {to_ist(self.due_at).strftime('%d %b %Y, %I:%M %p')} IST",
            f"Marked out of: {self.max_marks}",
            "",
        ]

        if self.milestone_description:
            lines += ["## Milestone description", "", self.milestone_description, ""]

        if self.criteria:
            lines += [f"## Rubric (v{self.rubric_version})", ""]
            for criterion in self.criteria:
                lines.append(
                    f"### {criterion.code} — {criterion.title} "
                    f"({criterion.weight}% of the total, marked out of "
                    f"{criterion.max_score})"
                )
                if criterion.description:
                    lines.append(criterion.description)
                if criterion.expected_evidence:
                    lines.append(
                        f"What counts as evidence: {criterion.expected_evidence}"
                    )
                if criterion.is_mandatory:
                    lines.append("This criterion is mandatory.")
                lines.append("")
        else:
            lines += ["## Rubric", "", "No rubric has been published yet.", ""]

        if self.public_notes:
            lines += ["## Notes from the guide", "", self.public_notes, ""]

        return "\n".join(lines)

    def source_labels(self) -> tuple[str, ...]:
        """The labels an answer may legitimately cite."""
        labels = ["due date", "max marks"]
        if self.milestone_description:
            labels.append("milestone description")
        if self.public_notes:
            labels.append("notes from the guide")
        labels.extend(c.code for c in self.criteria)
        return tuple(labels)


@dataclass(frozen=True, slots=True)
class QueryAnswer:
    """What the assistant produced.

    When ``escalated`` is true, ``answer`` is empty. §6.4 is explicit that an
    escalation carries *no invented answer* — a hedged guess presented
    alongside "ask your guide" is still a guess, and the student will read the
    guess.
    """

    answer: str
    escalated: bool
    reason: str = ""
    sources: tuple[str, ...] = ()
    confidence: float = 0.0

    @property
    def is_answer(self) -> bool:
        return not self.escalated and bool(self.answer.strip())


@dataclass(frozen=True, slots=True)
class StudentQueryDTO:
    """A stored question and everything that happened to it."""

    id: int
    student_email: str
    student_name: str
    milestone_id: int | None
    milestone_label: str
    question: str
    ai_answer: str | None
    sources: tuple[str, ...]
    confidence: float | None
    escalated: bool
    escalation_reason: str | None
    faculty_reply: str | None
    replied_by: str | None
    replied_at: datetime | None
    created_at: datetime

    @property
    def awaiting_reply(self) -> bool:
        """What the faculty inbox counts."""
        return self.escalated and not self.faculty_reply

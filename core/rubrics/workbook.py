"""Turn a parsed rubric workbook into milestones and draft rubrics.

The parser in :mod:`core.rubrics.excel_import` reads the file; this decides
what to do with what it read.

Two rules shape it.

**Nothing is published.** Every rubric it creates is a draft. Publishing
freezes a rubric for everything graded against it, so it stays a deliberate
act a person performs after reading what was imported — not a side effect of
an upload.

**Nothing already published is touched.** A milestone whose rubric is already
published gets a new draft version beside it, exactly as editing by hand
would. Work already marked keeps the rubric it was marked against
(invariant #7).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from core.academics.access import require_faculty
from core.academics.milestones import create_milestone, list_milestones
from core.auth.actor import Actor
from core.clock import utc_now
from core.errors import ValidationError
from core.rubrics.excel_import import ParsedReview, parse_rubric_workbook
from core.rubrics.service import (
    add_criterion,
    clone_for_edit,
    create_rubric,
    draft_rubric_for,
    published_rubric_for,
)

#: How far apart imported milestones land when the workbook gives no dates.
#: A spreadsheet of criteria says nothing about when anything is due, so the
#: guide sets real dates afterwards; these only exist because a milestone
#: cannot be created without one.
DEFAULT_GAP = timedelta(days=45)


@dataclass(frozen=True, slots=True)
class ImportedReview:
    """What happened to one review in the workbook."""

    index: int
    title: str
    milestone_id: int
    rubric_id: int
    criteria: int
    milestone_created: bool
    replaced_published: bool

    @property
    def note(self) -> str:
        if self.milestone_created:
            return "new review created, rubric drafted"
        if self.replaced_published:
            return "drafted as a new version beside the published one"
        return "existing draft replaced"


@dataclass(frozen=True, slots=True)
class ImportSummary:
    reviews: tuple[ImportedReview, ...]

    @property
    def criteria_total(self) -> int:
        return sum(r.criteria for r in self.reviews)


def preview_workbook(data: bytes) -> tuple[ParsedReview, ...]:
    """Read the workbook without writing anything.

    Separate from :func:`import_workbook` so a page can show what it found and
    let the guide decide, rather than importing and asking afterwards.
    """
    return parse_rubric_workbook(data)


def import_workbook(
    actor: Actor,
    session: Session,
    *,
    cycle_id: int,
    subject_id: int,
    data: bytes,
) -> ImportSummary:
    """Create or update a draft rubric for every review in the workbook."""
    require_faculty(actor, "import rubrics")

    reviews = parse_rubric_workbook(data)
    if not reviews:
        raise ValidationError("That workbook contains no reviews to import.")

    existing = {
        milestone.index: milestone
        for milestone in list_milestones(actor, session, subject_id=subject_id)
    }

    imported: list[ImportedReview] = []
    for review in reviews:
        milestone = existing.get(review.index)
        created = milestone is None

        if milestone is None:
            milestone = create_milestone(
                actor,
                session,
                cycle_id=cycle_id,
                index=review.index,
                title=review.title,
                due_at=utc_now() + DEFAULT_GAP * review.index,
                max_marks=review.max_marks,
                description=(
                    "Imported from the department rubric workbook. "
                    "Set the due date before publishing."
                ),
                is_visible=False,
            )

        rubric_id, replaced = _draft_for(actor, session, milestone.id)

        for criterion in review.criteria:
            add_criterion(
                actor,
                session,
                rubric_id=rubric_id,
                code=criterion.code,
                title=criterion.title,
                weight=criterion.weight,
                max_score=criterion.max_score,
                description=criterion.description,
                expected_evidence=_expected(criterion.descriptors),
                # The first criterion of a review is the one a mark cannot be
                # awarded without evidence for; the workbook does not say
                # which are mandatory, so the guide sets the rest by hand.
                is_mandatory=criterion.code == "C1",
            )

        imported.append(
            ImportedReview(
                index=review.index,
                title=review.title,
                milestone_id=milestone.id,
                rubric_id=rubric_id,
                criteria=len(review.criteria),
                milestone_created=created,
                replaced_published=replaced,
            )
        )

    return ImportSummary(reviews=tuple(imported))


def _draft_for(actor: Actor, session: Session, milestone_id: int) -> tuple[int, bool]:
    """A draft rubric to fill, and whether a published one already existed.

    An existing draft is reused and emptied rather than added to, or a second
    import would leave ten criteria where the workbook declares five.
    """
    draft = draft_rubric_for(actor, session, milestone_id)
    if draft is not None:
        _empty(session, draft.id)
        return draft.id, False

    published = published_rubric_for(actor, session, milestone_id)
    if published is not None:
        clone = clone_for_edit(actor, session, rubric_id=published.id)
        _empty(session, clone.id)
        return clone.id, True

    return create_rubric(actor, session, milestone_id=milestone_id).id, False


def _empty(session: Session, rubric_id: int) -> None:
    """Remove the criteria of a draft, so an import replaces rather than adds.

    Deleting rows is allowed here and only here: a *draft* criterion has never
    been graded against, so nothing references it. Invariant #7 protects
    submissions, evaluations and overrides — not an unpublished draft nobody
    has used.
    """
    from sqlalchemy import delete

    from core.db.models import Criterion

    session.execute(delete(Criterion).where(Criterion.rubric_id == rubric_id))
    session.flush()


def _expected(descriptors: tuple[tuple[str, str], ...]) -> str:
    """What full marks looks like — the first level with anything in it."""
    for _label, text in descriptors:
        if text:
            return text
    return ""


def weights_are_publishable(review: ParsedReview) -> bool:
    """Whether this review would survive the publish check."""
    return review.weight_total == Decimal(100) and bool(review.criteria)

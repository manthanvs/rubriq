"""Fix item 6 — rubric immutability.

The four failures it names, each with a test:

1. a published rubric edited in place, retroactively changing what an
   already-graded submission was measured against;
2. publishing without the weight-sum check;
3. deleting a criterion that scores still reference;
4. a submission evaluated against an unpublished draft.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.db.engine import session_scope
from core.errors import NotAuthorized, ValidationError
from core.rubrics.service import (
    add_criterion,
    clone_for_edit,
    create_rubric,
    draft_rubric_for,
    get_rubric,
    list_rubrics,
    publish_rubric,
    published_rubric_for,
    remove_criterion,
)


def _draft_with_weights(session, actor, milestone_id, weights) -> int:
    """A draft rubric carrying one criterion per weight given."""
    rubric = create_rubric(actor, session, milestone_id=milestone_id)
    for index, weight in enumerate(weights, start=1):
        add_criterion(
            actor,
            session,
            rubric_id=rubric.id,
            code=f"C{index}",
            title=f"Criterion {index}",
            weight=weight,
            max_score=10,
        )
    return rubric.id


@pytest.fixture
def published_rubric(db_factory, world) -> int:
    with session_scope(db_factory) as session:
        rubric_id = _draft_with_weights(
            session, world.faculty_a, world.milestone_visible, [60, 40]
        )
        publish_rubric(world.faculty_a, session, rubric_id=rubric_id)
    return rubric_id


class TestPublishValidation:
    def test_weights_must_sum_to_one_hundred(self, db_factory, world) -> None:
        """Weights summing to 95 make every base_total silently out of 95."""
        with session_scope(db_factory) as session:
            rubric_id = _draft_with_weights(
                session, world.faculty_a, world.milestone_visible, [60, 35]
            )

            with pytest.raises(ValidationError) as excinfo:
                publish_rubric(world.faculty_a, session, rubric_id=rubric_id)

        assert "100" in str(excinfo.value)
        assert "95" in str(excinfo.value)

    def test_a_rubric_with_no_criteria_cannot_publish(self, db_factory, world) -> None:
        with session_scope(db_factory) as session:
            rubric = create_rubric(
                world.faculty_a, session, milestone_id=world.milestone_visible
            )

            with pytest.raises(ValidationError):
                publish_rubric(world.faculty_a, session, rubric_id=rubric.id)

    def test_exactly_one_hundred_publishes(self, db_factory, world) -> None:
        with session_scope(db_factory) as session:
            rubric_id = _draft_with_weights(
                session, world.faculty_a, world.milestone_visible, [25, 25, 50]
            )
            published = publish_rubric(world.faculty_a, session, rubric_id=rubric_id)

        assert published.is_published
        assert published.total_weight == Decimal("100")
        assert published.published_by == world.faculty_a.email

    def test_fractional_weights_that_sum_exactly_are_accepted(
        self, db_factory, world
    ) -> None:
        """Decimal, not float: 33.33 + 33.33 + 33.34 is exactly 100 here."""
        with session_scope(db_factory) as session:
            rubric_id = _draft_with_weights(
                session,
                world.faculty_a,
                world.milestone_visible,
                ["33.33", "33.33", "33.34"],
            )
            published = publish_rubric(world.faculty_a, session, rubric_id=rubric_id)

        assert published.total_weight == Decimal("100.00")


class TestImmutability:
    def test_a_published_rubric_rejects_new_criteria(
        self, db_factory, world, published_rubric
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError) as excinfo:
                add_criterion(
                    world.faculty_a,
                    session,
                    rubric_id=published_rubric,
                    code="C3",
                    title="Sneaked in",
                    weight=10,
                    max_score=10,
                )

        assert "published" in str(excinfo.value).lower()

    def test_a_published_rubric_rejects_criterion_removal(
        self, db_factory, world, published_rubric
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError):
                remove_criterion(
                    world.faculty_a, session, rubric_id=published_rubric, code="C1"
                )

    def test_publishing_twice_is_refused(
        self, db_factory, world, published_rubric
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError):
                publish_rubric(world.faculty_a, session, rubric_id=published_rubric)


class TestCloneForEdit:
    def test_editing_a_published_rubric_creates_v2(
        self, db_factory, world, published_rubric
    ) -> None:
        with session_scope(db_factory) as session:
            clone = clone_for_edit(world.faculty_a, session, rubric_id=published_rubric)

        assert clone.version == 2
        assert clone.is_published is False
        assert [c.code for c in clone.criteria] == ["C1", "C2"]

    def test_v1_is_untouched_by_edits_to_v2(
        self, db_factory, world, published_rubric
    ) -> None:
        """The whole point: what v1 was graded against does not move."""
        with session_scope(db_factory) as session:
            before = get_rubric(world.faculty_a, session, published_rubric)

        with session_scope(db_factory) as session:
            clone = clone_for_edit(world.faculty_a, session, rubric_id=published_rubric)
            remove_criterion(world.faculty_a, session, rubric_id=clone.id, code="C2")
            add_criterion(
                world.faculty_a,
                session,
                rubric_id=clone.id,
                code="C9",
                title="Brand new",
                weight=40,
                max_score=10,
            )

        with session_scope(db_factory) as session:
            after = get_rubric(world.faculty_a, session, published_rubric)

        assert after == before, "v1 changed when v2 was edited"
        assert [c.code for c in after.criteria] == ["C1", "C2"]
        assert after.published_at == before.published_at

    def test_a_removed_criterion_is_deactivated_not_deleted(
        self, db_factory, world, published_rubric
    ) -> None:
        """CriterionScore rows still point at it (invariant #7)."""
        from sqlalchemy import select

        from core.db.models import Criterion

        with session_scope(db_factory) as session:
            clone = clone_for_edit(world.faculty_a, session, rubric_id=published_rubric)
            remove_criterion(world.faculty_a, session, rubric_id=clone.id, code="C2")

        with session_scope(db_factory) as session:
            rows = session.scalars(
                select(Criterion).where(Criterion.rubric_id == clone.id)
            ).all()

        codes = {row.code: row.is_active for row in rows}
        assert codes == {"C1": True, "C2": False}, "the row must survive, deactivated"

    def test_a_draft_cannot_be_cloned(self, db_factory, world) -> None:
        with session_scope(db_factory) as session:
            rubric = create_rubric(
                world.faculty_a, session, milestone_id=world.milestone_visible
            )

            with pytest.raises(ValidationError):
                clone_for_edit(world.faculty_a, session, rubric_id=rubric.id)

    def test_only_one_draft_at_a_time(self, db_factory, world, published_rubric) -> None:
        """Two open drafts leave "which one publishes" undefined."""
        with session_scope(db_factory) as session:
            clone_for_edit(world.faculty_a, session, rubric_id=published_rubric)

        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError):
                clone_for_edit(world.faculty_a, session, rubric_id=published_rubric)


class TestSelection:
    def test_only_a_published_rubric_is_offered_for_grading(
        self, db_factory, world
    ) -> None:
        """A draft must never be what a submission is evaluated against."""
        with session_scope(db_factory) as session:
            _draft_with_weights(
                session, world.faculty_a, world.milestone_visible, [50, 50]
            )
            assert (
                published_rubric_for(world.faculty_a, session, world.milestone_visible)
                is None
            )

    def test_the_highest_published_version_wins(
        self, db_factory, world, published_rubric
    ) -> None:
        with session_scope(db_factory) as session:
            clone = clone_for_edit(world.faculty_a, session, rubric_id=published_rubric)
            publish_rubric(world.faculty_a, session, rubric_id=clone.id)

        with session_scope(db_factory) as session:
            current = published_rubric_for(
                world.faculty_a, session, world.milestone_visible
            )
            history = list_rubrics(world.faculty_a, session, world.milestone_visible)

        assert current.version == 2
        assert [r.version for r in history] == [2, 1], "v1 is still retrievable"

    def test_the_draft_is_separate_from_the_published_one(
        self, db_factory, world, published_rubric
    ) -> None:
        with session_scope(db_factory) as session:
            clone_for_edit(world.faculty_a, session, rubric_id=published_rubric)

        with session_scope(db_factory) as session:
            live = published_rubric_for(world.faculty_a, session, world.milestone_visible)
            draft = draft_rubric_for(world.faculty_a, session, world.milestone_visible)

        assert live.version == 1 and live.is_published
        assert draft.version == 2 and not draft.is_published


class TestScoping:
    def test_a_student_cannot_create_a_rubric(self, db_factory, world) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                create_rubric(
                    world.student_1, session, milestone_id=world.milestone_visible
                )

    def test_a_student_cannot_publish(self, db_factory, world, published_rubric) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                publish_rubric(world.student_1, session, rubric_id=published_rubric)

    def test_another_faculty_cannot_touch_your_rubric(
        self, db_factory, world, published_rubric
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                clone_for_edit(world.faculty_b, session, rubric_id=published_rubric)

"""Importing the department workbook into real milestones and rubrics.

The parser's tests prove the file is read correctly. These prove what is done
with it — and in particular the two things that must not happen: nothing is
published by an upload, and nothing already published is overwritten.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.db.engine import session_scope
from core.rubrics.service import (
    draft_rubric_for,
    publish_rubric,
    published_rubric_for,
)
from core.rubrics.workbook import import_workbook, preview_workbook

FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "department_rubric.xlsx"
)


@pytest.fixture(scope="module")
def workbook() -> bytes:
    return FIXTURE.read_bytes()


def _import(world, db_factory, data):
    """Import into the world's existing subject and cycle.

    The world already has milestones at index 1 and 2, which is exactly the
    interesting case: the workbook declares reviews 1 and 2, so an import has
    to attach to what is there rather than creating a duplicate pair.
    """
    with session_scope(db_factory) as session:
        return import_workbook(
            world.faculty_a,
            session,
            cycle_id=world.cycle_a,
            subject_id=world.subject_a,
            data=data,
        )


def test_preview_reads_without_writing(workbook) -> None:
    reviews = preview_workbook(workbook)
    assert [r.index for r in reviews] == [1, 2]


def test_import_creates_a_draft_for_every_review(world, db_factory, workbook) -> None:
    summary = _import(world, db_factory, workbook)

    assert len(summary.reviews) == 2
    assert summary.criteria_total == 10

    with session_scope(db_factory) as session:
        for imported in summary.reviews:
            draft = draft_rubric_for(world.faculty_a, session, imported.milestone_id)
            assert draft is not None, "the import should leave a draft"
            assert draft.published_at is None, "an upload must not publish"
            assert len(draft.criteria) == 5


def test_nothing_is_published_by_an_upload(world, db_factory, workbook) -> None:
    """Publishing freezes a rubric for everything graded against it."""
    summary = _import(world, db_factory, workbook)

    with session_scope(db_factory) as session:
        for imported in summary.reviews:
            published = published_rubric_for(
                world.faculty_a, session, imported.milestone_id
            )
            assert published is None


def test_importing_twice_replaces_rather_than_doubles(
    world, db_factory, workbook
) -> None:
    """A second upload of the same file must not leave ten criteria."""
    first = _import(world, db_factory, workbook)
    second = _import(world, db_factory, workbook)

    with session_scope(db_factory) as session:
        for imported in second.reviews:
            draft = draft_rubric_for(world.faculty_a, session, imported.milestone_id)
            assert len(draft.criteria) == 5

    # The same milestones, not a second set.
    assert {r.milestone_id for r in first.reviews} == {
        r.milestone_id for r in second.reviews
    }
    assert all(not r.milestone_created for r in second.reviews)


def test_a_published_rubric_is_left_alone(world, db_factory, workbook) -> None:
    """Import beside it as a new version; never edit what is frozen."""
    summary = _import(world, db_factory, workbook)
    first = summary.reviews[0]

    with session_scope(db_factory) as session:
        published = publish_rubric(world.faculty_a, session, rubric_id=first.rubric_id)
        published_id = published.id

    again = _import(world, db_factory, workbook)
    reimported = next(r for r in again.reviews if r.milestone_id == first.milestone_id)

    assert reimported.replaced_published is True
    assert reimported.rubric_id != published_id, "the frozen one must not be reused"

    with session_scope(db_factory) as session:
        still = published_rubric_for(world.faculty_a, session, first.milestone_id)
        assert still.id == published_id, "the published version must still resolve"
        assert len(still.criteria) == 5

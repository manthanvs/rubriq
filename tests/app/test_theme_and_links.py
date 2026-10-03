"""Cross-page links, and the shared status vocabulary.

``page_path_for`` exists so a dashboard can send someone to the page that
resolves the number it just showed. It reads the same spec list the sidebar
is built from, which is what stops it becoming a second, quietly divergent
idea of who may see what — a hardcoded link string would be exactly that, and
invariant #6 is not something to re-implement per page.
"""

from __future__ import annotations

import pytest

from app.components.theme import STATUS_STYLE, metric_card, section, status_chip
from app.navigation import APP_DIR, page_path_for
from core.auth.pages import pages_for
from core.auth.roles import Role

FACULTY_ONLY = ("faculty_review_grid", "faculty_reports", "faculty_activity")
STUDENT_ONLY = ("student_submit", "student_feedback", "student_ask")


@pytest.mark.parametrize("key", FACULTY_ONLY)
def test_a_student_gets_no_link_to_a_faculty_page(key: str) -> None:
    """The negative. A link is navigation, so it has to obey the same rule."""
    assert page_path_for(Role.STUDENT, key) is None


@pytest.mark.parametrize("key", STUDENT_ONLY)
def test_faculty_gets_no_link_to_a_student_page(key: str) -> None:
    assert page_path_for(Role.FACULTY, key) is None


@pytest.mark.parametrize("role", [Role.FACULTY, Role.STUDENT])
def test_every_page_a_role_has_resolves_to_a_real_file(role: Role) -> None:
    for spec in pages_for(role):
        resolved = page_path_for(role, spec.key)
        assert resolved is not None, f"{role.name} lost {spec.key}"
        assert resolved.is_absolute(), "relative paths break when the entry moves"
        assert resolved.is_file(), f"{resolved} does not exist"
        assert resolved.parent.is_relative_to(APP_DIR)


def test_an_unknown_key_is_none_rather_than_an_error() -> None:
    """A caller should be able to not draw a link, not handle an exception."""
    assert page_path_for(Role.FACULTY, "no_such_page") is None


def test_every_status_the_dashboards_use_has_a_style() -> None:
    """A status with no entry renders grey with a question mark, which is a
    silent way to be wrong. These are the ones the pages actually pass."""
    used = {"Submitted", "Not submitted", "Approved", "Absent"}
    assert used <= set(STATUS_STYLE)


def test_the_render_helpers_import_and_are_callable() -> None:
    """They touch Streamlit at call time, so this only guards the signatures."""
    for helper in (metric_card, section, status_chip):
        assert callable(helper)

"""Phase 1 exit criterion: a student can never reach a faculty page.

CLAUDE.md §10 is explicit that this is proved "by a test on the page-list
builder, not by clicking around". So the policy lives in ``core`` as data and
is asserted here — no Streamlit, no browser, no session.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.auth.pages import ALL_PAGES, can_access, default_page_for, pages_for
from core.auth.roles import Role

APP = Path(__file__).resolve().parents[3] / "app"

# §8, verbatim.
EXPECTED_FACULTY = [
    "Dashboard",
    "Subjects",
    "Rubric Builder",
    "Calendar",
    "Review Grid",
    "Query Inbox",
    "Reports",
]
EXPECTED_STUDENT = ["Dashboard", "Calendar", "Submit", "Feedback", "Ask RubriQ"]


class TestRoleFiltering:
    def test_faculty_sees_exactly_the_pages_in_section_8(self) -> None:
        assert [spec.title for spec in pages_for(Role.FACULTY)] == EXPECTED_FACULTY

    def test_student_sees_exactly_the_pages_in_section_8(self) -> None:
        assert [spec.title for spec in pages_for(Role.STUDENT)] == EXPECTED_STUDENT

    def test_a_student_gets_no_faculty_page(self) -> None:
        """The criterion itself: nothing under pages/faculty/ is ever returned."""
        paths = [spec.path for spec in pages_for(Role.STUDENT)]

        assert paths, "a student must still get their own pages"
        assert not [p for p in paths if "faculty" in p]

    def test_a_faculty_member_gets_no_student_page(self) -> None:
        paths = [spec.path for spec in pages_for(Role.FACULTY)]

        assert not [p for p in paths if "student" in p]

    def test_admin_sees_the_teaching_side(self) -> None:
        assert [spec.title for spec in pages_for(Role.ADMIN)] == EXPECTED_FACULTY

    def test_every_role_lands_somewhere(self) -> None:
        for role in Role:
            assert default_page_for(role) is not None


class TestCanAccess:
    @pytest.mark.parametrize(
        "key",
        [
            "faculty_review_grid",
            "faculty_subjects",
            "faculty_rubrics",
            "faculty_reports",
            "faculty_query_inbox",
        ],
    )
    def test_a_student_is_refused_every_faculty_page(self, key: str) -> None:
        assert can_access(Role.STUDENT, key) is False

    def test_faculty_is_allowed_the_review_grid(self) -> None:
        assert can_access(Role.FACULTY, "faculty_review_grid") is True

    def test_an_unknown_key_is_refused_not_ignored(self) -> None:
        """A renamed page should lock, not silently open."""
        assert can_access(Role.FACULTY, "faculty_does_not_exist") is False

    def test_can_access_agrees_with_pages_for(self) -> None:
        """The two must not drift — they are the same policy asked twice."""
        for role in Role:
            allowed = {spec.key for spec in pages_for(role)}
            for spec in ALL_PAGES:
                assert can_access(role, spec.key) is (spec.key in allowed)


class TestSpecIntegrity:
    def test_keys_are_unique(self) -> None:
        keys = [spec.key for spec in ALL_PAGES]
        assert len(keys) == len(set(keys))

    def test_no_page_is_visible_to_nobody(self) -> None:
        for spec in ALL_PAGES:
            assert spec.roles, f"{spec.key} has no roles and can never be reached"

    def test_exactly_one_default_per_role(self) -> None:
        for role in Role:
            defaults = [spec for spec in pages_for(role) if spec.default]
            assert len(defaults) == 1, f"{role} has {len(defaults)} default pages"

    def test_every_declared_page_module_exists(self) -> None:
        """A typo in a path is a runtime 404 that no other test would catch."""
        missing = [spec.path for spec in ALL_PAGES if not (APP / spec.path).is_file()]

        assert not missing, f"declared but not on disk: {missing}"

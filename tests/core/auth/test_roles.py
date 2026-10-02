"""Invariant #5 — a role comes from the allow-list, server-side."""

from __future__ import annotations

from core.auth.roles import Role, resolve_role

FACULTY = ("guide@pccoepune.org",)
ADMINS = ("admin@pccoepune.org",)


def test_an_unlisted_address_is_a_student() -> None:
    """The safe default: unknown means least privilege."""
    assert resolve_role("someone@pccoepune.org", FACULTY, ADMINS) is Role.STUDENT


def test_an_allow_listed_address_is_faculty() -> None:
    assert resolve_role("guide@pccoepune.org", FACULTY) is Role.FACULTY


def test_matching_ignores_case() -> None:
    """The allow-list is hand-written; Google does not promise a case."""
    assert resolve_role("Guide@PCCOEPune.org", FACULTY) is Role.FACULTY


def test_matching_ignores_surrounding_whitespace_in_the_list() -> None:
    assert resolve_role("hod@pccoepune.org", ("  hod@pccoepune.org  ",)) is Role.FACULTY


def test_admin_wins_over_faculty() -> None:
    both = ("both@pccoepune.org",)
    assert resolve_role("both@pccoepune.org", both, both) is Role.ADMIN


def test_empty_allow_lists_produce_students_only() -> None:
    assert resolve_role("anyone@pccoepune.org") is Role.STUDENT


def test_role_renders_as_its_value() -> None:
    """Guards the audit payloads and the sidebar from showing 'Role.FACULTY'."""
    assert f"{Role.FACULTY}" == "FACULTY"

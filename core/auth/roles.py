"""Role resolution.

Invariant #5: a role is derived from a seeded allow-list, server-side, every
time. It is never read from the client, never chosen on a sign-up form, and
never trusted from a stored row — the stored value is a cache of this
function's answer, not its source.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from core.auth.domain import normalise_email


class Role(StrEnum):
    """Who someone is.

    ``StrEnum`` so it persists and renders as its plain value — an audit
    payload reading ``"FACULTY"`` rather than ``"Role.FACULTY"`` is the
    difference between a readable history panel and a puzzle.
    """

    STUDENT = "STUDENT"
    FACULTY = "FACULTY"
    ADMIN = "ADMIN"


def resolve_role(
    email: str,
    faculty_allowlist: Iterable[str] = (),
    admin_allowlist: Iterable[str] = (),
) -> Role:
    """Resolve a role from the allow-lists.

    Everyone not named is a student. That default is deliberate: a typo in the
    allow-list costs a faculty member their pages until it is fixed, which is
    noticed immediately, whereas the opposite default would hand a student a
    review grid and nobody would notice at all.
    """
    normalised = normalise_email(email)

    if normalised in {normalise_email(entry) for entry in admin_allowlist}:
        return Role.ADMIN

    if normalised in {normalise_email(entry) for entry in faculty_allowlist}:
        return Role.FACULTY

    return Role.STUDENT

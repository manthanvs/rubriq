"""The acting user, as a plain value.

Every public service function in ``core/`` takes one of these as its first
argument and scopes its query by it (fix item 3). It is deliberately *not* the
``User`` ORM row:

* it is detached, so passing it across a Streamlit rerun cannot trigger a lazy
  load against a closed session;
* it is frozen, so a page cannot hand a service a mutated role;
* it carries only what authorisation needs, so there is nothing extra to leak.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.auth.roles import Role


@dataclass(frozen=True, slots=True)
class Actor:
    """Who is making this request."""

    email: str
    role: Role
    name: str = ""

    @property
    def is_faculty(self) -> bool:
        """Faculty and admin both see the teaching side."""
        return self.role in {Role.FACULTY, Role.ADMIN}

    @property
    def is_student(self) -> bool:
        return self.role is Role.STUDENT

    @property
    def is_admin(self) -> bool:
        return self.role is Role.ADMIN

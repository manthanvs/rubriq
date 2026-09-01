"""Exception hierarchy.

Two failures that look similar and must never be confused:

* :class:`AuthError` — *who are you*. The sign-in itself is refused.
* :class:`NotAuthorized` — identity is established, but this actor may not
  touch this row. Raised by the query layer, never by the UI hiding a button.
"""

from __future__ import annotations


class RubriQError(Exception):
    """Base for every error this application raises deliberately.

    Carries a message written for a human, because the view layer renders it
    directly rather than showing a traceback (fix item 13).
    """


class AuthError(RubriQError):
    """Sign-in refused — wrong domain, missing claim, malformed email."""


class NotAuthorized(RubriQError):
    """The actor is known and may not do this (invariant #6)."""


class ValidationError(RubriQError):
    """Input failed a domain rule — weights not summing to 100, empty reason."""

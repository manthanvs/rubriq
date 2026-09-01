"""Email normalisation and the institute-domain assertion.

This is invariant #4 and it is the *only* thing standing between the app and
a personal Google account. The ``hd=pccoepune.org`` parameter handed to Google
changes which accounts the consent screen offers; it is a convenience, and a
determined user can bypass it by editing the authorisation URL. The check that
counts happens here, server-side, against the email claim that comes back.
"""

from __future__ import annotations

from core.errors import AuthError


def normalise_email(raw: str | None) -> str:
    """Lower-case and strip an email claim.

    Google does not promise a particular case in the ``email`` claim, and the
    faculty allow-list is written by hand. Comparing anything but normalised
    forms is how ``Anjana.Arakerimath@…`` quietly becomes a student.
    """
    return (raw or "").strip().lower()


def domain_of(email: str) -> str:
    """The part after the single ``@``, without a trailing dot.

    Raises :class:`AuthError` rather than returning something empty, so a
    malformed address cannot slip through as "domain didn't match".
    """
    normalised = normalise_email(email)

    if normalised.count("@") != 1:
        raise AuthError(f"{email!r} is not a valid email address.")

    local, _, domain = normalised.partition("@")
    domain = domain.rstrip(".")

    if not local or not domain:
        raise AuthError(f"{email!r} is not a valid email address.")

    return domain


def assert_allowed_domain(email: str | None, allowed_domain: str) -> str:
    """Return the normalised email, or raise :class:`AuthError`.

    Matching is exact. ``student@pccoepune.org.example.com`` and
    ``student@mail.pccoepune.org`` are both refused — the first is a
    lookalike domain, the second is a subdomain nobody has authorised.
    """
    allowed = normalise_email(allowed_domain).rstrip(".")

    if not allowed:
        raise AuthError("No allowed email domain is configured.")

    normalised = normalise_email(email)

    if not normalised:
        raise AuthError("Google did not return an email address for this account.")

    if domain_of(normalised) != allowed:
        raise AuthError(
            f"Sign-in is restricted to @{allowed} accounts. "
            f"You signed in as {normalised}."
        )

    return normalised

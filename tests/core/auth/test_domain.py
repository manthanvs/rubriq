"""Invariant #4 — sign-in is restricted to the institute domain.

Phase 1's exit criterion is "a personal Gmail account is rejected". These are
the tests that prove it, and they prove it without a browser: the assertion is
a pure function, so the lookalike-domain cases below can be enumerated rather
than clicked through.
"""

from __future__ import annotations

import pytest

from core.auth.domain import assert_allowed_domain, domain_of, normalise_email
from core.errors import AuthError

DOMAIN = "pccoepune.org"


class TestNormalise:
    def test_lowercases_and_strips(self) -> None:
        assert normalise_email("  Manthan.Sankpal@PCCOEPune.org ") == (
            "manthan.sankpal@pccoepune.org"
        )

    def test_none_becomes_empty(self) -> None:
        assert normalise_email(None) == ""


class TestDomainOf:
    def test_extracts_the_domain(self) -> None:
        assert domain_of("student@pccoepune.org") == "pccoepune.org"

    def test_strips_a_trailing_dot(self) -> None:
        assert domain_of("student@pccoepune.org.") == "pccoepune.org"

    @pytest.mark.parametrize(
        "bad",
        ["no-at-sign", "two@at@signs.com", "@pccoepune.org", "student@", ""],
    )
    def test_malformed_addresses_raise(self, bad: str) -> None:
        with pytest.raises(AuthError):
            domain_of(bad)


class TestAssertAllowedDomain:
    def test_accepts_an_institute_address(self) -> None:
        assert assert_allowed_domain("student@pccoepune.org", DOMAIN) == (
            "student@pccoepune.org"
        )

    def test_returns_the_normalised_form(self) -> None:
        assert assert_allowed_domain(" Student@PCCOEPune.ORG ", DOMAIN) == (
            "student@pccoepune.org"
        )

    def test_rejects_a_personal_gmail_account(self) -> None:
        """The Phase 1 exit criterion, stated directly."""
        with pytest.raises(AuthError) as excinfo:
            assert_allowed_domain("manthan@gmail.com", DOMAIN)

        message = str(excinfo.value)
        assert "pccoepune.org" in message
        assert "manthan@gmail.com" in message  # tell them what they signed in as

    @pytest.mark.parametrize(
        "lookalike",
        [
            "student@pccoepune.org.example.com",  # suffix attack
            "student@mail.pccoepune.org",  # unauthorised subdomain
            "student@pccoepune.com",  # wrong TLD
            "student@pccoepune.org.in",
            "student@notpccoepune.org",
        ],
    )
    def test_rejects_lookalike_domains(self, lookalike: str) -> None:
        with pytest.raises(AuthError):
            assert_allowed_domain(lookalike, DOMAIN)

    def test_rejects_a_missing_email_claim(self) -> None:
        with pytest.raises(AuthError):
            assert_allowed_domain(None, DOMAIN)

    def test_rejects_when_no_domain_is_configured(self) -> None:
        """Fail closed. An empty allowed domain must never mean 'allow all'."""
        with pytest.raises(AuthError):
            assert_allowed_domain("student@pccoepune.org", "")

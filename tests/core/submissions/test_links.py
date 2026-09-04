"""Decision #6 — a repository URL is accepted on the strength of a *registered*
profile, not on the strength of looking like a GitHub link.

The interesting tests here are the negative ones. A URL parser that accepts
everything shaped like GitHub is a URL parser that accepts somebody else's
work, and the host-spoofing cases below are the ones a naive "does it contain
github.com" check waves straight through.
"""

from __future__ import annotations

import pytest

from core.errors import ValidationError
from core.submissions.links import (
    GitHubRef,
    assert_owned,
    matching_profile,
    parse_github_url,
)

STUDENT = "manthan.sankpal@pccoepune.org"
MATE = "rahul.deshmukh@pccoepune.org"

REGISTER = {STUDENT: "manthan-vs", MATE: "rahul-d"}


class TestShapesStudentsActuallyPaste:
    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/manthan-vs/rubriq",
            "http://github.com/manthan-vs/rubriq",
            "https://www.github.com/manthan-vs/rubriq",
            "github.com/manthan-vs/rubriq",
            "https://github.com/manthan-vs/rubriq/",
            "https://github.com/manthan-vs/rubriq.git",
            "git@github.com:manthan-vs/rubriq.git",
            "  https://github.com/manthan-vs/rubriq  ",
        ],
    )
    def test_every_spelling_reaches_the_same_repository(self, url: str) -> None:
        ref = parse_github_url(url)

        assert (ref.owner, ref.repo) == ("manthan-vs", "rubriq")
        assert ref.normalised_url == "https://github.com/manthan-vs/rubriq"

    def test_the_raw_string_is_kept_verbatim(self) -> None:
        """What the student typed is evidence; the normalised form is derived."""
        ref = parse_github_url("git@github.com:manthan-vs/rubriq.git")

        assert ref.url == "git@github.com:manthan-vs/rubriq.git"

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://github.com/manthan-vs/rubriq/tree/main", "main"),
            ("https://github.com/manthan-vs/rubriq/tree/review-2/docs", "review-2"),
            ("https://github.com/manthan-vs/rubriq/blob/main/README.md", "main"),
            ("https://github.com/manthan-vs/rubriq/commit/abc123", "abc123"),
            ("https://github.com/manthan-vs/rubriq", None),
        ],
    )
    def test_a_deep_link_keeps_its_ref(self, url: str, expected: str | None) -> None:
        assert parse_github_url(url).ref == expected


class TestRefusals:
    def test_a_lookalike_host_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="Only github.com"):
            parse_github_url("https://github.com.evil.example/manthan-vs/rubriq")

    def test_credentials_cannot_disguise_the_host(self) -> None:
        """``https://github.com@evil/...`` has host ``evil``, not github.com."""
        with pytest.raises(ValidationError, match="Only github.com"):
            parse_github_url("https://github.com@evil.example/manthan-vs/rubriq")

    @pytest.mark.parametrize(
        "url",
        [
            "https://gitlab.com/manthan-vs/rubriq",
            "https://bitbucket.org/manthan-vs/rubriq",
            "https://raw.githubusercontent.com/manthan-vs/rubriq/main/a.py",
        ],
    )
    def test_another_host_is_refused(self, url: str) -> None:
        with pytest.raises(ValidationError):
            parse_github_url(url)

    @pytest.mark.parametrize(
        "url",
        ["https://github.com/manthan-vs", "https://github.com/", "github.com"],
    )
    def test_a_profile_is_not_a_repository(self, url: str) -> None:
        with pytest.raises(ValidationError, match="not a repository"):
            parse_github_url(url)

    def test_an_empty_string_says_so_plainly(self) -> None:
        with pytest.raises(ValidationError, match="Enter a repository URL"):
            parse_github_url("   ")

    @pytest.mark.parametrize("owner", ["-leading", "trailing-", "has space", "a" * 40])
    def test_an_impossible_account_name_is_refused(self, owner: str) -> None:
        with pytest.raises(ValidationError):
            parse_github_url(f"https://github.com/{owner}/rubriq")


class TestOwnership:
    def test_a_students_own_repository_is_accepted(self) -> None:
        ref = parse_github_url("https://github.com/manthan-vs/rubriq")

        assert assert_owned(ref, REGISTER) == STUDENT

    def test_the_match_is_case_insensitive(self) -> None:
        """GitHub usernames are; a register entry's casing is not a rule."""
        ref = parse_github_url("https://github.com/Manthan-VS/rubriq")

        assert assert_owned(ref, REGISTER) == STUDENT

    def test_a_group_mates_repository_is_accepted(self) -> None:
        """A granted group submits one piece of work, from one of its repos."""
        ref = parse_github_url("https://github.com/rahul-d/rubriq")

        assert assert_owned(ref, REGISTER) == MATE

    def test_somebody_elses_repository_is_refused(self) -> None:
        """The whole point of the decision."""
        ref = parse_github_url("https://github.com/torvalds/linux")

        with pytest.raises(ValidationError, match="not an account on record"):
            assert_owned(ref, REGISTER)

    def test_the_refusal_names_the_accounts_that_would_work(self) -> None:
        ref = parse_github_url("https://github.com/torvalds/linux")

        with pytest.raises(ValidationError) as exc:
            assert_owned(ref, REGISTER)

        assert "manthan-vs" in str(exc.value)
        assert "rahul-d" in str(exc.value)

    def test_no_registered_profile_is_an_administrative_message(self) -> None:
        """Not "try another link" — the student cannot fix this by editing."""
        ref = parse_github_url("https://github.com/manthan-vs/rubriq")

        with pytest.raises(ValidationError, match="Ask your guide"):
            assert_owned(ref, {STUDENT: None})

    def test_a_blank_register_entry_is_not_a_wildcard(self) -> None:
        """An empty username must never match an empty owner or anything else."""
        ref = parse_github_url("https://github.com/manthan-vs/rubriq")

        assert matching_profile(ref, {STUDENT: "   ", MATE: ""}) is None


def test_the_ref_label_reads_as_a_repository() -> None:
    ref = GitHubRef(url="x", owner="manthan-vs", repo="rubriq", ref=None)

    assert ref.label == "manthan-vs/rubriq"

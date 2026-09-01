"""Fix item 14, P0 half — a cache key that omits the actor is a data leak.

The invalidation *ergonomics* are Phase 7 polish. The keying is not: a
``@st.cache_data`` entry keyed only on, say, a milestone id is shared by every
signed-in user in the process, so one faculty member's grid can be served to a
student. That is fix item 3 wearing a cache's clothing, so it is tested from
Phase 1.
"""

from __future__ import annotations

from app.state import cache_scope

FACULTY = "guide@pccoepune.org"
STUDENT = "manthan.sankpal@pccoepune.org"


def test_the_key_contains_the_actor() -> None:
    assert FACULTY in cache_scope(FACULTY, 0)


def test_two_users_never_share_a_key() -> None:
    assert cache_scope(FACULTY, 0) != cache_scope(STUDENT, 0)


def test_bumping_the_version_changes_the_key() -> None:
    """This is what invalidate() does — expire, without clearing other users."""
    assert cache_scope(FACULTY, 0) != cache_scope(FACULTY, 1)


def test_the_key_is_stable_for_the_same_inputs() -> None:
    assert cache_scope(FACULTY, 3) == cache_scope(FACULTY, 3)


def test_a_prefix_of_one_key_is_not_another_key() -> None:
    """The email leads, so truncation cannot collide two users."""
    a = cache_scope("ab@pccoepune.org", 0)
    b = cache_scope("a@pccoepune.org", 0)

    assert not a.startswith(b) and not b.startswith(a)

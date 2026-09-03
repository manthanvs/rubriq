"""Session-state keys and cache scoping.

Fix item 14 is split across two phases, and the half that lands here is the P0
half: **every ``@st.cache_data`` key must include the actor's email.** A cache
keyed only on, say, a subject id is shared across every signed-in user, which
turns a caching decision into a cross-user data leak — that is fix item 3, not
polish.

The convention: any cached function takes ``scope`` as its first parameter and
ignores it. Streamlit hashes it into the key; the function body never uses it.

    @st.cache_data
    def load_subjects(scope: str, subject_id: int) -> list[SubjectDTO]:
        ...

    load_subjects(current_scope(actor), subject_id)
"""

from __future__ import annotations

import streamlit as st

from core.auth.actor import Actor

#: Bumped by :func:`invalidate` to expire every actor-scoped cache entry.
CACHE_VERSION_KEY = "rubriq.cache_version"

#: Which email the current session has already upserted a ``users`` row for.
SIGNED_IN_EMAIL_KEY = "rubriq.signed_in_email"


def cache_scope(actor_email: str, version: int) -> str:
    """Build a cache-key fragment. Pure, so it is unit-tested.

    The email comes first so a truncated key still differs per user.
    """
    return f"{actor_email}|v{version}"


def cache_version() -> int:
    return int(st.session_state.get(CACHE_VERSION_KEY, 0))


def current_scope(actor: Actor) -> str:
    """The cache-key fragment for the signed-in user, right now."""
    return cache_scope(actor.email, cache_version())


def invalidate() -> None:
    """Expire this session's actor-scoped cache entries.

    Called explicitly after every mutation. Bumping a version rather than
    calling ``st.cache_data.clear()`` avoids throwing away every other user's
    entries in the same process.

    §14 sketches this as ``invalidate(*keys)``. It takes no keys, deliberately:
    there is one version counter per session, so a bump expires everything this
    user cached regardless of what was named. A ``*keys`` parameter that changed
    nothing would read like surgical invalidation while doing the opposite,
    which is worse than the blunt version. Add per-key counters the day a page
    is slow enough to need one, and not before.
    """
    st.session_state[CACHE_VERSION_KEY] = cache_version() + 1


#: One-shot messages that must survive the ``st.rerun()`` which follows a
#: mutation. Without this, ``st.success(...)`` immediately before a rerun is
#: drawn and then discarded, so the student never sees that their submission
#: landed — the page just silently redraws.
FLASH_KEY = "rubriq.flash"


def flash(message: str, *, icon: str = ":material/check_circle:") -> None:
    """Queue a success message to be shown after the next rerun."""
    st.session_state[FLASH_KEY] = (message, icon)


def render_flash() -> None:
    """Draw and clear any queued message.

    Called once by ``app/main.py``, above whichever page runs, so a new page
    gets its confirmations without having to remember anything.
    """
    payload = st.session_state.pop(FLASH_KEY, None)
    if payload is None:
        return

    message, icon = payload
    st.success(message, icon=icon)


def after_mutation(message: str, *, icon: str = ":material/check_circle:") -> None:
    """Invalidate, queue the confirmation, and rerun — the whole ritual.

    Every mutating branch in ``app/`` ends in the same three lines, and getting
    them out of order is not a visible mistake: ``st.success()`` before
    ``st.rerun()`` is drawn and immediately discarded, so the user is told
    nothing and the page just blinks. Doing it in one place makes that
    unorderable.

    This never returns — ``st.rerun()`` raises to restart the script.
    """
    invalidate()
    flash(message, icon=icon)
    st.rerun()

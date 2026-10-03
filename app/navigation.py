"""Turn page specs into Streamlit pages.

The policy — which role sees which page — lives in ``core.auth.pages`` and is
unit-tested there. This module only translates. It constructs ``st.Page``
objects **solely** for the specs returned for the signed-in role, so a
student's faculty pages are never built and there is nothing to reach (§8).
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from core.auth.actor import Actor
from core.auth.pages import PageSpec, pages_for

#: Spec paths are written relative to this package. Resolving them here, to an
#: absolute path, is what keeps them working wherever the entry script lives:
#: ``st.Page`` resolves a relative path against the *entry script's* directory,
#: so when the entry point moved to the repository root every page became
#: unfindable. A spec should not have to know where the app is launched from.
APP_DIR = Path(__file__).resolve().parent


def _to_page(spec: PageSpec) -> st.Page:
    return st.Page(
        APP_DIR / spec.path,
        title=spec.title,
        icon=spec.icon,
        url_path=spec.key,
        default=spec.default,
    )


def page_path_for(role, key: str) -> Path | None:
    """The absolute path of a page, but only if this role may see it.

    Links are built from the same spec list as the sidebar, so a link can
    never point somewhere the signed-in role has no page for. Returning
    ``None`` rather than raising lets a caller simply not draw the link —
    which is what a student should get, not an error.
    """
    for spec in pages_for(role):
        if spec.key == key:
            return APP_DIR / spec.path
    return None


def build_navigation(actor: Actor):
    """Build the sidebar for this actor, grouped by section."""
    grouped: dict[str, list[st.Page]] = {}

    for spec in pages_for(actor.role):
        grouped.setdefault(spec.section, []).append(_to_page(spec))

    return st.navigation(grouped, position="sidebar")

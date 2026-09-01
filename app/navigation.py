"""Turn page specs into Streamlit pages.

The policy — which role sees which page — lives in ``core.auth.pages`` and is
unit-tested there. This module only translates. It constructs ``st.Page``
objects **solely** for the specs returned for the signed-in role, so a
student's faculty pages are never built and there is nothing to reach (§8).
"""

from __future__ import annotations

import streamlit as st

from core.auth.actor import Actor
from core.auth.pages import PageSpec, pages_for


def _to_page(spec: PageSpec) -> st.Page:
    return st.Page(
        spec.path,
        title=spec.title,
        icon=spec.icon,
        url_path=spec.key,
        default=spec.default,
    )


def build_navigation(actor: Actor):
    """Build the sidebar for this actor, grouped by section."""
    grouped: dict[str, list[st.Page]] = {}

    for spec in pages_for(actor.role):
        grouped.setdefault(spec.section, []).append(_to_page(spec))

    return st.navigation(grouped, position="sidebar")

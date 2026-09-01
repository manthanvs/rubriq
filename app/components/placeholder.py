"""Placeholder for pages whose phase has not arrived yet.

Every page in §8 exists from Phase 1 so the navigation is real and role
filtering can be demonstrated. A page that has no content yet says which phase
brings it, rather than rendering a blank region (fix item 13).
"""

from __future__ import annotations

import streamlit as st


def coming_soon(title: str, *, phase: int, blurb: str) -> None:
    """Render a named, dated stub."""
    st.title(title)
    st.info(f"Arrives in **Phase {phase}**.", icon=":material/schedule:")
    st.write(blurb)

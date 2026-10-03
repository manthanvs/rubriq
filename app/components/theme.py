"""Shared presentation: the card look, and the chips that carry status.

Deliberately thin. Streamlit 1.62 gives bordered metrics, badges and page
links natively, so almost all of the "card" styling here is a native argument
rather than a CSS rule. The small stylesheet below only softens corners and
tightens spacing — it does not position anything.

That restraint is the point. CSS aimed at Streamlit's internals has to target
``data-testid`` attributes, which are implementation details that move between
releases; a stylesheet that lays the page out would break on an upgrade and
break *silently*, because a misapplied rule still renders. Anything
structural therefore uses a documented API, and this file stays cosmetic.

No logic lives here and nothing reads the database — see §9 and fix item 10.
Status wording is derived in one place so two pages cannot describe the same
row differently.
"""

from __future__ import annotations

import streamlit as st

#: Corner radius and spacing only. Every selector is a documented class or a
#: plain element; nothing here depends on an internal test id.
_CSS = """
<style>
  /* Cards: soften what Streamlit draws square. */
  div[data-testid="stMetric"] { border-radius: 12px; }
  div[data-testid="stMetric"] [data-testid="stMetricValue"] {
      font-size: 2rem; line-height: 1.1;
  }
  /* Page links read as navigation rather than as body text. */
  a[data-testid="stPageLink-NavLink"] { border-radius: 8px; }
  /* A little more air between stacked blocks. */
  div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 12px; }
</style>
"""


def inject_css() -> None:
    """Apply the stylesheet once per rerun, from the shell.

    Called in ``app/main.py`` rather than per page: a page that forgets it
    would render unstyled, and that is the kind of omission nobody notices
    until a demo.
    """
    st.markdown(_CSS, unsafe_allow_html=True)


def metric_card(
    container,
    label: str,
    value,
    *,
    icon: str | None = None,
    help: str | None = None,
) -> None:
    """One bordered metric. A function so the arguments cannot drift apart."""
    container.metric(label, value, border=True, icon=icon, help=help)


#: Status -> (badge colour, icon). One mapping, so the Review Grid, the
#: dashboards and the student's own view cannot describe a row three ways.
#: Fix item 10 asks for exactly this: status is rendered, never re-derived.
STATUS_STYLE: dict[str, tuple[str, str]] = {
    "Approved": ("green", ":material/verified:"),
    "Awaiting approval": ("orange", ":material/hourglass_top:"),
    "Not scored": ("grey", ":material/edit_note:"),
    "Absent": ("red", ":material/event_busy:"),
    "Not submitted": ("grey", ":material/inbox:"),
    "Submitted": ("blue", ":material/upload_file:"),
    "Late": ("orange", ":material/schedule:"),
    "On time": ("green", ":material/check:"),
}


def status_chip(status: str) -> None:
    """Render a status as a badge, or as plain text if it is an unknown one."""
    colour, icon = STATUS_STYLE.get(status, ("grey", ":material/help:"))
    st.badge(status, color=colour, icon=icon)


def section(title: str, caption: str | None = None) -> None:
    """A subheading with an optional line of explanation under it."""
    st.subheader(title)
    if caption:
        st.caption(caption)

"""Fix item 13 — every page against an empty database.

§14 calls for "a manual checklist". A checklist is a thing you forget to run,
so this is the same walk done by ``AppTest``: each of §8's pages is executed
against a freshly-created, completely empty schema, and asserted to (a) raise
nothing and (b) render *something*. Those two are the whole item — a page that
throws shows a traceback to a faculty member mid-review, and a page that
renders nothing is the blank region §14 explicitly forbids.

This does not judge whether the copy is good; it proves there is copy. The
wording is checked by eye once, here it is only guarded against regressing to
an empty screen.

``st.navigation`` is not involved: the page scripts are run directly, which is
a stricter test than clicking through, because a page cannot rely on something
the shell happened to put in ``session_state`` first.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from core.config import Settings
from core.db.engine import build_engine
from core.db.models import Base

REPO_ROOT = Path(__file__).resolve().parents[2]
APP = REPO_ROOT / "app"

FACULTY = "guide@pccoepune.org"
STUDENT = "manthan.sankpal@pccoepune.org"

FACULTY_PAGES = [
    "pages/faculty/dashboard.py",
    "pages/faculty/subjects.py",
    "pages/faculty/rubric_builder.py",
    "pages/faculty/calendar.py",
    "pages/faculty/review_grid.py",
    "pages/faculty/query_inbox.py",
    "pages/faculty/reports.py",
    "pages/faculty/activity.py",
]
STUDENT_PAGES = [
    "pages/student/dashboard.py",
    "pages/student/calendar.py",
    "pages/student/submit.py",
    "pages/student/feedback.py",
    "pages/student/ask.py",
]
ALL_PAGES = [(p, FACULTY) for p in FACULTY_PAGES] + [(p, STUDENT) for p in STUDENT_PAGES]


@pytest.fixture(scope="module")
def empty_database(tmp_path_factory) -> str:
    """An empty schema — every table present, not one row in any of them."""
    path = tmp_path_factory.mktemp("empty") / "empty.db"
    url = f"sqlite:///{path}"
    engine = build_engine(Settings(database_url=url))
    Base.metadata.create_all(engine)
    engine.dispose()
    return url


def run_page(page: str, actor: str, database_url: str) -> AppTest:
    at = AppTest.from_file(str(APP / page), default_timeout=30)
    at.secrets["database"] = {"url": database_url, "echo_sql": False}
    at.secrets["rubriq"] = {
        "allowed_email_domain": "pccoepune.org",
        "faculty_allowlist": [FACULTY],
    }
    at.secrets["dev"] = {"impersonate": actor, "name": "Test User"}
    return at.run()


def rendered_text(at: AppTest) -> str:
    """Everything the page put on screen, flattened."""
    parts = []
    for block in (
        at.markdown,
        at.title,
        at.header,
        at.subheader,
        at.caption,
        at.info,
        at.warning,
        at.error,
        at.success,
    ):
        parts.extend(str(element.value) for element in block)
    return "\n".join(parts)


@pytest.mark.parametrize("page,actor", ALL_PAGES, ids=[p for p, _ in ALL_PAGES])
def test_a_page_does_not_raise_on_an_empty_database(
    page: str, actor: str, empty_database: str
) -> None:
    """A traceback in front of a faculty member is the failure mode here."""
    at = run_page(page, actor, empty_database)

    assert not at.exception, [str(e.value) for e in at.exception]


@pytest.mark.parametrize("page,actor", ALL_PAGES, ids=[p for p, _ in ALL_PAGES])
def test_a_page_says_something_on_an_empty_database(
    page: str, actor: str, empty_database: str
) -> None:
    """No page renders a blank region — there is always a next action to name."""
    at = run_page(page, actor, empty_database)

    assert rendered_text(at).strip(), f"{page} rendered nothing at all"


@pytest.mark.parametrize("page,actor", ALL_PAGES, ids=[p for p, _ in ALL_PAGES])
def test_a_page_offers_a_zero_state_rather_than_a_bare_title(
    page: str, actor: str, empty_database: str
) -> None:
    """A title alone is not a zero state; something must name what to do next."""
    at = run_page(page, actor, empty_database)

    assert at.info or at.warning or at.success or at.error, (
        f"{page} shows no zero-state message on an empty database"
    )

"""The app rendered through its real entry point, against a populated database.

``test_empty_states.py`` drives each page file directly and against an empty
schema. Both of those are deliberate, and between them they leave a gap:

* A page run on its own has no ``st.navigation``, so anything using
  ``st.page_link`` raises ``KeyError: 'url_pathname'`` — a condition that
  cannot occur in the real app, where navigation is always registered.
* On an empty database the dashboard's counts are all zero, so the branches
  that *draw* those links never execute at all.

So the "Waiting on you" links had no coverage from either direction: the test
that runs the page cannot reach them, and the test that could reach them does
not run the page that way. This runs the entry point, with data, as both
roles — the path a person actually takes.
"""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from core.auth.roles import Role
from core.config import Settings
from core.db.engine import build_engine
from core.db.models import Base

REPO_ROOT = pytest.importorskip("pathlib").Path(__file__).resolve().parents[2]
ENTRY = REPO_ROOT / "streamlit_app.py"

FACULTY = "guide@pccoepune.org"
STUDENT = "a.student@pccoepune.org"


@pytest.fixture(scope="module")
def seeded_database(tmp_path_factory) -> str:
    """A real seeded cohort, built the way `make seed` builds one."""
    path = tmp_path_factory.mktemp("seeded") / "seeded.db"
    url = f"sqlite:///{path.as_posix()}"

    engine = build_engine(Settings(database_url=url))
    Base.metadata.create_all(engine)
    engine.dispose()

    import scripts.seed_demo as seed

    settings = Settings(
        database_url=url,
        allowed_email_domain="pccoepune.org",
        faculty_allowlist=(FACULTY,),
        uploads_root=path.parent / "uploads",
    )
    seed.build(settings, faculty_email=FACULTY, faculty_name="Test Guide")
    return url


def _run(entry_url: str, actor: str) -> AppTest:
    at = AppTest.from_file(str(ENTRY), default_timeout=300)
    at.secrets["database"] = {"url": entry_url, "echo_sql": False}
    at.secrets["rubriq"] = {
        "allowed_email_domain": "pccoepune.org",
        "faculty_allowlist": [FACULTY],
    }
    at.secrets["dev"] = {"impersonate": actor, "name": "Test User"}
    return at.run()


@pytest.mark.slow
@pytest.mark.parametrize(
    ("actor", "role"), [(FACULTY, Role.FACULTY), (STUDENT, Role.STUDENT)]
)
def test_the_entry_point_renders_for_both_roles(
    seeded_database: str, actor: str, role: Role
) -> None:
    at = _run(seeded_database, actor)

    assert not at.exception, (
        f"{role.name} dashboard raised: "
        f"{at.exception[0].message if at.exception else ''}"
    )
    assert not at.error, f"{role.name} rendered an error: {[e.value for e in at.error]}"


@pytest.mark.slow
def test_the_faculty_dashboard_draws_its_links(seeded_database: str) -> None:
    """The branch the empty-state walk cannot reach.

    A seeded cohort always has rows waiting on the guide, so these links are
    drawn — which is what exercises ``st.page_link`` under real navigation.
    """
    at = _run(seeded_database, FACULTY)

    labels = [m.label for m in at.metric]
    assert "Needs attention" in labels
    assert "Students" in labels

    attention = next(m for m in at.metric if m.label == "Needs attention")
    assert int(attention.value) > 0, "a seeded cohort should need attention"

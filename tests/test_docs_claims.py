"""The documentation makes checkable claims. This checks them.

Every requirement row in ``docs/requirements.md`` names the module that
implements it and the test that proves it, and the documents quote a test count
in several places. Those are facts about the repository, and facts about a
repository go stale — usually silently, and usually just before someone reads
them aloud.

So this is a test rather than a proofreading pass. It fails when a document
names a file that no longer exists, or quotes a number that no longer matches.
It cannot check whether the prose is *true*; it can check that it is not
provably false.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"

#: Paths quoted in prose that are illustrative rather than real.
IGNORED_PATHS = {
    "docs/report/",
    "core/db/",
    "core/ai/",
    "core/scoring/",
    "app/components/",
    "core/",
    "app/",
    "tests/",
}


def _resolves(doc: Path, path: str) -> bool:
    """Whether a path quoted in a document points at something real.

    Three ways it can, all of them ordinary in prose: from the repository root
    (``core/scoring/engine.py``), from the document's own directory
    (``diagrams/er.md`` inside ``docs/design.md``), or as the tail of a real
    file — a table of modules under ``core/ai/`` reasonably writes
    ``graphs/evaluation.py`` rather than repeating the prefix on every row.
    """
    bare = path.split("::")[0]
    if bare in IGNORED_PATHS:
        return True
    if (REPO_ROOT / bare).exists() or (doc.parent / bare).exists():
        return True

    suffix = "/" + bare.replace("\\", "/")
    return any(
        str(candidate.relative_to(REPO_ROOT)).replace("\\", "/").endswith(suffix)
        for candidate in REPO_ROOT.rglob("*" + Path(bare).suffix)
        if ".venv" not in candidate.parts and ".git" not in candidate.parts
    )


def markdown_files() -> list[Path]:
    """Every document that makes claims about this repository.

    README.md is in the list because it is the first thing anyone reads on
    GitHub, which makes a stale number there more visible than a stale one
    anywhere else.
    """
    return sorted(DOCS.rglob("*.md")) + [
        REPO_ROOT / "CLAUDE.md",
        REPO_ROOT / "README.md",
    ]


def test_there_are_documents_to_check() -> None:
    """Guards against a vacuous pass if the glob silently finds nothing."""
    assert len(markdown_files()) >= 10


@pytest.mark.parametrize("doc", markdown_files(), ids=lambda p: p.name)
def test_every_module_path_named_in_a_document_exists(doc: Path) -> None:
    """A document naming a module that was renamed is worse than one that is silent."""
    text = doc.read_text(encoding="utf-8")

    # Backticked paths that look like real files: a slash and a known suffix.
    quoted = set(re.findall(r"`([A-Za-z0-9_./-]+\.(?:py|toml|txt|md|db))`", text))

    missing = sorted(
        path for path in quoted if "/" in path and not _resolves(doc, path)
    )

    assert not missing, f"{doc.name} names files that do not exist: {missing}"


@pytest.mark.parametrize("doc", markdown_files(), ids=lambda p: p.name)
def test_every_relative_link_resolves(doc: Path) -> None:
    broken = []
    for label, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", doc.read_text("utf-8")):
        if target.startswith(("http", "#", "mailto:")):
            continue
        if not (doc.parent / target.split("#")[0]).exists():
            broken.append(f"[{label}]({target})")

    assert not broken, f"{doc.name} has broken links: {broken}"


def collected_test_count(*paths: str) -> int:
    """How many tests actually exist, counted the way pytest counts them.

    With ``paths``, counts only those; with none, the whole suite.
    """
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *paths],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    match = re.search(r"(\d+) tests? collected", result.stdout)
    if match:
        return int(match.group(1))

    # Older pytest prints "N tests collected" only on some paths; fall back to
    # counting the per-file summary lines it always prints.
    return sum(
        int(n) for n in re.findall(r"^tests[^\n:]*: (\d+)$", result.stdout, re.M)
    )


@pytest.mark.slow
def test_the_quoted_test_count_matches_reality() -> None:
    """Several documents state a total. One of them being stale is enough."""
    actual = collected_test_count()
    assert actual > 0, "could not count the tests; the check would pass vacuously"

    wrong = []
    for doc in markdown_files():
        text = doc.read_text(encoding="utf-8")
        for quoted in re.findall(r"(\d{3,4}) tests", text):
            if int(quoted) != actual:
                wrong.append(f"{doc.name} says {quoted}, actual {actual}")

    assert not wrong, "stale test counts: " + "; ".join(wrong)



@pytest.mark.slow
def test_the_streamlit_free_subset_matches_reality() -> None:
    """Three documents claim "N of the M tests need no Streamlit runtime".

    The total-count test above only matches the literal "<number> tests", so M
    was checked and N never was. N drifted to two below the truth and stayed
    there until somebody counted by hand. A derived number needs deriving, not
    reading.
    """
    total = collected_test_count()
    runtime_bound = collected_test_count("tests/app/test_empty_states.py")
    assert total > 0 and runtime_bound > 0, "collection failed; the check is vacuous"
    expected = total - runtime_bound

    wrong = []
    for doc in markdown_files():
        text = doc.read_text(encoding="utf-8")
        for claimed, stated_total in re.findall(r"(\d{3,4}) of the (\d{3,4})", text):
            if (int(claimed), int(stated_total)) != (expected, total):
                wrong.append(
                    f"{doc.name} says {claimed} of {stated_total}, "
                    f"actual {expected} of {total}"
                )

    assert not wrong, "stale subset counts: " + "; ".join(wrong)

def test_the_page_list_in_the_srs_matches_the_code() -> None:
    """§8's page list and the real navigation must not drift apart."""
    from core.auth.pages import ALL_PAGES
    from core.auth.roles import Role

    srs = (DOCS / "srs.md").read_text(encoding="utf-8")

    for role in (Role.FACULTY, Role.STUDENT):
        for spec in ALL_PAGES:
            if role in spec.roles:
                assert spec.title in srs, (
                    f"srs.md does not mention the {role} page '{spec.title}'"
                )


def test_the_late_policy_table_matches_the_code() -> None:
    """The penalty bands are quoted in three documents and defined once."""
    from core.scoring.policy import DEFAULT_LATE_POLICY

    quoted = {
        1: "10",
        2: "20",
        3: "35",
    }
    for days, percent in quoted.items():
        band = DEFAULT_LATE_POLICY.band_for(days)
        assert str(int(band.percent)) == percent, (
            f"{days} day(s) late is {band.percent}% in code, "
            f"but the documents say {percent}%"
        )

    assert DEFAULT_LATE_POLICY.band_for(4).absent, "4 days late must be ABSENT"
    assert DEFAULT_LATE_POLICY.band_for(6).needs_reinstatement, (
        "past 5 days must need reinstatement"
    )

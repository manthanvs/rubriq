"""The entry point, and why it has to sit at the repository root.

``make run`` launched ``python -m streamlit run app/main.py`` for most of this
project's life. The ``-m`` form puts the *working directory* on ``sys.path``,
so ``app.navigation`` and ``core.config`` resolved and the app ran perfectly on
this machine.

A host does not launch it that way. Streamlit Community Cloud runs the
``streamlit`` console script, which adds only the directory holding the script
it was handed. Point that at ``app/main.py`` and the sole project directory on
the path is ``app/`` — so the first ``from app...`` line raises
ModuleNotFoundError and the app never starts. It had never been deployable.
Nothing tested it the way a host runs it, and ``make run`` could not have
caught it, because ``-m`` was quietly supplying the missing path entry.

These tests launch it the way a host does.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINT = "streamlit_app.py"

#: Imported by the entry point, directly or transitively. Each one needs the
#: repository root on sys.path; none of them is reachable from ``app/``.
REQUIRED_MODULES = ("app.main", "app.bootstrap", "core.config")

_PROBE = (
    "import sys, importlib.util\n"
    # Exactly what `streamlit run <script>` does before executing the script.
    "sys.path.insert(0, sys.argv[1])\n"
    "missing = []\n"
    "for name in sys.argv[2:]:\n"
    "    try:\n"
    "        if importlib.util.find_spec(name) is None:\n"
    "            missing.append(name)\n"
    "    except ModuleNotFoundError:\n"
    "        missing.append(name)\n"
    "print(','.join(missing))\n"
)


def _unresolvable_from(script: Path) -> list[str]:
    """Which of REQUIRED_MODULES a host could not import, given this script.

    Run with ``-P`` and from an unrelated working directory so that nothing but
    the inserted path is in play — otherwise the test passes for the same
    reason the bug hid.
    """
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    with tempfile.TemporaryDirectory() as elsewhere:
        result = subprocess.run(
            [sys.executable, "-P", "-c", _PROBE, str(script.parent), *REQUIRED_MODULES],
            cwd=elsewhere,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
    assert result.returncode == 0, result.stderr
    return [name for name in result.stdout.strip().split(",") if name]


def test_the_entry_point_resolves_its_imports_the_way_a_host_launches_it() -> None:
    entry = REPO_ROOT / ENTRY_POINT
    assert entry.is_file(), f"{ENTRY_POINT} must exist at the repository root"
    assert entry.parent == REPO_ROOT, (
        "the entry point only works because its own directory is the "
        "repository root — moving it into a package reintroduces the bug"
    )
    assert not _unresolvable_from(entry)


def test_app_main_is_still_not_launchable_directly() -> None:
    """The negative half, so the test above cannot pass vacuously.

    If this ever starts failing, something has put the repository root on the
    path by another route and the check above has stopped proving anything.
    """
    assert _unresolvable_from(REPO_ROOT / "app" / "main.py") == list(REQUIRED_MODULES)


@pytest.mark.parametrize(
    ("name", "needle"),
    [
        ("Makefile", f"streamlit run {ENTRY_POINT}"),
        ("make.ps1", f"'streamlit', 'run', '{ENTRY_POINT}'"),
        (".claude/launch.json", f'"streamlit", "run", "{ENTRY_POINT}"'),
        ("docs/deployment.md", f"main file path `{ENTRY_POINT}`"),
        (".devcontainer/devcontainer.json", f"streamlit run {ENTRY_POINT}"),
    ],
)
def test_every_launcher_names_the_entry_point(name: str, needle: str) -> None:
    """Local and hosted must run the same file.

    Two entry points is the arrangement that hid this: what ran here was not
    what ran there, so here could stay green while there was broken.
    """
    path = REPO_ROOT / name
    if not path.exists():  # launch.json is editor config, not required
        pytest.skip(f"{name} is not present")
    assert needle in path.read_text(encoding="utf-8")


def test_launch_json_is_valid_json_if_present() -> None:
    path = REPO_ROOT / ".claude" / "launch.json"
    if not path.exists():
        pytest.skip("launch.json is not present")
    json.loads(path.read_text(encoding="utf-8"))

"""The Phase 0 gate: import-boundary enforcement.

Two rules from §12, checked mechanically:

* ``core/`` never imports Streamlit (invariant #9)
* ``langgraph`` appears only inside ``core/ai/``

Parsed with :mod:`ast` rather than grepped, so a mention of "streamlit" in a
docstring or a comment does not fail the build and an import hidden inside a
function body does not sneak past.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE = REPO_ROOT / "core"
APP = REPO_ROOT / "app"
CORE_AI = CORE / "ai"


def _python_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _imported_roots(path: Path) -> set[str]:
    """Top-level package names imported by ``path``.

    Relative imports are skipped — they are internal structure, never a
    third-party dependency.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            if node.module:
                roots.add(node.module.split(".", 1)[0])

    return roots


def test_core_package_has_modules_to_check() -> None:
    """Guard against a vacuous pass.

    An empty ``core/`` would satisfy every assertion below while proving
    nothing, so assert there is something to inspect first.
    """
    assert _python_files(CORE), f"No Python files found under {CORE}"


def test_core_never_imports_streamlit() -> None:
    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in _python_files(CORE)
        if "streamlit" in _imported_roots(path)
    ]
    assert not offenders, (
        "core/ must never import streamlit (invariant #9). "
        f"Offending files: {offenders}. "
        "Pass config or the acting user in as an argument instead."
    )


def test_langgraph_only_inside_core_ai() -> None:
    offenders = []
    for root in (CORE, APP):
        for path in _python_files(root):
            if CORE_AI in path.parents:
                continue
            if {"langgraph", "langchain"} & _imported_roots(path):
                offenders.append(path.relative_to(REPO_ROOT).as_posix())

    assert not offenders, (
        "langgraph/langchain may only be imported inside core/ai/ (§12). "
        f"Offending files: {offenders}."
    )

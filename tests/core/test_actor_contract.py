"""Fix item 3 — every database-touching service takes an explicit ``actor``.

The rule from §12: *"Every service function takes an explicit ``actor: User``
and scopes its query by it. No implicit 'current user'."* A function that
forgot its ``actor`` is the single most likely way one student ends up seeing
another's work, and it is invisible in review because the code still runs.

How this is checked: any public function in ``core/`` that accepts a
``Session`` is, by definition, talking to the database, and must therefore also
accept ``actor`` — unless it appears in :data:`EXEMPT` with a stated reason.

**On its current strength.** In Phase 1 the only DB-touching functions are the
sign-in path and the audit helper, and both are exempt, so this test does not
yet reject anything real. That is exactly why :class:`TestExemptionsAreHonest`
exists: it fails if an exemption names a function that no longer exists, so the
list cannot quietly rot into a blanket amnesty. The test grows teeth in Phase 2,
when ``core/academics/`` lands.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE = REPO_ROOT / "core"

ACTOR_PARAM = "actor"
SESSION_ANNOTATIONS = {"Session", "sqlalchemy.orm.Session"}

#: Functions allowed to touch a Session without an actor, and why.
#: Every entry must name a function that exists — see TestExemptionsAreHonest.
EXEMPT: dict[str, str] = {
    "core.auth.service.sign_in": ("Produces the actor. Requiring one would be circular."),
    "core.audit.record": (
        "Infrastructure, not a service. Takes actor_email explicitly and is "
        "called from inside an already-scoped transaction."
    ),
}


def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(REPO_ROOT).with_suffix("").parts)


def _annotation_name(node: ast.expr | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):  # Optional[Session], etc.
        return _annotation_name(node.value)
    return ""


def _parameters(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.arg]:
    args = func.args
    return [*args.posonlyargs, *args.args, *args.kwonlyargs]


def _public_functions() -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    """Every public top-level function under ``core/``, with its dotted name."""
    found = []

    for path in sorted(CORE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        module = _module_name(path)

        for node in tree.body:
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if node.name.startswith("_"):
                continue
            found.append((f"{module}.{node.name}", node))

    return found


def _touches_the_database(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        _annotation_name(param.annotation) in SESSION_ANNOTATIONS
        for param in _parameters(func)
    )


class TestActorContract:
    def test_there_are_functions_to_inspect(self) -> None:
        """Guard against a vacuous pass if the walk silently finds nothing."""
        assert _public_functions()

    def test_every_db_touching_service_takes_an_actor(self) -> None:
        offenders = []

        for dotted, func in _public_functions():
            if not _touches_the_database(func):
                continue
            if dotted in EXEMPT:
                continue
            if ACTOR_PARAM not in {param.arg for param in _parameters(func)}:
                offenders.append(dotted)

        assert not offenders, (
            "These functions accept a Session but no actor, so their queries "
            f"cannot be scoped to anyone (fix item 3): {offenders}. "
            "Add `actor: Actor` and filter in the WHERE clause, or add an "
            "entry to EXEMPT with a reason."
        )


class TestExemptionsAreHonest:
    """An exemption list nobody maintains is a permanent hole."""

    def test_every_exemption_still_exists(self) -> None:
        known = {dotted for dotted, _ in _public_functions()}
        stale = sorted(set(EXEMPT) - known)

        assert not stale, (
            f"EXEMPT names functions that no longer exist: {stale}. "
            "Remove them so the list keeps meaning something."
        )

    def test_every_exemption_has_a_reason(self) -> None:
        assert all(reason.strip() for reason in EXEMPT.values())

    def test_the_exemption_list_stays_short(self) -> None:
        """A rising count is the signal to look, not a reason to raise the cap."""
        assert len(EXEMPT) <= 4, (
            "More than four functions now bypass the actor contract. "
            "That is worth a look rather than a bigger number here."
        )

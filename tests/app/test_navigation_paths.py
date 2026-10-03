"""Navigation hands Streamlit paths that exist, from wherever it is launched.

This file exists because 639 tests passed against an app that could not render
a single page. ``tests/app/test_empty_states.py`` drives each page file
directly through ``AppTest.from_file``, so it never goes through
``build_navigation`` — and nothing else built an ``st.Page`` at all. The whole
navigation layer was untested, and the gap only showed when somebody signed in.

The specific break: ``st.Page`` resolves a relative path against the *entry
script's* directory. Page specs are written relative to ``app/``, which was
correct for as long as ``app/main.py`` was the entry script and wrong the
moment it moved to the repository root. Every page became unfindable at once.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import streamlit as st

from app.navigation import APP_DIR, build_navigation
from core.auth.actor import Actor
from core.auth.pages import pages_for
from core.auth.roles import Role


def _actor(role: Role) -> Actor:
    return Actor(email=f"{role.name.lower()}@pccoepune.org", role=role, name="Test")


@pytest.mark.parametrize("role", list(Role))
def test_every_page_spec_points_at_a_file_that_exists(role: Role) -> None:
    specs = pages_for(role)
    for spec in specs:
        resolved = APP_DIR / spec.path
        assert resolved.is_file(), f"{role.name}: {spec.key} -> {resolved} is missing"


@pytest.mark.parametrize("role", [Role.FACULTY, Role.STUDENT])
def test_navigation_passes_absolute_paths(role: Role, monkeypatch) -> None:
    """The property that makes it independent of the entry point.

    A relative path here works only while the entry script happens to sit in
    ``app/``. Asserting absolute is asserting that it no longer matters.
    """
    seen: list[Path] = []

    def _fake_page(path, **_kwargs):
        seen.append(Path(path))
        return object()

    monkeypatch.setattr(st, "Page", _fake_page)
    monkeypatch.setattr(st, "navigation", lambda grouped, **_kw: grouped)

    build_navigation(_actor(role))

    assert seen, f"{role.name} got no pages at all"
    for path in seen:
        assert path.is_absolute(), f"{path} is relative; it will break when moved"
        assert path.is_file(), f"{path} does not exist"


def test_a_student_never_gets_a_faculty_page(monkeypatch) -> None:
    """Invariant #6 at the navigation layer, now that it is reachable in a test."""
    seen: list[Path] = []
    monkeypatch.setattr(st, "Page", lambda path, **_kw: seen.append(Path(path)))
    monkeypatch.setattr(st, "navigation", lambda grouped, **_kw: grouped)

    build_navigation(_actor(Role.STUDENT))

    assert seen
    assert not [p for p in seen if "faculty" in p.parts]

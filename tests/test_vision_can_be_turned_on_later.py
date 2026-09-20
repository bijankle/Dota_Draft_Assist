"""Downloading the portraits must give the app its screen reading.

`_build_provider` ends `if session is None: return gsi` - a provider
with no vision at all - with the comment "no portraits yet; the banner
says to fetch them". The banner does. You fetch them, `reload_backend`
runs, and it could only refresh a session that ALREADY existed. There
was none, so nothing happened, and the app read no frame for the rest
of the process: a real bot draft logged "0 ticks captured a frame"
across 213 ticks while the recorder - which grabs its own frames -
saved eighteen good ones.

WHAT IT COSTS IS THE TEAMS. The minimap cannot say whose five are
whose; `_resolve_sides_by_sight` settles it off the pick bar, and with
no vision it can never run. Four of five heroes on the wrong team.
"""

import ast
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from draft_assist.ui import app as app_mod                    # noqa: E402


def _method(name: str) -> ast.FunctionDef:
    tree = ast.parse(Path(app_mod.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} has gone")


def test_reload_backend_can_turn_vision_on():
    """The line that was missing. Refreshing an existing session is not
    the same as being able to acquire one."""
    assert "_ensure_vision" in ast.dump(_method("reload_backend")), (
        "reload_backend cannot give the app vision it did not start "
        "with, so the download the banner asks for changes nothing")


def test_ensure_vision_respects_the_tick_box():
    """Screen reading off is a decision, not a gap to be filled in."""
    body = ast.dump(_method("_ensure_vision"))
    assert "use_vision" in body


def test_ensure_vision_does_not_rebuild_the_listener():
    """Rebuilding the sources rebinds the GSI port, which would drop a
    draft in progress. It attaches to the provider instead."""
    body = ast.dump(_method("_ensure_vision"))
    assert "GsiServer" not in body
    assert "_apply_sources" not in body


def test_ensure_vision_leaves_the_other_providers_alone():
    """Demo, replay and manual are not a missing capture session."""
    body = ast.dump(_method("_ensure_vision"))
    assert "GsiProvider" in body and "HybridProvider" in body


def test_the_provider_still_starts_without_portraits():
    """The premise: a missing library must not stop the app opening."""
    source = Path(app_mod.__file__).read_text(encoding="utf-8")
    assert "no portraits yet; the banner says to fetch them" in source

"""The small blank window that flashes up at every boot.

Reported as "still get these small windows flashign up on the screen
frequently jsut on boot - they have the app logo top left and are small
blank windowwws flickering on / off".

Two candidates, and the app's own side is ruled out by measurement rather
than by argument: `test_ui_smoke.
test_the_app_owns_exactly_one_window_and_nothing_else` holds that the
whole QApplication contains exactly one parentless widget, so there is no
stray Qt window that could flash, and the tests below hold that every
subprocess this app starts is given `CREATE_NO_WINDOW`.

What is left is the launcher. cmd.exe creates a console for a batch file
BEFORE its first line runs, so nothing inside the script can prevent it,
and on the installed path that console echoes nothing at all — a small
blank box, titled with the app's own name, gone again within a blink. The
answer is a shortcut straight to `pythonw.exe`, which has no console to
show, put where somebody actually double-clicks.
"""

import ast
import pathlib

import pytest

from draft_assist import console
from draft_assist.config import APP_NAME, REPO_ROOT
from draft_assist.ui import appicon

SOURCES = sorted(list((REPO_ROOT / "draft_assist").rglob("*.py"))
                 + list((REPO_ROOT / "tools").rglob("*.py")))


def test_the_console_free_shortcut_sits_beside_the_launcher():
    """Not in the Start menu only. Telling somebody to go and find a
    Start-menu entry instead of the file they have been opening for
    months is not a fix for a window flashing in their face."""
    link = appicon.folder_link()
    assert link.parent == REPO_ROOT
    assert link.suffix == ".lnk"
    assert (REPO_ROOT / f"{APP_NAME}.bat").exists(), \
        "the shortcut is meant to sit beside the launcher"


def test_its_name_cannot_be_confused_with_the_launcher():
    """Explorer hides a .lnk's extension, so a shortcut named exactly
    what the app is named leaves the folder holding two items that read
    the same and behave differently."""
    assert appicon.folder_link().stem != APP_NAME
    assert APP_NAME in appicon.folder_link().stem


def test_the_shortcut_runs_an_interpreter_WITH_NO_CONSOLE():
    """This is the whole property. `python.exe` is a console
    application: a shortcut pointing at it opens a black box and keeps it
    open for the life of the app, and one carrying the app's own icon
    would look exactly like the thing being reported."""
    source = (REPO_ROOT / "draft_assist/ui/appicon.py").read_text()
    body = source.split("def launch_python")[1].split("\ndef ")[0]
    candidates = body.split("for candidate in")[1]
    # The venv's pythonw first, then a pythonw beside whatever is
    # running, and only then the interpreter itself — which off Windows
    # is the only one that exists, and there a console means nothing.
    assert candidates.index("pythonw.exe") < candidates.index("Path(sys"), \
        "pythonw must be preferred over whatever interpreter is running"
    assert "pythonw.exe" in candidates


def test_both_shortcuts_go_through_one_writer():
    """Two implementations could write two different shortcuts for one
    AppUserModelID, which is the disagreement `shell_ico` already exists
    to prevent one level down."""
    source = (REPO_ROOT / "draft_assist/ui/appicon.py").read_text()
    tree = ast.parse(source)
    writers = [n.name for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef)
               and n.name.startswith("write_shortcut")]
    assert writers == ["write_shortcut"], writers


def test_neither_shortcut_is_fatal_off_windows():
    """Both report and return False rather than raising — the app must
    open on a machine that has neither a Start menu nor pywin32."""
    appicon._folder_done = False
    assert appicon.ensure_folder_shortcut() is False
    assert appicon.folder_shortcut_note == "not Windows"


def test_the_folder_shortcut_reports_separately():
    """One failing must not be readable as the other having failed."""
    assert appicon.folder_shortcut_note is not appicon.shortcut_note
    paste = (REPO_ROOT / "draft_assist/ui/app.py").read_text()
    assert "folder_shortcut_note" in paste, \
        "Debug > Copy everything must say whether it was written"


def test_the_launcher_says_nothing_at_all_on_the_installed_path():
    """Which is WHY the window reads as blank rather than as a script
    doing something — and why it is worth removing rather than
    explaining. A line echoed here would make it more visible, not
    less."""
    raw = (REPO_ROOT / f"{APP_NAME}.bat").read_bytes().decode("utf-8")
    # The LAST one: ":launch" appears earlier as the target of a `goto`.
    # Cut at the next label, or `:failed` — which is only reached when
    # setup has gone wrong and SHOULD speak — lands in the slice.
    launch = raw.split(":launch")[-1]
    launch = launch.split("\n:")[0]
    spoken = [line.strip() for line in launch.splitlines()
              if line.strip().lower().startswith("echo")
              and line.strip().lower() != "echo off"]
    assert spoken == [], spoken


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_every_subprocess_is_started_without_a_console(path):
    """The other way a small blank window appears on Windows. The app is
    launched windowless, so a child that wants a console is GIVEN a fresh
    black box on top of whatever the user was doing."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "attr", None)
        module = getattr(getattr(func, "value", None), "id", None)
        if module != "subprocess" or name not in ("run", "Popen", "call",
                                                  "check_call",
                                                  "check_output"):
            continue
        # Openers that are not Windows console programs: `os.startfile`
        # is what this app uses there, and these sit in the branches
        # Windows never takes — plus `explorer`, which is the shell and
        # has no console to give. A console can only flash where one can
        # be created.
        argv = node.args[0] if node.args else None
        first = ""
        if isinstance(argv, (ast.List, ast.Tuple)) and argv.elts:
            head = argv.elts[0]
            first = head.value if isinstance(head, ast.Constant) else ""
        if first in ("open", "xdg-open", "explorer"):
            continue
        spread = any(k.arg is None for k in node.keywords)
        explicit = any(k.arg == "creationflags" for k in node.keywords)
        assert spread or explicit, (
            f"{path.name}:{node.lineno} starts a process without "
            "console.no_window() — it will flash a black window")


def test_no_window_is_harmless_where_the_flag_does_not_exist():
    """A helper that raises on Linux is one nobody can test on Linux."""
    assert isinstance(console.no_window(), dict)

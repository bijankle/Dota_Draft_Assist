"""Help ▸ User manual, Help ▸ About, and the fluff they replaced.

The app explained itself in place — a wall of text in the first-run
wizard, a paragraph under every download button, an About box describing
the product rather than the build. All true, all read once, and all of it
between somebody and the control they had come for. These tests hold the
two halves of the fix: the screens stay short, and the manual stays
complete.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication                # noqa: E402

from draft_assist import version                        # noqa: E402
from draft_assist.ui import handbook, tasks             # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


# ---- the manual ----------------------------------------------------------

def test_every_section_is_listed_and_reachable(qapp):
    """The contents list and the page are built from ONE structure, so
    they cannot disagree about what is in the manual or in what order —
    the lesson `analyse.BLOCK_ORDER` is in this app for."""
    window = handbook.ManualWindow()
    idents = [ident for ident, _, _ in handbook.SECTIONS]
    assert list(window.sections.order) == idents
    assert set(window._anchors) == set(idents)
    for ident in idents:
        window._jump_to(ident)
        assert window.sections.lit() == ident


def test_the_manual_answers_what_the_screens_stopped_saying(qapp):
    """Cutting the prose is only half a fix if the facts went with it.

    Each of these was in a wizard paragraph, a task blurb or the old
    About box, and each is something somebody can be stuck on.
    """
    words = " ".join(
        block if isinstance(block, str) else " ".join(
            line if isinstance(line, str) else " ".join(line)
            for line in block[1])
        for _, _, blocks in handbook.SECTIONS for block in blocks).lower()
    for fact in (".env",                      # where the key lives
                 "never leaves your machine",  # and that it stays there
                 "stratz.com/api",            # where to get one
                 "gamestateintegration",      # the step everyone forgets
                 "numeric id",                # where variant portraits go
                 "skips what is already",     # a retry is cheap
                 "never injects code",        # the boundary
                 "friend id",                 # what the History tab takes
                 "expose public match data"):  # why it found no matches
        assert fact in words, f"the manual lost {fact!r}"


def test_a_section_title_fits_the_sidebar(qapp):
    """They are the bookmarks as well as the headings, and a bookmark
    list of wrapped two-line rows is a list you cannot scan."""
    for _, title, _ in handbook.SECTIONS:
        assert len(title) <= 16, f"{title!r} will wrap in the sidebar"


# ---- and the screens stay short -----------------------------------------

def test_no_task_explains_itself_at_length():
    """Every one of these was a three-paragraph essay under a button
    whose whole job is one action. A blurb says what the button DOES;
    how the thing works is the manual's."""
    for key, task in tasks.TASKS.items():
        assert len(task.blurb) <= 200, f"{key} is a wall of text again"
        assert "\n\n" not in task.blurb, f"{key} runs to paragraphs"


def test_the_wizard_asks_rather_than_explains():
    """It is two controls and a Finish button; it was also four
    paragraphs about where statistics come from."""
    import re
    from pathlib import Path
    source = Path("draft_assist/ui/setup_wizard.py").read_text(
        encoding="utf-8")
    for call in re.findall(r"paragraph\(\s*((?:\s*\"[^\"]*\")+)", source):
        text = "".join(re.findall(r'"([^"]*)"', call))
        assert len(text) <= 120, f"the wizard lectures again: {text[:60]!r}"


# ---- About ---------------------------------------------------------------

def test_about_names_a_version_and_a_build():
    """Two different answers: the version is what a person says out
    loud, the build is what identifies the code."""
    assert version.VERSION.count(".") == 2
    assert version.build()                     # never blank
    assert version.VERSION in version.described()


def test_the_build_is_never_an_exception(tmp_path, monkeypatch):
    """It is read by the About box and by the diagnostic paste. A copy
    with no git and no install record is a first unzip, not a fault."""
    monkeypatch.setattr(version, "ROOT", tmp_path)
    assert version.build() == "unknown"


def test_the_build_is_read_from_the_install_record(tmp_path, monkeypatch):
    """A copy unzipped from GitHub has no git at all, and its commit is
    in the file the updater wrote."""
    import json
    (tmp_path / "installed_version.json").write_text(
        json.dumps({"branch": "main", "sha": "abcdef1234567", "files": []}),
        encoding="utf-8")
    monkeypatch.setattr(version, "ROOT", tmp_path)
    assert version.build().startswith("abcdef1")


# ---- and it is reachable -------------------------------------------------

def a_window(qapp):
    from draft_assist.config import RULES_FILE
    from draft_assist.model import items as items_mod
    from draft_assist.ui.app import MainWindow
    from draft_assist.ui.providers import DemoProvider
    import sys
    sys.path.insert(0, "tests")
    from test_ui_smoke import demo_dataset
    ds = demo_dataset()
    rules, meta = items_mod.load_rules(RULES_FILE)
    window = MainWindow(ds, DemoProvider(ds), rules, meta)
    window.timer.stop()
    return window


def test_help_offers_the_manual_and_the_menu_can_open_it(qapp):
    """Wired straight to a method that takes an argument, because
    QAction.triggered hands its slot a `checked` flag — which would
    otherwise arrive as the section to jump to."""
    window = a_window(qapp)
    try:
        actions = {a.text().replace("&", "")
                   for m in window.menu_bar.actions() if m.menu()
                   for a in m.menu().actions()}
        assert "User manual" in actions
        window._open_manual(False)          # what triggered() actually sends
        assert window.manual_window.isVisible()
        assert window.manual_window.sections.lit() == handbook.SECTIONS[0][0]
        window.manual_window.close()
    finally:
        window.close()


def test_the_manual_is_built_once(qapp):
    """A second copy is a second window in the taskbar and a second
    thing to keep in step — the settings window's rule."""
    window = a_window(qapp)
    try:
        window._open_manual()
        first = window.manual_window
        window.manual_window.close()
        window._open_manual()
        assert window.manual_window is first
        window.manual_window.close()
    finally:
        window.close()

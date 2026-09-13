"""The progress dialog's output is visible, and copyable BY HAND.

At the user's request, and the reasoning is theirs: "I don't trust that
the copy and paste works unless I can see the console in the app." The
dialog has always streamed the output live; what it lacked was a button,
so the only copy was the automatic one, which is convenient and
invisible. Invisible is the half that had to be fixed.
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication            # noqa: E402

from draft_assist.ui.task_dialog import TaskDialog  # noqa: E402
from draft_assist.ui.tasks import TASKS             # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def dialog(qapp):
    box = TaskDialog(TASKS["score_recognition"])
    yield box
    box.deleteLater()


def test_the_copy_button_copies_the_whole_transcript(dialog, qapp):
    dialog._append("slots RIGHT 88%")
    dialog._append("slots WRONG 1%")
    dialog._copy()
    copied = qapp.clipboard().text()
    assert "slots RIGHT 88%" in copied
    assert "slots WRONG 1%" in copied


def test_it_says_so_in_place_rather_than_silently(dialog, qapp):
    """A button that does its job silently is one nobody believes, which
    is the whole reason it exists beside the automatic copy. The answer
    is on the button - no second dialog to dismiss - and it goes back
    afterwards so it reads as a button again rather than a status."""
    dialog._append("one line")
    dialog._copy()
    assert "Copied" in dialog.copy_button.text()
    assert not dialog.copy_button.isEnabled()
    dialog._copy_button_back()
    assert dialog.copy_button.text() == "Copy output"
    assert dialog.copy_button.isEnabled()


def test_the_bar_follows_the_tools_own_percentage(dialog):
    """Nothing guesses a percentage out of ordinary output: a run prints
    tables, hero names and paths, and a bar driven by whatever looked
    like a number would jump about through all of it."""
    assert dialog.progress.maximum() == 0        # indeterminate to start
    dialog._append("PROGRESS 40%  looking for the pick bar")
    assert dialog.progress.maximum() == 100
    assert dialog.progress.value() == 40
    dialog._append("PROGRESS 100%  done")
    assert dialog.progress.value() == 100


def test_a_tool_that_reports_nothing_keeps_a_spinning_bar(qapp):
    """A bar stuck at 0 reads as NO progress, where a spinning one reads
    as progress of an unknown amount - which is the truth about a tool
    that does not report."""
    box = TaskDialog(TASKS["update_app"])
    try:
        box._append("Pulling from origin/main - the release branch.")
        assert box.progress.maximum() == 0
    finally:
        box.deleteLater()


def test_copying_an_empty_log_does_not_raise(dialog, qapp):
    dialog._copy()
    assert "Copied" in dialog.copy_button.text()


# --------------------------------------------------------------------
# TEN UNKNOWNS AT THE MENU IS THE RIGHT ANSWER, and the log has to say
# so. A real paste came back with eight UNKNOWN, two EMPTY and distances
# of 84-104 against a ceiling of 51 - which reads as ten broken crop
# boxes and was in fact Dota sitting in the menu with no pick bar on
# screen at all.


def test_a_blank_game_state_is_explained_in_the_recognition_log():
    """`game_state` is BLANK when Dota is open with no match - the
    commonest moment anybody presses Copy everything. The guard used to
    be `if state and ...`, so blank fell straight through and printed
    ten failures with nothing saying why."""
    source = (ROOT / "draft_assist" / "ui" / "app.py").read_text(
        encoding="utf-8")
    body = source[source.index("gate score: {snap.gate_score"):]
    body = body[:body.index("for s in read.slots")]
    assert "if not state:" in body, (
        "a blank game state must be explained, not skipped")
    assert "not in a match" in body

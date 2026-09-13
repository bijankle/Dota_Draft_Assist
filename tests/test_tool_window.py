"""Run, watch, copy — the window the user specified.

Verbatim: "a window pops up with a terminal / area for text, a button
saying run - i hit run and the button turns grey, the text window shows
all the thinking the program is doing and when its ready the button
turns its original color ie. red and it says copy results - and i paste
it to you."

THE BUG THAT MADE THIS NECESSARY is the one checked first. Both
diagnostic checks built a `TaskDialog` by hand, wired its signals and
called `start()` — and never `show()` or `exec()`. `run_task`, the path
every other task takes, does `start()` AND THEN `exec()`. So the worker
ran with nothing on screen ("there is no ability to see what the program
is thinking") and the dialog's `finished` signal, which fires when a
dialog is CLOSED, never fired — so the automatic copy hanging off it
never ran either ("nothing copied to clipboard"). One missing call,
both complaints.
"""

import os
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QPushButton     # noqa: E402

from draft_assist.ui.tasks import TASKS, Task             # noqa: E402
from draft_assist.ui.tool_window import (ToolWindow,      # noqa: E402
                                         pictures_in)

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp):
    made = []

    def build(key="check_resolutions", start_in=None, what="results"):
        win = ToolWindow(TASKS[key], start_in=start_in, what=what)
        made.append(win)
        return win
    yield build
    for win in made:
        win.close()
        win.deleteLater()


def test_neither_check_starts_a_run_nobody_can_see(qapp):
    """THE BUG. A window whose purpose is to be watched must not be able
    to run unwatched."""
    source = (ROOT / "draft_assist" / "ui" / "app.py").read_text(
        encoding="utf-8")
    body = source[source.index("def _open_tool"):]
    body = body[:body.index("\n    def ")]
    assert ".show()" in body, "the window has to be shown"

    for name in ("_check_recognition", "_check_resolutions"):
        one = source[source.index(f"def {name}"):]
        one = one[:one.index("\n    def ")]
        assert "_open_tool" in one
        assert "TaskDialog" not in one, (
            f"{name} builds a dialog by hand again — that is the bug")


def test_the_button_says_run_before_anything_happens(window):
    win = window()
    assert win.action.text() == "Run"
    assert win.action.property("accent") is True


def test_it_greys_out_while_the_tool_works(window):
    win = window()
    win._running()
    assert win.action.text() == "Running…"
    assert win.action.isEnabled() is False
    assert win.action.property("accent") is False


def test_and_comes_back_red_saying_copy_results(window):
    win = window()
    win._running()
    win._append("PROGRESS 100%  done")
    win._finished(0, "Finished")
    assert win.action.text() == "Copy results"
    assert win.action.isEnabled() is True
    assert win.action.property("accent") is True


def test_pressing_it_then_copies_the_transcript(window, qapp):
    win = window()
    win._append("1920x1200.png   located 10")
    win._append("DO THE RESOLUTIONS AGREE?")
    win._finished(0, "Finished")
    win._pressed()
    assert QApplication.clipboard().text() == (
        "1920x1200.png   located 10\nDO THE RESOLUTIONS AGREE?")
    assert win.action.text() == "Copied 2 lines"


def test_a_failed_run_is_the_one_most_worth_pasting_back(window):
    """So the button does not consult `succeeded` — only whether there
    is anything to copy."""
    win = window()
    win._append("Traceback (most recent call last):")
    win._finished(1, "Failed")
    assert win.succeeded is False
    assert win.action.text() == "Copy results"


def test_a_run_that_printed_nothing_offers_run_again(window):
    win = window()
    win._finished(1, "Failed")
    assert win.action.text() == "Run"


def test_the_words_on_the_button_are_the_callers(window):
    win = window(key="score_recognition", what="report")
    win._append("something")
    win._finished(0, "Finished")
    assert win.action.text() == "Copy report"


def test_the_transcript_can_be_selected_and_copied_by_hand(window):
    """"I should be able to manually copy it." Read-only is not the same
    as unselectable, and a QPlainTextEdit is selectable either way — what
    would break it is the text being REPLACED on every refresh, which is
    why this appends."""
    win = window()
    win._append("one")
    win._append("two")
    assert win.log.isReadOnly()
    assert win.log.toPlainText() == "one\ntwo"
    from PyQt6.QtGui import QTextCursor
    win.log.selectAll()
    assert win.log.textCursor().selectedText()
    assert isinstance(win.log.textCursor(), QTextCursor)


def test_it_does_not_drag_the_view_away_from_a_reader(window):
    """Scrolling to the end on every line pulls the view out from under
    somebody who scrolled up to read or select."""
    win = window()
    for number in range(200):
        win._append(f"line {number}")
    bar = win.log.verticalScrollBar()
    bar.setValue(0)
    win._append("line 200")
    assert bar.value() == 0, "it followed the tail while being read"
    bar.setValue(bar.maximum())
    win._append("line 201")
    assert bar.value() == bar.maximum(), "it stopped following at the tail"


def test_progress_lines_drive_the_bar(window):
    win = window()
    win.progress.setRange(0, 0)
    win._append("PROGRESS 34%  1920x1200.png")
    assert win.progress.maximum() == 100
    assert win.progress.value() == 34


def test_the_folder_row_gates_run(window, tmp_path):
    """Run stays dead until there is a folder with pictures in it."""
    win = window(start_in=tmp_path)
    assert win.action.isEnabled() is False
    assert "No folder chosen" in win.folder_label.text()


def test_a_folder_with_no_pictures_is_named_rather_than_run(window,
                                                            tmp_path,
                                                            monkeypatch):
    """The tool exits with "No images in ..." on stderr, which arrives as
    a failed run with one line in it — a worse way to say "wrong
    folder"."""
    empty = tmp_path / "empty"
    empty.mkdir()
    from draft_assist.ui import tool_window
    monkeypatch.setattr(tool_window.QFileDialog, "getExistingDirectory",
                        staticmethod(lambda *a, **k: str(empty)))
    win = window(start_in=tmp_path)
    win._choose()
    assert win.folder == ""
    assert win.action.isEnabled() is False
    assert "no pictures" in win.folder_label.text()


def test_a_folder_with_pictures_enables_it_and_says_how_many(window,
                                                             tmp_path,
                                                             monkeypatch):
    shots = tmp_path / "All Resolutions - Dota 2"
    shots.mkdir()
    for name in ("1920x1080.png", "1920x1200.PNG", "notes.txt"):
        (shots / name).write_bytes(b"")
    from draft_assist.ui import tool_window
    monkeypatch.setattr(tool_window.QFileDialog, "getExistingDirectory",
                        staticmethod(lambda *a, **k: str(shots)))
    win = window(start_in=tmp_path)
    win._choose()
    assert win.folder == str(shots)
    assert win.action.isEnabled() is True
    assert "(2 pictures)" in win.folder_label.text()


def test_the_chosen_folder_reaches_the_tool(window, tmp_path, monkeypatch):
    """`{arg}` is what the tool is pointed at; a window that collected a
    folder and ran without it would sweep the wrong place."""
    shots = tmp_path / "shots"
    shots.mkdir()
    (shots / "1600x1200.png").write_bytes(b"")
    from draft_assist.ui import tool_window
    monkeypatch.setattr(tool_window.QFileDialog, "getExistingDirectory",
                        staticmethod(lambda *a, **k: str(shots)))
    win = window(start_in=tmp_path)
    win._choose()
    started = {}

    def fake(task, parent):
        started["task"] = task
        return _FakeWorker()

    monkeypatch.setattr(tool_window, "TaskWorker", fake)
    win.start()
    argv = [part for step in started["task"].steps for part in step]
    assert str(shots) in argv
    assert "{arg}" not in argv


def test_counting_pictures_never_raises_on_a_bad_path():
    assert pictures_in("/no/such/folder/anywhere") == 0


class _FakeWorker:
    """Enough of TaskWorker for `start()` to run without a subprocess."""

    class _Signal:
        def connect(self, _slot):
            pass

    def __init__(self):
        self.line = self._Signal()
        self.done = self._Signal()

    def start(self):
        pass

    def isRunning(self):
        return False

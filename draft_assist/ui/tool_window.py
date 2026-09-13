"""Run a diagnostic tool, watch it, copy what it said.

THE SHAPE IS THE USER'S, stated verbatim: "a window pops up with a
terminal / area for text, a button saying run - i hit run and the button
turns grey, the text window shows all the thinking the program is doing
and when its ready the button turns its original color ie. red and it
says copy results - and i paste it to you."

So there is ONE button that carries the whole state of the run. It reads
Run before, it is grey and says Running while the tool works, and it
comes back in the accent red as Copy results when there is something to
copy. Nothing here copies to the clipboard on its own: an automatic copy
is invisible, and invisible is precisely what was wrong.

WHY THIS EXISTS RATHER THAN `TaskDialog`. That one starts on the way up
and is driven by `run_task`, which calls `start()` AND THEN `exec()`.
Two callers built a TaskDialog by hand, wired its signals and called
`start()` WITHOUT ever showing it — so the worker ran with nothing on
screen and the dialog's `finished` signal, which fires when a dialog is
CLOSED, never fired at all. That is both halves of what was reported:
"there is no ability to see what the program is thinking", and then
"nothing copied to clipboard". A window whose whole purpose is to be
watched should not be able to run unwatched, so this one SHOWS ITSELF
and the run is a button inside it.
"""

import os
import re
from pathlib import Path

from PyQt6.QtCore import QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QApplication, QDialog, QFileDialog, QHBoxLayout,
                             QLabel, QPlainTextEdit, QProgressBar,
                             QPushButton, QVBoxLayout)

from .task_dialog import PERCENT
from .tasks import Task, TaskWorker

PICTURES = (".png", ".jpg", ".jpeg", ".bmp")
# A MARKED LINE, the same idea as PERCENT: the tool SAYS where it put
# the proof sheet rather than leaving us to recognise a path among the
# folders, hero names and file names an ordinary run prints.
SHEET = re.compile(r"^SHEET\s+(.+)$")


def pictures_in(folder: str) -> int:
    """How many images are directly in this folder. Never raises."""
    try:
        return sum(1 for name in os.listdir(folder)
                   if name.lower().endswith(PICTURES))
    except OSError:
        return 0


class ToolWindow(QDialog):
    """One tool, one transcript, one button.

    `start_in` turns on the folder row: the tool takes a folder as its
    `{arg}` and Run stays disabled until one with pictures in it is
    chosen. The row lives IN this window rather than as a picker that
    opens first, so there is one window rather than two and a wrong
    folder is changed without starting over.
    """

    line = pyqtSignal(str)

    def __init__(self, task: Task, parent=None, start_in: Path | None = None,
                 what: str = "results"):
        super().__init__(parent)
        self.task = task
        self.what = what
        self.folder = ""
        self.succeeded = False
        self.sheet: Path | None = None
        self._worker: TaskWorker | None = None
        self.setWindowTitle(task.title)
        self.setMinimumSize(820, 520)

        layout = QVBoxLayout(self)
        heading = QLabel(task.title)
        heading.setProperty("heading", True)
        layout.addWidget(heading)
        if task.blurb:
            blurb = QLabel(task.blurb)
            blurb.setWordWrap(True)
            blurb.setProperty("dim", True)
            layout.addWidget(blurb)

        self.folder_row = None
        if start_in is not None:
            self.folder_row = QHBoxLayout()
            self.folder_label = QLabel("No folder chosen")
            self.folder_label.setProperty("dim", True)
            self.folder_label.setWordWrap(True)
            choose = QPushButton("Choose folder…")
            choose.clicked.connect(self._choose)
            self.folder_row.addWidget(choose)
            self.folder_row.addWidget(self.folder_label, 1)
            layout.addLayout(self.folder_row)
            self._start_in = start_in

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        # READ-ONLY BUT SELECTABLE, which is what a QPlainTextEdit already
        # is — "I should be able to manually copy it". The button is the
        # convenience, never the only way out.
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.log, 1)

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        self.summary.hide()
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        self.cancel_button = QPushButton("Stop")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch(1)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.close_button)
        # THE ONE BUTTON. Accent red throughout its life except while the
        # tool is running, because it is the one action this window is
        # for and a window with no obvious action is a window nobody
        # knows what to do with.
        self.action = QPushButton("Run")
        self.action.setProperty("accent", True)
        self.action.setDefault(True)
        self.action.clicked.connect(self._pressed)
        buttons.addWidget(self.action)
        layout.addLayout(buttons)

        self._ready()

    # ---- the button's four states ----------------------------------

    def _restyle(self) -> None:
        """A property change needs the style re-applied by hand."""
        self.action.style().unpolish(self.action)
        self.action.style().polish(self.action)

    def _ready(self) -> None:
        self.action.setText("Run")
        self.action.setProperty("accent", True)
        self.action.setEnabled(
            self.folder_row is None or bool(self.folder))
        self._restyle()

    def _running(self) -> None:
        self.action.setText("Running…")
        # GREY, at the user's request — "the button turns grey". The
        # accent is what says "press me", so a running task must not
        # wear it.
        self.action.setProperty("accent", False)
        self.action.setEnabled(False)
        self._restyle()

    def _copyable(self) -> None:
        self.action.setText(f"Copy {self.what}")
        self.action.setProperty("accent", True)
        self.action.setEnabled(True)
        self._restyle()

    # ---- doing things ----------------------------------------------

    def _pressed(self) -> None:
        if self._busy():
            return
        if self.action.text().startswith("Copy"):
            self._copy()
        else:
            self.start()

    def _choose(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Folder of draft screenshots, one per resolution",
            self.folder or str(self._start_in))
        if not folder:
            return
        found = pictures_in(folder)
        self.folder = folder
        if found:
            self.folder_label.setText(f"{folder}  ({found} pictures)")
        else:
            # NAMED HERE RATHER THAN INSIDE THE RUN. The tool exits with
            # "No images in ..." on stderr, which arrives as a failed run
            # with one line in it — a worse way to say "wrong folder".
            self.folder_label.setText(
                f"{folder}  — no pictures in this folder. Pick the one "
                "holding the screenshots themselves.")
            self.folder = ""
        self._ready()

    def start(self) -> None:
        task = (self.task.with_argument(self.folder)
                if self.folder else self.task)
        self.log.clear()
        self.summary.hide()
        # A SECOND RUN MUST NOT REOPEN THE FIRST ONE'S PICTURE, which
        # would be the app confidently showing a sheet that describes a
        # run the user has just replaced.
        self.sheet = None
        self.progress.setRange(0, 0)          # indeterminate until told
        self._worker = TaskWorker(task, self)
        self._worker.line.connect(self._append)
        self._worker.done.connect(self._finished)
        self._running()
        self.cancel_button.setEnabled(task.cancellable)
        self._worker.start()

    def _append(self, text: str) -> None:
        bar = self.log.verticalScrollBar()
        # ONLY FOLLOW IF ALREADY AT THE BOTTOM. Scrolling to the end on
        # every line drags the view out from under somebody who scrolled
        # up to read or select something, which is the other half of
        # "I should be able to manually copy it".
        following = bar.value() >= bar.maximum() - 2
        self.log.appendPlainText(text)
        if following:
            bar.setValue(bar.maximum())
        self.line.emit(text)
        marked = SHEET.match(text.strip())
        if marked:
            # A MARKED LINE, exactly like PROGRESS, rather than scanning
            # ordinary output for something that looks like a path: a
            # run prints folders, hero names and file names throughout.
            self.sheet = Path(marked.group(1).strip())
        found = PERCENT.match(text.strip())
        if found:
            share = min(100, max(0, int(found.group(1))))
            if self.progress.maximum() == 0:
                self.progress.setRange(0, 100)
                self.progress.setTextVisible(True)
            self.progress.setValue(share)

    def _cancel(self) -> None:
        self.cancel_button.setEnabled(False)
        if self._worker is not None:
            self._worker.cancel()

    def _finished(self, code: int, summary: str) -> None:
        self.succeeded = code == 0
        self.cancel_button.setEnabled(False)
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 1)
        self.progress.setValue(self.progress.maximum())
        self.summary.setText(summary)
        self.summary.setProperty("pill", "good" if self.succeeded else "warn")
        self.summary.style().unpolish(self.summary)
        self.summary.style().polish(self.summary)
        self.summary.show()
        # COPYABLE EITHER WAY. A run that FAILED is the one whose output
        # is most worth pasting back, so the button does not check
        # `succeeded` — it checks whether there is anything to copy.
        if self.log.toPlainText().strip():
            self._copyable()
        else:
            self._ready()
        self._show_sheet()

    def _show_sheet(self) -> None:
        """Open the proof sheet, if the run wrote one.

        "I want you to flash up on the screen snippets of all the
        portraits on their own for each run for each resolution." The
        crops have been written to a folder throughout and nobody has
        ever opened them, which is the same fault as the dialog that was
        never shown: a thing produced where nobody is looking has not
        been produced. It is the system viewer rather than a pane of our
        own, because the sheet is one tall picture that wants scrolling
        and zooming, and this window is for TEXT the user copies.

        Never fatal, and never noisy: a missing file or a machine with
        no image viewer simply leaves the path in the log.
        """
        sheet = getattr(self, "sheet", None)
        if sheet is None or not Path(sheet).is_file():
            return
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(sheet)))
        except Exception:                      # pragma: no cover - viewer
            pass

    def _copy(self) -> None:
        text = self.log.toPlainText()
        QApplication.clipboard().setText(text)
        lines = text.count("\n") + 1 if text else 0
        self.action.setText(f"Copied {lines} lines")
        self.action.setEnabled(False)
        QTimer.singleShot(1800, self._copyable)

    def _busy(self) -> bool:
        """Is a run in flight? NEVER RAISES, because this is asked from
        `closeEvent` — and an exception out of a Qt event handler during
        teardown aborts the process rather than raising, which is the
        same class of fault as touching a QPixmap before the
        QApplication. A window that cannot be closed is worse than one
        that closes over a run it could not ask about."""
        worker = self._worker
        if worker is None:
            return False
        try:
            return bool(worker.isRunning())
        except Exception:                     # noqa: BLE001 - see above
            return False

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self._busy():
            self._worker.cancel()
            self._worker.wait(3000)
        super().closeEvent(event)

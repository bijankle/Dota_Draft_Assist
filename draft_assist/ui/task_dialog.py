"""Live progress dialog for maintenance tasks.

Replaces the console windows the .bat launchers used to open: the same
output, but inside the app, scrolling live, with the failure explained in
plain language instead of a traceback scrolling past a "Press any key"
prompt.
"""

import re

from PyQt6.QtCore import Qt
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel,
                             QPlainTextEdit, QProgressBar, QPushButton,
                             QVBoxLayout)

from .tasks import Task, TaskWorker

# A tool that wants a real progress bar says so on its own lines. Nothing
# guesses at the percentage from ordinary output: a run prints tables,
# names and paths, and a bar driven by whatever looked like a number
# would jump about through all of it.
PERCENT = re.compile(r"^PROGRESS\s+(\d{1,3})%")


class TaskDialog(QDialog):
    def __init__(self, task: Task, parent=None):
        super().__init__(parent)
        self.task = task
        self.succeeded = False
        # Set by the caller for a task that ends in the app relaunching:
        # pressing Close on a progress box and then watching the app you
        # just updated restart anyway is one click for nothing.
        self.close_on_success = False
        self.setWindowTitle(task.title)
        self.setMinimumSize(760, 460)

        layout = QVBoxLayout(self)
        heading = QLabel(task.title)
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        if task.blurb:
            blurb = QLabel(task.blurb)
            blurb.setWordWrap(True)
            blurb.setProperty("dim", True)
            layout.addWidget(blurb)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)          # indeterminate while running
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.log, 1)

        self.summary = QLabel("Working…")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        # COPY IS ON THE LEFT AND LIVE THROUGHOUT, at the user's request:
        # "I don't trust that the copy and paste works unless I can see
        # the console in the app." Copying silently on success is
        # convenient and invisible, and invisible is the half that has to
        # be fixed - so there is a button, it is pressable while the run
        # is still going, and it says so when it has done it.
        self.copy_button = QPushButton("Copy output")
        self.copy_button.clicked.connect(self._copy)
        buttons.addWidget(self.copy_button)
        buttons.addStretch(1)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(task.cancellable)
        self.cancel_button.clicked.connect(self._cancel)
        buttons.addWidget(self.cancel_button)
        self.close_button = QPushButton("Close")
        self.close_button.setProperty("accent", True)
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self.worker = TaskWorker(task, self)
        self.worker.line.connect(self._append)
        self.worker.done.connect(self._finished)

    def start(self) -> None:
        self.worker.start()

    def _append(self, text: str) -> None:
        self.log.appendPlainText(text)
        bar = self.log.verticalScrollBar()
        bar.setValue(bar.maximum())
        found = PERCENT.match(text.strip())
        if found:
            # An indeterminate bar says "something is happening" and
            # nothing else, which is the question already answered by the
            # text scrolling beside it.
            share = min(100, max(0, int(found.group(1))))
            if self.progress.maximum() == 0:
                self.progress.setRange(0, 100)
                self.progress.setTextVisible(True)
            self.progress.setValue(share)

    def _copy(self) -> None:
        """Put the whole transcript on the clipboard, and SAY SO.

        A button that does its job silently is one nobody believes, which
        is the whole reason this exists rather than the automatic copy
        alone. The label answers it in place - no second dialog to
        dismiss - and goes back after a moment so it reads as a button
        again rather than a status.
        """
        text = self.log.toPlainText()
        QApplication.clipboard().setText(text)
        lines = text.count("\n") + 1 if text else 0
        self.copy_button.setText(f"Copied {lines} lines")
        self.copy_button.setEnabled(False)
        QTimer.singleShot(1800, self._copy_button_back)

    def _copy_button_back(self) -> None:
        self.copy_button.setText("Copy output")
        self.copy_button.setEnabled(True)

    def _cancel(self) -> None:
        self.summary.setText("Cancelling…")
        self.cancel_button.setEnabled(False)
        self.worker.cancel()

    def _finished(self, code: int, summary: str) -> None:
        self.succeeded = code == 0
        self.summary.setText(summary)
        self.summary.setProperty("pill", "good" if self.succeeded else "warn")
        self.summary.style().unpolish(self.summary)
        self.summary.style().polish(self.summary)
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 1)
        self.progress.setValue(self.progress.maximum())
        self.cancel_button.setEnabled(False)
        self.close_button.setEnabled(True)
        self.close_button.setFocus()
        if self.succeeded and self.close_on_success:
            # Queued, not called here: this runs inside the worker's
            # finished signal, and accepting a dialog from inside one of
            # its own children's signals is how a half-torn-down event
            # loop happens.
            QTimer.singleShot(0, self.accept)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(3000)
        super().closeEvent(event)

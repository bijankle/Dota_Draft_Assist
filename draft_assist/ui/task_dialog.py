"""Live progress dialog for maintenance tasks.

Replaces the console windows the .bat launchers used to open: the same
output, but inside the app, scrolling live, with the failure explained in
plain language instead of a traceback scrolling past a "Press any key"
prompt.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPlainTextEdit,
                             QProgressBar, QPushButton, QVBoxLayout)

from .tasks import Task, TaskWorker


class TaskDialog(QDialog):
    def __init__(self, task: Task, parent=None):
        super().__init__(parent)
        self.task = task
        self.succeeded = False
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

    def _cancel(self) -> None:
        self.summary.setText("Cancelling…")
        self.cancel_button.setEnabled(False)
        self.worker.cancel()

    def _finished(self, code: int, summary: str) -> None:
        self.succeeded = code == 0
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.summary.setText(summary)
        self.summary.setProperty("pill", "good" if self.succeeded else "warn")
        self.summary.style().unpolish(self.summary)
        self.summary.style().polish(self.summary)
        self.cancel_button.setEnabled(False)
        self.close_button.setEnabled(True)
        self.close_button.setFocus()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(3000)
        super().closeEvent(event)

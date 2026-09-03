"""Maintenance jobs run from the application's menus.

Everything that used to be a separate .bat file — updating the app, pulling
statistics, tuning recognition, probing capture, listing windows — is
defined here as a Task and executed as a subprocess in a worker thread, with
its output streamed live into a dialog. The app stays responsive, failures
are readable in place, and there is exactly one thing to launch.

Subprocesses (rather than in-process calls) are deliberate: these jobs are
long, chatty and occasionally crash, and a crashing pull must never take the
running draft window down with it.
"""

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from ..config import REPO_ROOT


@dataclass
class Task:
    key: str
    title: str
    # Each step is an argv list; {py} is replaced with this environment's
    # interpreter so the venv is always used.
    steps: list[list[str]]
    blurb: str = ""
    needs_network: bool = False
    # Reload dataset/library into the running app when the task succeeds.
    reload_after: bool = False
    cancellable: bool = True
    env: dict = field(default_factory=dict)


PY = "{py}"

TASKS = {
    "update_data": Task(
        key="update_data",
        title="Update statistics and portraits",
        steps=[[PY, "tools/pull_data.py"], [PY, "tools/build_library.py"]],
        blurb=("Downloads hero statistics for the bracket set in "
               "Data > Statistics bracket, verifies bracket indexing across "
               "OpenDota and Stratz, rebuilds the interaction matrices, and "
               "fetches hero portraits. Run about once a day, and after a "
               "patch."),
        needs_network=True,
        reload_after=True,
    ),
    "tune": Task(
        key="tune",
        title="Tune recognition",
        steps=[[PY, "-m", "draft_assist.proving.tune"]],
        blurb=("Generates synthetic draft screens from the portrait library "
               "and searches for the recognition settings that never produce "
               "a wrong hero. Takes a few minutes. Run after updating "
               "portraits or labelling new crops."),
        reload_after=True,
    ),
    "update_app": Task(
        key="update_app",
        title="Update application",
        steps=[["git", "pull", "--rebase", "--autostash"],
               [PY, "-m", "pip", "install", "-q", "-r", "requirements.txt",
                "-r", "requirements-windows.txt"]],
        blurb=("Pulls the latest code from GitHub, keeping any local edits "
               "(such as your item rules) and re-applying them on top, then "
               "refreshes dependencies. Restart the app afterwards."),
        needs_network=True,
    ),
    "list_windows": Task(
        key="list_windows",
        title="List capture sources",
        steps=[[PY, "tools/list_windows.py"]],
        blurb=("Lists every visible window and reports whether the Dota "
               "client is among them, with its measured size."),
        cancellable=False,
    ),
    "probe_gsi": Task(
        key="probe_gsi",
        title="Record game data",
        steps=[[PY, "tools/probe_gsi.py", "--minutes", "10"]],
        blurb=("Listens for Dota's Game State Integration payloads for ten "
               "minutes, archives every one, and reports which components "
               "the game actually sends. Run it and sit through a draft: "
               "the verdict at the end says whether GSI can see the enemy "
               "line-up or whether those picks must be entered by hand."),
    ),
    "probe": Task(
        key="probe",
        title="Run capture probe",
        steps=[[PY, "tools/probe_capture.py", "--minutes", "2"]],
        blurb=("Saves frames from the Dota window every 2 seconds for two "
               "minutes into captures/probe/. Cover the Dota window while it "
               "runs: frames should keep showing Dota and keep reporting "
               "CHANGED. This is the test that occluded capture works."),
    ),
}


class TaskWorker(QThread):
    """Runs a Task's steps in order, streaming combined output."""

    line = pyqtSignal(str)
    done = pyqtSignal(int, str)      # exit code, human summary

    def __init__(self, task: Task, parent=None):
        super().__init__(parent)
        self.task = task
        self._proc: subprocess.Popen | None = None
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        proc = self._proc
        if proc and proc.poll() is None:
            proc.terminate()

    def _argv(self, step: list[str]) -> list[str]:
        return [sys.executable if part == PY else part for part in step]

    def run(self) -> None:  # noqa: D401 - QThread entry point
        env = {**os.environ, "PYTHONUNBUFFERED": "1", **self.task.env}
        for index, step in enumerate(self.task.steps, start=1):
            if self._cancelled:
                self.done.emit(1, "Cancelled.")
                return
            argv = self._argv(step)
            self.line.emit(f"$ {' '.join(argv)}\n")
            try:
                self._proc = subprocess.Popen(
                    argv, cwd=str(REPO_ROOT), env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                    creationflags=(subprocess.CREATE_NO_WINDOW
                                   if sys.platform == "win32" else 0),
                )
            except FileNotFoundError:
                missing = argv[0]
                self.done.emit(127, (
                    f"'{missing}' was not found. "
                    + ("Install Git from git-scm.com and restart the app."
                       if missing == "git" else
                       "The Python environment looks incomplete.")))
                return
            assert self._proc.stdout is not None
            for raw in self._proc.stdout:
                self.line.emit(raw.rstrip("\n"))
            code = self._proc.wait()
            if code != 0:
                if self._cancelled:
                    self.done.emit(1, "Cancelled.")
                else:
                    self.done.emit(code, (
                        f"Step {index} of {len(self.task.steps)} failed "
                        f"(exit code {code}). The output above says why."))
                return
        self.done.emit(0, "Finished successfully.")

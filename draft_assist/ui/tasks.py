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
    # Run without blocking the main window. Tasks that FEED the app (the
    # simulators, the replayer) exist to make the draft panel move, so a
    # modal dialog over it defeats the whole point -- you could watch the
    # heroes arrive but not click one to see why it scores well.
    modeless: bool = False
    env: dict = field(default_factory=dict)

    def with_argument(self, value: str) -> "Task":
        """A copy with {arg} filled in — for tasks that act on a thing the
        user selected, like replaying one recording."""
        from dataclasses import replace
        return replace(self, steps=[[part.replace("{arg}", value)
                                     for part in step]
                                    for step in self.steps])


PY = "{py}"

TASKS = {
    # RECOGNITION IS BACK ON THE MENU, for one job and at the user's
    # request: "if its complex - add the code launching via the help
    # dropdown as you did before". It REVERSES "all of those were used to
    # refine the software - once its done i dont nteed them", which took
    # the whole Recognition checks submenu out — and the reversal is
    # narrower than what it removes: two items that answer the two
    # questions this exercise is actually about, rather than four
    # instruments and a window of their own.
    #
    # NEITHER TOUCHES THE APP. Both read pictures off disk and write a
    # sheet into `debug_out/`; nothing they do can change a calibration,
    # which is why they are safe to put in front of somebody mid-patch.
    "check_crop_boxes": Task(
        key="check_crop_boxes",
        title="Check the crop boxes",
        steps=[[PY, "tools/find_portraits.py", "{arg}", "--boxes-only"]],
        blurb=("Cuts the app's own ten crop boxes out of every screenshot "
               "in a folder, draws each box on what is around it, and "
               "stacks them into one sheet. Seconds per picture."),
    ),
    "locate_portraits": Task(
        key="locate_portraits",
        title="Locate the portraits",
        steps=[[PY, "tools/find_portraits.py", "{arg}", "--tall"]],
        blurb=("Searches each screenshot for the pick bar and measures "
               "where it really is. About a minute per picture, so it "
               "runs only the shots that can answer the question."),
    ),
    "fix_crop_boxes": Task(
        key="fix_crop_boxes",
        title="Fix the crop boxes from screenshots",
        steps=[[PY, "tools/find_portraits.py", "{arg}", "--sample", "8",
                "--apply"]],
        blurb=("Measures where the pick bar really is across a spread of "
               "screenshots and saves it as this machine's calibration. "
               "Nothing is written unless they agree."),
        reload_after=True,
    ),
    "update_data": Task(
        key="update_data",
        title="Update statistics and portraits",
        steps=[[PY, "tools/pull_data.py"], [PY, "tools/fetch_assets.py"]],
        blurb=("Downloads hero statistics for the ranks you chose, then "
               "tops up any artwork this machine is missing. The one "
               "job worth repeating every few weeks."),
        needs_network=True,
        reload_after=True,
    ),
    "fetch_item_icons": Task(
        key="fetch_item_icons",
        title="Fetch item icons",
        steps=[[PY, "tools/fetch_item_icons.py"]],
        blurb=("Downloads just the item pictures for the strip under the "
               "draft."),
        needs_network=True,
        reload_after=True,
    ),
    "fetch_assets": Task(
        key="fetch_assets",
        title="Download hero portraits and item icons",
        steps=[[PY, "tools/fetch_assets.py"]],
        blurb=("Downloads every hero portrait and item icon to this "
               "machine. Needs no account, and skips whatever is "
               "already on disk."),
        needs_network=True,
        reload_after=True,
    ),
    "fetch_custom_portraits": Task(
        key="fetch_custom_portraits",
        title="Fetch alternative hero portraits",
        steps=[[PY, "tools/fetch_custom_portraits.py"]],
        blurb=("Downloads the community's persona, arcana and custom-set "
               "portraits, so a teammate wearing one stops reading as "
               "UNKNOWN."),
        reload_after=True,
    ),
    "update_app": Task(
        key="update_app",
        title="Update application",
        steps=[[PY, "tools/update_app.py"],
               [PY, "-m", "pip", "install", "-q", "-r", "requirements.txt",
                "-r", "requirements-windows.txt"],
               ],
        blurb=("Gets the latest code and reopens. Seconds rather than "
               "minutes: no statistics and no artwork, and nothing of "
               "yours is touched."),
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
    # IT READS A RECORDING AND WRITES NOTHING, which is what makes it
    # safe to put beside Replay. The two questions it answers are the
    # ones a screenshot cannot: the game's own account of where everybody
    # stood (so a wrong split can be told from a coin flip), and whether
    # the pick bar sits in the same place during HERO SELECTION as it
    # does at strategy time - which every measurement so far has had to
    # assume, because no screenshot in the sample was taken while the
    # bar was both up and full.
    "measure_recording": Task(
        key="measure_recording",
        title="Measure this recording",
        # --row ALWAYS, because this button is the whole route a
        # measurement takes back to `vision/measured.py`. The flag stays
        # on the tool for a command line, but a row nobody can reach
        # from the app is a row nobody sends — and the section refuses
        # cleanly when the frames cannot produce one, so there is
        # nothing to switch off.
        steps=[[PY, "tools/measure_recording.py", "{arg}", "--row"]],
        blurb=("Measures one recording: where each hero stood when the "
               "teams were decided, where the pick bar really was, and "
               "a line to send back so this screen size ships correct."),
    ),
    "replay_gsi": Task(
        key="replay_gsi",
        title="Replay recorded game data",
        steps=[[PY, "tools/simulate_gsi.py", "--from", "{arg}"]],
        blurb=("Replays this recording's payloads exactly as Dota sent "
               "them. Nothing is modelled, so it can find faults a "
               "simulated draft cannot."),
        cancellable=True,
        modeless=True,
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
        # ONE ENCODING, DECLARED AT BOTH ENDS. `text=True` with nothing
        # said uses the machine's locale, which on Windows is cp1252 —
        # so a tool printing any character outside it raised
        # UnicodeEncodeError INSIDE THE TOOL, writing to our pipe. That
        # is what killed `fetch_assets`' error handler mid-report. The
        # child is told to speak UTF-8 and we decode UTF-8, so a tool
        # keeps its glyphs whatever codepage the machine is set to; the
        # `:replace` and `errors=` are the belt to that braces, since
        # neither end may raise over a character.
        env = {**os.environ, "PYTHONUNBUFFERED": "1",
               "PYTHONIOENCODING": "utf-8:replace", **self.task.env}
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
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
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

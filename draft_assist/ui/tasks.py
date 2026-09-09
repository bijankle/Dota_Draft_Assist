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
    "update_data": Task(
        key="update_data",
        title="Update statistics and portraits",
        steps=[[PY, "tools/pull_data.py"], [PY, "tools/fetch_assets.py"]],
        blurb=("Downloads hero statistics for the ranks set in Setup ▸ "
               "Statistics bracket, verifies bracket indexing across "
               "OpenDota and Stratz, rebuilds the interaction matrices, "
               "and then tops up any artwork this machine is missing "
               "— which is how a hero added in a patch gets its "
               "picture.\n\nThis is the ONE recurring job: the "
               "statistics stop tracking the current patch after a few "
               "weeks, and the banner at the top of the window says so "
               "once they are older than the reminder set in Settings. "
               "Nothing else needs updating on a schedule."),
        needs_network=True,
        reload_after=True,
    ),
    "check_item_icons": Task(
        key="check_item_icons",
        title="Check item icons",
        steps=[[PY, "tools/check_item_icons.py"]],
        blurb=("Names every item in the rules that has no picture, and says "
               "which of the three reasons it is: no file was ever written "
               "(the download 404'd, or the rules name an item OpenDota "
               "does not list), the name matches two icons and is refused "
               "rather than guessed at, or the file on disk will not "
               "decode. An item with no icon draws its NAME instead, and "
               "that fallback looks the same whatever went wrong.\n\n"
               "A missing file is fixed by Download > Item icons, which "
               "skips what is already there and so retries exactly the "
               "ones that failed."),
        needs_network=False,
    ),
    "fetch_item_icons": Task(
        key="fetch_item_icons",
        title="Fetch item icons",
        steps=[[PY, "tools/fetch_item_icons.py"]],
        blurb=("Downloads only the item pictures for the strip under the "
               "draft, and prints the URL it tried and how many files it "
               "wrote. The full update does this too — this exists so that "
               "'the icons are still blank' has an answer rather than a "
               "shrug."),
        needs_network=True,
        reload_after=True,
    ),
    "make_shortcut": Task(
        key="make_shortcut",
        title="Make a shortcut you can pin",
        steps=[[PY, "tools/make_shortcut.py"]],
        blurb=("Makes a proper .lnk in your Start menu, carrying the app's "
               "icon and the app identity Windows matches a pinned button "
               "against, and opens the folder so you can drag it to the "
               "taskbar.\n\nNothing can pin to the taskbar on your behalf: "
               "Windows removed that verb. And a .bat cannot be pinned "
               "usefully at all — Windows pins the shell rather than the "
               "app and the icon is the console's.\n\nAlready pinned the "
               "running window? Unpin it and pin this instead: a pin keeps "
               "whatever identity it was made with."),
    ),
    "fetch_assets": Task(
        key="fetch_assets",
        title="Download hero portraits and item icons",
        steps=[[PY, "tools/fetch_assets.py"]],
        blurb=("Fetches every hero portrait, every item icon and the "
               "community's alternative (persona, arcana, custom set) "
               "portraits, to THIS machine's disk.\n\nNeeds no API key "
               "and no account — the pictures come from OpenDota's public "
               "constants and Valve's CDN. The statistics are a separate "
               "job, because those do need a free Stratz key.\n\nThe app "
               "does not carry any of this artwork: it is Valve's, and a "
               "repository anybody can clone is not a place to hand out "
               "somebody else's pictures from. Downloading it to your own "
               "disk is a different thing, and it is what every install "
               "has always done. Update runs this too, so a new version "
               "never leaves you short of a picture.\n\nAlready have "
               "them? It skips what is on disk, so this only ever costs "
               "the files that are actually missing."),
        needs_network=True,
        reload_after=True,
    ),
    "fetch_custom_portraits": Task(
        key="fetch_custom_portraits",
        title="Fetch alternative hero portraits",
        steps=[[PY, "tools/fetch_custom_portraits.py"]],
        blurb=("Downloads the community's collection of persona, arcana and "
               "custom-set hero pictures and files them under the right "
               "hero, so a teammate on a set portrait stops reading as "
               "UNKNOWN.\n\nThey land in assets\\portraits\\variants "
               "under a folder named for the HERO'S NUMERIC ID, not its "
               "name — so that folder looks empty until you open one.\n\n"
               "To your disk only — they are Valve's artwork "
               "and the app does not carry them.\n\nTwo caveats: these are "
               "named \"icon\", and a hero icon may not be the same asset "
               "as the top-bar portrait; and the hero is read out of the "
               "filename. Neither could be checked where this was written, "
               "so read the output. The app also learns an unmatched "
               "portrait off your own screen while you play, which needs no "
               "download and is always the right picture."),
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
        steps=[[PY, "tools/update_app.py"],
               [PY, "-m", "pip", "install", "-q", "-r", "requirements.txt",
                "-r", "requirements-windows.txt"],
               ],
        blurb=("Gets the latest version of THIS app, refreshes its "
               "dependencies, and reopens. THE CODE AND NOTHING ELSE — "
               "it downloads no statistics and no artwork, so it takes "
               "seconds rather than minutes. Anything the app then finds "
               "missing is flagged in the strip at the top of the window, "
               "with a button that fetches it.\n\nIt works on both kinds of "
               "install. A git clone is updated with git, which keeps any "
               "edits you have made and re-applies them on top. A copy "
               "downloaded from GitHub — no git installed, no .git folder "
               "— downloads the release and writes the files out.\n\n"
               "YOUR OWN FILES ARE NEVER TOUCHED: the Stratz key in .env, "
               "your settings, your calibration, your remembered accounts, "
               "the statistics and every portrait you have downloaded are "
               "not part of what the app ships, so an update cannot land "
               "on top of them. You will never have to put your key back "
               "in.\n\nAlready on the newest version? It says so and "
               "stops. That is not an error."),
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
    "simulate_gsi": Task(
        key="simulate_gsi",
        title="Simulate a draft — full teams",
        steps=[[PY, "tools/simulate_gsi.py", "--with-draft", "--loop"]],
        blurb=("Pretends to be Dota and sends game data to this app, so the "
               "whole path — listener, parser, draft panel, overlay — can be "
               "exercised with the game closed. Watch the Draft tab: both "
               "teams fill in, then it loops. Close this dialog to stop.\n\n"
               "This sends BOTH line-ups, which real GSI probably does not "
               "do — it is the best way to see the app working, not a "
               "faithful picture of a live match. For that, use 'Simulate a "
               "draft — only your hero'."),
        cancellable=True,
        modeless=True,
    ),
    "simulate_gsi_real": Task(
        key="simulate_gsi_real",
        title="Simulate a draft — ONLY your hero (as real GSI)",
        steps=[[PY, "tools/simulate_gsi.py", "--loop"]],
        blurb=("EXPECT MOSTLY EMPTY SLOTS. This sends what a player's own "
               "GSI feed is believed to contain: your hero and the game "
               "state, and nothing about anyone else. You will see one hero "
               "in your team and no enemies, looping.\n\n"
               "That is the point — it shows the real limitation, and where "
               "you would click the enemy picks in by hand. To watch the "
               "app work with a full draft, use 'Simulate a draft — full "
               "teams' instead."),
        cancellable=True,
        modeless=True,
    ),
    "replay_gsi": Task(
        key="replay_gsi",
        title="Replay recorded game data",
        steps=[[PY, "tools/simulate_gsi.py", "--from", "{arg}"]],
        blurb=("Replays this recording's payloads exactly as Dota sent "
               "them. The highest-fidelity test available without "
               "launching the game: nothing is modelled, so it can find "
               "faults a simulated draft cannot."),
        cancellable=True,
        modeless=True,
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

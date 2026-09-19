"""Where an unhandled error goes when there is no console to print it to.

The app is started by `pythonw.exe`, which has NO console at all - so a
traceback printed to stderr goes nowhere and the only symptom is a
window that never appears. That is the same shape as the launcher fault
this folder was built for: the thing that would explain it exists for a
moment and is then gone.

TWO KINDS OF ENDING, AND ONLY ONE IS CATCHABLE.
  * A Python exception reaches `sys.excepthook`, and `save` writes it.
  * Qt ABORTS THE PROCESS on an unbounded layout, and CLAUDE.md keeps a
    list of the times it has - `_match_grid_portraits`, the team panel's
    size ratchet, `_apply_greyscale` rebuilding views before layout. No
    `except` anywhere can see one of those, and there is no traceback
    into our own code. `faulthandler` is the only thing that leaves a
    stack behind, and it has to be armed BEFORE the crash with a file
    already open, because by then the interpreter cannot allocate one.

SO THE HARD-CRASH FILE IS FILED ON THE NEXT RUN. faulthandler needs one
open file for the life of the process; a fatal signal writes into it and
nothing of ours runs afterwards. The next start finds it non-empty and
moves it into a dated folder - which is why a hard crash is reported one
launch late and a soft one immediately.

NOTHING HERE MAY IMPORT Qt: it is armed before the QApplication exists.
"""

import faulthandler
import time
import traceback
from pathlib import Path

from . import debugdir

# One open file, truncated each run. Empty is the normal state.
HARD = "hard-crash.txt"
_HELD = None                     # kept open deliberately; see above


def hard_crash_file() -> Path:
    return debugdir.folder("crashes") / HARD


def file_away_last_crash() -> Path | None:
    """Move a non-empty hard-crash file into its own dated folder.

    Returns where it went, or None when the last run ended cleanly -
    which is almost always, since faulthandler writes nothing unless the
    process is killed.
    """
    where = hard_crash_file()
    try:
        if not where.is_file() or where.stat().st_size == 0:
            return None
    except OSError:
        return None
    try:
        made = debugdir.new_run("crashes")
        where.rename(made / "faulthandler.txt")
        (made / "what-happened.txt").write_text(
            "The app was killed rather than raising - almost always Qt\n"
            "aborting on a layout that never settles. The stack in\n"
            "faulthandler.txt is from the run BEFORE this one.\n",
            encoding="utf-8")
        return made
    except OSError:
        return None


def arm() -> Path | None:
    """File away any previous hard crash and start watching for the next.

    NEVER FATAL. A read-only folder is a reason to lose the diagnostic,
    never a reason the app does not start.
    """
    global _HELD
    filed = file_away_last_crash()
    try:
        where = hard_crash_file()
        where.parent.mkdir(parents=True, exist_ok=True)
        _HELD = where.open("w", encoding="utf-8")
        faulthandler.enable(file=_HELD)
    except (OSError, ValueError, RuntimeError):
        _HELD = None
    return filed


def save(exc: BaseException, extra: str = "") -> Path | None:
    """Write one traceback into its own dated folder. Returns the file."""
    text = "".join(traceback.format_exception(type(exc), exc,
                                              exc.__traceback__))
    try:
        made = debugdir.new_run("crashes")
        target = made / "traceback.txt"
        head = f"Dota Draft Assist - {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        target.write_text(head + text + ("\n" + extra if extra else ""),
                          encoding="utf-8")
        return target
    except OSError:
        return None

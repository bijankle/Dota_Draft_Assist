"""One copy of this app at a time, and no dialog about it.

At the user's request: "i dont want to allow the user to open 2 instances
of the app... (no popup warning required just dont allwo it )".

WHY IT MATTERS HERE RATHER THAN BEING A NICETY. Two copies are not two
harmless windows: they both bind the GSI listener, so the second one
takes the port or fails to get it and then reports "no data from Dota"
about a feed the first one is happily reading; they both write
`ui_settings.json`, so whichever closes last wins and the other's
settings are lost; and both write into `recordings/`. The app is also
started from several places — the launcher, a Start-menu shortcut, a
taskbar pin, and its own Update — so a second one is easy to ask for by
accident.

**NO MESSAGE, AND THAT IS THE REQUEST.** A second launch simply does
nothing. The one thing it does do is ask the window manager to raise the
copy that is already running, because an app that appears to ignore a
double-click is indistinguishable from one that has crashed — and that
is a message in the only form this app is allowed to use here: the window
you asked for, in front of you.

**A LOCK FILE, NOT A NAMED MUTEX.** A mutex is Windows-only, and the one
thing this file must not do is behave differently on the machines the
tests run on. A file carrying the owner's PID is checkable everywhere:
stale after a crash (the PID is gone, so the lock is taken), held while
the process lives, and removed on a clean exit.

**AND A STALE LOCK MUST NEVER BLOCK A START.** The app crashing once
would otherwise mean it can never be opened again, which is far worse
than the two copies this prevents. So every failure here — an unreadable
file, an unwritable folder, a PID that cannot be checked — resolves to
"go ahead and run".
"""

import os
import sys
from pathlib import Path

from ..config import REPO_ROOT

LOCK_FILE = REPO_ROOT / "running.lock"


# Windows constants, spelled here so the ctypes call below reads.
_QUERY_LIMITED = 0x1000        # PROCESS_QUERY_LIMITED_INFORMATION
_STILL_ACTIVE = 259            # what GetExitCodeProcess says for a live one
_ERROR_ACCESS_DENIED = 5       # it exists and is not ours to look at


def _alive_windows(pid: int) -> bool:
    """Is this pid running? Asked WITHOUT the power to end it.

    **`os.kill(pid, 0)` IS NOT A LIVENESS CHECK ON WINDOWS, AND THIS
    MODULE USED IT AS ONE.** CPython maps `os.kill` to `OpenProcess`
    followed by `TerminateProcess` for every signal except the two
    console CTRL events — so signal 0 does not ask whether a process is
    alive, it asks Windows to end it with exit code 0. What actually
    decided the answer was how `OpenProcess(PROCESS_ALL_ACCESS)`
    happened to fail: access denied came back as PermissionError and was
    read as "alive", and any other failure came back as a plain OSError
    and was read as "gone" — which frees the lock and lets a second copy
    start. That is the two windows.
    So this asks the question the documented way. It opens the process
    for the WEAKEST right that can answer it, reads the exit code, and
    closes the handle; there is no path through it that can stop
    anything.

    THREE-VALUED UNDERNEATH, like `required` in the capture session: a
    process that exists but cannot be opened is somebody else's and the
    id IS in use, so it counts as alive; only "no such process" and a
    real exit code count as gone. A question we could not ask must never
    refuse to start the app, which is why everything unexpected falls
    through to False.
    """
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL,
                                     wintypes.DWORD)
    handle = kernel32.OpenProcess(_QUERY_LIMITED, False, pid)
    if not handle:
        err = ctypes.get_last_error()
        # It is there and shut to us — that id is in use. Anything else
        # (87, ERROR_INVALID_PARAMETER, is "no process has this id") is
        # gone, and so is a question we could not ask: see above.
        return err == _ERROR_ACCESS_DENIED
    try:
        code = wintypes.DWORD()
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE,
                                                ctypes.POINTER(wintypes.DWORD))
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == _STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _alive(pid: int) -> bool:
    """Is a process with this id running?

    POSIX answers with `os.kill(pid, 0)`, which really is a probe there.
    Windows needs its own question entirely — see `_alive_windows`.

    UNKNOWN COUNTS AS ALIVE only for a permission error: that is
    somebody else's process and the id is genuinely in use. Everything
    else is treated as gone, because refusing to start over a question
    we could not ask is the failure mode this module is least allowed to
    have.
    """
    if pid <= 0:
        return False
    if sys.platform.startswith("win"):
        try:
            return _alive_windows(pid)
        except Exception:      # noqa: BLE001 - never fatal, see above
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def holder(path: Path | None = None) -> int:
    """The PID in the lock file, or 0 when nothing holds it.

    The path is resolved at CALL time rather than bound as a default —
    the rule `load_layout` and `ui_settings.load` already follow, so a
    test that repoints `LOCK_FILE` is not writing into the repository.
    """
    where = Path(path) if path is not None else LOCK_FILE
    try:
        pid = int(where.read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        return 0
    return pid if _alive(pid) and pid != os.getpid() else 0


def claim(path: Path | None = None) -> bool:
    """Take the lock for this process. False when somebody else has it."""
    where = Path(path) if path is not None else LOCK_FILE
    if holder(where):
        return False
    try:
        where.parent.mkdir(parents=True, exist_ok=True)
        where.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        # Cannot write the lock — a read-only folder, a full disk. Let
        # the app start: the thing this prevents is a nuisance, and not
        # starting at all is not.
        return True
    return True


def release(path: Path | None = None) -> None:
    """Give it up, but only if it is still OURS.

    A crash-and-restart can leave the new process holding the file while
    the old one is still tearing down; deleting somebody else's lock on
    the way out would let a third copy in.
    """
    where = Path(path) if path is not None else LOCK_FILE
    try:
        if int(where.read_text(encoding="utf-8").strip() or 0) != os.getpid():
            return
        where.unlink()
    except (OSError, ValueError):
        pass


def raise_the_one_already_running() -> None:
    """Bring the copy that IS running to the front, if that can be done.

    The second launch shows no message — that was the request — but it
    must not simply vanish either: an app that appears to ignore a
    double-click is indistinguishable from one that has crashed. Putting
    the existing window in front IS the acknowledgement, in the only form
    allowed here.

    WINDOWS ONLY, and never fatal. It is pure ctypes against the window
    title, so there is nothing to import that is not already there and
    nothing that can raise out of here: the worst case is the second
    launch quietly doing nothing, which is what it was going to do
    anyway.
    """
    import sys
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        # `restype` is NOT optional: the default is a 32-bit int, so a
        # 64-bit HWND comes back TRUNCATED and every call after it acts
        # on nothing. The same trap `appicon` carries two notes about.
        user32.FindWindowW.restype = ctypes.c_void_p
        user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        window = user32.FindWindowW(None, "Dota Draft Assist")
        if not window:
            return
        user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        user32.ShowWindow(window, 9)          # SW_RESTORE
        user32.SetForegroundWindow(window)
    except Exception:       # noqa: BLE001 - a nuisance, never a failure
        pass

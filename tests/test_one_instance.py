"""One copy of this app at a time, and no dialog about it.

At the user's request: "i dont want to allow the user to open 2 instances
of the app... (no popup warning required just dont allwo it )".

Two copies are not two harmless windows: they both bind the GSI listener
and both write `ui_settings.json`, so the second reports "no data from
Dota" about a feed the first is reading, and whichever closes last wins
the settings.
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from draft_assist.ui import single              # noqa: E402


@pytest.fixture
def lock(tmp_path):
    return tmp_path / "running.lock"


def test_the_first_copy_takes_it_and_a_second_is_refused(lock):
    assert single.claim(lock) is True
    assert lock.read_text(encoding="utf-8").strip() == str(os.getpid())
    # A SECOND PROCESS is what the guard is about, so the check has to
    # be against somebody else's live id — our own must never lock us
    # out of our own claim.
    lock.write_text(str(_a_live_pid_that_is_not_ours()), encoding="utf-8")
    assert single.claim(lock) is False


def test_our_own_pid_never_blocks_us(lock):
    """The holder is only a holder if it is somebody ELSE. A process that
    re-checked its own lock and refused would be an app that cannot
    survive asking twice."""
    lock.write_text(str(os.getpid()), encoding="utf-8")
    assert single.holder(lock) == 0
    assert single.claim(lock) is True


def test_a_stale_lock_never_blocks_a_start(lock):
    """**THE FAILURE THIS MODULE IS LEAST ALLOWED TO HAVE.** Crashing
    once would otherwise mean the app can never be opened again, which is
    far worse than the two copies this prevents."""
    lock.write_text("999999999", encoding="utf-8")       # long gone
    assert single.holder(lock) == 0
    assert single.claim(lock) is True


@pytest.mark.parametrize("rubbish", ["", "   ", "not a pid", "-4", "0"])
def test_an_unreadable_lock_never_blocks_a_start(lock, rubbish):
    lock.write_text(rubbish, encoding="utf-8")
    assert single.holder(lock) == 0
    assert single.claim(lock) is True


def test_a_folder_that_cannot_be_written_never_blocks_a_start(tmp_path):
    """A read-only folder or a full disk costs the guard, not the app."""
    where = tmp_path / "nope" / "deep"
    where.mkdir(parents=True)
    where.chmod(0o500)
    try:
        assert single.claim(where / "running.lock") is True
    finally:
        where.chmod(0o700)


def test_releasing_only_drops_our_own(lock):
    single.claim(lock)
    assert lock.exists()
    single.release(lock)
    assert not lock.exists()

    # Somebody else's lock is left exactly where it is: a crash and
    # restart can leave the new process holding the file while the old
    # one is still tearing down, and deleting theirs would let a third in.
    other = str(_a_live_pid_that_is_not_ours())
    lock.write_text(other, encoding="utf-8")
    single.release(lock)
    assert lock.exists() and lock.read_text(encoding="utf-8") == other


def test_the_path_is_resolved_at_call_time(monkeypatch, tmp_path):
    """The rule `load_layout` and `ui_settings.load` already follow: a
    default argument is evaluated once at import, so a test that
    repointed the file would still write into the repository."""
    moved = tmp_path / "elsewhere.lock"
    monkeypatch.setattr(single, "LOCK_FILE", moved)
    assert single.claim() is True
    assert moved.exists()
    single.release()
    assert not moved.exists()


def test_raising_the_other_copy_is_never_fatal():
    """It is the only acknowledgement a second launch gets — no message
    was the request — and it must not be able to stop one either."""
    single.raise_the_one_already_running()


def _a_live_pid_that_is_not_ours() -> int:
    """A process id that certainly exists and is certainly not ours.

    PID 1 on Linux; on Windows `os.kill(1, 0)` answers for the System
    Idle Process, which is also always there. Either way it is not this
    interpreter, which is the whole point.
    """
    return 1


# ---- and the check itself ---------------------------------------------

def test_the_windows_check_never_asks_to_terminate_anything():
    """`os.kill(pid, 0)` IS NOT A LIVENESS CHECK ON WINDOWS, and this
    module used it as one — which is how two windows opened from the
    launcher.

    CPython maps `os.kill` to OpenProcess + TerminateProcess for every
    signal except the two console CTRL events, so signal 0 there does
    not ask whether a process is alive: it asks Windows to end it with
    exit code 0. What actually decided the answer was how
    `OpenProcess(PROCESS_ALL_ACCESS)` happened to fail — access denied
    arrived as PermissionError and read as "alive", anything else
    arrived as a plain OSError and read as "gone", which frees the lock
    and lets a second copy start.

    CHECKED IN THE SOURCE, because this machine is Linux and cannot run
    that branch at all — which is the whole reason it has to be a check
    with no power to stop anything even when it is wrong.
    """
    import ast
    import inspect

    # THE CODE, NOT THE PROSE ABOUT IT. This function's own docstring
    # names `TerminateProcess` to explain the trap, and a scan of the
    # raw source would fail on the explanation — the same reason
    # `test_no_stale_menu_trails` reads string literals rather than
    # whole files.
    tree = ast.parse(inspect.getsource(single._alive_windows).strip())
    fn = tree.body[0]
    if (fn.body and isinstance(fn.body[0], ast.Expr)
            and isinstance(fn.body[0].value, ast.Constant)):
        fn.body = fn.body[1:]           # drop the docstring
    body = ast.unparse(fn)
    assert "TerminateProcess" not in body, "it can still end a process"
    assert "os.kill" not in body
    # The WEAKEST right that can answer the question.
    assert "_QUERY_LIMITED" in body
    assert single._QUERY_LIMITED == 0x1000
    assert "GetExitCodeProcess" in body and "CloseHandle" in body
    # And `_alive` must route Windows to it rather than falling through
    # to the POSIX probe.
    route = inspect.getsource(single._alive)
    assert 'sys.platform.startswith("win")' in route
    assert "_alive_windows" in route


def test_a_pid_that_exists_but_is_shut_to_us_counts_as_alive():
    """Three-valued underneath, like `required` in the capture session:
    a pid we cannot open is somebody else's and IS in use, so the lock
    stays taken. Only "no such process" frees it."""
    import inspect

    assert single._ERROR_ACCESS_DENIED == 5
    assert single._STILL_ACTIVE == 259
    body = inspect.getsource(single._alive_windows)
    assert "return err == _ERROR_ACCESS_DENIED" in body, (
        "a pid that cannot be opened no longer counts as in use")


def test_our_own_pid_is_alive_and_a_made_up_one_is_not():
    """The POSIX branch, which this machine can actually run."""
    import os

    assert single._alive(os.getpid()) is True
    assert single._alive(4_000_000) is False
    assert single._alive(0) is False


# ---- and a second launch focuses the first ----------------------------

def test_a_second_launch_raises_the_window_rather_than_doing_nothing():
    """"if the user tries to open a second version of the app it should
    just focus on the window of the app that is already open."

    No message — that was the earlier request and it stands. But a
    launcher that appears to ignore a double-click is indistinguishable
    from one that has crashed, so the raise IS the acknowledgement, and
    `_main` has to reach it on the one path where the claim fails.
    """
    import ast
    import inspect

    from draft_assist.ui import app as ui_app

    body = inspect.getsource(ui_app._main)
    tree = ast.parse(body.strip())
    called = {ast.unparse(node.func) for node in ast.walk(tree)
              if isinstance(node, ast.Call)}
    assert "single.claim" in called, "nothing takes the lock"
    assert "single.raise_the_one_already_running" in called, (
        "a refused second launch does nothing at all")
    # And it STOPS there: a second copy that went on to build a window
    # is the thing the lock exists to prevent.
    refused = [node for node in ast.walk(tree)
               if isinstance(node, ast.If)
               and "single.claim" in ast.unparse(node.test)]
    assert refused, "the claim is not what decides"
    assert any(isinstance(step, ast.Return) for step in refused[0].body), (
        "the second copy carries on after being refused")


def test_it_searches_for_the_title_the_window_actually_has():
    """`FindWindowW` is an EXACT title match, so the name the window is
    GIVEN and the name the raise LOOKS FOR are one constant.

    Spelled twice, a rename reaches one of them, the search finds
    nothing, and the second launch quietly does nothing — which is
    precisely the failure the raise exists to prevent, wearing the
    appearance of the bug it fixed.
    """
    import inspect

    from draft_assist.config import APP_NAME
    from draft_assist.ui import app as ui_app, appicon

    assert "FindWindowW(None, APP_NAME)" in inspect.getsource(
        single.raise_the_one_already_running), "it searches for a literal"
    # The window takes its title from the same place...
    assert "self.setWindowTitle(APP_NAME)" in inspect.getsource(
        ui_app.MainWindow.__init__)
    # ...and so does everything else that names this app to Windows.
    assert appicon.APP_NAME == appicon.SHORTCUT_NAME == APP_NAME


def test_it_restores_only_a_MINIMISED_window():
    """`SW_RESTORE` on a MAXIMISED window un-maximises it.

    So the unconditional call this used to make would have shrunk a
    full-screen app as the price of focusing it — a second launch
    REARRANGING the first copy is worse than one that does nothing.
    `IsIconic` separates the case the restore is for from the case it
    damages.
    """
    import inspect

    body = inspect.getsource(single.raise_the_one_already_running)
    assert "if user32.IsIconic(window):" in body, (
        "it restores unconditionally and will un-maximise the window")
    assert single._SW_RESTORE == 9
    # BringWindowToTop goes with SetForegroundWindow, which Windows
    # refuses to a process without the foreground right: the pair is
    # what makes a refusal degrade to "raised but not focused".
    assert "BringWindowToTop(window)" in body
    assert "SetForegroundWindow(window)" in body


def test_the_raise_says_whether_it_found_anything():
    """It answered None, so "no window by that name" and "brought it to
    the front" were the same result — and this module's own rule is that
    doing nothing silently is indistinguishable from being broken.

    Off Windows there is nothing to find, which is the branch the test
    machines take.
    """
    assert single.raise_the_one_already_running() is False

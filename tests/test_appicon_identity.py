"""The pieces a Windows pin is built from.

The pin itself cannot be tested here — there is no shell — but everything
it reads can be: the command it would run, the .ico it would draw, and the
fact that asking for the identity on a machine that is not Windows says no
rather than raising.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication                    # noqa: E402

from draft_assist.config import REPO_ROOT                   # noqa: E402
from draft_assist.ui import appicon                         # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def test_relaunch_command_quotes_both_halves():
    command = appicon.relaunch_command()
    # A path with a space in it — "Dota Draft Assist" is one — splits into
    # two arguments unquoted, and the pin then launches nothing.
    assert command.count('"') == 4
    assert command.endswith('__main__.py"')


def test_relaunch_target_exists_and_needs_no_working_directory():
    """The whole reason __main__.py exists: a pin has no working directory.

    Run it from somewhere else entirely with the repository NOT on
    PYTHONPATH. It must get as far as importing the app — which needs Qt,
    so the check is that the import itself was not what failed.
    """
    target = REPO_ROOT / "draft_assist" / "__main__.py"
    assert target.exists()
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["QT_QPA_PLATFORM"] = "offscreen"
    done = subprocess.run(
        [sys.executable, "-c",
         # run_name keeps main() from firing: this is about the import.
         f"import runpy; runpy.run_path({str(target)!r}, run_name='probe')"],
        cwd=Path(target.anchor), capture_output=True, text=True, timeout=300,
        env=env)
    assert "No module named 'draft_assist'" not in done.stderr, done.stderr


def test_shell_ico_is_a_multi_size_icon(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    path = appicon.shell_ico()
    assert path is not None and path.exists()
    head = path.read_bytes()[:6]
    assert head[:4] == b"\x00\x00\x01\x00"          # an icon, not a cursor
    assert int.from_bytes(head[4:6], "little") == len(appicon.ICO_SIZES)


def test_a_supplied_ico_is_used_as_it_is(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    supplied = tmp_path / "app.ico"
    supplied.write_bytes(b"\x00\x00\x01\x00\x00\x00")
    assert appicon.shell_ico() == supplied


@pytest.mark.skipif(sys.platform == "win32", reason="this IS the Windows path")
def test_claiming_the_window_identity_is_a_no_op_off_windows():
    assert appicon.claim_window_identity(12345) is False


def test_no_handle_is_never_an_attempt():
    """A window with no native handle yet answers 0, and 0 is not an hwnd."""
    assert appicon.claim_window_identity(0) is False


def test_a_failure_says_which_half_failed():
    """A silent False leaves a pin that still shows Python undiagnosable.

    The note goes into Debug ▸ Copy everything, so whatever went wrong
    arrives with the rest of the report rather than needing another round
    trip to find out.
    """
    appicon.claim_window_identity(0)
    assert appicon.identity_note == "no window handle"
    appicon.claim_window_identity(12345)
    assert appicon.identity_note != "no window handle"


# ---------------------------------------------- the shipped default ----

def test_the_shipped_default_is_used_when_the_user_has_no_icon(
        qapp, tmp_path, monkeypatch):
    """A committed icon reaches every install, so a fresh download opens
    with the app's real icon rather than the drawn fallback."""
    from PyQt6.QtGui import QPixmap
    from draft_assist.ui import appicon

    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    appicon.forget()
    assert appicon.source() == "drawn"

    art = QPixmap(64, 64)
    art.fill()
    art.save(str(tmp_path / "app-default.png"))
    appicon.forget()
    assert appicon.default_path() == tmp_path / "app-default.png"
    assert appicon.source() == "default"
    assert not appicon.icon().isNull()
    appicon.forget()


def test_the_users_own_icon_still_beats_the_shipped_one(qapp, tmp_path,
                                                        monkeypatch):
    """THE TWO NAMES ARE THE WHOLE POINT. Setup ▸ Choose app icon… writes
    `app.ico`; if the shipped default used that name too, every update
    would overwrite a choice somebody made on their own machine."""
    from PyQt6.QtGui import QPixmap
    from draft_assist.ui import appicon

    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    art = QPixmap(64, 64)
    art.fill()
    art.save(str(tmp_path / "app-default.png"))
    art.save(str(tmp_path / "app.png"))
    appicon.forget()
    assert appicon.source() == "assets"
    assert appicon.supplied_path() == tmp_path / "app.png"
    appicon.forget()


def test_the_shipped_name_is_not_gitignored():
    """The user's own icon is gitignored on purpose; the shipped one must
    NOT be, or committing it would silently do nothing."""
    import subprocess
    for name in ("assets/app-default.ico", "assets/app-default.png"):
        done = subprocess.run(["git", "check-ignore", name],
                              capture_output=True, text=True)
        assert done.returncode != 0, f"{name} is gitignored"
    # And the user's own still is, so an update cannot land on it.
    done = subprocess.run(["git", "check-ignore", "assets/app.ico"],
                          capture_output=True, text=True)
    assert done.returncode == 0, "the user's own icon must stay ignored"

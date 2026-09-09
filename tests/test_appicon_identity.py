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
    """A REAL one, carrying at least one image. A header claiming zero
    images is not a usable icon — the shell would draw nothing from it —
    so `is_ico` refuses it and one gets generated instead."""
    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    appicon.forget()
    supplied = appicon.write_ico(tmp_path / "app.ico")
    appicon.forget()
    assert appicon.is_ico(supplied)
    assert appicon.shell_ico() == supplied

    empty = tmp_path / "app.ico"
    empty.write_bytes(b"\x00\x00\x01\x00\x00\x00")   # zero images
    assert not appicon.is_ico(empty)
    assert appicon.shell_ico().name == "app-generated.ico"
    appicon.forget()


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


def test_a_big_png_is_downsampled_at_every_size_the_shell_asks_for(
        qapp, tmp_path, monkeypatch):
    """The normal source file is one big square — 1024x1024 — and a QIcon
    carrying a single pixmap is exactly how a taskbar button comes out
    blurry: Windows asks for 16, 32, 48 and 256, finds only the one, and
    scales it itself. The drawn and portrait sources were already built at
    every size; a supplied file must be too."""
    from PyQt6.QtGui import QPixmap
    from draft_assist.ui import appicon

    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    big = QPixmap(1024, 1024)
    big.fill()
    big.save(str(tmp_path / "app-default.png"))
    appicon.forget()

    baked = {size.width() for size in appicon.icon().availableSizes()}
    assert set(appicon.SIZES) <= baked, (
        f"missing {sorted(set(appicon.SIZES) - baked)} — the shell would "
        "scale one pixmap itself")
    # And each one really is that size, not the 1024 handed back.
    for size in (16, 32, 48):
        assert appicon.pixmap(size).width() == size
    appicon.forget()


def test_a_real_ico_is_used_exactly_as_supplied(qapp, tmp_path,
                                                monkeypatch):
    """It already carries every size, drawn or hinted for each, so
    rebuilding it from one of them would throw that work away."""
    from PyQt6.QtGui import QPixmap
    from draft_assist.ui import appicon

    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    art = QPixmap(256, 256)
    art.fill()
    appicon.forget()
    written = appicon.write_ico(tmp_path / "app-default.ico")
    assert written.exists()

    appicon.forget()
    assert appicon.default_path() == tmp_path / "app-default.ico"
    assert not appicon.icon().isNull()
    # A shipped .ico is what the shortcut and the taskbar pin point at.
    assert appicon.shell_ico() == tmp_path / "app-default.ico"
    appicon.forget()


def test_a_png_renamed_to_ico_is_not_treated_as_one(qapp, tmp_path,
                                                    monkeypatch):
    """THE TITLE BAR WORKED AND THE TASKBAR DID NOT, which is the whole
    signature of this. Qt sniffs an image's content and ignores its
    extension, so a PNG renamed to .ico loads fine and the window looks
    right — but the Windows shell needs a genuine ICO container for a
    taskbar button, a pin and a shortcut, and quietly draws something else
    when it does not get one."""
    import struct
    from PyQt6.QtGui import QPixmap
    from draft_assist.ui import appicon

    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    art = QPixmap(1024, 1024)
    art.fill()
    fake = tmp_path / "app-default.ico"
    art.save(str(fake), "PNG")                  # named .ico, is a PNG
    appicon.forget()

    assert not appicon.is_ico(fake)
    # It is still USED — the picture is fine, it is the container that is
    # wrong — but rebuilt at every size rather than passed through whole.
    baked = {size.width() for size in appicon.icon().availableSizes()}
    assert set(appicon.SIZES) <= baked

    # And the shell is handed a real one, generated from it.
    shell = appicon.shell_ico()
    assert shell.name == "app-generated.ico"
    assert appicon.is_ico(shell)
    assert struct.unpack("<HHH", shell.read_bytes()[:6])[2] == len(
        appicon.ICO_SIZES)
    appicon.forget()


def test_is_ico_reads_the_header_rather_than_the_name(qapp, tmp_path):
    from PyQt6.QtGui import QPixmap
    from draft_assist.ui import appicon

    art = QPixmap(32, 32)
    art.fill()
    appicon.forget()
    real = appicon.write_ico(tmp_path / "no-extension-at-all")
    assert appicon.is_ico(real), "a real ICO, whatever it is called"

    art.save(str(tmp_path / "actually.png"), "PNG")
    assert not appicon.is_ico(tmp_path / "actually.png")
    assert not appicon.is_ico(tmp_path / "does-not-exist.ico")
    (tmp_path / "empty.ico").write_bytes(b"")
    assert not appicon.is_ico(tmp_path / "empty.ico")
    appicon.forget()


def test_an_ico_holding_one_small_image_is_rebuilt_not_passed_through(
        qapp, tmp_path, monkeypatch):
    """A REAL .ico can hold as few as one image. A single 32x32 satisfies
    the header check and is enough for a title bar, and leaves a taskbar
    button — which asks for 40, 48 and 256 depending on the display's
    scaling — nothing to draw from. Title bar right, taskbar wrong, again,
    for a completely different reason from a renamed PNG."""
    import struct
    from PyQt6.QtGui import QPixmap
    from draft_assist.ui import appicon

    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    art = QPixmap(32, 32)
    art.fill()
    appicon.forget()
    monkeypatch.setattr(appicon, "ICO_SIZES", (32,))     # one image only
    thin = appicon.write_ico(tmp_path / "app-default.ico")
    monkeypatch.setattr(appicon, "ICO_SIZES", (16, 32, 48, 64, 128, 256))
    appicon.forget()

    assert appicon.is_ico(thin), "it is a genuine icon file"
    assert appicon.ico_sizes(thin) == {32}
    assert not appicon.covers_the_shell(thin), "one 32 is not enough"

    baked = {size.width() for size in appicon.icon().availableSizes()}
    assert set(appicon.SIZES) <= baked, "rebuilt around its biggest image"

    shell = appicon.shell_ico()
    assert shell.name == "app-generated.ico"
    assert appicon.ico_sizes(shell) == set(appicon.ICO_SIZES)
    appicon.forget()


def test_a_full_ico_is_still_handed_over_untouched(qapp, tmp_path,
                                                   monkeypatch):
    """One that carries the big sizes was drawn or hinted for each of
    them, and rebuilding from one would throw that work away."""
    from PyQt6.QtGui import QPixmap
    from draft_assist.ui import appicon

    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    art = QPixmap(256, 256)
    art.fill()
    appicon.forget()
    full = appicon.write_ico(tmp_path / "app-default.ico")
    appicon.forget()

    assert appicon.covers_the_shell(full)
    assert max(appicon.ico_sizes(full)) >= appicon.PASS_THROUGH_MIN
    assert appicon.shell_ico() == full
    appicon.forget()


def test_ico_sizes_refuses_what_is_not_a_directory_of_images(tmp_path):
    from draft_assist.ui import appicon
    assert appicon.ico_sizes(tmp_path / "missing.ico") == set()
    (tmp_path / "short.ico").write_bytes(b"\x00\x00\x01\x00")
    assert appicon.ico_sizes(tmp_path / "short.ico") == set()
    # Claims two images and carries no directory for them.
    (tmp_path / "lying.ico").write_bytes(b"\x00\x00\x01\x00\x02\x00")
    assert appicon.ico_sizes(tmp_path / "lying.ico") == set()

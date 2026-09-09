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


def test_the_bigger_picture_wins_rather_than_the_first_extension(
        qapp, tmp_path, monkeypatch):
    """THE THIRD CAUSE of "title bar right, taskbar wrong", and the one
    that looked like nothing had changed at all.

    `DEFAULT_CANDIDATES` named the .ico first, and `default_path` returned
    the first name that existed — so a 1024x1024 PNG dropped in beside an
    .ico holding a single 32x32 was never opened. The advice that produced
    that state was "supply the PNG and let the app render the .ico
    itself", and following it made no difference whatsoever, with the
    ignored file sitting right there in the folder.
    """
    from PyQt6.QtGui import QPixmap
    from draft_assist.ui import appicon

    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    appicon.forget()
    monkeypatch.setattr(appicon, "ICO_SIZES", (32,))
    appicon.write_ico(tmp_path / "app-default.ico")
    monkeypatch.setattr(appicon, "ICO_SIZES", (16, 32, 48, 64, 128, 256))
    appicon.forget()
    big = QPixmap(1024, 1024)
    big.fill()
    assert big.save(str(tmp_path / "app-default.png"), "PNG")

    assert appicon.default_path().name == "app-default.png"
    assert appicon.chosen_path().name == "app-default.png"
    # And the .ico the shell is handed is rendered from the PNG, not from
    # the 32 — which is the whole point of choosing the right file.
    shell = appicon.shell_ico()
    assert shell.name == "app-generated.ico"
    assert appicon.ico_sizes(shell) == set(appicon.ICO_SIZES)
    appicon.forget()


def test_a_thirty_two_pixel_icon_on_its_own_is_still_used(
        qapp, tmp_path, monkeypatch):
    """Asked for outright: "please allow for 32 x 32 icons, and keep the
    icon that i put in that assets folder". Ranking by size must not turn
    into refusing the small one — with nothing better present it is what
    the app has, and it is what the app draws."""
    from draft_assist.ui import appicon

    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    appicon.forget()
    monkeypatch.setattr(appicon, "ICO_SIZES", (32,))
    thin = appicon.write_ico(tmp_path / "app-default.ico")
    monkeypatch.setattr(appicon, "ICO_SIZES", (16, 32, 48, 64, 128, 256))
    appicon.forget()

    assert appicon.chosen_path() == thin
    assert appicon.source() == "default"
    baked = {size.width() for size in appicon.icon().availableSizes()}
    assert set(appicon.SIZES) <= baked
    appicon.forget()


def test_a_tie_goes_to_the_real_ico(qapp, tmp_path, monkeypatch):
    """Same size in both, so nothing distinguishes them on content — and
    the .ico can be handed to the shell untouched while the PNG has to be
    re-encoded into one."""
    from PyQt6.QtGui import QPixmap
    from draft_assist.ui import appicon

    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    appicon.forget()
    full = appicon.write_ico(tmp_path / "app-default.ico")   # up to 256
    art = QPixmap(256, 256)
    art.fill()
    assert art.save(str(tmp_path / "app-default.png"), "PNG")

    assert appicon.default_path() == full
    assert appicon.shell_ico() == full, "no need to render one"
    appicon.forget()


def test_a_file_that_holds_no_picture_is_passed_over(qapp, tmp_path,
                                                     monkeypatch):
    """`biggest_image` doubles as the readability test, so a truncated or
    corrupt file can never win over one that actually has something in
    it — nor leave the app on the drawn fallback while a good file sits
    beside it."""
    from PyQt6.QtGui import QPixmap
    from draft_assist.ui import appicon

    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    appicon.forget()
    (tmp_path / "app-default.ico").write_bytes(b"not an icon at all")
    assert appicon.biggest_image(tmp_path / "app-default.ico") == 0
    art = QPixmap(512, 512)
    art.fill()
    assert art.save(str(tmp_path / "app-default.png"), "PNG")

    assert appicon.chosen_path().name == "app-default.png"
    assert appicon.biggest_image(tmp_path / "app-default.png") == 512
    appicon.forget()


def test_the_window_and_the_pin_are_built_from_the_same_file(
        qapp, tmp_path, monkeypatch):
    """`shell_ico` used to carry its own hard-coded pair of filenames, so
    it could hand the shell a file the window's icon was not built from —
    the pin and the title bar drawing two different pictures, which is
    worse than either being wrong."""
    from PyQt6.QtGui import QPixmap
    from draft_assist.ui import appicon

    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    appicon.forget()
    # The user's own choice is a PNG; the shipped default is a full .ico.
    # The user's must win BOTH questions, not one each.
    appicon.write_ico(tmp_path / "app-default.ico")
    art = QPixmap(512, 512)
    art.fill()
    assert art.save(str(tmp_path / "app.png"), "PNG")

    assert appicon.chosen_path().name == "app.png"
    assert appicon.source() == "assets"
    assert appicon.shell_ico().name == "app-generated.ico", \
        "the shipped .ico is not the picture the window is showing"
    appicon.forget()


def test_describe_names_the_file_and_what_is_in_it(qapp, tmp_path,
                                                   monkeypatch):
    """None of the three causes of a wrong taskbar icon is visible in the
    picture, and all three are obvious in this one line — so it goes in
    the paste, where a report can carry it."""
    from draft_assist.ui import appicon

    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    appicon.forget()
    assert "no icon file" in appicon.describe()

    monkeypatch.setattr(appicon, "ICO_SIZES", (32,))
    appicon.write_ico(tmp_path / "app-default.ico")
    monkeypatch.setattr(appicon, "ICO_SIZES", (16, 32, 48, 64, 128, 256))
    appicon.forget()
    said = appicon.describe()
    assert "app-default.ico" in said and "[32]" in said
    assert "rebuilt" in said, "it says the small one is not handed over"
    appicon.forget()


def test_the_shell_sizes_are_dibs_and_only_256_is_a_png(qapp, tmp_path,
                                                        monkeypatch):
    """THE FOURTH CAUSE, and the one that survived fixing the other three.

    Every entry used to be PNG-compressed, on the strength of "every
    Windows since Vista reads PNG icons". What Vista added was PNG at
    **256**, for the extra-large view. The shell's older icon paths — the
    ones that draw a taskbar button, a pin and a shortcut, at 16, 32 and
    48 — expect the original DIB layout and draw nothing when handed a
    PNG at those sizes. Qt reads either, which is why the window's own
    icon was perfect throughout and only the shell's copy was wrong: the
    exact signature this app has now produced four separate times.
    """
    import struct
    from draft_assist.ui import appicon

    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    appicon.forget()
    written = appicon.write_ico(tmp_path / "probe.ico")
    raw = written.read_bytes()
    count = struct.unpack("<HHH", raw[:6])[2]
    assert count == len(appicon.ICO_SIZES)

    seen = {}
    for index in range(count):
        entry = raw[6 + index * 16:22 + index * 16]
        width, _, _, _, _, _, nbytes, offset = struct.unpack("<BBBBHHII",
                                                            entry)
        blob = raw[offset:offset + nbytes]
        seen[width or 256] = blob[:8] == b"\x89PNG\r\n\x1a\n"

    for size, is_png in seen.items():
        if size >= appicon.PNG_ENTRY_MIN:
            assert is_png, f"{size} should stay PNG"
        else:
            assert not is_png, (
                f"{size} is a PNG entry; the shell draws nothing from one")
    # The sizes the taskbar actually asks for are the ones that matter.
    for asked in (16, 32, 48):
        assert seen.get(asked) is False, f"{asked} must be a DIB"
    appicon.forget()


def test_every_dib_entry_describes_its_own_payload(qapp, tmp_path,
                                                   monkeypatch):
    """A DIB inside an .ico has three traps and all three are silent: the
    header's HEIGHT IS DOUBLED (it counts the colour bitmap and the mask
    as one image), the mask's rows are padded to four bytes, and the byte
    count in the directory has to cover all of it. Get any of them wrong
    and the file parses far enough to look fine."""
    import struct
    from draft_assist.ui import appicon

    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    appicon.forget()
    raw = appicon.write_ico(tmp_path / "probe.ico").read_bytes()
    count = struct.unpack("<HHH", raw[:6])[2]
    checked = 0
    for index in range(count):
        entry = raw[6 + index * 16:22 + index * 16]
        _, _, _, _, _, _, nbytes, offset = struct.unpack("<BBBBHHII", entry)
        blob = raw[offset:offset + nbytes]
        if blob[:8] == b"\x89PNG\r\n\x1a\n":
            continue
        (hsize, width, height, planes, bits, compression,
         _, _, _, _, _) = struct.unpack("<IiiHHIIiiII", blob[:40])
        assert hsize == 40, "a BITMAPINFOHEADER is 40 bytes"
        assert height == 2 * width, "the height is doubled for the mask"
        assert planes == 1 and bits == 32 and compression == 0
        mask_stride = ((width + 31) // 32) * 4
        assert nbytes == 40 + width * width * 4 + mask_stride * width, (
            "the directory's byte count does not cover header + pixels + mask")
        checked += 1
    assert checked >= 3, "there should be several DIB entries to check"
    appicon.forget()


def test_the_written_ico_still_reads_back_upright_and_unchanged(
        qapp, tmp_path, monkeypatch):
    """A DIB is stored BOTTOM-UP, so writing one is the obvious place to
    ship an upside-down icon — and nothing about a wolf's face at 16
    pixels makes that leap out of a screenshot. Read every entry back and
    compare it against what the app draws."""
    from draft_assist.ui import appicon
    from PyQt6.QtGui import QIcon

    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    appicon.forget()
    written = appicon.write_ico(tmp_path / "probe.ico")
    back = QIcon(str(written))
    assert {s.width() for s in back.availableSizes()} == set(appicon.ICO_SIZES)

    for size in (16, 32, 48):
        source = appicon.pixmap(size).toImage()
        got = back.pixmap(size, size).toImage()
        upright = flipped = 0
        for y in range(size):
            for x in range(size):
                here = got.pixelColor(x, y)
                same = source.pixelColor(x, y)
                other = source.pixelColor(x, size - 1 - y)
                if abs(same.red() - here.red()) > 6:
                    upright += 1
                if abs(other.red() - here.red()) > 6:
                    flipped += 1
        assert upright == 0, f"{size}px does not match what the app draws"
        # And it is not accidentally symmetric, or the check above proves
        # nothing about the row order.
        assert flipped > size, f"{size}px is too symmetric to test with"
    appicon.forget()


def test_the_identity_note_says_whether_the_shell_got_an_icon(
        qapp, tmp_path, monkeypatch):
    """It used to read the same either way. A report saying "set on hwnd
    ..." was consistent both with the shell having been handed a picture
    and with it having been handed none, which is the one question the
    note exists to answer — and the one it could not."""
    from draft_assist.ui import appicon

    got = appicon._identity_summary(4242, '"py.exe" "main.py"',
                                    tmp_path / "app-generated.ico")
    assert "4242" in got and "app-generated.ico" in got

    missing = appicon._identity_summary(4242, '"py.exe" "main.py"', None)
    assert "NO ICON FILE" in missing
    assert missing != got, "the two outcomes must not read the same"


def test_the_shell_is_actually_handed_an_icon_on_a_normal_install(
        qapp, tmp_path, monkeypatch):
    """The branch above only matters because it can go the other way.
    With the shipped default present — the ordinary case — a file must
    come back, or the pin has nothing to draw."""
    from PyQt6.QtGui import QPixmap
    from draft_assist.ui import appicon

    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    appicon.forget()
    art = QPixmap(1024, 1024)
    art.fill()
    assert art.save(str(tmp_path / "app-default.png"), "PNG")
    handed = appicon.shell_ico()
    assert handed is not None and handed.exists()
    assert appicon.is_ico(handed)
    appicon.forget()


def test_pushing_the_native_icon_is_a_no_op_off_windows(qapp):
    """Same rule as the identity: it says no rather than raising, and the
    note says which half stopped it."""
    from draft_assist.ui import appicon

    assert appicon.push_native_icon(0) is False
    assert appicon.window_icon_note == "no window handle"
    assert appicon.push_native_icon(1234) is False
    assert appicon.window_icon_note == "not Windows"


def test_the_window_icon_is_reapplied_after_the_frameless_flags(qapp):
    """THE ORDERING IS THE BUG. `setWindowIcon` ran at the top of
    `__init__` and `setWindowFlags(FramelessWindowHint | ...)` five lines
    later — and changing a window's flags on Windows DESTROYS AND
    RECREATES the native handle, so the icon was pushed at an HWND that
    no longer existed. The taskbar draws a running window's button from
    the window's own Win32 icon, not from any relaunch property, so it
    fell back to pythonw.exe while our painted title bar — which reads
    `appicon.pixmap` directly — looked right the whole time.

    Read the source: the effect needs a real Windows handle, but the
    ORDER is the thing that was wrong and it is checkable anywhere.
    """
    import inspect
    from draft_assist.ui.app import MainWindow

    source = inspect.getsource(MainWindow.__init__)
    flags = source.index("setWindowFlags")
    after = source.rindex("setWindowIcon")
    assert after > flags, (
        "the window icon must be applied AFTER setWindowFlags, which "
        "recreates the native window and drops it")
    assert source.rindex("push_native_icon") > flags


def test_choosing_a_new_icon_reaches_the_window_as_well_as_the_files(qapp):
    """A newly chosen icon has to reach all of it: the QIcon, the shell's
    .ico, the relaunch properties AND the window's own Win32 icon. The
    last one was the half nobody was setting."""
    import inspect
    from draft_assist.ui.app import MainWindow

    source = inspect.getsource(MainWindow._apply_app_icon)
    for call in ("setWindowIcon", "claim_window_identity",
                 "push_native_icon"):
        assert call in source, call


def test_the_paste_reports_both_taskbar_mechanisms(qapp):
    """They fail independently and for different reasons — one is a
    property store, the other a window message — so a report naming only
    one cannot say which is at fault. Four rounds of this were spent on
    diagnostics that could not tell two outcomes apart."""
    import inspect
    from draft_assist.ui.app import MainWindow

    source = inspect.getsource(MainWindow._copy_debug_log)
    assert "identity_note" in source
    assert "window_icon_note" in source


def test_the_start_menu_shortcut_is_written_automatically(qapp):
    """AT THE USER'S REQUEST — "it should be all auto anyway" — and
    because an AppUserModelID without one is worse than never setting one.

    Declaring an ID stops Windows treating the process as pythonw.exe and
    makes it its own application; the shell then resolves that
    application's icon and name through the Start-menu shortcut carrying
    the same string. With no such shortcut there is nothing to resolve
    to, which is why the button drew as a BLANK PAGE rather than as
    Python's logo — it had stopped being Python and had not become
    anything.
    """
    import inspect
    from draft_assist.ui import app as app_mod
    from draft_assist.ui import appicon

    # It happens on startup without being asked for. WHERE is settled by
    # `test_only_the_ctypes_half_runs_before_the_qapplication`: it renders
    # an .ico, so it cannot sit beside `claim_taskbar_identity` in `main`.
    assert "claim_taskbar_identity" in inspect.getsource(app_mod.main)
    assert "ensure_start_menu_shortcut" in inspect.getsource(app_mod._main), (
        "claiming the identity without providing the shortcut it resolves "
        "to is what left the taskbar button with nothing to draw")
    assert appicon.ensure_start_menu_shortcut() is False   # not Windows here
    assert appicon.shortcut_note == "not Windows"


def test_one_writer_for_the_shortcut(qapp):
    """The menu item and the automatic call must not be able to produce
    two different shortcuts for one AppUserModelID. Two lists that can
    disagree is what made `shell_ico` and `_build` pick different files,
    and it is the same failure shape."""
    import inspect
    import tools.make_shortcut as tool
    from draft_assist.ui import appicon

    assert hasattr(appicon, "write_shortcut")
    source = inspect.getsource(tool.main)
    assert "appicon.write_shortcut()" in source
    assert "CoCreateInstance" not in source, \
        "the tool must not build its own link"
    # And one spelling of the name, for the reason the font family has one.
    assert not hasattr(tool, "NAME"), \
        "two spellings of one shortcut name is a shortcut that silently " \
        "becomes two files"


def test_the_shortcut_is_rewritten_rather_than_only_created(qapp):
    """The thing it points at MOVES. This app is normally run from a
    folder somebody unzipped, and downloading a newer ZIP produces a
    second folder beside the first — a shortcut left pointing at the old
    one is worse than none."""
    import inspect
    from draft_assist.ui import appicon

    source = inspect.getsource(appicon.ensure_start_menu_shortcut)
    assert "exists()" not in source, \
        "it must not skip the write just because a file is there"
    # Once per process, though: it is a disk write, not a per-tick cost.
    assert "_shortcut_done" in source


def test_the_paste_reports_all_three_taskbar_mechanisms(qapp):
    """The identity, the window's own icon, and the shortcut the identity
    resolves to. They fail independently, and five rounds of this went on
    diagnostics that could not say which one was at fault."""
    import inspect
    from draft_assist.ui.app import MainWindow

    source = inspect.getsource(MainWindow._copy_debug_log)
    for note in ("identity_note", "window_icon_note", "shortcut_note"):
        assert note in source, note


def test_nothing_that_paints_runs_before_the_qapplication(qapp):
    """**THIS ONE STOPPED THE APP OPENING AT ALL.**

    `ensure_start_menu_shortcut` was called from `main()` before the
    QApplication was built, and it reaches a QPixmap through `shell_ico`
    -> `write_ico` -> `pixmap`. Qt does not raise for that: it prints
    "QPixmap: Must construct a QGuiApplication before a QPixmap" and
    ABORTS, so no `except` can catch it and there is no traceback. From
    outside it is simply an app that does not open.

    Run every painting entry point in a subprocess with no QApplication.
    The subprocess must SURVIVE — an abort would take it down before it
    could print anything.
    """
    import subprocess
    import sys

    from draft_assist.config import REPO_ROOT

    probe = """
import sys
sys.path.insert(0, %r)
from draft_assist.ui import appicon
assert appicon.gui_ready() is False
assert appicon.shell_ico() is None
for call in (appicon.icon, lambda: appicon.write_ico("ignored.ico")):
    try:
        call()
    except RuntimeError:
        pass
    else:
        raise SystemExit("it should refuse, not return")
print("SURVIVED")
""" % str(REPO_ROOT)
    done = subprocess.run([sys.executable, "-c", probe],
                          capture_output=True, text=True, timeout=300,
                          env={"QT_QPA_PLATFORM": "offscreen", "PATH": "/usr/bin:/bin"})
    assert "SURVIVED" in done.stdout, (
        f"the process died instead of refusing.\n"
        f"stdout: {done.stdout}\nstderr: {done.stderr}")


def test_only_the_ctypes_half_runs_before_the_qapplication(qapp):
    """`claim_taskbar_identity` is pure ctypes and MUST run before the
    first window, so it stays in `main()`. Everything else about the icon
    has to wait for the QApplication — which is the distinction that was
    missed."""
    import inspect
    from draft_assist.ui import app as app_mod

    early = inspect.getsource(app_mod.main)
    assert "claim_taskbar_identity" in early
    assert "ensure_start_menu_shortcut" not in early, \
        "it renders an .ico; before the QApplication that aborts the process"
    assert "appicon.icon()" not in early

    late = inspect.getsource(app_mod._main)
    assert "ensure_start_menu_shortcut" in late
    # Still after the QApplication and before the window is built.
    assert (late.index("QApplication(sys.argv)")
            < late.index("ensure_start_menu_shortcut")
            < late.index("MainWindow("))


def test_the_shortcut_refuses_early_rather_than_aborting(qapp, monkeypatch):
    """On Windows the platform check passes, so the guard has to be the
    thing that stops it — and it has to say so, not fail silently."""
    import sys as _sys

    from draft_assist.ui import appicon

    monkeypatch.setattr(appicon, "gui_ready", lambda: False)
    monkeypatch.setattr(appicon, "_shortcut_done", False)
    monkeypatch.setattr(_sys, "platform", "win32")
    assert appicon.ensure_start_menu_shortcut() is False
    assert "before the QApplication" in appicon.shortcut_note

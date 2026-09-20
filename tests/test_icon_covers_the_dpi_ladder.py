"""The .ico must carry the size the shell asks for, not a near one.

Reported as "the app icon is still small", with a screenshot of the
taskbar: our button's picture visibly inset where Dota's, beside it,
filled its slot. Nothing about the artwork was wrong - `pixmap(n)`
fills 100% of its square at every size, with zero margin - so the
margin was being added outside this app, and an icon drawn smaller
than its slot is what the shell does when it has no entry at the size
it wanted: it takes the nearest SMALLER one and centres it.

The sizes it wants are not round numbers. Windows scales the shell's
16/24/32/48px icons by the display scaling, and a 2560x1600 laptop is
never at 100%.
"""

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication            # noqa: E402

from draft_assist.ui import appicon                 # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])

# What the shell draws from, before scaling: small, taskbar (Windows 11
# uses 24 logical px), large, extra large.
SHELL_BASES = (16, 24, 32)
# The scalings Windows offers that people actually run at. Above 200%
# the ladder stops being exact on purpose - scaling DOWN from a bigger
# entry is the direction that looks right.
SCALINGS = (1.0, 1.25, 1.5, 1.75, 2.0)


@pytest.mark.parametrize("base", SHELL_BASES)
@pytest.mark.parametrize("scale", SCALINGS)
def test_the_ladder_has_the_size_windows_asks_for(base, scale):
    wanted = round(base * scale)
    assert wanted in appicon.ICO_SIZES, (
        f"a {base}px shell icon at {scale:.0%} asks for {wanted}px, which "
        f"this .ico does not carry - the taskbar draws the nearest smaller "
        f"entry centred in the slot, which is the inset button")


def test_the_two_ladders_are_the_same_list():
    """The window draws from SIZES and the shell from ICO_SIZES. Two
    lists that can disagree is the two drawing different pictures."""
    assert appicon.SIZES == appicon.ICO_SIZES


def test_every_size_is_a_legal_ico_entry():
    """An .ico stores width and height in ONE byte each, 0 meaning 256."""
    for size in appicon.ICO_SIZES:
        assert 1 <= size <= 256, size


def test_the_artwork_still_fills_every_square(qapp):
    """The half that was never wrong, held so it cannot become wrong:
    if the app ever starts insetting its own art, the fix above stops
    being the answer and this says so."""
    import numpy as np
    from PyQt6.QtGui import QImage
    for size in appicon.ICO_SIZES:
        img = appicon.pixmap(size).toImage().convertToFormat(
            QImage.Format.Format_RGBA8888)
        w, h = img.width(), img.height()
        buf = img.constBits()
        buf.setsize(h * img.bytesPerLine())
        a = np.frombuffer(buf, np.uint8).reshape(
            h, img.bytesPerLine() // 4, 4)[:, :w, :]
        opaque = a[..., 3] > 16
        assert opaque.any(), f"{size}px is empty"
        ys, xs = np.where(opaque)
        assert xs.min() == 0 and xs.max() == w - 1, f"{size}px is inset"
        assert ys.min() == 0 and ys.max() == h - 1, f"{size}px is inset"


# ---- the live taskbar button -----------------------------------------

def test_the_window_icon_asks_for_dpi_scaled_metrics():
    """`GetSystemMetrics` is NOT DPI-scaled in a DPI-aware process, and
    Qt declares this app DPI-aware. On a 150% display it answers
    SM_CXSMICON 16 while the taskbar's slot is 24 - so the button got a
    16px picture in a 24px hole, which is what was measured on a real
    2560x1600 laptop: our icon 16x16 beside Dota's 24x24.

    The .ico ladder alone cannot fix this. A running window's button
    comes from WM_SETICON, not from the shortcut, so it never sees how
    many sizes the file has - only the size it was asked to load.
    """
    import ast
    from pathlib import Path
    source = Path(appicon.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    body = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "push_native_icon":
            body = ast.dump(node)
    assert body is not None, "push_native_icon has gone"
    assert "GetSystemMetricsForDpi" in body, (
        "the window icon is loaded at un-scaled metrics, so a high-DPI "
        "taskbar gets a 16px icon for a 24px slot")
    assert "GetDpiForWindow" in body


def test_the_window_icon_still_works_without_the_dpi_calls():
    """Windows before 10/1607 has neither call. The flat metric is what
    those machines were always getting, so it must stay reachable."""
    import ast
    from pathlib import Path
    source = Path(appicon.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "push_native_icon":
            assert "GetSystemMetrics" in ast.dump(node)


def test_the_diagnostic_says_what_size_it_asked_for():
    """"the window has an icon" and "the window has an icon the taskbar
    can use" are different claims; this fault was the second being
    false while the first was true."""
    import ast
    from pathlib import Path
    tree = ast.parse(Path(appicon.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "push_native_icon":
            assert "asked for " in ast.dump(node)


# ---- the shell's icon cache ------------------------------------------

def test_the_generated_ico_is_named_after_its_contents(qapp):
    """THE LAST PLACE A STALE PICTURE COULD COME FROM. A taskbar button
    for a process with an AppUserModelID is resolved through the
    matching Start-menu shortcut, not from the window - and that path
    goes through the shell's icon cache, keyed on the icon's PATH.
    Rewriting one fixed filename with better contents is precisely what
    it does not notice.

    Measured: with the window's own ICON_SMALL a valid 24px handle, the
    button still drew 16x16 beside Steam's 24x24.
    """
    first = appicon.generated_ico()
    assert first.name.startswith(appicon.GENERATED_PREFIX)
    assert first.suffix == ".ico"
    assert first.name != f"{appicon.GENERATED_PREFIX}.ico", (
        "a fixed name is what the icon cache can serve stale")


def test_a_different_ladder_is_a_different_file(qapp, monkeypatch):
    """Different contents must mean a different path, or the cache can
    hand back the old render."""
    was = appicon.generated_ico()
    monkeypatch.setattr(appicon, "ICO_SIZES", (16, 32))
    assert appicon.generated_ico() != was


def test_the_same_icon_is_not_rewritten(qapp):
    """An unchanged icon is eighteen sizes that need not be rendered."""
    first = appicon.ensure_generated_ico()
    stamp = first.stat().st_mtime_ns
    again = appicon.ensure_generated_ico()
    assert again == first
    assert again.stat().st_mtime_ns == stamp


def test_old_generated_icos_are_swept(qapp, tmp_path, monkeypatch):
    """`assets/` must not collect one file per icon anybody ever chose."""
    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    stale = tmp_path / f"{appicon.GENERATED_PREFIX}-deadbeef01.ico"
    stale.write_bytes(b"not really an icon")
    keep = appicon.ensure_generated_ico()
    assert keep.exists()
    assert not stale.exists()


# ---- what the window ends up holding ---------------------------------

def test_the_file_itself_is_beyond_doubt(qapp):
    """Decoded frame by frame, every entry must be its declared size
    AND fill it. This is the half that kept being assumed: the .ico was
    provably right while the button was provably wrong, and measuring
    `pixmap()` instead of the written FILE could not tell them apart."""
    import numpy as np
    from PyQt6.QtGui import QImage, QImageReader
    reader = QImageReader(str(appicon.ensure_generated_ico()))
    assert reader.imageCount() == len(appicon.ICO_SIZES)
    seen = []
    for index in range(reader.imageCount()):
        reader.jumpToImage(index)
        img = reader.read().convertToFormat(QImage.Format.Format_RGBA8888)
        assert not img.isNull(), f"frame {index} will not decode"
        w, h = img.width(), img.height()
        buf = img.constBits()
        buf.setsize(h * img.bytesPerLine())
        a = np.frombuffer(buf, np.uint8).reshape(
            h, img.bytesPerLine() // 4, 4)[:, :w, :]
        ys, xs = np.where(a[..., 3] > 16)
        assert len(xs), f"frame {index} ({w}x{h}) is empty"
        assert (xs.min(), xs.max()) == (0, w - 1), f"{w}x{h} is inset"
        assert (ys.min(), ys.max()) == (0, h - 1), f"{w}x{h} is inset"
        seen.append(w)
    assert sorted(seen) == sorted(appicon.ICO_SIZES)


def test_the_diagnostic_measures_the_icon_rather_than_naming_a_handle():
    """A handle says an icon EXISTS; it cannot say how big it is, and
    "how big" is the whole question for a taskbar button. Three fixes
    in a row were reported on by a line that could not tell the two
    apart."""
    import ast
    from pathlib import Path
    source = Path(appicon.__file__).read_text(encoding="utf-8")
    assert "def _icon_size(" in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "push_native_icon":
            assert "_icon_size" in ast.dump(node)


def test_measuring_an_icon_never_leaks_its_bitmaps():
    """GetIconInfo hands back two bitmaps that belong to the caller. A
    diagnostic that exhausts GDI handles is worse than the bug."""
    import ast
    from pathlib import Path
    tree = ast.parse(Path(appicon.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_icon_size":
            body = ast.dump(node)
            assert "DeleteObject" in body
            assert any(isinstance(n, ast.Try) and n.finalbody
                       for n in ast.walk(node)), "the delete must be in a finally"


def test_the_window_puts_its_icon_back_after_qt():
    """Qt sets the window icon on the way up, at the un-scaled metric.
    Ours ran at the end of __init__, which is before that."""
    import ast
    from pathlib import Path
    from draft_assist.ui import app as app_mod
    tree = ast.parse(Path(app_mod.__file__).read_text(encoding="utf-8"))
    shown = [n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "showEvent"]
    assert shown, "MainWindow.showEvent has gone"
    assert any("push_native_icon" in ast.dump(n) for n in shown)


# ---- the size the taskbar actually draws at --------------------------

TASKBAR_LOGICAL = 24


@pytest.mark.parametrize("scale", SCALINGS)
def test_the_ladder_has_the_taskbar_size(scale):
    """Windows 11 draws an app icon at 24 LOGICAL px. There is no system
    metric for that - SM_CXSMICON is 16 and SM_CXICON is 32 - so it has
    to be carried explicitly."""
    assert round(TASKBAR_LOGICAL * scale) in appicon.ICO_SIZES


def test_the_small_icon_is_not_the_small_icon_metric():
    """THE FAULT, as arithmetic. SM_CXSMICON is 16 logical and the
    taskbar draws at 24 logical, and both scale with DPI - so an
    ICON_SMALL taken from that metric is exactly two thirds of the
    button at EVERY scaling. Measured twice: 16px beside a neighbour's
    24px, a ratio of 0.667 against a predicted 0.667.

    It is also why making the metric DPI-aware changed nothing visible:
    that was right and not enough, since 16 became 24 while the slot
    became 36.
    """
    import ast
    from pathlib import Path
    source = Path(appicon.__file__).read_text(encoding="utf-8")
    assert "_TASKBAR_ICON = 24" in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "push_native_icon":
            body = ast.dump(node)
            assert "_TASKBAR_ICON" in body, (
                "ICON_SMALL is still taken from SM_CXSMICON alone, which "
                "is two thirds of the taskbar's slot at every scaling")
            assert "max" in body, "it must never go BELOW the metric either"


@pytest.mark.parametrize("scale", SCALINGS)
def test_the_small_icon_would_now_fill_the_slot(scale):
    """The arithmetic the fix performs, checked independently of it."""
    dpi = round(96 * scale)
    metric_small = round(16 * dpi / 96)
    taskbar = round(TASKBAR_LOGICAL * dpi / 96)
    chosen = max(metric_small, taskbar)
    assert chosen == taskbar, f"{scale:.0%} would still under-fill"
    assert chosen in appicon.ICO_SIZES, f"{chosen}px is not in the file"


# ---- the class icon, and a diagnostic that cannot say "?" ------------

def test_the_class_icon_is_set_too():
    """Windows falls back to the window CLASS icon, and Qt sets one for
    itself - this app's class comes back named "Qt6112QWindowIcon".
    WM_SETICON should win over it, and the button stayed at exactly two
    thirds of its slot through two fixes that each provably did what
    they claimed, so both are set now."""
    import ast
    from pathlib import Path
    source = Path(appicon.__file__).read_text(encoding="utf-8")
    assert "_GCLP_HICON" in source and "_GCLP_HICONSM" in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "push_native_icon":
            body = ast.dump(node)
            assert "SetClassLongPtrW" in body
            assert "SetClassLongW" in body, "32-bit Windows needs the other name"


def test_the_readback_never_reports_a_bare_question_mark():
    """It did, on both icons, and said nothing about whether the size
    had stuck - which cost a whole round. Every failure path has to
    name itself."""
    import ast
    from pathlib import Path
    tree = ast.parse(Path(appicon.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_icon_size":
            for leaf in ast.walk(node):
                if isinstance(leaf, ast.Return) and isinstance(
                        leaf.value, ast.Constant):
                    assert leaf.value.value != "?", (
                        "a bare '?' cannot separate two causes")


def test_the_readback_declares_its_argtypes():
    """ctypes defaults a return to a 32-bit int; a truncated handle is
    a handle to nothing. The rule the rest of this module follows."""
    import ast
    from pathlib import Path
    tree = ast.parse(Path(appicon.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_icon_size":
            body = ast.dump(node)
            assert "argtypes" in body and "restype" in body

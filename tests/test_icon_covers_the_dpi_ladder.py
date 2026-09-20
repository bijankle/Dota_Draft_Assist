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

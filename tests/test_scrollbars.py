"""Scrollbars, which Qt draws out of six separate pieces.

The bug these exist for: the stylesheet named the groove and the handle
and nothing else, so `add-page` and `sub-page` — the track either side of
the handle — were left to the native style. On Windows that draws a
dithered texture, which through a translucent always-on-top window reads
as a clump of white specks, with the stepper buttons as specks at each
end. "Expecting a smooth continuous solid look like most scrollbars" is
exactly right, and the cause is not the colour: it is that a stylesheet
which touches a widget does not leave the parts it skips alone, it hands
them to somebody else to draw.

So the check is not "does it look nice" — this machine renders with
Fusion and cannot reproduce a Windows native fallback at all — but "is
every sub-control named", which is the thing that decides it.
"""

import os
import re

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import (QApplication, QPlainTextEdit,      # noqa: E402
                             QScrollBar)

from draft_assist.ui import theme                               # noqa: E402

# Every piece Qt composes a scrollbar from. Leave one out and the native
# style paints it.
SUB_CONTROLS = ["handle", "add-line", "sub-line", "add-page", "sub-page",
                "up-arrow", "down-arrow", "left-arrow", "right-arrow"]


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def test_every_scrollbar_sub_control_is_styled():
    """The one that was missing is add-page/sub-page, and it is the one
    the eye actually reads as "the bar"."""
    css = theme.STYLESHEET
    for part in SUB_CONTROLS:
        assert f"QScrollBar::{part}" in css, (
            f"QScrollBar::{part} is unstyled, so the native style draws it")


def test_both_orientations_are_styled():
    css = theme.STYLESHEET
    for rule in ("QScrollBar:vertical", "QScrollBar:horizontal",
                 "QScrollBar::handle:vertical",
                 "QScrollBar::handle:horizontal"):
        assert rule in css, rule


def test_the_steppers_are_removed_rather_than_merely_shrunk():
    """A zero width and height alone still leaves the native style
    something to paint into; it has to be told there is no background and
    no border either."""
    block = re.search(
        r"QScrollBar::add-line, QScrollBar::sub-line \{([^}]*)\}",
        theme.STYLESHEET)
    assert block, "the stepper rule is gone"
    body = block.group(1)
    assert "background: none" in body
    assert "border: none" in body
    assert "height: 0" in body and "width: 0" in body


def test_the_corner_between_two_bars_is_styled():
    """Its own sub-control again, and it drew as a native grey notch."""
    assert "QAbstractScrollArea::corner" in theme.STYLESHEET


def test_the_handle_is_lighter_than_the_surfaces_it_sits_on():
    """It was BG_DEEP — darker than the panel around it — so it read as a
    hole rather than as a control you can grab."""
    def value(colour: str) -> int:
        colour = colour.lstrip("#")
        return sum(int(colour[i:i + 2], 16) for i in (0, 2, 4))

    for surface in (theme.BG, theme.BG_ELEVATED, theme.BG_DEEP):
        assert value(theme.SCROLL) > value(surface), surface
    assert value(theme.SCROLL_HOVER) > value(theme.SCROLL), \
        "hover has to lift, not sink"


def test_a_real_scrollbar_paints_without_falling_back(qapp):
    """Render one and read the pixels down its track: with every piece
    styled the groove is the widget's own background, so the track either
    side of the handle holds no colour the stylesheet did not choose."""
    qapp.setStyleSheet(theme.STYLESHEET)
    box = QPlainTextEdit()
    box.setPlainText("\\n".join(f"line {n}" for n in range(200)))
    box.resize(320, 200)
    box.show()
    qapp.processEvents()

    bar = box.verticalScrollBar()
    assert isinstance(bar, QScrollBar) and bar.isVisible()
    shot = bar.grab().toImage()
    assert shot.width() > 0 and shot.height() > 0

    # Down the middle of the bar, every pixel is either the handle colour
    # or the surface behind it — never a third colour some other painter
    # introduced.
    handle = theme.SCROLL.lstrip("#").lower()
    seen = set()
    x = shot.width() // 2
    for y in range(shot.height()):
        seen.add(f"{shot.pixelColor(x, y).name().lstrip('#').lower()}")
    assert handle in seen, f"the handle never painted; saw {sorted(seen)}"
    # A dithered native track shows up as many near-identical greys; a
    # styled one is a small handful of flat colours.
    assert len(seen) <= 4, f"too many colours down the track: {sorted(seen)}"
    # CLOSED, not merely scheduled for deletion. `deleteLater` needs an
    # event loop to reach the deferred-delete, and a test run has none —
    # so this stayed a SHOWN TOP-LEVEL WIDGET for the rest of the session
    # and tripped the smoke test that counts the app's windows, whenever
    # allocation happened to keep it alive that long.
    box.close()
    box.deleteLater()
    qapp.processEvents()


# --- and the one menu nobody wrote -------------------------------------

def test_the_app_turns_menu_icons_off_before_it_builds_any_widget():
    """The standard context menu is the same fault one widget over.

    Right-click any text in this app — the debug log, a selectable
    label, a task's output — and the menu that opens is Qt's, not ours:
    Copy, Select All, each with an icon from the PLATFORM's theme,
    drawn at that theme's weight and colour beside labels drawn at this
    app's. Every menu this app builds is words alone, so the one menu
    nobody wrote was the only one that did not match its own text.

    CHECKED IN THE SOURCE, for the reason the rest of this file is.
    Rendered here the actions carry no icon at all — there is no icon
    theme on this machine — so a test of the menu would pass against
    the very build that is wrong on Windows. What decides it is that
    the attribute is set, and that it is set BEFORE the widgets whose
    menus it governs are built.
    """
    import inspect
    from draft_assist.ui import app as ui_app
    # `main` is the crash wrapper; `_main` is the body that
    # builds the QApplication and the window.
    body = inspect.getsource(ui_app._main)
    assert "AA_DontShowIconsInMenus" in body, (
        "nothing turns the platform's menu icons off")
    at = body.index("AA_DontShowIconsInMenus")
    # BEFORE THE WINDOW. The attribute governs menus built after it is
    # set, and `MainWindow` builds the menu bar in its constructor.
    assert at < body.index("MainWindow("), (
        "the attribute is set after the window is built, which is after "
        "the menus it governs already exist")

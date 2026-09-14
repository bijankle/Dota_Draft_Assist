"""The pin: hold the window in front, or let it fall behind.

"if the pin is hollow, that means that the window is not pinned ie. if
you click on a window in the background, that clicked window will be
brought to the front... however if you click on the pin symbol it will
become filled - in this state it is always in front so you can be playing
dota 2 while the app remains in front of dota 2."

The window was always-on-top with no way to say otherwise, which is a
mode rather than a setting when the thing underneath is a game you are
trying to click on. So the flag becomes a choice, and it DEFAULTS to what
the app has always done — a fresh install behaves exactly as before, and
the pin is purely something gained.
"""

import os
import sys
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from draft_assist.config import RULES_FILE                   # noqa: E402
from draft_assist.model import items as items_mod            # noqa: E402
from draft_assist.ui import chrome, ontop, theme             # noqa: E402
from draft_assist.ui import settings as ui_settings          # noqa: E402
from draft_assist.ui.app import MainWindow                   # noqa: E402
from draft_assist.ui.demo import demo_dataset                # noqa: E402
from draft_assist.ui.providers import DemoProvider           # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def build(qapp):
    ds = demo_dataset()
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, DemoProvider(ds), rules, meta)
    win.timer.stop()
    qapp.processEvents()
    return win


@pytest.fixture()
def win(qapp):
    window = build(qapp)
    yield window
    window.close()


# ---- where it is and what it says --------------------------------------

def test_the_pin_sits_to_the_LEFT_of_minimise(win):
    """As asked. It is a window control, so it belongs with the other
    three rather than two menus away in Settings."""
    bar = win.title_bar
    order = []
    row = bar.layout()
    for index in range(row.count()):
        widget = row.itemAt(index).widget()
        if isinstance(widget, chrome.WindowButton):
            order.append(widget.kind)
    assert order == ["pin", "min", "max", "close"], order


def test_it_starts_filled_because_that_is_what_the_app_always_did(win):
    """Changing the default silently would be a behaviour regression
    nobody asked for: this window has been always-on-top from the start."""
    assert ui_settings.DEFAULTS["always_on_top"] is True
    assert win.title_bar.pin.isChecked() is True


def test_hollow_and_filled_are_the_two_states(win, qapp):
    pin = win.title_bar.pin
    assert pin.isCheckable()
    pin.click()
    qapp.processEvents()
    assert pin.isChecked() is False, "one press should empty it"
    pin.click()
    qapp.processEvents()
    assert pin.isChecked() is True


def test_pressing_it_is_remembered(qapp, tmp_path, monkeypatch):
    """A window that forgets where it sits in the Z order is one you
    re-pin every session."""
    monkeypatch.setattr(ui_settings, "SETTINGS_FILE", tmp_path / "s.json")
    first = build(qapp)
    try:
        first.title_bar.pin.click()
        qapp.processEvents()
        assert first.settings["always_on_top"] is False
    finally:
        first.close()

    second = build(qapp)
    try:
        assert second.settings["always_on_top"] is False
        assert second.title_bar.pin.isChecked() is False
    finally:
        second.close()


def test_restoring_the_setting_is_not_the_user_pressing_it(qapp, tmp_path,
                                                           monkeypatch):
    """An unblocked restore writes the settings file on every start —
    the trap every other remembered control here carries a note about."""
    monkeypatch.setattr(ui_settings, "SETTINGS_FILE", tmp_path / "s.json")
    fired = []
    bar = chrome.TitleBar("t")
    bar.pinned.connect(fired.append)
    bar.set_pinned(False)
    assert bar.pin.isChecked() is False
    assert fired == [], "restoring announced itself as a fresh choice"
    bar.deleteLater()


# ---- the mark ----------------------------------------------------------

def test_filled_really_is_filled_and_hollow_really_is_not(qapp):
    """It is in the stylesheet has twice not meant it is on the screen,
    so this counts the PIXELS the two states actually paint."""
    was = qapp.styleSheet()
    qapp.setStyleSheet(theme.STYLESHEET)
    try:
        pin = chrome.PinButton()
        pin.resize(46, chrome.BAR_HEIGHT)

        def ink(checked):
            pin.setChecked(checked)
            picture = pin.grab().toImage()
            background = picture.pixel(0, 0)
            return sum(picture.pixel(x, y) != background
                       for x in range(picture.width())
                       for y in range(picture.height()))

        hollow, filled = ink(False), ink(True)
        assert hollow > 20, "the hollow pin drew nothing at all"
        assert filled > hollow, (
            f"filled ({filled}px) is not more ink than hollow ({hollow}px)")
        pin.deleteLater()
    finally:
        qapp.setStyleSheet(was)


def test_the_held_pin_wears_the_frames_own_gold(qapp):
    """Gold is this app's "this one" colour — the window border, the
    focus ring and the suggestion star all wear it, and none of them
    mean good or bad. A pin is a state, not a judgement."""
    was = qapp.styleSheet()
    qapp.setStyleSheet(theme.STYLESHEET)
    try:
        pin = chrome.PinButton()
        pin.resize(46, chrome.BAR_HEIGHT)
        pin.setChecked(True)
        picture = pin.grab().toImage()
        gold = QColor(theme.FRAME_GOLD).rgb()
        assert any(picture.pixel(x, y) == gold
                   for x in range(picture.width())
                   for y in range(picture.height()))
        pin.deleteLater()
    finally:
        qapp.setStyleSheet(was)


# ---- the trap it was written around ------------------------------------

def test_it_does_NOT_change_the_window_flags_on_windows():
    """**THE WHOLE REASON `ui/ontop.py` EXISTS.** Changing a window's
    flags on Windows DESTROYS AND RECREATES the native handle, and this
    app has already paid for that once — `setWindowIcon` ran before
    `setWindowFlags`, the icon went to an HWND that no longer existed and
    the taskbar button fell back to pythonw.exe. On a BUTTON it would
    happen on every press, taking the window's Win32 icon and its
    relaunch identity with it each time.
    """
    import ast
    import inspect

    def calls(func):
        """The CALLS a function makes, never its prose. This assertion
        first failed on the docstring that NAMES the trap, which would
        have made the note unwriteable."""
        tree = ast.parse(inspect.getsource(func).lstrip())
        return {node.func.attr for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)}

    made = calls(ontop._windows)
    assert "SetWindowPos" in made
    assert not any(name.startswith("setWindowFlag") for name in made), (
        "the Windows path must not touch the flags")
    # `apply`'s OTHER branch may: off Windows there is no handle to
    # destroy and Qt's flag is the only route there is.
    # And the handler on the window goes through it rather than round it.
    handler = calls(MainWindow._set_pinned)
    assert "apply" in handler
    assert not any(name.startswith("setWindowFlag") for name in handler)


def test_the_ctypes_call_declares_its_return_type():
    """`restype` is not optional: the default is a 32-bit int, and the
    same omission truncated a 64-bit handle elsewhere in this app."""
    import inspect
    body = inspect.getsource(ontop._windows)
    assert "restype" in body and "argtypes" in body


def test_applying_it_never_raises_whatever_it_is_handed():
    """A window that will not come to the front is a nuisance; an app
    that will not start because it could not reorder itself is worse."""
    class Hopeless:
        def winId(self):
            raise OSError("no handle")

        def isVisible(self):
            raise OSError("no window")

    assert ontop.apply(Hopeless(), True) in (True, False)
    assert ontop.note


def test_it_says_what_it_last_did():
    """The note reads identically whether the call worked or was never
    made, unless it says which — the lesson `identity_note` carries."""
    bar = chrome.TitleBar("t")
    ontop.apply(bar, True)
    assert ontop.note != "not attempted"
    bar.deleteLater()


# ---- the shape the user asked for --------------------------------------

def test_the_mark_is_a_tack_LYING_AT_AN_ANGLE(qapp):
    """"use this pin look" — a thumbtack on the diagonal, needle running
    off to the bottom-left. The angle is most of what makes it read: the
    upright version was a cap over a body over a needle and came back as
    unrecognisable at this size. It is also the only diagonal thing in
    the title bar, so it cannot be taken for its three square
    neighbours.
    """
    pin = chrome.PinButton()
    pin.resize(46, chrome.BAR_HEIGHT)
    picture = pin.grab().toImage()
    background = picture.pixel(0, 0)
    ink = [(x, y)
           for x in range(picture.width())
           for y in range(picture.height())
           if picture.pixel(x, y) != background]
    assert ink
    # The needle's tip is the bottom-LEFT extreme, and the cap the
    # top-right: on the diagonal those are the same two points.
    left = min(x for x, _ in ink)
    right = max(x for x, _ in ink)
    top = min(y for _, y in ink)
    bottom = max(y for _, y in ink)
    lowest = max(y for x, y in ink if x <= left + 1)
    highest = min(y for x, y in ink if x >= right - 1)
    assert lowest > (top + bottom) / 2, "the left end is not the low end"
    assert highest < (top + bottom) / 2, "the right end is not the high end"
    # And it is about as tall as it is wide, like the marks beside it.
    assert abs((right - left) - (bottom - top)) <= 3
    pin.deleteLater()


def test_the_two_states_are_the_SAME_outline(qapp):
    """Only the ink inside it changes. A mark that changes SHAPE when it
    changes meaning is two marks, and the user has to learn both."""
    pin = chrome.PinButton()
    pin.resize(46, chrome.BAR_HEIGHT)

    def box(checked):
        pin.setChecked(checked)
        picture = pin.grab().toImage()
        background = picture.pixel(0, 0)
        ink = [(x, y)
               for x in range(picture.width())
               for y in range(picture.height())
               if picture.pixel(x, y) != background]
        return (min(x for x, _ in ink), min(y for _, y in ink),
                max(x for x, _ in ink), max(y for _, y in ink))

    hollow, filled = box(False), box(True)
    assert all(abs(a - b) <= 1 for a, b in zip(hollow, filled)), (
        f"hollow {hollow} and filled {filled} are different shapes")
    pin.deleteLater()


def test_the_filled_pin_is_SOLID(qapp):
    """"full solid fill when it is active". Not a heavier outline: the
    middle of the head has to actually carry ink, which is the one thing
    that reads from the corner of the eye."""
    pin = chrome.PinButton()
    pin.resize(46, chrome.BAR_HEIGHT)

    def middle_of_the_head(checked):
        pin.setChecked(checked)
        picture = pin.grab().toImage()
        background = picture.pixel(0, 0)
        ink = [(x, y)
               for x in range(picture.width())
               for y in range(picture.height())
               if picture.pixel(x, y) != background]
        # The centre of the mark's own bounding box is inside the head.
        cx = (min(x for x, _ in ink) + max(x for x, _ in ink)) // 2
        cy = (min(y for _, y in ink) + max(y for _, y in ink)) // 2
        return picture.pixel(cx, cy) != background

    assert middle_of_the_head(True), "the held pin is hollow in the middle"
    assert not middle_of_the_head(False), "the loose pin is filled in"
    pin.deleteLater()

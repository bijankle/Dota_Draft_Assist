"""View ▸ Greyscale: the whole app with the colour taken out.

Two halves, and it is only worth anything with both. The STYLESHEET
covers every widget Qt draws; the hero portraits and item icons are
pixmaps this app paints itself, and greying only the first leaves
full-colour faces on a grey screen — which is most of the window still
in colour.

**IT IS A PALETTE SWAP, NOT AN EFFECT.** A `QGraphicsEffect` over the
shell would catch anything added later and costs an offscreen re-render
of the whole window on every repaint, four times a second, over a
frameless translucent always-on-top window. Swapping at the source costs
nothing per frame and is checkable, which is what these do.
"""

import os
import re

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap   # noqa: E402
from PyQt6.QtWidgets import QApplication                    # noqa: E402

from draft_assist.ui import theme                           # noqa: E402

HEX = re.compile(r"#[0-9a-fA-F]{6}\b")


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _colour_comes_back():
    """MODULE STATE, so it is reset either side of every test — the same
    rule the size multipliers and the portrait cache follow. A test that
    turned the app grey and then failed would otherwise leave every test
    after it measuring a grey palette."""
    theme.set_greyscale(False)
    yield
    theme.set_greyscale(False)


def _is_grey(colour: str) -> bool:
    return colour[1:3].lower() == colour[3:5].lower() == colour[5:7].lower()


# ---- the palette --------------------------------------------------------

def test_every_colour_the_theme_names_goes_grey():
    coloured = [name for name in theme._COLOURS
                if not _is_grey(getattr(theme, name))]
    assert coloured, "nothing in the palette had colour to begin with"
    theme.set_greyscale(True)
    for name in theme._COLOURS:
        assert _is_grey(getattr(theme, name)), f"{name} kept its colour"


def test_it_goes_back():
    before = {name: getattr(theme, name) for name in theme._COLOURS}
    sheet = theme.STYLESHEET
    theme.set_greyscale(True)
    theme.set_greyscale(False)
    for name, was in before.items():
        assert getattr(theme, name) == was, name
    assert theme.STYLESHEET == sheet


def test_no_literal_in_the_stylesheet_keeps_its_colour():
    """Most rules read the constants, but a handful carry their own —
    the tinted grounds behind the warning and "good" pills. Sweeping the
    built string catches those and anything added later, without a list
    somebody has to remember to maintain."""
    theme.set_greyscale(True)
    left = sorted({found for found in HEX.findall(theme.STYLESHEET)
                   if not _is_grey(found)})
    assert not left, f"colour left in the stylesheet: {left}"


def test_good_and_bad_stay_apart_and_readable():
    """THE ONE PLACE LUMINANCE IS REFUSED, and refusing it is the point.
    #23a55a and #f23f43 — the green and red every signed number in this
    app is printed in — both desaturate to a mid grey about four points
    apart, so +6.4 and -6.4 would read identically. "Keep good/bad
    readable in grey" was the call, so good becomes the brightest text
    and bad a muted one.
    """
    honest_good = theme._luma("#23a55a")
    honest_bad = theme._luma("#f23f43")
    assert abs(int(honest_good[1:3], 16) - int(honest_bad[1:3], 16)) < 12, (
        "the premise has changed: luminance now tells them apart")

    theme.set_greyscale(True)
    good = int(theme.GOOD[1:3], 16)
    bad = int(theme.BAD[1:3], 16)
    assert good - bad >= 60, "good and bad are not far enough apart to read"
    # And both have to be legible on the content ground, which is dark.
    ground = int(theme.BG[1:3], 16)
    assert good > ground + 60 and bad > ground + 40, (
        "a signed number would be unreadable on the background")


def test_luma_is_weighted_rather_than_a_plain_mean():
    """The eye is far more sensitive to green than to blue, so averaging
    the channels turns a mid green and a mid blue into greys neither of
    them reads as."""
    green = int(theme._luma("#00ff00")[1:3], 16)
    blue = int(theme._luma("#0000ff")[1:3], 16)
    assert green > blue * 3, "a plain mean would make these equal"


# ---- the artwork --------------------------------------------------------

def _swatch(colour: QColor, alpha_half: bool = True) -> QPixmap:
    pixmap = QPixmap(4, 4)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.fillRect(0, 0, 2, 4, colour)
    painter.end()
    return pixmap


def test_a_picture_loses_its_colour_and_keeps_its_alpha(qapp):
    """`Format_Grayscale8` has NO alpha channel, so converting straight
    to it and back leaves every item icon on an opaque black square.
    The alpha is lifted off the original and put back."""
    grey = theme.greyed(_swatch(QColor(35, 165, 90)))
    image = grey.toImage().convertToFormat(QImage.Format.Format_ARGB32)

    drawn = QColor.fromRgba(image.pixel(0, 0))
    assert drawn.red() == drawn.green() == drawn.blue(), "colour survived"
    assert drawn.alpha() == 255
    assert QColor.fromRgba(image.pixel(3, 0)).alpha() == 0, (
        "the transparent half came back opaque")


def test_greying_nothing_is_not_a_crash(qapp):
    """A missing portrait is NORMAL — a fresh install has none — so this
    is asked about None and about a null pixmap constantly."""
    assert theme.greyed(None) is None
    assert theme.greyed(QPixmap()).isNull()


# ---- the window ---------------------------------------------------------

@pytest.fixture()
def window(qapp, tmp_path, monkeypatch):
    from draft_assist.config import RULES_FILE
    from draft_assist.model import items as items_mod
    from draft_assist.ui import settings as ui_settings
    from draft_assist.ui.app import MainWindow
    from draft_assist.ui.demo import demo_dataset
    from draft_assist.ui.providers import DemoProvider
    monkeypatch.setattr(ui_settings, "SETTINGS_FILE", tmp_path / "ui.json")
    ds = demo_dataset()
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, DemoProvider(ds), rules, meta)
    win.timer.stop()
    yield win
    win.close()


def test_the_tick_turns_it_on_and_remembers(window, qapp):
    assert window.settings["greyscale"] is False
    assert not theme.GREYSCALE

    window.greyscale_action.setChecked(True)
    qapp.processEvents()
    assert window.settings["greyscale"] is True
    assert theme.GREYSCALE
    assert _is_grey(theme.ACCENT)

    window.greyscale_action.setChecked(False)
    qapp.processEvents()
    assert window.settings["greyscale"] is False
    assert not theme.GREYSCALE


def test_the_setting_is_what_the_tick_follows_rather_than_the_reverse(
        window, qapp):
    """A settings file saying greyscale must arrive at a grey window on
    the FIRST paint, not once somebody opens the View menu. And setting
    a control to what the file already says is not the user pressing it,
    so the signal is blocked while it is corrected — unblocked it would
    rewrite the settings file on every start."""
    window.settings["greyscale"] = True
    window._apply_greyscale()
    qapp.processEvents()
    assert window.greyscale_action.isChecked()
    assert theme.GREYSCALE


def test_the_stylesheet_actually_reaches_the_application(window, qapp):
    """`theme.STYLESHEET` changing is not the app changing: the string
    has to be handed to the QApplication, or the palette swaps in the
    module and nothing on screen moves."""
    window.settings["greyscale"] = True
    window._apply_greyscale()
    qapp.processEvents()
    assert qapp.styleSheet() == theme.STYLESHEET
    left = sorted({f for f in HEX.findall(qapp.styleSheet())
                   if not _is_grey(f)})
    assert not left, f"colour on screen: {left}"


def test_the_portrait_cache_is_dropped_so_the_art_follows(window, qapp,
                                                          monkeypatch):
    """A portrait is greyed once as it is LOADED, so the only way to
    change the answer is to make it be loaded again. Forgetting to drop
    the caches would leave every face in colour on a grey screen, which
    is most of the window."""
    from draft_assist.ui import portraits
    dropped = []
    monkeypatch.setattr(portraits, "forget",
                        lambda: dropped.append(1))
    window.settings["greyscale"] = True
    window._apply_greyscale()
    assert dropped, "the portraits kept their colour"


def test_the_window_frame_goes_grey_too():
    """The border is the most prominent thing on screen after the draft
    itself, and three of its four shades live in `ornate` rather than in
    the palette — they were QColor objects built at import, so greyscale
    left a full gold frame round a grey app."""
    from draft_assist.ui import ornate
    theme.set_greyscale(True)
    for shade in (ornate.DARK_GOLD, ornate.MID_GOLD, ornate.INNER_GOLD):
        painted = ornate._own(shade)
        assert painted.red() == painted.green() == painted.blue(), shade

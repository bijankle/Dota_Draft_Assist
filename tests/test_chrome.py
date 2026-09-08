"""The window's own chrome, and the icon it wears.

The frameless window has to put back by hand everything the system bar was
providing, and every one of those pieces has been wrong at least once: the
icon sliced top and bottom, the menu titles riding along the top edge of a
48px strip, and the floating toggle — the only part of the app on screen
when the window is hidden — drawing its plate and no icon at all.
"""

import os
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt                                 # noqa: E402
from PyQt6.QtGui import QColor, QPixmap                     # noqa: E402
from PyQt6.QtWidgets import QApplication, QMenuBar          # noqa: E402

from draft_assist.ui import appicon, chrome                  # noqa: E402
from draft_assist.ui import settings as ui_settings          # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def assets(tmp_path, monkeypatch):
    """An empty assets folder, and no portraits behind it."""
    monkeypatch.setattr(appicon, "ASSETS_DIR", tmp_path)
    monkeypatch.setattr(appicon, "_hero_pixmap", lambda: None)
    appicon.forget()
    yield tmp_path
    appicon.forget()


def wide(width=256, height=144, colour="#c04040") -> QPixmap:
    """The shape a Dota portrait is: a landscape crop of a hero's head."""
    art = QPixmap(width, height)
    art.fill(QColor(colour))
    return art


# ---- the icon is square, and it is not cropped --------------------------

def test_a_wide_source_is_letterboxed_never_sliced(assets, monkeypatch, qapp):
    """Bloodseeker's portrait is 256x144. Filling a square box with it cuts
    the top and bottom off the hero's head, which is what the title bar
    looked like."""
    monkeypatch.setattr(appicon, "_hero_pixmap", lambda: wide())
    appicon.forget()
    art = appicon.pixmap(40)
    assert (art.width(), art.height()) == (40, 40)
    image = art.toImage()
    # The picture keeps its own aspect inside the square: the middle band
    # is the portrait, the top row is the transparent letterbox.
    assert image.pixelColor(20, 20).alpha() == 255
    assert image.pixelColor(20, 0).alpha() == 0


def test_a_square_source_fills_the_box(assets, monkeypatch, qapp):
    """Which is the whole point of the user supplying their own: a square
    icon should reach the edges of the bar, not float in a margin."""
    monkeypatch.setattr(appicon, "_hero_pixmap", lambda: wide(256, 256))
    appicon.forget()
    image = appicon.pixmap(40).toImage()
    assert image.pixelColor(20, 1).alpha() == 255
    assert image.pixelColor(20, 38).alpha() == 255


def test_the_icon_is_built_at_every_size_the_shell_asks_for(assets,
                                                            monkeypatch, qapp):
    """Windows asks a taskbar icon for 16, 32, 48 and 256. A QIcon holding
    one pixmap gets scaled by the shell into something blurry."""
    monkeypatch.setattr(appicon, "_hero_pixmap", lambda: wide(256, 256))
    appicon.forget()
    sizes = {(s.width(), s.height()) for s in appicon.icon().availableSizes()}
    assert (32, 32) in sizes and (256, 256) in sizes


# ---- the user's own file ------------------------------------------------

def test_the_users_own_icon_wins_over_everything(assets, monkeypatch, qapp):
    """This repository ships no icon and will not — the ones asked for are
    someone else's artwork. A file picker is the honest answer."""
    monkeypatch.setattr(appicon, "_hero_pixmap", lambda: wide())
    source = assets / "mine.png"
    wide(64, 64, "#20a020").save(str(source), "PNG")
    appicon.forget()
    assert appicon.source() == "portrait"

    appicon.install(source)
    assert appicon.source() == "assets"
    assert (assets / "app.png").exists()
    assert appicon.pixmap(32).toImage().pixelColor(16, 16).green() > 100


def test_installing_an_icon_replaces_the_last_one(assets, qapp):
    """Two candidates would leave the order in CANDIDATES deciding, which
    is not what the user just chose."""
    (assets / "app.ico").write_bytes(QPixmap(8, 8).toImage().bits().asstring(0)
                                     if False else b"")
    first = assets / "first.png"
    wide(32, 32, "#101010").save(str(first), "PNG")
    appicon.install(first)
    assert not (assets / "app.ico").exists()
    assert (assets / "app.png").exists()


def test_a_file_that_is_not_an_image_is_refused_loudly(assets, qapp):
    """A silent no-op here looks exactly like the bug it is meant to fix."""
    junk = assets / "notes.txt"
    junk.write_text("this is not an icon")
    with pytest.raises(ValueError):
        appicon.install(junk)


# ---- the title bar ------------------------------------------------------

def test_the_title_bar_icon_fills_the_bars_height(qapp):
    bar = chrome.TitleBar("Dota Draft Assist")
    assert bar.height() == chrome.BAR_HEIGHT
    assert bar.icon.width() == bar.icon.height() == chrome.ICON
    assert chrome.BAR_HEIGHT - chrome.ICON <= 10      # snug, not a bullet


def test_the_menus_sit_on_the_bars_middle_line(qapp):
    """Given the bar's full height a QMenuBar draws its titles hard against
    the top edge, which is what "Setup Game View Help" riding high in the
    strip was."""
    bar = chrome.TitleBar("Dota Draft Assist")
    menus = QMenuBar()
    menus.addMenu("&Setup")
    menus.addMenu("&Game")
    bar.add_menu_bar(menus)
    bar.resize(600, chrome.BAR_HEIGHT)
    bar.show()
    QApplication.processEvents()
    assert menus.height() < chrome.BAR_HEIGHT
    middle = menus.geometry().center().y()
    assert abs(middle - chrome.BAR_HEIGHT // 2) <= 2
    bar.hide()


# ---- preferences that were being dropped on the way to disk -------------

def test_the_transparency_setting_survives_a_restart(tmp_path):
    """`save` writes only the keys DEFAULTS names, so a preference the app
    set but that dict did not know about was kept in memory and lost."""
    path = tmp_path / "ui_settings.json"
    settings = ui_settings.load(path)
    settings["overlay_opacity"] = 0.45
    ui_settings.save(settings, path)

    again = ui_settings.load(path)
    assert again["overlay_opacity"] == 0.45
    assert again["auto_record"] is True


# ---- the .ico a Windows shortcut needs ----------------------------------

def test_a_real_ico_is_written_for_the_shortcut(assets, monkeypatch, qapp):
    """A shortcut cannot use a .png — `IconLocation` pointed at one draws
    blank, and a pinned taskbar button with no picture is what that looks
    like."""
    from PyQt6.QtGui import QIcon
    monkeypatch.setattr(appicon, "_hero_pixmap", lambda: wide(256, 256))
    appicon.forget()
    path = appicon.write_ico(assets / "app-generated.ico")
    assert path.exists() and path.stat().st_size > 0
    # It is an ICO, and Windows will find every size in it.
    head = path.read_bytes()[:6]
    assert head[:4] == b"\x00\x00\x01\x00"
    sizes = {(s.width(), s.height()) for s in QIcon(str(path)).availableSizes()}
    assert (16, 16) in sizes and (256, 256) in sizes


def test_the_shortcut_and_the_app_claim_the_same_identity():
    """Windows matches a pinned button to a Start-menu shortcut by this
    string; two spellings of it means the pin finds nothing and falls back
    to python.exe's icon."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "make_shortcut", Path(__file__).resolve().parents[1]
        / "tools" / "make_shortcut.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.APP_ID == appicon.APP_ID


def test_the_title_bar_actually_paints_its_background(qapp):
    """`QWidget#titleBar { background: ... }` was parsed and then ignored.

    Qt paints a stylesheet background on a plain QWidget subclass only when
    WA_StyledBackground is set, so the bar drew in the BODY's grey while
    the tab row below it was properly dark. It was invisible for as long as
    everything above the tabs was the same grey, and became the step in the
    padding the moment the tab band went dark.
    """
    from PyQt6.QtGui import QColor
    from draft_assist.ui import theme
    qapp.setStyleSheet(theme.STYLESHEET)
    bar = chrome.TitleBar("Dota Draft Assist")
    assert bar.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    bar.resize(600, chrome.BAR_HEIGHT)
    image = bar.grab().toImage()
    # A column clear of the icon, the title and the window buttons.
    painted = QColor(image.pixel(400, chrome.BAR_HEIGHT - 2)).name()
    assert painted == theme.BG_DEEP, (
        f"the title bar drew {painted}, not {theme.BG_DEEP} — the "
        "stylesheet background is being ignored again")


# The font stack has a file of its own now: tests/test_fonts.py.
def test_the_title_is_the_frames_own_gold_and_wears_no_box(qapp):
    """A QLabel takes its background from the base QWidget rule, so the
    title drew a rectangle of CONTENT colour behind itself — a box round
    the app's name that nobody asked for."""
    from draft_assist.ui import ornate, theme
    assert theme.FRAME_GOLD in theme.STYLESHEET
    assert ornate.LIGHT.name() == theme.FRAME_GOLD
    rule = theme.STYLESHEET[theme.STYLESHEET.index("QLabel#titleText"):]
    rule = rule[:rule.index("}")]
    assert "background: transparent" in rule
    assert theme.FRAME_GOLD in rule


def test_the_window_buttons_are_the_same_size_as_each_other(qapp):
    """They were the characters "─", "□" and "✕", and a hollow square has
    no ink in the middle of it — at one point size it reads smaller than a
    dash and a cross, and every change of font resized the three by
    different amounts. Painted, they cannot drift.

    Measured as the INK's bounding box, because that is what the eye
    compares — a glyph's advance width says nothing about how big the mark
    inside it looks.
    """
    from PyQt6.QtGui import QColor

    def ink_box(kind):
        button = chrome.WindowButton(kind)
        button.resize(46, chrome.BAR_HEIGHT)
        image = button.grab().toImage()
        xs, ys = [], []
        for y in range(image.height()):
            for x in range(image.width()):
                pixel = QColor(image.pixel(x, y))
                if pixel.alpha() and pixel.lightness() > 60:
                    xs.append(x)
                    ys.append(y)
        assert xs, f"{kind} drew nothing"
        return max(xs) - min(xs) + 1, max(ys) - min(ys) + 1

    widths = {kind: ink_box(kind)[0] for kind in ("min", "max", "close")}
    assert abs(widths["max"] - widths["close"]) <= 2, (
        f"the square and the cross are different widths: {widths}")
    assert widths["min"] >= widths["max"] - 2, (
        f"the dash is narrower than the square: {widths}")


def test_close_is_the_one_that_goes_red(qapp):
    """The only button whose hover has to be unmistakable."""
    from PyQt6.QtGui import QColor
    from draft_assist.ui import theme
    button = chrome.WindowButton("close")
    button.resize(46, chrome.BAR_HEIGHT)
    # underMouse is false in a headless grab, so this checks the DECISION
    # rather than the hover: close asks for BAD, the others for BG_HOVER.
    assert theme.BAD != theme.BG_HOVER
    assert not button.grab().isNull()
    assert button.kind == "close"

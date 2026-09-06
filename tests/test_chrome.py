"""The window's own chrome, and the icon it wears.

The frameless window has to put back by hand everything the system bar was
providing, and every one of those pieces has been wrong at least once: the
icon sliced top and bottom, the menu titles riding along the top edge of a
48px strip, and the floating toggle — the only part of the app on screen
when the window is hidden — drawing its plate and no icon at all.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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


# ---- the floating toggle ------------------------------------------------

def test_the_toggle_draws_its_icon_itself(assets, monkeypatch, qapp):
    """It used to hand the icon to QPushButton, and a translucent frameless
    top-level button under a stylesheet drew the plate and nothing else —
    a blank square as the only thing on screen with the window hidden."""
    monkeypatch.setattr(appicon, "_hero_pixmap", lambda: wide(64, 64, "#20c020"))
    appicon.forget()
    toggle = chrome.OverlayToggle()
    assert not toggle._art.isNull()
    image = toggle.grab().toImage()
    middle = image.pixelColor(toggle.width() // 2, toggle.height() // 2)
    assert middle.green() > 100, "the icon is not being painted"


def test_the_toggle_reads_as_on_or_off(assets, monkeypatch, qapp):
    """Mid-draft the user has to know whether the window is hidden or
    merely behind Dota."""
    monkeypatch.setattr(appicon, "_hero_pixmap", lambda: wide(64, 64))
    appicon.forget()
    toggle = chrome.OverlayToggle()
    toggle.setChecked(True)
    on = toggle.grab().toImage()
    toggle.setChecked(False)
    off = toggle.grab().toImage()
    assert on != off


def test_a_new_icon_reaches_the_toggle_without_a_restart(assets, monkeypatch,
                                                         qapp):
    monkeypatch.setattr(appicon, "_hero_pixmap", lambda: None)
    appicon.forget()
    toggle = chrome.OverlayToggle()
    before = toggle.grab().toImage()
    chosen = assets / "chosen.png"
    wide(64, 64, "#c020c0").save(str(chosen), "PNG")
    appicon.install(chosen)
    toggle.refresh_icon()
    assert toggle.grab().toImage() != before


# ---- preferences that were being dropped on the way to disk -------------

def test_the_transparency_setting_survives_a_restart(tmp_path):
    """`save` writes only the keys DEFAULTS names, so a preference the app
    set but that dict did not know about was kept in memory and lost."""
    path = tmp_path / "ui_settings.json"
    settings = ui_settings.load(path)
    settings["overlay_opacity"] = 0.45
    settings["toggle_x"], settings["toggle_y"] = 900, 300
    ui_settings.save(settings, path)

    again = ui_settings.load(path)
    assert again["overlay_opacity"] == 0.45
    assert (again["toggle_x"], again["toggle_y"]) == (900, 300)

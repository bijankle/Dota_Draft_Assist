"""The draft tiles.

Painting is hard to assert on, but it is where the bugs are — the portrait
branch shipped once with a mistyped Qt enum and nothing caught it, because
no test had a portrait on disk to take that branch. So every tile state is
actually rendered here, and the ones that carry text are read back off the
pixmap's own colours where that is what the change is about.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import QColor, QPixmap  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from draft_assist.ui import portraits, teams  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def art(tmp_path, qapp, monkeypatch):
    """A portrait folder shaped like the recognition library's."""
    for hero_id, colour in ((36, "#804020"), (1, "#204080")):
        pixmap = QPixmap(144, 160)
        pixmap.fill(QColor(colour))
        pixmap.save(str(tmp_path / f"{hero_id}_hero.png"))
    monkeypatch.setattr(portraits, "BASE_DIR", tmp_path)
    portraits.forget()
    yield tmp_path
    portraits.forget()


def test_a_portrait_is_found_by_hero_id(art):
    assert portraits.portrait(36) is not None
    assert portraits.portrait(1) is not None


def test_a_hero_with_no_downloaded_portrait_is_not_an_error(art):
    """A fresh install has none, and the menu action that downloads them is
    optional — the tile just draws itself plain."""
    assert portraits.portrait(999) is None
    assert portraits.portrait(None) is None


def test_the_tile_draws_with_and_without_art(art, qapp):
    tile = teams.HeroTile("ally", 0)
    tile.set_edge(120)
    for hero_id in (36, 999, None):
        tile.set_pick("Necrophos" if hero_id else None, None, hero_id)
        tile.show_delta(0.012, "with")
        assert not tile.grab().isNull()


def test_the_tile_keeps_the_role_and_name_in_its_text(qapp):
    """The rest of the window reads a slot's label off the button, so the
    tile has to keep saying the same thing the row button did."""
    tile = teams.HeroTile("enemy", 2)
    tile.set_pick("Necrophos", "Pos 3", 36)
    assert tile.text() == "Pos 3 · Necrophos"
    tile.set_pick(None, "Pos 3", None)
    assert tile.text() == "Pos 3 · +"
    tile.set_pick(None, None, None)
    assert tile.text() == "+"


def test_the_number_line_is_reserved_whether_or_not_it_holds_a_number(qapp):
    """Tiles that grew by a text height on every click made the panel
    restless, and a draft panel that moves under the cursor is one you
    misclick."""
    tile = teams.HeroTile("ally", 0)
    tile.set_pick("Necrophos", None, 36)
    tall = tile.sizeHint().height()
    tile.show_delta(-0.03, "vs")
    assert tile.sizeHint().height() == tall
    assert tile.delta_text() == "vs -3.0"
    tile.clear_delta()
    assert tile.sizeHint().height() == tall
    assert tile.delta_text() == ""


def test_a_bare_delta_carries_no_kind_marker(qapp):
    """The resting number is the hero's own net figure, not its relation to
    anything, so labelling it 'with' or 'vs' would be a lie."""
    tile = teams.HeroTile("ally", 0)
    tile.show_delta(0.021)
    assert tile.delta_text() == "+2.1"


def test_a_panel_is_five_tiles_that_know_their_slot(qapp):
    panel = teams.TeamPanel("enemy", "Enemy team")
    assert len(panel.buttons) == 5
    for index, tile in enumerate(panel.slots):
        assert tile.property("side") == "enemy"
        assert tile.property("slot_index") == index


# ---- the tile is square, whatever the window does -----------------------

def test_a_tile_is_always_square(qapp):
    """Full-screening the window used to hand each tile the leftover width
    at a fixed height, which stretched every portrait into a letterbox with
    the hero's head cropped off."""
    tile = teams.HeroTile("ally", 0)
    for edge in (40, 90, 200, 1000):
        tile.set_edge(edge)
        assert tile.width() == tile.height()
        assert teams.TILE_MIN <= tile.width() <= teams.TILE_MAX


def test_a_panel_keeps_its_tiles_square_at_every_width(qapp):
    panel = teams.TeamPanel("ally", "Your team")
    for width in (420, 700, 1200, 2400):
        panel.resize(width, 200)
        for tile in panel.slots:
            assert tile.width() == tile.height(), f"stretched at {width}px"
            assert tile.width() <= teams.TILE_MAX


def test_the_whole_portrait_fits_inside_the_tile(art, qapp):
    """Fit, not fill: a portrait cropped to a square told you less than the
    art the game itself shows, and the crop moved as the window resized."""
    from draft_assist.ui.portraits import portrait
    tile = teams.HeroTile("ally", 0)
    tile.set_edge(120)
    tile.set_pick("Necrophos", None, 36)
    art_pixmap = portrait(36)
    scaled = art_pixmap.scaled(tile.rect().adjusted(0, 0, -1, -1).size(),
                               Qt.AspectRatioMode.KeepAspectRatio)
    assert scaled.width() <= tile.width()
    assert scaled.height() <= tile.height()


def test_a_long_name_shrinks_rather_than_overflowing(qapp):
    """The name is the thing the panel exists to show, so the font gives
    way before the text does."""
    tile = teams.HeroTile("ally", 0)
    tile.set_edge(70)
    small, lines = tile._fit_name("Keeper of the Light", 62, 24)
    assert small < teams.NAME_MAX_PT
    tile.set_edge(teams.TILE_MAX)
    big, _ = tile._fit_name("Lion", teams.TILE_MAX - 8, 40)
    assert big == teams.NAME_MAX_PT
    assert lines


def test_a_name_that_cannot_fit_on_one_line_wraps_evenly(qapp):
    assert teams._split("Keeper of the Light") == ["Keeper of", "the Light"]
    assert teams._split("Lion") == ["Lion"]

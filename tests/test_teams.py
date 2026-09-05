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
    tile.resize(120, teams.TILE_HEIGHT)
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

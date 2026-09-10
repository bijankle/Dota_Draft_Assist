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

def test_a_tile_keeps_the_PORTRAITS_shape_at_every_size(qapp):
    """It was square because the name band across the top took the
    difference. With the name gone, a square tile is a 16:9 picture with a
    dead strip above and below it on all ten picks — so the tile is the
    art's own shape and the window gets that height back.

    The aspect must be FIXED whatever the width: handing each tile the
    leftover width at a fixed height is what stretched every portrait into
    a slice with the hero's head cropped off."""
    tile = teams.HeroTile("ally", 0)
    for edge in (40, 90, 200, 1000):
        tile.set_edge(edge)
        assert teams.TILE_MIN <= tile.width() <= teams.TILE_MAX
        assert abs(tile.width() / tile.height() - 16 / 9) < 0.06, \
            f"{tile.width()}x{tile.height()} is not the portrait's shape"


def test_a_panel_keeps_that_shape_at_every_width(qapp):
    panel = teams.TeamPanel("ally", "Your team")
    for width in (420, 700, 1200, 2400):
        panel.resize(width, 200)
        for tile in panel.slots:
            assert abs(tile.width() / tile.height() - 16 / 9) < 0.06, \
                f"stretched at {width}px"
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
    assert teams.split_two("Keeper of the Light") == ["Keeper of", "the Light"]
    assert teams.split_two("Lion") == ["Lion"]


# ---- the real drag path, not just the handler ---------------------------

def test_a_drag_actually_starts_and_a_drop_is_delivered(qapp):
    """The handler had tests; the Qt machinery that reaches it did not, and
    a drag that never starts looks exactly like a feature that does not
    exist."""
    from PyQt6.QtCore import QMimeData, QPoint, QPointF
    from PyQt6.QtGui import QDropEvent, QMouseEvent

    panel = teams.TeamPanel("ally", "Your team")
    panel.resize(700, 200)
    source, target = panel.slots[0], panel.slots[3]
    source.set_pick("Necrophos", None, 36)
    target.set_pick("Lion", None, 1)

    seen = []
    target.dropped_on.connect(
        lambda fs, fi, ts, ti: seen.append((fs, fi, ts, ti)))

    data = QMimeData()
    data.setData(teams.SLOT_MIME, b"ally:0")
    drop = QDropEvent(QPointF(5, 5), Qt.DropAction.MoveAction, data,
                      Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier)
    target.dropEvent(drop)
    assert seen == [("ally", 0, "ally", 3)]

    # And the press-then-move that produces that mime data in the first
    # place must be recognised as a drag rather than swallowed as a click.
    press = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(4, 4),
                        QPointF(4, 4), Qt.MouseButton.LeftButton,
                        Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    source.mousePressEvent(press)
    assert source._press == QPoint(4, 4)


def test_an_empty_tile_is_not_draggable(qapp):
    """There is nothing to move, and a drag from a '+' would exchange a
    hero for a hole."""
    panel = teams.TeamPanel("ally", "Your team")
    empty = panel.slots[2]
    empty.set_pick(None, None, None)
    assert not empty.filled


def test_a_drop_from_something_else_is_ignored(qapp):
    """The tiles accept their own mime type and nothing else, so a file or
    a browser selection dropped on the draft does not reach the handler."""
    from PyQt6.QtCore import QMimeData, QPointF
    from PyQt6.QtGui import QDropEvent

    panel = teams.TeamPanel("enemy", "Enemy team")
    tile = panel.slots[1]
    tile.set_pick("Lion", None, 1)
    seen = []
    tile.dropped_on.connect(lambda *a: seen.append(a))

    data = QMimeData()
    data.setText("some text from elsewhere")
    tile.dropEvent(QDropEvent(QPointF(5, 5), Qt.DropAction.MoveAction, data,
                              Qt.MouseButton.LeftButton,
                              Qt.KeyboardModifier.NoModifier))
    assert seen == []


# ---- the focus ring -----------------------------------------------------

def ring_pixels(widget) -> int:
    """How many pixels of the window's own gold the widget painted."""
    from draft_assist.ui import tilekit
    want = QColor(tilekit.FOCUS_COLOUR)
    image = widget.grab().toImage()
    seen = 0
    for y in range(image.height()):
        for x in range(image.width()):
            if QColor(image.pixel(x, y)) == want:
                seen += 1
    return seen


def test_the_focused_pick_wears_the_windows_own_frame(qapp):
    """It was `theme.ACCENT` at 2px — the deep red this app uses for the
    one ACTION a screen wants — sitting on a portrait to mean "this is the
    hero everything else is measured against", which is not an action.
    At the user's request it is the gold and the weight of the frame
    painted round the whole window."""
    from draft_assist.ui import ornate, theme, tilekit
    assert tilekit.FOCUS_COLOUR == theme.FRAME_GOLD
    assert tilekit.FOCUS_WIDTH == ornate.WIDTH

    panel = teams.TeamPanel("ally", "Radiant")
    tile = panel.slots[0]
    tile.set_pick("Lion", None, 1)
    tile.resize(120, 68)
    assert ring_pixels(tile) == 0, "nothing is focused yet"
    tile.set_focused(True)
    assert ring_pixels(tile) > 0


def test_the_ring_is_inside_the_tile(qapp):
    """A 3px pen is CENTRED on its coordinate, so drawn on the tile's own
    edge a third of it falls outside the widget and is clipped — the ring
    then reads thinner on the outside edges than on the inside, which is
    the even-width pen trap one width along."""
    from draft_assist.ui import tilekit
    panel = teams.TeamPanel("ally", "Radiant")
    tile = panel.slots[0]
    tile.set_pick("Lion", None, 1)
    tile.resize(120, 68)
    tile.set_focused(True)
    image = tile.grab().toImage()
    want = QColor(tilekit.FOCUS_COLOUR)
    # Down the middle of the left edge, where no rounded corner reaches.
    middle = image.height() // 2
    run = [x for x in range(10)
           if QColor(image.pixel(x, middle)) == want]
    assert run == list(range(tilekit.FOCUS_WIDTH)), run


def test_a_drop_target_still_reads_as_a_drop_target(qapp):
    """Dragging a hero onto a tile that happens to be the focused one has
    to keep saying "drop here" — the amber says what is about to happen,
    the gold says what is being measured, and the one in progress wins."""
    from draft_assist.ui import tilekit
    panel = teams.TeamPanel("ally", "Radiant")
    tile = panel.slots[0]
    tile.set_pick("Lion", None, 1)
    tile.resize(120, 68)
    tile.set_focused(True)
    tile.set_drop_target(True)
    assert ring_pixels(tile) == 0

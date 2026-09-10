"""The suggested picks strip.

It is the Analysis tab's ranked list, cut to its head and laid out like the
item strip — same tiles, same order, best on the left. What is checked here
is that it says the same thing as that list, that it stays quiet when there
is nothing to rank, and that it wears the shared tile look rather than one
of its own.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QPixmap                     # noqa: E402
from PyQt6.QtWidgets import QApplication                    # noqa: E402

from draft_assist.ui import portraits, theme, tilekit       # noqa: E402
from draft_assist.ui.item_row import ItemTile               # noqa: E402
from draft_assist.ui.suggest_row import (PLACEHOLDERS,      # noqa: E402
                                         SuggestRow, SuggestTile)


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def art(tmp_path, monkeypatch):
    pixmap = QPixmap(256, 144)
    pixmap.fill(QColor("#3050a0"))
    pixmap.save(str(tmp_path / "1_anti-mage.png"))
    monkeypatch.setattr(portraits, "BASE_DIR", tmp_path)
    portraits.forget()
    yield tmp_path
    portraits.forget()


def rows(count=3):
    return [(1, f"Hero {i}", 0.05 - 0.01 * i, f"why {i}") for i in range(count)]


def test_it_keeps_the_order_it_was_given(qapp):
    """Best draft fit on the left, descending right — the same order the
    ranked list is in, because it IS that list's head."""
    row = SuggestRow()
    row.show_heroes(rows(4))
    assert row.heroes == ["Hero 0", "Hero 1", "Hero 2", "Hero 3"]


def test_the_cap_belongs_to_the_caller_not_the_row(qapp):
    """How many to show is a SETTING, so the row draws what it is handed.

    A second cap in here would silently overrule it: raising Settings to
    twelve and getting eight is a bug with nothing on screen to explain
    it. The caller cuts the ranked list; the row is the layout.
    """
    row = SuggestRow()
    row.show_heroes(rows(13))
    assert len(row.heroes) == 13


def test_it_swaps_its_contents_without_piling_up(qapp):
    """It is rebuilt on every draft change; leaked tiles would grow the
    strip until it pushed the grids off the screen."""
    row = SuggestRow()
    row.show_heroes(rows(4))
    row.show_heroes(rows(2))
    assert row.heroes == ["Hero 0", "Hero 1"]
    row.show_heroes([])
    assert row.heroes == []
    assert len(row._blanks) == PLACEHOLDERS


def test_a_tile_draws_with_and_without_a_portrait(art, qapp):
    """A missing portrait is normal — a fresh install has none."""
    assert not SuggestTile(1, "Anti-Mage", 0.05).grab().isNull()
    assert not SuggestTile(999, "Nobody", -0.05).grab().isNull()


def test_the_fit_is_shown_the_way_a_drafted_tile_shows_it(art, qapp):
    """Same figure, same corner, same colours, so a suggestion and a pick
    can be compared without translating between two layouts."""
    drawn = []
    badges = []
    import draft_assist.ui.suggest_row as strip
    real = strip.QPainter.drawText

    class Spy(strip.QPainter):
        def drawText(self, *args):        # noqa: N802 - Qt naming
            drawn.append(args[-1])
            return real(self, *args)

    real_badge = strip.tilekit.paint_badge

    def spy_badge(painter, box, text, colour, base):
        badges.append((text, colour))
        return real_badge(painter, box, text, colour, base)

    keep, keep_badge = strip.QPainter, strip.tilekit.paint_badge
    strip.QPainter = Spy
    strip.tilekit.paint_badge = spy_badge
    try:
        SuggestTile(1, "Anti-Mage", 0.0542).grab()
    finally:
        strip.QPainter = keep
        strip.tilekit.paint_badge = keep_badge
    # Through `paint_badge` rather than `drawText`: the number is an
    # OUTLINED path now, so that the portrait shows through around it.
    assert ("+5.4", theme.GOOD) in badges
    # And the NAME is not drawn. The picture is the tile: a player who
    # knows the game reads the face faster than four letters, and a row of
    # pictures reads at a glance where a row of labelled pictures reads as
    # a list. The name is the tooltip's job.
    assert "Anti-Mage" not in drawn


def test_the_three_strips_are_one_look(qapp):
    """Items, suggestions and picks were three tile designs; the point of
    `tilekit` is that they cannot drift apart again.

    Same HEIGHT, not the same size: each strip takes its own art's aspect
    — a hero portrait is 16:9 and an item icon is 88x64 — because a tile
    wider than its picture is dead space either side of every icon, which
    reads as the items being spaced further apart than the heroes.
    """
    from draft_assist.model.items import ItemAdvice
    from draft_assist.ui import teams
    suggestion = SuggestTile(1, "Anti-Mage", 0.05)
    item = ItemTile(ItemAdvice(item="Black King Bar", score=1.0,
                               any_stale=False, triggers=[]))
    assert suggestion.height() == item.height()
    assert abs(suggestion.width() / suggestion.height() - 16 / 9) < 0.06
    assert abs(item.width() / item.height() - 88 / 64) < 0.06
    assert teams.NAME_MAX_PT == tilekit.NAME_MAX_PT
    assert teams.CHROME == tilekit.CHROME


def test_without_a_portrait_the_name_comes_back(qapp, monkeypatch):
    """A blank plate names nothing, and a fresh install has no art at all.

    So the band is a FALLBACK rather than gone: no picture, no tile — put
    the name back and the strip still says something.
    """
    import draft_assist.ui.suggest_row as strip
    monkeypatch.setattr(strip, "scaled", lambda *a, **k: None)
    drawn = []
    real = strip.QPainter.drawText

    class Spy(strip.QPainter):
        def drawText(self, *args):        # noqa: N802 - Qt naming
            drawn.append(args[-1])
            return real(self, *args)

    keep = strip.QPainter
    strip.QPainter = Spy
    try:
        tile = SuggestTile(1, "Anti-Mage", 0.0542)
        tile.grab()
    finally:
        strip.QPainter = keep
    assert "Anti-Mage" in drawn
    assert "Anti-Mage" in tile.toolTip()


def test_a_focused_suggestion_wears_the_same_ring_as_a_pick(qapp):
    """One selection, one ring. A suggestion and a pick can each be the
    hero the board is measured against, and two implementations of "draw
    the gold box" is two rings that drift apart."""
    from PyQt6.QtGui import QColor
    from draft_assist.ui import tilekit
    tile = SuggestTile(1, "Anti-Mage", 0.05)
    tile.resize(120, 68)

    def gold() -> int:
        image = tile.grab().toImage()
        want = QColor(tilekit.FOCUS_COLOUR)
        return sum(QColor(image.pixel(x, y)) == want
                   for y in range(image.height())
                   for x in range(image.width()))

    assert gold() == 0
    tile.set_focused(True)
    assert gold() > 0


def test_a_suggestion_shows_a_relation_instead_of_its_fit(qapp):
    """Instead, not beside: two numbers in one corner is two numbers to
    tell apart at a glance, which is what both grids dropped their totals
    for."""
    tile = SuggestTile(1, "Anti-Mage", 0.05)
    assert tile.delta_text() == ""
    tile.show_delta(0.052, "with")
    assert tile.delta_text() == "with +5.2"
    tile.show_delta(-0.018, "vs")
    assert tile.delta_text() == "vs -1.8"
    tile.clear_delta()
    assert tile.delta_text() == ""


def test_the_row_hands_the_numbers_round_and_takes_them_back(qapp):
    """And a candidate the dataset has nothing to say about keeps its own
    fit rather than going blank — a hole in the strip reads as the tile
    being broken."""
    row = SuggestRow()
    row.show_heroes([(1, "Anti-Mage", 0.05, ""), (2, "Axe", 0.04, ""),
                     (3, "Bane", 0.03, "")])
    assert row.hero_ids == [1, 2, 3]
    row.show_deltas({1: (0.02, "with"), 3: (-0.01, "vs")})
    assert [t.delta_text() for t in row.tiles] == ["with +2.0", "", "vs -1.0"]
    row.set_focus(2)
    assert [t.focused for t in row.tiles] == [False, True, False]
    row.clear_deltas()
    assert not any(t.delta_text() for t in row.tiles)
    assert not any(t.focused for t in row.tiles)


def test_a_starred_suggestion_wears_the_frames_gold(qapp):
    """The third thing in this app in that colour, beside the window's
    border and the focus ring — all three mean "this one" rather than
    "this is good", which green and red are already spoken for."""
    from PyQt6.QtGui import QColor
    from draft_assist.ui import tilekit
    tile = SuggestTile(1, "Anti-Mage", 0.05)
    tile.resize(120, 68)

    def gold() -> int:
        image = tile.grab().toImage()
        want = QColor(tilekit.FOCUS_COLOUR)
        return sum(QColor(image.pixel(x, y)) == want
                   for y in range(image.height())
                   for x in range(image.width()))

    assert gold() == 0
    tile.set_star(True, "40 games at 65%")
    assert gold() > 0
    assert tile.starred
    tile.set_star(False)
    assert gold() == 0


def test_the_star_keeps_out_of_the_numbers_corner(qapp):
    """The bottom-right is the fit's and the whole border is the focus
    ring's, so the top right is the one corner with nothing in it."""
    from PyQt6.QtCore import QRect
    from draft_assist.ui import tilekit
    box = QRect(0, 0, 120, 68)
    star = tilekit.star_box(box)
    assert star.right() < box.right() and star.top() > box.top()
    assert star.bottom() < box.height() // 2, "top half, clear of the badge"
    # It scales with the tile and stops scaling before it eats one.
    small = tilekit.star_box(QRect(0, 0, 48, 27)).width()
    huge = tilekit.star_box(QRect(0, 0, 600, 338)).width()
    assert tilekit.STAR_MIN_PX <= small < huge == tilekit.STAR_MAX_PX


def test_the_reason_rides_in_the_tooltip_beside_the_rest(qapp):
    """Not on the tile: the star's job is to be seen without being read,
    and a figure beside it would be a third number in a corner that
    already has the fit in it."""
    tile = SuggestTile(1, "Anti-Mage", 0.05, "Anti-Mage\nfit +5.00")
    tile.set_star(True, "40 games at 65%, inside the top 30% by picks.")
    assert "fit +5.00" in tile.toolTip()
    assert "40 games at 65%" in tile.toolTip()
    tile.show_delta(0.02, "with")
    assert "with +2.0" in tile.toolTip(), "the relation is still there"
    assert "40 games at 65%" in tile.toolTip(), "and so is the star's"


def test_the_row_stars_from_a_measurement(qapp):
    from draft_assist.history import stars as stars_mod
    from dataclasses import dataclass

    @dataclass
    class Played:
        hero_id: int
        win: bool

    matches = ([Played(1, True)] * 20 + [Played(1, False)] * 10
               + [Played(2, False)] * 20 + [Played(3, True)] * 2)
    row = SuggestRow()
    row.show_heroes([(1, "Anti-Mage", 0.05, ""), (2, "Axe", 0.04, ""),
                     (3, "Bane", 0.03, "")])
    row.set_stars(stars_mod.measure(matches, 50, 50))
    assert [t.starred for t in row.tiles] == [True, False, False]
    # No run loaded draws the same as a run that starred nobody, because
    # there is nothing honest to put on a tile either way.
    row.set_stars(None)
    assert not any(t.starred for t in row.tiles)

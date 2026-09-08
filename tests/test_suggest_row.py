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

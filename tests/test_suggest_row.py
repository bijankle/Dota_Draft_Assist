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

from draft_assist.ui import portraits, tilekit              # noqa: E402
from draft_assist.ui.item_row import ItemTile               # noqa: E402
from draft_assist.ui.suggest_row import (MAX_SHOWN,         # noqa: E402
                                         PLACEHOLDERS, SuggestRow,
                                         SuggestTile)


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


def test_it_is_capped(qapp):
    row = SuggestRow()
    row.show_heroes(rows(MAX_SHOWN + 5))
    assert len(row.heroes) == MAX_SHOWN


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
    import draft_assist.ui.suggest_row as strip
    real = strip.QPainter.drawText

    class Spy(strip.QPainter):
        def drawText(self, *args):        # noqa: N802 - Qt naming
            drawn.append(args[-1])
            return real(self, *args)

    keep = strip.QPainter
    strip.QPainter = Spy
    try:
        SuggestTile(1, "Anti-Mage", 0.0542).grab()
    finally:
        strip.QPainter = keep
    assert "+5.4" in drawn
    assert "Anti-Mage" in drawn


def test_the_three_strips_are_one_look(qapp):
    """Items, suggestions and picks were three tile designs; the point of
    `tilekit` is that they cannot drift apart again."""
    from draft_assist.model.items import ItemAdvice
    from draft_assist.ui import teams
    suggestion = SuggestTile(1, "Anti-Mage", 0.05)
    item = ItemTile(ItemAdvice(item="Black King Bar", score=1.0,
                               any_stale=False, triggers=[]))
    assert suggestion.size() == item.size()
    assert teams.NAME_MAX_PT == tilekit.NAME_MAX_PT
    assert teams.CHROME == tilekit.CHROME

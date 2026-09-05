"""The item strip under the draft.

The strip exists because items as prose in a side panel, gated behind
locking your own pick, were blank on the screen where they mattered. So
what is checked here is that it shows something useful early, that a
missing icon costs nothing, and that the reasoning is still reachable.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QPixmap  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from draft_assist.model.items import ItemAdvice, Trigger  # noqa: E402
from draft_assist.ui import item_icons  # noqa: E402
from draft_assist.ui.item_row import ItemRow, ItemTile  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def advice(item="Black King Bar", severity=3, stale=False):
    return ItemAdvice(item=item, score=1.0, any_stale=stale,
                      triggers=[Trigger(hero="Lion", severity=severity,
                                        reason="Lion chains disables",
                                        stale=stale)])


@pytest.fixture()
def icons(tmp_path, monkeypatch):
    pixmap = QPixmap(88, 64)
    pixmap.fill(QColor("#804020"))
    pixmap.save(str(tmp_path / "black_king_bar.png"))
    monkeypatch.setattr(item_icons, "ITEMS_DIR", tmp_path)
    item_icons.forget()
    yield tmp_path
    item_icons.forget()


def test_the_icon_is_found_by_the_display_name(icons, qapp):
    """The rules file says "Black King Bar" because a person wrote it;
    making it carry an internal key would be making the file worse to suit
    the loader."""
    assert item_icons.slug("Black King Bar") == "black_king_bar"
    assert item_icons.icon("Black King Bar") is not None


def test_an_item_with_no_downloaded_icon_is_not_an_error(icons, qapp):
    """A fresh install has none, and a rule can name something OpenDota
    does not list."""
    assert item_icons.icon("Some Item That Does Not Exist") is None
    tile = ItemTile(advice("Some Item That Does Not Exist"))
    assert not tile.grab().isNull()      # draws the name instead


def test_a_tile_draws_with_its_icon(icons, qapp):
    assert not ItemTile(advice()).grab().isNull()


def test_the_reasoning_is_in_the_tooltip_not_the_strip(icons, qapp):
    """A strip that explained itself in place would be the paragraph this
    replaced."""
    tip = ItemTile(advice()).toolTip()
    assert "Lion chains disables" in tip
    assert "Hand-authored" in tip


def test_a_stale_rule_says_so(icons, qapp):
    assert "unverified" in ItemTile(advice(stale=True)).toolTip()


def test_the_row_swaps_its_contents_without_piling_up(icons, qapp):
    """It is rebuilt on every draft change, so leaked tiles would grow the
    strip until it pushed the grids off the screen."""
    row = ItemRow()
    row.show_items([advice("A"), advice("B"), advice("C")], "none")
    assert row.items == ["A", "B", "C"]
    row.show_items([advice("D")], "none")
    assert row.items == ["D"]
    row.show_items([], "nothing to flag")
    assert row.items == []
    assert row.message.text() == "nothing to flag"


def test_the_strip_is_capped_so_it_cannot_run_off_the_window(icons, qapp):
    from draft_assist.ui.item_row import MAX_SHOWN
    row = ItemRow()
    row.show_items([advice(f"Item {i}") for i in range(MAX_SHOWN + 6)], "none")
    assert len(row.items) == MAX_SHOWN

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
from draft_assist.ui import tilekit
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
    replaced.

    The "Hand-authored" signature that used to be asserted here was cut
    at the user's request - see `reasons.item_reasons`. What the tip
    must still carry is the REASON and the hero that triggered it.
    """
    tip = ItemTile(advice()).toolTip()
    assert "Lion chains disables" in tip
    assert "Lion |" in tip
    assert "Hand-authored" not in tip


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


def test_it_cannot_run_off_the_window_because_it_WRAPS(icons, qapp):
    """It used to cap at eight so a long strip could not overflow, and the
    cap silently overruled the user's setting. Wrapping removes the need:
    the strip is one tile wide at its narrowest and as tall as the rows it
    needs, so every tile is on screen at any window width."""
    row = ItemRow()
    row.show_items([advice(f"Item {i}") for i in range(14)], "none")
    assert len(row.items) == 14
    assert row.minimumSizeHint().width() <= tilekit.STRIP_W + 4
    tall = row.layout().heightForWidth(tilekit.STRIP_W * 3)
    wide = row.layout().heightForWidth(tilekit.STRIP_W * 14 + 200)
    assert tall > wide, "a narrow strip must use more rows, not scroll"


def test_a_long_item_name_shrinks_and_wraps_rather_than_being_cut(icons, qapp):
    """A long item name in a strip tile is the same problem as "Keeper of
    the Light" in a hero tile, so it gets the same answer."""
    from draft_assist.ui.item_row import ICON_W, NAME_H, NAME_MAX_PT
    from draft_assist.ui.textfit import fit
    long_name = "Eul's Scepter of Divinity"
    tile = ItemTile(advice(long_name))
    size, lines = fit(long_name, ICON_W - 2, NAME_H - 3, tile.font(),
                      NAME_MAX_PT, 7, bold=True)
    assert size <= NAME_MAX_PT
    assert len(lines) == 2          # wrapped, not truncated
    assert "".join(lines).replace(" ", "") == long_name.replace(" ", "")


def test_an_item_with_no_icon_shows_its_name_once(icons, qapp):
    """An earlier version drew the name in the picture's place AND kept the
    label underneath, so a missing icon showed the name twice."""
    import draft_assist.ui.item_row as row_mod
    drawn = []
    real = row_mod.QPainter.drawText

    class Spy(row_mod.QPainter):
        def drawText(self, *args):        # noqa: N802 - Qt naming
            drawn.append(args[-1])
            return real(self, *args)

    monkey = row_mod.QPainter
    row_mod.QPainter = Spy
    try:
        ItemTile(advice("Nothing Downloaded")).grab()
    finally:
        row_mod.QPainter = monkey
    # ONCE. It used to be drawn in a band AND under the art. At a tile
    # this size a long name elides — the tooltip carries the whole of it —
    # so what is checked is that it is drawn, and drawn once.
    named = [text for text in drawn
             if isinstance(text, str) and text.startswith("Noth")]
    assert len(named) == 1, f"the name was drawn {len(named)} times"


def test_the_icon_resolves_through_a_longer_published_name(tmp_path,
                                                           monkeypatch, qapp):
    """The rules say "Eul's Scepter"; the published item is "Eul's Scepter
    of Divinity". A unique prefix resolves rather than making the rules
    file carry the long form."""
    from PyQt6.QtGui import QColor, QPixmap
    pixmap = QPixmap(88, 64)
    pixmap.fill(QColor("#204080"))
    pixmap.save(str(tmp_path / "eul_s_scepter_of_divinity.png"))
    monkeypatch.setattr(item_icons, "ITEMS_DIR", tmp_path)
    item_icons.forget()
    assert item_icons.icon("Eul's Scepter") is not None
    item_icons.forget()


def test_two_matching_prefixes_resolve_to_nothing(tmp_path, monkeypatch, qapp):
    """Guessing between two items is worse than showing the name."""
    from PyQt6.QtGui import QColor, QPixmap
    for stem in ("blade_mail", "blade_of_alacrity"):
        pixmap = QPixmap(8, 8)
        pixmap.fill(QColor("#111111"))
        pixmap.save(str(tmp_path / f"{stem}.png"))
    monkeypatch.setattr(item_icons, "ITEMS_DIR", tmp_path)
    item_icons.forget()
    assert item_icons.icon("Blade") is None
    item_icons.forget()


def test_the_strip_says_when_no_icons_have_been_downloaded(qapp):
    """One missing icon is normal; none at all means the pack was never
    fetched, and a row of grey plates looks broken rather than unconfigured."""
    row = ItemRow()
    row.set_note("No item icons yet — run Data ▸ Update statistics.")
    assert row.note.isVisible() or row.note.text()
    row.set_note("")
    assert not row.note.text()


def test_a_tile_with_no_picture_says_which_of_the_four_causes(qapp,
                                                              monkeypatch,
                                                              tmp_path):
    """"Eul's still doesn't have artwork" cannot be answered from the
    picture: the download 404'd, the rules name an item OpenDota does not
    list, the name matches two icons and is refused, or the file will not
    decode. All four draw the name."""
    from draft_assist.ui import item_icons

    monkeypatch.setattr(item_icons, "ITEMS_DIR", tmp_path)
    item_icons.forget()
    assert "downloaded yet" in item_icons.why_missing("Eul's Scepter")

    (tmp_path / "black_king_bar.png").write_bytes(b"")
    item_icons.forget()
    assert "failed for it" in item_icons.why_missing("Eul's Scepter")

    (tmp_path / "eul_s_scepter_of_divinity.png").write_bytes(b"")
    (tmp_path / "eul_s_scepter_recipe.png").write_bytes(b"")
    item_icons.forget()
    assert "refused" in item_icons.why_missing("Eul's Scepter")

    (tmp_path / "eul_s_scepter_recipe.png").unlink()
    item_icons.forget()
    assert "will not decode" in item_icons.why_missing("Eul's Scepter")
    item_icons.forget()

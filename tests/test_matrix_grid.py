"""The two grids: their portrait headers, and what they draw when empty.

Both faults here were invisible to every test that only asked what the
numbers were. The headers scale from different measurements — a column
section is (stretched width) x (fixed header height), a row section is
(fixed header width) x (row height) — so without one shared box a wide
window grows one axis' portraits and not the other's. And an empty grid
used to hide itself, which moved everything below it.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QPixmap                     # noqa: E402
from PyQt6.QtWidgets import QApplication                    # noqa: E402

from draft_assist.model.scoring import Matrix               # noqa: E402
from draft_assist.ui import portraits                       # noqa: E402
from draft_assist.ui.tables import (HEADER_ICON,            # noqa: E402
                                    HEADER_ICON_MAX, BLANK_SIDE,
                                    MatrixTable, PortraitHeader)

HEROES = [(1, "Anti-Mage"), (2, "Axe"), (3, "Bane"), (4, "Bloodseeker"),
          (5, "Crystal Maiden")]


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def art(tmp_path, monkeypatch):
    """Portraits on disk, at the shape Dota publishes them: 256x144."""
    for hero_id, name in HEROES:
        pixmap = QPixmap(256, 144)
        pixmap.fill(QColor("#3050a0"))
        pixmap.save(str(tmp_path / f"{hero_id}_{name.lower()}.png"))
    monkeypatch.setattr(portraits, "BASE_DIR", tmp_path)
    portraits.forget()
    yield tmp_path
    portraits.forget()


def grid() -> Matrix:
    return Matrix(rows=list(HEROES), cols=list(HEROES),
                  cells=[[0.01 * (r + c) for c in range(5)] for r in range(5)])


def built(qapp, width=700) -> MatrixTable:
    table = MatrixTable()
    table.set_compact(True, short_names=False)
    table.set_icon_headers(True)
    table.set_margins(False)
    table.resize(width, 400)
    table.show()                    # geometry is not applied until shown
    QApplication.processEvents()
    table.show_matrix(grid())
    QApplication.processEvents()
    return table


def boxes(table: MatrixTable) -> tuple[int, int]:
    return (table.table.horizontalHeader().box,
            table.table.verticalHeader().box)


def drawn(table: MatrixTable) -> tuple[tuple, tuple]:
    """The size of the portrait each header actually puts on screen.

    Computed the way `paintSection` does, from the section it is handed —
    which is the whole point: the two sections are shaped differently and
    the pictures still have to come out the same.
    """
    from draft_assist.ui.portraits import scaled
    inner = table.table
    hero = next(iter(inner.horizontalHeader().heroes.values()))
    column = scaled(hero, min(inner.horizontalHeader().box,
                              inner.columnWidth(0)),
                    inner.horizontalHeader().height())
    row = scaled(hero, min(inner.verticalHeader().box,
                           inner.verticalHeader().width()),
                 inner.rowHeight(0))
    return ((column.width(), column.height()), (row.width(), row.height()))


def test_both_headers_draw_the_same_portrait(art, qapp):
    """The complaint was that widening the window grew one axis' portraits
    and left the other alone."""
    table = built(qapp)
    across, down = boxes(table)
    assert across == down
    assert drawn(table)[0] == drawn(table)[1]


def test_the_sections_are_cut_to_what_they_draw(art, qapp):
    """A portrait is 256x144, so a square header section would be 40%
    empty space and every row 40% too tall."""
    table = built(qapp)
    width, height = drawn(table)[0]
    assert table.table.horizontalHeader().height() == height + 4
    assert table.table.verticalHeader().width() == width + 4
    assert table.table.rowHeight(0) == height + 4


def test_a_wider_window_grows_both_or_neither(art, qapp):
    narrow = built(qapp, width=340)
    wide = built(qapp, width=1400)
    assert boxes(narrow)[0] == boxes(narrow)[1]
    assert boxes(wide)[0] == boxes(wide)[1]
    assert boxes(wide)[0] > boxes(narrow)[0], "a wide grid should use the room"
    assert boxes(wide)[0] <= HEADER_ICON_MAX


def test_the_portraits_are_never_smaller_than_the_floor(art, qapp):
    table = built(qapp, width=200)
    assert boxes(table) == (HEADER_ICON, HEADER_ICON)


def test_with_no_portraits_the_headers_stay_at_the_floor(qapp, monkeypatch,
                                                          tmp_path):
    """Names, not pictures — and a 68px row header elides "Tidehunter"
    while making every row 68px tall for nothing."""
    monkeypatch.setattr(portraits, "BASE_DIR", tmp_path)
    portraits.forget()
    table = built(qapp, width=1400)
    assert boxes(table) == (HEADER_ICON, HEADER_ICON)
    portraits.forget()


def test_the_header_paints_the_portrait_itself(art, qapp):
    """Qt will not: a QHeaderView under a stylesheet ignores iconSize."""
    table = built(qapp)
    header = table.table.horizontalHeader()
    assert isinstance(header, PortraitHeader)
    assert header.heroes, "no hero ids reached the header"
    assert not table.table.grab().isNull()


def test_an_empty_grid_is_an_outline_not_a_hole(qapp):
    """A card that vanishes until the draft fills in moves everything under
    it; the shape of the answer is itself information."""
    table = MatrixTable()
    table.set_icon_headers(True)
    table.show_matrix(Matrix(rows=[], cols=[], cells=[]), "Fill in both teams.")
    assert not table.table.isHidden()
    assert table.table.rowCount() == BLANK_SIDE
    assert table.table.columnCount() == BLANK_SIDE
    assert table.empty_note.text() == "Fill in both teams."


def test_every_cell_has_a_border(art, qapp):
    """The numbers were meant to be the structure, and across five columns
    of signed deltas they are not — the eye loses which column it is in.
    The lines are on for the filled grid and the empty outline alike, so
    there is no per-state stylesheet to keep in step."""
    from draft_assist.ui import theme
    assert f"gridline-color: {theme.BORDER}" in theme.STYLESHEET
    table = built(qapp)
    assert "gridline-color" not in table.table.styleSheet(), \
        "no local override: the app-wide rule is the only one"
    assert table.table.showGrid()

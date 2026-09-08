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


def test_the_two_headers_agree_at_every_width(art, qapp):
    """Both or neither, always. The complaint that started this was a wide
    window growing one axis' portraits and leaving the other alone.

    The columns are SNUG now — cut to the picture rather than stretched to
    the card — so the portrait settles at a size of its own instead of
    following the window up. What has to hold at every width is that the
    two axes land on the same one."""
    sizes = set()
    for width in (200, 340, 700, 1400):
        table = built(qapp, width=width)
        across, down = boxes(table)
        assert across == down, f"at {width}: {across} vs {down}"
        sizes.add(across)
    assert len(sizes) == 1, f"the size should not chase the window: {sizes}"
    # THE NUMBER SETS THE FLOOR, not HEADER_ICON_MAX: a column has to print
    # "+12.34" whatever the portrait would have liked to be, so the picture
    # is whichever of the two is bigger.
    table = built(qapp, width=1400)
    digits = table.table.fontMetrics().horizontalAdvance("+12.34") + 10
    assert boxes(table)[0] == max(HEADER_ICON_MAX, digits - 4)


def test_the_portraits_are_never_smaller_than_the_floor(art, qapp):
    """Squeezed, they shrink; there is a size below which a portrait is not
    worth drawing at all and the headers stop there."""
    table = built(qapp, width=200)
    across, down = boxes(table)
    assert across == down
    assert across >= HEADER_ICON


def test_the_columns_are_snug_and_the_slack_is_on_the_right(art, qapp):
    """The rows were already the height of the picture in them; the columns
    stretched to the card, so there was a gap between every pair of columns
    and none between any pair of rows. Fixed to the portrait, the table has
    a width of its own — and it is aligned LEFT, so the grid still begins
    under the heading above it."""
    from PyQt6.QtCore import Qt
    table = built(qapp, width=1400)
    inner = table.table
    drawn_w = drawn(table)[0][0]
    for col in range(5):
        assert inner.columnWidth(col) == drawn_w + 4
    assert inner.width() < table.width(), "the table still fills the card"
    assert inner.x() < 20, "the slack should all be on the right"
    align = table.layout().itemAt(table.layout().indexOf(inner)).alignment()
    assert align & Qt.AlignmentFlag.AlignLeft


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


# --------------------------------------------------------------------------
# The synergy grid: both teams, as the two triangles of one square.
# --------------------------------------------------------------------------

def test_a_pair_cell_actually_draws_its_portrait_and_number(qapp, tmp_path,
                                                            monkeypatch):
    """RENDER the portrait branch, don't just assert about the data.

    This grid's whole point is a picture behind a figure, and the portrait
    branch of a painter is exactly the kind of code that ships with a
    mistyped enum and no test to catch it — there is no portrait on disk in
    a dev checkout, so nothing takes that branch by accident.
    """
    from PyQt6.QtCore import QRect, Qt
    from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
    from PyQt6.QtWidgets import QStyleOptionViewItem, QTableWidget, \
        QTableWidgetItem
    from draft_assist.ui import portraits, theme
    from draft_assist.ui.tables import PAIR_HERO, PAIR_VALUE, PairCellDelegate

    blue = QPixmap(256, 144)
    blue.fill(QColor("#3050a0"))
    blue.save(str(tmp_path / "1_anti-mage.png"))
    monkeypatch.setattr(portraits, "BASE_DIR", tmp_path)
    portraits.forget()
    try:
        table = QTableWidget(1, 1)
        item = QTableWidgetItem()
        item.setData(PAIR_HERO, 1)
        item.setData(PAIR_VALUE, 0.0421)
        table.setItem(0, 0, item)

        picture = QImage(90, 40, QImage.Format.Format_ARGB32)
        picture.fill(0)
        painter = QPainter(picture)
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 90, 40)
        PairCellDelegate(table).paint(painter, option,
                                      table.model().index(0, 0))
        painter.end()

        colours = {picture.pixelColor(x, y).name()
                   for y in range(picture.height())
                   for x in range(picture.width())}
        # Drawn, and knocked back rather than at full strength.
        assert "#3050a0" not in colours, "the veil never went on"
        assert any(c.startswith("#1") or c.startswith("#2") for c in colours)
        assert theme.GOOD in colours, "the number is not on top of it"
        assert "#000000" in colours, "no outline round the digits"
        assert picture.pixelColor(2, 2).alpha() == 255, "unpainted cell"
    finally:
        portraits.forget()


def test_the_cell_portrait_is_the_same_shape_as_the_header_above_it(qapp,
                                                                    tmp_path,
                                                                    monkeypatch):
    """Fitted, never filled. Covering the cell instead threw away the top
    and bottom of a 16:9 head shot — a cell is wider than it is tall — and
    left a wide slice of the middle that read as stretched."""
    from PyQt6.QtGui import QColor, QPixmap
    from draft_assist.ui import portraits

    wide = QPixmap(256, 144)
    wide.fill(QColor("#3050a0"))
    wide.save(str(tmp_path / "1_anti-mage.png"))
    monkeypatch.setattr(portraits, "BASE_DIR", tmp_path)
    portraits.forget()
    try:
        art = portraits.scaled(1, 120, 40)
        assert art is not None
        # The portrait's own 16:9, not the cell's shape.
        assert abs(art.width() / art.height() - 256 / 144) < 0.05
        assert art.height() <= 40 and art.width() <= 120
    finally:
        portraits.forget()


def _render_pair_cell(table, row, col, size=(90, 40)):
    """One cell of a pair grid, painted into an image we can look at."""
    from PyQt6.QtCore import QRect
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QStyleOptionViewItem
    from draft_assist.ui.tables import PairCellDelegate

    picture = QImage(size[0], size[1], QImage.Format.Format_ARGB32)
    picture.fill(0)
    painter = QPainter(picture)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, size[0], size[1])
    PairCellDelegate(table).paint(painter, option,
                                  table.model().index(row, col))
    painter.end()
    return picture


def test_each_triangle_is_outlined_in_its_own_colour(qapp):
    """Two triangles that touch need a line saying which is which, traced
    per cell from its neighbours — which gives the stepped diagonal in
    both colours for free.

    The sides are ALLY and ENEMY here, not Radiant and Dire: which team is
    which side is something only the UI knows, so the colours are set from
    outside and default to your own team green."""
    from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
    from draft_assist.ui import theme
    from draft_assist.ui.tables import PAIR_SIDE

    # Yours in the lower left, theirs in the upper right.
    table = QTableWidget(2, 3)
    for row, col, side in ((0, 0, "ally"), (0, 1, "enemy"),
                           (0, 2, "enemy"), (1, 0, "ally"),
                           (1, 1, "ally"), (1, 2, "enemy")):
        item = QTableWidgetItem()
        item.setData(PAIR_SIDE, side)
        table.setItem(row, col, item)

    def colours(row, col):
        picture = _render_pair_cell(table, row, col)
        return {picture.pixelColor(x, y).name()
                for y in range(picture.height())
                for x in range(picture.width())}

    # An outside edge: the top row borders the header either way.
    assert theme.GOOD in colours(0, 0), "no green round your triangle"
    assert theme.BAD in colours(0, 1), "no red round theirs"
    # And where they meet, each side draws its own half of the boundary.
    assert theme.GOOD in colours(1, 1)
    assert theme.BAD in colours(1, 2)


def test_the_outline_colour_follows_the_side_the_player_is_on(qapp):
    """Radiant is green and Dire is red — Dota's own colours — so which of
    ally and enemy gets which changes with the match. Nothing below the UI
    knows the answer, so it is set from outside."""
    from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
    from draft_assist.ui import theme
    from draft_assist.ui.tables import MatrixTable, PAIR_SIDE

    grid = MatrixTable()
    grid.set_icon_headers(True)
    grid.set_team_colours(theme.BAD, theme.GOOD)      # the player is Dire
    table = QTableWidget(1, 1)
    item = QTableWidgetItem()
    item.setData(PAIR_SIDE, "ally")
    table.setItem(0, 0, item)

    from PyQt6.QtCore import QRect
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QStyleOptionViewItem
    picture = QImage(90, 40, QImage.Format.Format_ARGB32)
    picture.fill(0)
    painter = QPainter(picture)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 90, 40)
    grid._pair_delegate().paint(painter, option, table.model().index(0, 0))
    painter.end()
    seen = {picture.pixelColor(x, y).name()
            for y in range(picture.height()) for x in range(picture.width())}
    assert theme.BAD in seen, "your own team on Dire should be outlined red"
    assert theme.GOOD not in seen


def test_the_counters_headers_are_boxed_by_team(art, qapp):
    """Your five DOWN the side against their five ACROSS the top, and
    nothing said which was which — the numbers read from your point of view
    either way, so the grid looked symmetrical while meaning two different
    things by its axes."""
    from draft_assist.ui import theme
    table = built(qapp)
    table.set_team_colours(theme.GOOD, theme.BAD)
    assert table.table.horizontalHeader().outline == theme.BAD
    assert table.table.verticalHeader().outline == theme.GOOD
    # An outline round five blank sections would be a claim about heroes
    # nobody has picked.
    table.show_matrix(Matrix(rows=[], cols=[], cells=[]))
    assert table.table.horizontalHeader().outline == ""


def test_a_cell_in_the_middle_of_a_triangle_has_no_outline(qapp):
    """Only the boundary is traced. Outlining every cell would be a grid
    of green and red boxes, which says nothing about where one team's
    half ends."""
    from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
    from draft_assist.ui import theme
    from draft_assist.ui.tables import PAIR_SIDE

    table = QTableWidget(3, 3)
    for row in range(3):
        for col in range(3):
            item = QTableWidgetItem()
            item.setData(PAIR_SIDE, "radiant")
            table.setItem(row, col, item)
    picture = _render_pair_cell(table, 1, 1)
    colours = {picture.pixelColor(x, y).name()
               for y in range(picture.height())
               for x in range(picture.width())}
    assert theme.GOOD not in colours


def test_the_axis_rows_are_full_brightness_and_carry_a_total(qapp, tmp_path,
                                                             monkeypatch):
    """The two header rows ARE the subject — they name the ten heroes the
    card is about — so they are not knocked back the way a cell behind a
    number is. Each carries that hero's synergy with its own four."""
    from PyQt6.QtGui import QColor, QPixmap
    from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
    from draft_assist.ui import portraits, theme
    from draft_assist.ui.tables import PAIR_HEADER, PAIR_HERO, PAIR_VALUE

    blue = QPixmap(256, 144)
    blue.fill(QColor("#3050a0"))
    blue.save(str(tmp_path / "1_anti-mage.png"))
    monkeypatch.setattr(portraits, "BASE_DIR", tmp_path)
    portraits.forget()
    try:
        table = QTableWidget(1, 2)
        for col, header in ((0, False), (1, True)):
            item = QTableWidgetItem()
            item.setData(PAIR_HERO, 1)
            item.setData(PAIR_VALUE, 0.0421)
            if header:
                item.setData(PAIR_HEADER, True)
            table.setItem(0, col, item)

        def colours(col):
            picture = _render_pair_cell(table, 0, col)
            return {picture.pixelColor(x, y).name()
                    for y in range(picture.height())
                    for x in range(picture.width())}

        body, axis = colours(0), colours(1)
        assert "#3050a0" not in body, "a cell behind a number is veiled"
        assert "#3050a0" in axis, "the axis row was knocked back too"
        # And the total is printed on it, in the same badge as everything.
        assert theme.GOOD in axis
        assert "#000000" in axis, "no outline round the digits"
    finally:
        portraits.forget()


def test_a_heros_total_is_its_four_pairs_not_a_row_of_the_grid(qapp):
    """A hero's pairs are split between a row and a column of its own
    triangle, so summing what is DRAWN in either direction alone gives a
    partial answer. The header number adds the four pairs it is in."""
    from draft_assist.model import scoring
    from draft_assist.ui.demo import demo_dataset

    ds = demo_dataset()
    allies, enemies = ds.hero_ids[:5], ds.hero_ids[5:10]
    grid = scoring.team_synergy_grid(
        ds, scoring.DraftState(allies=allies, enemies=enemies))
    for team, totals in ((allies, grid.ally_totals),
                         (enemies, grid.enemy_totals)):
        for hero in team:
            expected = sum(float(ds.delta_with[ds.index[hero], ds.index[other]])
                           for other in team if other != hero)
            assert totals[hero] == pytest.approx(expected)

"""THE SAME DRAFT AS TEXT, IN BANDS (the Visual | Simplified switch).

At the user's request, across three messages. First the view: "a
spreadsheet view where it's just like simple data tables... it's got
what's been drafted, what the recommended hero selection is, what the
synergies are", "hero names in text instead of any portraits", "off by
default", "once you toggle to it it should be remembered". Then the
shape, chosen from five previews - "go with A, show as many as fit is
fine" - with the switch "at top corner", the three board buttons on the
page, no Pos column, the totals at the table size, and every card
collapsible "and you remember the last state".

Every one of those clauses is a test here, and so is the property that
holds the whole thing up: the two views never compute a figure twice,
so they cannot disagree about one.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ast  # noqa: E402
from pathlib import Path  # noqa: E402

from PyQt6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QFont, QWheelEvent  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QAbstractItemView, QApplication  # noqa: E402

from draft_assist.config import RULES_FILE  # noqa: E402
from draft_assist.model import items as items_mod  # noqa: E402
from draft_assist.model import scoring  # noqa: E402
from draft_assist.ui import settings as ui_settings  # noqa: E402
from draft_assist.ui import chrome, simpleview, theme, tilekit  # noqa: E402
from draft_assist.ui.app import MainWindow  # noqa: E402
from draft_assist.ui.demo import demo_dataset  # noqa: E402
from draft_assist.ui.providers import DemoProvider  # noqa: E402

SOURCE = Path(simpleview.__file__)
# The owner's own window, which is what "fits in one view" is measured
# against.
OWN_W, OWN_H = 940, 895


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def styled(qapp):
    was = qapp.styleSheet()
    qapp.setStyleSheet(theme.STYLESHEET)
    yield qapp
    qapp.setStyleSheet(was)


def _build(qapp):
    ds = demo_dataset()
    provider = DemoProvider(ds)
    provider.draft.started -= 45       # fully drafted, short of the restart
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, provider, rules, meta)
    win.timer.stop()
    return win


def _settle(n=6):
    for _ in range(n):
        QApplication.processEvents()


@pytest.fixture()
def window(qapp):
    win = _build(qapp)
    yield win
    win.close()


@pytest.fixture()
def simple(styled, window):
    """A shown window at the owner's own size, switched to the simplified
    view with the board drawn."""
    window.resize(OWN_W, OWN_H)
    window.show()
    _settle()
    window.refresh()
    window._set_simple_view(True)
    window.refresh()
    _settle()
    return window


def _column(table, index):
    return [table.item(r, index).text() if table.item(r, index) else ""
            for r in range(table.rowCount())]


def _headers(table):
    return [table.horizontalHeaderItem(c).text()
            for c in range(table.columnCount())]


def _slot_names(view):
    """The heroes drawn on the board: a chip that was never filled has no
    name and is not an open slot either."""
    return [chip.name for row in ("top", "bottom")
            for chip in view.slots[row] if chip.name and not chip.open]


# ---- the request's own clauses --------------------------------------

def test_it_is_off_by_default(window):
    assert ui_settings.DEFAULTS["simple_view"] is False
    assert window.draft_pages.currentWidget() is window.draft_scroll
    assert not window.view_switch.simplified


def test_the_switch_is_in_the_top_corner_of_the_tab_row(window):
    """"simplified view should be a toggle at top corner". Two labelled
    halves on the strip's right-hand end, after the stretch - not a tick
    in a menu."""
    switch = window.view_switch
    assert isinstance(switch, chrome.ViewSwitch)
    assert switch.parentWidget() is window.tabs.strip
    row = window.tabs.strip.layout()
    assert row.indexOf(switch) == row.count() - 1
    assert switch.visual.text() == "Visual"
    assert switch.simple.text() == "Simplified"
    titles = [a.text() for a in window.view_menu.actions()]
    assert not any("implified" in t for t in titles)


def test_clicking_the_switch_changes_the_page_and_is_remembered(window):
    window.refresh()
    window.view_switch.simple.click()
    assert window.draft_pages.currentWidget() is window.simple_scroll
    assert ui_settings.load()["simple_view"] is True
    window.view_switch.visual.click()
    assert window.draft_pages.currentWidget() is window.draft_scroll
    assert ui_settings.load()["simple_view"] is False
    assert window.suggest_row.hero_ids       # the rich page is intact


def test_the_choice_survives_a_restart(qapp, window):
    """"restart the app or update it, whatever, it should stay in that
    simplified view" - a second MainWindow is what one is from the
    settings file's point of view."""
    window.refresh()
    window._set_simple_view(True)
    again = _build(qapp)
    try:
        assert again.draft_pages.currentWidget() is again.simple_scroll
        assert again.view_switch.simplified
    finally:
        again.close()


def test_the_three_board_buttons_are_on_the_page(simple):
    """"i also dont have those 3 buttons at the top". A second set of
    buttons wired to the SAME handlers, since a widget has one parent
    and the originals are between the Radiant and Dire headings."""
    labels = [b.text() for b in simple.simple_buttons]
    assert labels == ["Clear all", "Detect all", "Demo"]
    for button in simple.simple_buttons:
        assert button.isVisibleTo(simple)
        assert simple.simple_view.isAncestorOf(button)
    before = _slot_names(simple.simple_view)
    assert before
    simple.simple_buttons[0].click()          # Clear all blanks the board
    simple.refresh()
    _settle()
    assert _slot_names(simple.simple_view) == []
    simple.simple_buttons[2].click()          # Demo fills it again
    simple.refresh()
    _settle()
    assert len(_slot_names(simple.simple_view)) == 10


def test_there_is_no_pos_column_anywhere(simple):
    """"dont show pos... i dont have that added to this drafter yet"."""
    view = simple.simple_view
    for table in (view.synergy, view.counters):
        assert "Pos" not in _headers(table)
    tree = ast.parse(SOURCE.read_text())
    strings = {n.value for n in ast.walk(tree)
               if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert "Pos" not in strings


def test_the_totals_are_the_table_size(simple):
    """"its weird that the total synergy value is a smaller font than the
    tables themselves"."""
    label = simple.simple_view.totals
    label.ensurePolished()
    assert label.font().pixelSize() == simpleview.CELL_PX
    assert label.text()                      # both sides drawn
    assert theme.GOOD in label.text() or theme.BAD in label.text()


def test_every_card_folds_from_its_heading_and_is_remembered(qapp, simple):
    """"i wanna be able to show / hide the different tables (collapsible)
    and you remember the last state"."""
    view = simple.simple_view
    assert set(view.cards) == set(simpleview.SimpleView.KEYS)
    for key in ("roles", "items"):
        QTest.mouseClick(view.cards[key].head, Qt.MouseButton.LeftButton)
    _settle()
    assert view.cards["roles"].closed and view.cards["items"].closed
    assert not view.cards["board"].closed
    assert sorted(ui_settings.load()["simple_collapsed"]) == ["items", "roles"]
    again = _build(qapp)
    try:
        assert again.simple_view.cards["roles"].closed
        assert again.simple_view.cards["items"].closed
        assert not again.simple_view.cards["synergy"].closed
    finally:
        again.close()
    # And it opens again from the same heading.
    QTest.mouseClick(view.cards["roles"].head, Qt.MouseButton.LeftButton)
    assert not view.cards["roles"].closed
    assert ui_settings.load()["simple_collapsed"] == ["items"]


def test_a_folded_card_keeps_its_heading(simple):
    """A folded card is one line naming what is behind it, not a gap."""
    card = simple.simple_view.cards["roles"]
    card.set_closed(True)
    assert card.title.isVisibleTo(simple) and card.body.isHidden()
    assert card.height() < 60 or card.sizeHint().height() < 60


# ---- it fits in one view ---------------------------------------------

def test_nothing_scrolls_at_the_owners_own_window_size(simple):
    """"i dont like scrolling". At 940x895 the page is as tall as its
    viewport and no taller."""
    assert simple.simple_scroll.verticalScrollBar().maximum() == 0
    assert simple.simple_scroll.horizontalScrollBar().maximum() == 0
    assert simple.simple_view.height() <= simple.simple_scroll.viewport().height()


def test_the_hero_grid_takes_the_rows_the_page_has_left(simple):
    """"show as many as fit is fine": the one block that could grow
    without bound is cut to the height left after everything else, and
    the heading says how many that was."""
    view = simple.simple_view
    total = len(view.picks.entries)
    assert total == len(simple.suggest_row.hero_ids)
    shown = view.picks.shown
    assert 0 < shown <= total
    sub = view.cards["picks"].sub.text()
    assert sub == (f"all {total}" if shown == total
                   else f"first {shown} of {total}")
    # Fold two cards and the grid grows into the room they leave.
    for key in ("roles", "items"):
        view.cards[key].set_closed(True)
    view._refit()
    _settle()
    assert view.picks.shown >= shown
    assert simple.simple_scroll.verticalScrollBar().maximum() == 0
    # Shrink the window and it gives rows back rather than scrolling.
    simple.resize(OWN_W, 700)
    _settle()
    assert view.picks.shown < total
    assert simple.simple_scroll.verticalScrollBar().maximum() == 0


def test_more_columns_on_a_wider_window(simple):
    view = simple.simple_view
    cols = view.picks.cols
    simple.resize(1500, OWN_H)
    _settle()
    assert view.picks.cols > cols


def test_the_hero_chips_are_in_the_strips_own_order(simple):
    view = simple.simple_view
    names = [c.name for c in view.picks.chips]
    strip = [simple.ds.name(h) for h in simple.suggest_row.hero_ids]
    assert names == strip[:len(names)]
    assert [c.rank for c in view.picks.chips] == [str(i + 1) for i in range(len(names))]


# ---- the two views never disagree -----------------------------------

def test_the_board_is_the_ten_picks_as_text_with_their_values(simple):
    view = simple.simple_view
    draft = simple._current_draft()
    net = scoring.net_contributions(simple.ds, draft)
    chips = {c.name: c for row in ("top", "bottom")
             for c in view.slots[row] if not c.open}
    for hid, value in net.items():
        chip = chips[simple.ds.name(hid)]
        assert chip.figure == tilekit.delta_text(value)
        assert chip.colour == ("GOOD" if value > 0 else "BAD" if value < 0
                               else "TEXT_DIM")
    # Radiant is the TOP row, always - the same rule the panels follow.
    mine, _theirs = simple._side_names
    top_side = "ally" if mine == "Radiant" else "enemy"
    top_names = {simple.ds.name(t.property("hero_id"))
                 for t in simple.team_buttons[top_side]
                 if t.property("hero_id") is not None}
    assert {c.name for c in view.slots["top"] if not c.open} == top_names
    # An open slot is drawn as one, dashed, rather than left out.
    assert sum(1 for row in ("top", "bottom")
               for c in view.slots[row]) == 10


def test_the_synergy_square_is_the_painted_grids_own_pairs(simple):
    """Lower-left is Radiant against the row names, upper-right Dire
    against the column names - the painted card's shape, every pair
    once, off the very grid the triangles are drawn from."""
    view = simple.simple_view
    draft = simple._current_draft()
    grid = scoring.team_synergy_grid(simple.ds, draft)
    name = simple.ds.name
    look = {}
    for c in grid.pairs:
        look[(name(c.hero_id), name(c.other_id))] = c.delta
        look[(name(c.other_id), name(c.hero_id))] = c.delta
    rows = _column(view.synergy, 0)
    cols = _headers(view.synergy)[1:]
    seen = 0
    for r in range(5):
        for c in range(5):
            text = view.synergy.item(r, c + 1).text()
            if r == c:
                assert text == ""
                continue
            a, b = (rows[r], rows[c]) if c < r else (cols[r], cols[c])
            if (a, b) in look:
                assert text == tilekit.delta_text(look[(a, b)])
                seen += 1
            else:
                assert text == ""
    assert seen == len(grid.pairs)


def test_the_counters_table_is_the_matrix_the_grid_is_handed(simple):
    draft = simple._current_draft()
    matrix = scoring.matchup_matrix(simple.ds, draft)
    view = simple.simple_view
    assert _headers(view.counters)[1:1 + len(matrix.cols)] == \
        [n for _h, n in matrix.cols]
    assert _column(view.counters, 0)[:len(matrix.rows)] == \
        [n for _h, n in matrix.rows]
    for r, line in enumerate(matrix.cells):
        for c, value in enumerate(line):
            assert view.counters.item(r, c + 1).text() == \
                tilekit.delta_text(value)
    mine, theirs = simple._side_names
    corner = _headers(view.counters)[0]
    assert mine in corner and theirs in corner


def test_the_items_are_the_strips_own_advice(simple):
    view = simple.simple_view
    advice = simple._last_advice
    assert [c.name.rstrip(" *") for c in view.items.chips] == \
        [a.item for a in advice]
    for chip, a in zip(view.items.chips, advice):
        assert chip.figure == f"{items_mod.importance(a.score)}%"
        for t in a.triggers:
            assert t.hero in chip.tail


def test_the_roles_strip_is_both_sides_share_per_role(simple):
    from draft_assist.model import roles as roles_mod
    view = simple.simple_view
    draft = simple._current_draft()
    ours = roles_mod.team_scores(draft.allies)
    heads = [view.roles.cells[(0, c)].text() for c in range(1, 9)]
    assert heads == list(roles_mod.ROLES)
    for c, score in enumerate(ours, start=1):
        assert view.roles.cells[(1, c)].text() == f"{round(score.share * 100)}%"


# ---- the shape of the page -------------------------------------------

def test_nothing_in_the_simplified_view_draws_a_portrait(simple):
    """Parsed rather than searched: the docstring has to quote "instead
    of any portraits" to explain why the module exists."""
    used = set()
    for node in ast.walk(ast.parse(SOURCE.read_text())):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, ast.alias):
            used.add(node.name.rsplit(".", 1)[-1])
        elif isinstance(node, ast.ImportFrom) and node.module:
            used.update(node.module.split("."))
    for forbidden in ("portraits", "item_icons", "QPixmap", "QIcon"):
        assert forbidden not in used, forbidden


def test_the_view_ticks_hide_the_same_blocks_here(simple):
    view = simple.simple_view
    for key, card_name in (("show_roles", "roles"),
                           ("show_suggestions", "picks"),
                           ("show_items", "items")):
        simple._set_section(key, False)
        assert view.cards[card_name].isHidden()
        simple._set_section(key, True)
        assert not view.cards[card_name].isHidden()


def test_the_matrices_are_drawn_whatever_the_matrices_tick_says(simple):
    """The one stated exception: "Synergies and counters" starts off
    because the painted cards are most of a screen; two 5x5s of text
    are a sixth of one, and synergies were named as content of this
    view in the breath that asked for it."""
    view = simple.simple_view
    simple._set_section("show_matrices", False)
    assert not view.cards["synergy"].isHidden()
    assert not view.cards["counters"].isHidden()


def test_no_table_ever_scrolls_inside_itself(simple):
    view = simple.simple_view
    for table in (view.synergy, view.counters):
        assert (table.verticalScrollBarPolicy()
                == Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        assert (table.horizontalScrollBarPolicy()
                == Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        wanted = (table.horizontalHeader().sizeHint().height()
                  + table.verticalHeader().length()
                  + 2 * table.frameWidth() + 2)
        assert table.height() >= wanted - 2


def test_a_table_lets_the_page_take_the_wheel(simple):
    table = simple.simple_view.counters
    event = QWheelEvent(
        QPointF(5, 5), QPointF(table.mapToGlobal(QPoint(5, 5))),
        QPoint(0, -40), QPoint(0, -120), Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    table.wheelEvent(event)
    assert not event.isAccepted()


def test_nothing_in_the_table_can_be_sorted_or_edited(simple):
    view = simple.simple_view
    for table in (view.synergy, view.counters):
        assert not table.isSortingEnabled()
        assert not table.horizontalHeader().sectionsClickable()
        assert (table.editTriggers()
                == QAbstractItemView.EditTrigger.NoEditTriggers)
        assert table.selectionMode() != QAbstractItemView.SelectionMode.NoSelection


def test_a_column_heading_fits_its_name_rather_than_cutting_it(simple):
    """Five hero names across half a card: Qt's header elides to "Sha..."
    or runs "Clockwerk" under the next column. `FitHeader` wraps at a
    space and shrinks a long single word, so the heading is two lines
    tall and no name is cut."""
    view = simple.simple_view
    for table in (view.synergy, view.counters):
        head = table.horizontalHeader()
        assert isinstance(head, simpleview.FitHeader)
        metrics = head.fontMetrics()
        assert head.sizeHint().height() >= 2 * metrics.lineSpacing()
        assert not head.sectionsClickable()


def test_the_simplified_page_does_not_set_the_windows_floor(qapp):
    win = _build(qapp)
    try:
        win.refresh()
        rich = win.minimumSizeHint().height()
        win._set_simple_view(True)
        win.refresh()
        assert win.minimumSizeHint().height() <= rich
    finally:
        win.close()


def test_it_is_not_filled_while_it_is_hidden(window):
    window.refresh()
    assert not _slot_names(window.simple_view)
    window._set_simple_view(True)
    assert len(_slot_names(window.simple_view)) >= 9


# ---- its own typography, and nobody else's ---------------------------

def test_the_page_is_a_plain_sans_at_a_reading_size(simple):
    """"very standardized, or ones that are notoriously easy to read" -
    the platform's own UI sans at a regular weight, the same exception
    `QLabel[prose="true"]` already makes for the manual."""
    table = simple.simple_view.counters
    table.ensurePolished()
    font = table.font()
    assert font.family() != theme.BODY_FAMILY
    assert font.family() == "Segoe UI"
    assert int(font.weight()) < int(QFont.Weight.DemiBold)


def test_it_restyles_nothing_outside_itself(simple):
    for widget in (simple.suggest_row, simple.matchup_matrix.table,
                   simple.item_row):
        widget.ensurePolished()
        assert widget.font().family() == theme.BODY_FAMILY
        assert widget.font().pixelSize() == theme.BODY_PX


def test_the_pages_colours_follow_greyscale(simple):
    """The page's own stylesheet carries colours now, so it is rebuilt
    from `theme` on every draw: a hex captured once would be the one
    thing on screen that stayed in colour."""
    view = simple.simple_view
    assert theme.BG_ELEVATED in view.styleSheet()
    try:
        simple._set_greyscale(True)
        _settle()
        assert theme.BG_ELEVATED in view.styleSheet()
        colours = {c.colour for row in ("top", "bottom")
                   for c in view.slots[row] if not c.open}
        assert colours & {"GOOD", "BAD"}
        for name in colours:
            hexed = getattr(theme, name)
            r, g, b = (int(hexed[i:i + 2], 16) for i in (1, 3, 5))
            assert max(r, g, b) - min(r, g, b) <= 2, hexed
    finally:
        simple._set_greyscale(False)

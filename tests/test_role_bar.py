"""The Roles card: eight roles twice, Radiant's left and Dire's right.

**THIS SHAPE REPLACES THE ONE THAT STOOD HERE**, at the user's request,
and the tests it replaces went with it. It used to be two bars facing
each other across ONE shared role name, under a "Radiant"/"Dire" heading
pair per group. Those headings are what went: "there should not be a
header for radiant and dire... its just if it sits under radiant its
radiant and likewise for dire, divided by the same central line" — and
then, asked which of two shapes that meant: "I mean you repeat the
header, and you know which team it belongs to because all headers on the
left are radiant, right are dire, by header I mean support, carry, etc."

So POSITION carries the team, exactly as it does on the board above, and
the tests below check the three things that makes load-bearing:

* the role NAMES are repeated, once per side, and nothing else labels a
  side;
* each side is its OWN CARD, sitting under the team panel it is about —
  "see the padding on the background that allows you to know that 5
  heroes at the pick menu are radiant? that padding should encapsulate
  the roles" — which replaced the centre rule that briefly divided one
  wide card, and took the "Roles" heading with it: "you don't need to
  state roles, it's obvious from the content";
* the column count follows the WIDTH and the minimum is one column —
  which is not cosmetic. Fixed at four this card asked for 1022px
  against a window floor of 940, so the Draft page stopped shrinking
  and the ten portraits could not scale down with the window.

Every pill is still the frame's gold, at the user's request, replacing a
red/green rule asked for one message earlier.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from draft_assist.model import roles as roles_mod      # noqa: E402
from draft_assist.ui import rolebar, theme             # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def styled(qapp):
    was = qapp.styleSheet()
    qapp.setStyleSheet(theme.STYLESHEET)
    yield qapp
    qapp.setStyleSheet(was)


@pytest.fixture()
def host(styled):
    """A parent to hang the widgets under test on, and to take them away.

    A PARENTLESS QWidget IS A WINDOW in Qt, which is this app's oldest
    trap — three separate second-taskbar-entries have come from it. In a
    test it is worse than cosmetic: `QApplication.topLevelWidgets()`
    keeps them, so the two smoke tests that count the app's windows fail
    LATER IN THE RUN, in another file, for something this one left
    behind. `deleteLater` alone does not do it either: it schedules, and
    nothing here spins the loop.
    """
    from PyQt6.QtWidgets import QWidget
    parent = QWidget()
    # SHOWN, because a child of a hidden parent is not visible either, and
    # Qt delivers no resize event to a widget that is not — which is the
    # whole mechanism the group count follows.
    parent.resize(1600, 600)
    parent.show()
    yield parent
    # HIDE FIRST, AND SEND THE DELETE. `processEvents()` does NOT dispatch
    # DeferredDelete when there is no event loop running under it, so
    # `deleteLater` alone leaves a SHOWN top-level widget behind — and two
    # smoke tests count the app's visible windows, in another file, far
    # later in the run. Hiding makes the count right whatever the delete
    # does; `sendPostedEvents` then actually destroys it.
    from PyQt6.QtCore import QEvent
    parent.hide()
    parent.setParent(None)
    parent.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()


@pytest.fixture()
def cards(host):
    """The pair, which is what scores a draft."""
    pair = rolebar.RoleCards(host)
    pair.set_sides("Radiant", "Dire")
    for widget in pair.bars.values():
        widget.show()
    return pair


@pytest.fixture()
def bar(cards):
    """One side's card — Radiant's, unless a test says otherwise."""
    return cards.bars["ally"]


def lay_out(widget, width: int) -> None:
    """Resize and make the layout ACTUALLY RUN.

    Qt defers layout, so reading a geometry straight after a resize reads
    the OLD one — the same trap `_hold_still` carries a note about in the
    History tab, where measuring before forcing the layout moved the
    control out from under the cursor.
    """
    widget.resize(width, widget.sizeHint().height())
    widget._fit()
    widget.layout().activate()
    QApplication.processEvents()
    widget.resize(width, widget.sizeHint().height())
    widget.layout().activate()


# ---- what it shows -----------------------------------------------------

def test_every_role_gets_a_cell_on_BOTH_cards(cards):
    """Eight roles, twice — the repetition IS the labelling."""
    for side in ("ally", "enemy"):
        bar = cards.bars[side]
        for role in roles_mod.ROLES:
            name, pills = bar._cells[role]
            assert name.text() == role
            assert isinstance(pills, rolebar.PillRow)
        assert len(bar._cells) == len(roles_mod.ROLES)


def test_NOTHING_on_a_card_names_a_team(bar, styled):
    """The whole of the request. A label reading "Radiant" anywhere on
    this card is the thing that was asked to go — the CARD says it, the
    way the panel above says it for the five picks."""
    from PyQt6.QtWidgets import QLabel
    words = {w.text().strip().lower() for w in bar.findChildren(QLabel)}
    assert "radiant" not in words
    assert "dire" not in words
    assert "roles" not in words         # nor a heading naming the block
    assert {r.lower() for r in roles_mod.ROLES} <= words


def test_the_pills_are_the_share_each_side_actually_scored(cards):
    cards.show_draft([1, 26, 8], [2, 5])
    ours = roles_mod.team_scores([1, 26, 8])
    theirs = roles_mod.team_scores([2, 5])
    for mine, yours in zip(ours, theirs):
        assert cards.bars["ally"]._cells[mine.role][1].filled == mine.pills
        assert cards.bars["enemy"]._cells[mine.role][1].filled == yours.pills


def test_both_cards_grow_the_SAME_way(cards):
    """REVERSES "each side grows outward from the name". That rule made
    two bars comparable by length from a SHARED origin; in two separate
    cards there is no shared origin at all, and the comparison lives in
    the tooltip."""
    for side in ("ally", "enemy"):
        for role in roles_mod.ROLES:
            assert cards.bars[side]._cells[role][1]._grows_right is True


def test_the_lead_is_carried_even_though_nothing_paints_it(cards):
    """Kept up to date so colouring by it again is one line in
    `_colour` — the point of not deleting arithmetic the moment it stops
    being drawn."""
    cards.show_draft([1, 26, 8, 2, 5], [14, 29, 18, 11, 41])
    leads = {cards.bars["ally"]._cells[r][1].lead for r in roles_mod.ROLES}
    assert leads - {0}, "no role registered a lead either way"
    for role in roles_mod.ROLES:
        assert (cards.bars["ally"]._cells[role][1].lead
                == -cards.bars["enemy"]._cells[role][1].lead)


def test_the_tooltip_carries_the_figures_a_rounded_pill_cannot(cards):
    """A row reading 3 against 3 can be 0.52 against 0.61."""
    cards.set_sides("Radiant", "Dire")
    cards.show_draft([1, 26, 8], [2, 5])
    tip = cards.bars["ally"]._cells["Carry"][0].toolTip()
    assert "Carry" in tip
    # AND IT NAMES THE SIDES, because no card does.
    assert "Radiant" in tip and "Dire" in tip
    assert "%" in tip
    # The SAME tooltip on both cards, so hovering either answers the
    # comparison that two separate cards cannot make on one line.
    assert cards.bars["enemy"]._cells["Carry"][0].toolTip() == tip


def test_an_empty_board_draws_the_shape_with_nothing_in_it(cards):
    cards.show_draft([], [])
    for side in ("ally", "enemy"):
        for role in roles_mod.ROLES:
            assert cards.bars[side]._cells[role][1].filled == 0


# ---- the colour --------------------------------------------------------

def test_every_pill_is_the_frames_gold(cards):
    """At the user's request: "just make it all gold - like the border of
    the app window". Gold is this app's "this one" colour rather than a
    judgement."""
    cards.show_draft([1, 26, 8, 2, 5], [14, 29, 18, 11, 41])
    for side in ("ally", "enemy"):
        for role in roles_mod.ROLES:
            assert (cards.bars[side]._cells[role][1]._colour()
                    == QColor(theme.FRAME_GOLD))


def test_a_filled_pill_is_actually_drawn_in_that_gold(bar, host):
    """It is in the code has twice not meant it is on the screen."""
    row = bar._cells["Carry"][1]
    row.set_share(3, 1)
    row.resize(row.sizeHint())
    picture = row.grab().toImage()
    gold = QColor(theme.FRAME_GOLD).rgb()
    assert any(picture.pixel(x, y) == gold
               for x in range(picture.width())
               for y in range(picture.height()))


# ---- how many across ---------------------------------------------------

def test_the_column_count_follows_the_width(bar):
    wide = bar.columns_for(4000)
    narrow = bar.columns_for(bar._cell_width() + 10)
    assert wide > narrow
    assert wide == max(rolebar.RoleBar.COLUMNS)
    assert narrow == 1


def test_the_counts_are_divisors_of_eight(bar):
    """A ragged last column reads as a cell having gone missing."""
    for count in rolebar.RoleBar.COLUMNS:
        assert len(roles_mod.ROLES) % count == 0


def test_its_MINIMUM_is_one_column(bar):
    """**THE LOAD-BEARING ONE.** A widget's minimum is the window's
    minimum. Reporting four columns put the Draft page's floor at 1314px
    against a window floor of 940 — so inside the tab's scroll area the
    page stopped shrinking, a horizontal scrollbar appeared and the ten
    portraits were pinned at one size at every window width: "i also feel
    like portraits are nto scaling down as i make the windows smaller"."""
    assert bar.minimumSizeHint().width() <= bar._cell_width()
    from draft_assist.ui import teams
    assert bar.minimumSizeHint().width() < teams.minimum_panel_width()


def test_a_card_shown_after_the_window_grew_still_reflows(bar, host):
    """Qt delivers no resize to a HIDDEN widget, and this card lives on a
    tab that hides its pages."""
    bar.hide()
    bar.resize(bar._cell_width() + 10, 60)
    bar._fit()
    assert bar.columns == 1
    bar.resize(4000, 60)
    bar.show()
    QApplication.processEvents()
    assert bar.columns == max(rolebar.RoleBar.COLUMNS)


def test_four_columns_is_shorter_than_one(bar, host):
    lay_out(bar, 4000)
    wide = bar.sizeHint().height()
    assert bar.columns == max(rolebar.RoleBar.COLUMNS)
    lay_out(bar, bar._cell_width() + 10)
    assert bar.columns == 1
    assert bar.sizeHint().height() > wide


def test_the_two_cards_reach_the_same_column_count(cards, host):
    """They are given equal stretch in one row, so they are the same
    width and arrive at the same answer on their own. Nothing keeps them
    in step, so this is what says they do not need to be."""
    for width in (4000, 900, 400, 200):
        for bar in cards.bars.values():
            lay_out(bar, width)
        counts = {bar.columns for bar in cards.bars.values()}
        assert len(counts) == 1, (width, counts)


def test_relaying_out_moves_the_cells_rather_than_rebuilding_them(cards):
    """Each cell owns its tooltip and its fill, so tearing them down on a
    window drag would drop what the card is showing — and a destroyed C++
    object behind a live Python wrapper is the trap the History tab's
    item block already found."""
    cards.show_draft([1, 26, 8], [2, 5])
    bar = cards.bars["ally"]
    before = {role: bar._cells[role] for role in roles_mod.ROLES}
    filled = bar._cells["Carry"][1].filled
    bar._relayout(1)
    bar._relayout(4)
    for role, pair in before.items():
        assert bar._cells[role] is pair
    assert bar._cells["Carry"][1].filled == filled


def test_no_widget_in_the_card_is_left_without_a_parent(cards):
    """A parentless QWidget in this app is a second window in the
    taskbar the moment anything shows it."""
    from PyQt6.QtWidgets import QWidget
    for bar in cards.bars.values():
        for role in roles_mod.ROLES:
            for widget in bar._cells[role]:
                assert widget.parent() is not None
        for child in bar.findChildren(QWidget):
            assert child.parent() is not None


def test_no_column_is_ever_created_with_no_roles_in_it(bar):
    """Eight roles over five columns is two each and the fifth gets
    nothing, which drew a pair of headings over thin air. The count is
    what the SLICES need, not what the width would permit."""
    for asked in range(1, 12):
        bar._relayout(asked)
        per = -(-len(roles_mod.ROLES) // bar.columns)
        assert per * bar.columns >= len(roles_mod.ROLES)
        assert (bar.columns - 1) * per < len(roles_mod.ROLES)


def test_all_five_pills_are_always_drawn_however_few_are_filled(host):
    """The space is reserved for 5/5 and the gold fills in — so the
    DENOMINATOR is visible. Drawing only the filled ones would make "2 of
    5" and "2 of 2" the same picture, and normalising by picks in the
    first place is the whole point."""
    from PyQt6.QtGui import QColor
    row = rolebar.PillRow(grows_right=True, parent=host)
    row.resize(row.sizeHint())
    widths = set()
    for filled in range(roles_mod.PILLS + 1):
        row.set_share(filled, 0)
        picture = row.grab().toImage()
        widths.add(row.width())
        gold = QColor(theme.FRAME_GOLD).rgb()
        lit = sum(picture.pixel(x, y) == gold
                  for x in range(picture.width())
                  for y in range(picture.height()))
        if filled:
            assert lit > 0, f"{filled} filled pills painted no gold"
        else:
            assert lit == 0, "an empty bar painted gold"
        # Ink of SOME kind in the last slot even when nothing is filled:
        # the empty pills are an outline, not nothing.
        assert not picture.isNull()
    assert len(widths) == 1, "the bar changed width with its fill"


def test_an_empty_bar_still_draws_its_outlines(host):
    """"there would be empty looking pills there and they get filled with
    gold depending on the attributes for the particular draft"."""
    row = rolebar.PillRow(grows_right=True, parent=host)
    row.set_share(0, 0)
    row.resize(row.sizeHint())
    picture = row.grab().toImage()
    background = picture.pixel(0, 0)
    drawn = sum(picture.pixel(x, y) != background
                for x in range(picture.width())
                for y in range(picture.height()))
    assert drawn > 50, "an unfilled bar drew nothing at all"


# ---- the pills sit under the portraits, not under the card -------------

def test_the_card_below_knows_where_the_tiles_are(styled):
    """`TeamPanel.tile_inset` is WORKED OUT rather than measured, because
    Qt defers layout and the tile row's geometry is not settled when the
    Roles card needs the answer.

    What it cannot work out from the documentation is which of the two
    stretches either side gets the odd pixel when dividing the width by
    five leaves one over — observed to be the FIRST — so this renders a
    laid-out panel and holds the arithmetic against the real thing. If Qt
    ever distributes it the other way, this fails rather than the card
    quietly sitting a pixel out.
    """
    from draft_assist.ui import teams

    panel = teams.TeamPanel("ally", "Radiant")
    panel.show()
    for width in range(700, 716):          # every remainder of five
        panel.resize(width, panel.height())
        panel.layout().activate()
        styled.processEvents()
        left, right = panel.tile_inset()
        assert panel.slots[0].x() == left, (width, panel.slots[0].x(), left)
        assert panel.width() - panel.slots[4].geometry().right() - 1 == right, (
            width, right)
    panel.close()


def test_every_role_name_is_left_aligned(styled):
    """"the text aligns left, so all 8 align left". They were right-
    aligned, each finishing against its own pills; `_align_names` gives
    them one width, so they line up with each other either way and only
    the end they hang from changes."""
    from PyQt6.QtCore import Qt

    bar = rolebar.RoleBar("ally")
    for role in roles_mod.ROLES:
        name, _pills = bar._cells[role]
        assert name.alignment() & Qt.AlignmentFlag.AlignLeft
        assert not (name.alignment() & Qt.AlignmentFlag.AlignRight)
    bar.deleteLater()


def test_the_pills_and_the_portraits_share_two_edges(styled):
    """"allign the pills to the right edge of the portraits, and the text
    aligns left ... but the left 4 align left and also align to the left
    edge of the protrait - do for both radiant and dire".

    BOTH SIDES, because each panel tells its own card: the two are the
    same width only by construction, and a panel a pixel out is a pixel
    out on its own side.
    """
    from draft_assist.config import RULES_FILE
    from draft_assist.model import items as items_mod
    from draft_assist.ui.app import MainWindow
    from draft_assist.ui.demo import demo_dataset
    from draft_assist.ui.providers import DemoProvider

    ds = demo_dataset()
    provider = DemoProvider(ds)
    provider.draft.started -= 45
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, provider, rules, meta)
    win.timer.stop()
    win.resize(1500, 1050)
    win.show()
    styled.processEvents()
    win.refresh()
    for _ in range(6):
        styled.processEvents()

    def left_of(widget):
        return widget.mapTo(win, widget.rect().topLeft()).x()

    for side in ("ally", "enemy"):
        panel = win.team_panels[side]
        bar = win.role_bar.bars[side]
        assert bar.columns > 1, "the window is too narrow to be reading this"
        first = bar._cells[roles_mod.ROLES[0]][0]
        last = bar._cells[roles_mod.ROLES[-1]][1]
        assert left_of(first) == left_of(panel.slots[0]), side
        assert (left_of(last) + last.width()
                == left_of(panel.slots[4]) + panel.slots[4].width()), side
    win.close()

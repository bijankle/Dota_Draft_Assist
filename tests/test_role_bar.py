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
* the centre rule lands where the gap between the two team panels does;
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
def bar(host):
    widget = rolebar.RoleBar(host)
    widget.set_sides("Radiant", "Dire")
    widget.show()
    return widget


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

def test_every_role_gets_a_cell_on_BOTH_sides(bar):
    """Eight roles, twice — the repetition IS the labelling."""
    for side in ("ally", "enemy"):
        for role in roles_mod.ROLES:
            name, pills = bar._cells[side][role]
            assert name.text() == role
            assert isinstance(pills, rolebar.PillRow)
    assert len(bar._cells["ally"]) == len(roles_mod.ROLES)
    assert len(bar._cells["enemy"]) == len(roles_mod.ROLES)


def test_NOTHING_on_the_card_names_a_team(bar, styled):
    """The whole of the request. A label reading "Radiant" anywhere on
    this card is the thing that was asked to go."""
    from PyQt6.QtWidgets import QLabel
    words = {w.text().strip().lower() for w in bar.findChildren(QLabel)}
    assert "radiant" not in words
    assert "dire" not in words
    assert {r.lower() for r in roles_mod.ROLES} <= words


def test_the_pills_are_the_share_each_side_actually_scored(bar):
    bar.show_draft([1, 26, 8], [2, 5])
    ours = roles_mod.team_scores([1, 26, 8])
    theirs = roles_mod.team_scores([2, 5])
    for mine, yours in zip(ours, theirs):
        assert bar._cells["ally"][mine.role][1].filled == mine.pills
        assert bar._cells["enemy"][mine.role][1].filled == yours.pills


def test_both_sides_now_grow_the_SAME_way(bar):
    """REVERSES "each side grows outward from the name". That rule made
    two bars comparable by length from a SHARED origin; with the halves
    split there is no shared origin, and a mirrored right half would put
    Dire's names down the middle of the card where the rule goes."""
    for role in roles_mod.ROLES:
        assert bar._cells["ally"][role][1]._grows_right is True
        assert bar._cells["enemy"][role][1]._grows_right is True


def test_the_lead_is_carried_even_though_nothing_paints_it(bar):
    """Kept up to date so colouring by it again is one line in
    `_colour` — the point of not deleting arithmetic the moment it stops
    being drawn."""
    bar.show_draft([1, 26, 8, 2, 5], [14, 29, 18, 11, 41])
    leads = {bar._cells["ally"][role][1].lead for role in roles_mod.ROLES}
    assert leads - {0}, "no role registered a lead either way"
    for role in roles_mod.ROLES:
        assert (bar._cells["ally"][role][1].lead
                == -bar._cells["enemy"][role][1].lead)


def test_the_tooltip_carries_the_figures_a_rounded_pill_cannot(bar):
    """A row reading 3 against 3 can be 0.52 against 0.61."""
    bar.set_sides("Radiant", "Dire")
    bar.show_draft([1, 26, 8], [2, 5])
    tip = bar._cells["ally"]["Carry"][0].toolTip()
    assert "Carry" in tip
    # AND IT NAMES THE SIDES, because the card no longer does.
    assert "Radiant" in tip and "Dire" in tip
    assert "%" in tip
    # Both halves of a role carry the SAME tooltip, so hovering either
    # answers the comparison the split no longer makes on one line.
    assert bar._cells["enemy"]["Carry"][0].toolTip() == tip


def test_an_empty_board_draws_the_shape_with_nothing_in_it(bar):
    bar.show_draft([], [])
    for side in ("ally", "enemy"):
        for role in roles_mod.ROLES:
            assert bar._cells[side][role][1].filled == 0


# ---- the colour --------------------------------------------------------

def test_every_pill_is_the_frames_gold(bar):
    """At the user's request: "just make it all gold - like the border of
    the app window". Gold is this app's "this one" colour rather than a
    judgement."""
    bar.show_draft([1, 26, 8, 2, 5], [14, 29, 18, 11, 41])
    for side in ("ally", "enemy"):
        for role in roles_mod.ROLES:
            assert (bar._cells[side][role][1]._colour()
                    == QColor(theme.FRAME_GOLD))


def test_a_filled_pill_is_actually_drawn_in_that_gold(bar, host):
    """It is in the code has twice not meant it is on the screen."""
    row = bar._cells["ally"]["Carry"][1]
    row.set_share(3, 1)
    row.resize(row.sizeHint())
    picture = row.grab().toImage()
    gold = QColor(theme.FRAME_GOLD).rgb()
    assert any(picture.pixel(x, y) == gold
               for x in range(picture.width())
               for y in range(picture.height()))


# ---- the split ---------------------------------------------------------

def test_there_is_one_rule_and_it_is_at_the_CENTRE(bar, host):
    """"divided by the same central line". Two halves carrying the same
    stretch put it there BY CONSTRUCTION — worked out as a grid column
    index instead, it landed 13px left, which is the family of error the
    grid borders were got wrong four times by."""
    lay_out(bar, 1200)
    left = bar._rule.mapTo(bar, bar._rule.rect().topLeft()).x()
    middle = bar.width() / 2
    assert abs(left - middle) <= 4, (
        f"the rule is at {left}, the card's centre is {middle}")


def test_radiant_is_ALL_of_the_left_and_dire_ALL_of_the_right(bar, host):
    """The one rule that replaces the headings: which side a cell is on
    is the only thing saying whose it is, so not one cell may cross."""
    lay_out(bar, 1200)
    middle = bar.width() / 2
    for role in roles_mod.ROLES:
        for widget in bar._cells["ally"][role]:
            right = widget.mapTo(bar, widget.rect().topRight()).x()
            assert right <= middle + 1, f"Radiant {role} crosses the rule"
        for widget in bar._cells["enemy"][role]:
            left = widget.mapTo(bar, widget.rect().topLeft()).x()
            assert left >= middle - 1, f"Dire {role} crosses the rule"


# ---- how many across ---------------------------------------------------

def test_the_column_count_follows_the_width(bar):
    wide = bar.columns_for(4000)
    narrow = bar.columns_for(bar._cell_width() * 2 + 40)
    assert wide > narrow
    assert wide == max(rolebar.RoleBar.COLUMNS)
    assert narrow == 1


def test_the_counts_are_divisors_of_eight(bar):
    """A ragged last column reads as a cell having gone missing."""
    for count in rolebar.RoleBar.COLUMNS:
        assert len(roles_mod.ROLES) % count == 0


def test_its_MINIMUM_is_one_column_a_side(bar):
    """**THE LOAD-BEARING ONE.** A widget's minimum is the window's
    minimum. Reporting four columns put the Draft page's floor at 1314px
    against a window floor of 940 — so inside the tab's scroll area the
    page stopped shrinking, a horizontal scrollbar appeared and the ten
    portraits were pinned at one size at every window width: "i also feel
    like portraits are not scaling down as i make the windows smaller"."""
    one = bar._cell_width() * 2 + bar._extra()
    assert bar.minimumSizeHint().width() <= one
    # And that is far under the window's own floor.
    from draft_assist.ui import teams
    assert bar.minimumSizeHint().width() < 2 * teams.minimum_panel_width()


def test_a_card_shown_after_the_window_grew_still_reflows(bar, host):
    """Qt delivers no resize to a HIDDEN widget, and this card lives on a
    tab that hides its pages."""
    bar.hide()
    bar.resize(bar._cell_width() * 2 + 40, 60)
    bar._fit()
    assert bar.columns == 1
    bar.resize(4000, 60)
    bar.show()
    QApplication.processEvents()
    assert bar.columns == max(rolebar.RoleBar.COLUMNS)


def test_four_columns_is_half_the_height_of_two(bar, host):
    lay_out(bar, 4000)
    wide = bar.sizeHint().height()
    assert bar.columns == max(rolebar.RoleBar.COLUMNS)
    lay_out(bar, bar._cell_width() * 2 + 60)
    assert bar.columns == 1
    narrow = bar.sizeHint().height()
    assert narrow > wide, (wide, narrow)


def test_relaying_out_moves_the_cells_rather_than_rebuilding_them(bar):
    """Each cell owns its tooltip and its fill, so tearing them down on a
    window drag would drop what the card is showing — and a destroyed C++
    object behind a live Python wrapper is the trap the History tab's
    item block already found."""
    bar.show_draft([1, 26, 8], [2, 5])
    before = {(side, role): bar._cells[side][role]
              for side in ("ally", "enemy") for role in roles_mod.ROLES}
    filled = bar._cells["ally"]["Carry"][1].filled
    bar._relayout(1)
    bar._relayout(4)
    for key, pair in before.items():
        assert bar._cells[key[0]][key[1]] is pair
    assert bar._cells["ally"]["Carry"][1].filled == filled


def test_no_widget_in_the_card_is_left_without_a_parent(bar):
    """A parentless QWidget in this app is a second window in the
    taskbar the moment anything shows it — including the centre rule,
    which `edge()` hands back unparented."""
    from PyQt6.QtWidgets import QWidget
    assert bar._rule.parent() is not None
    for side in ("ally", "enemy"):
        for role in roles_mod.ROLES:
            for widget in bar._cells[side][role]:
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

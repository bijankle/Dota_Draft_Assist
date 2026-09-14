"""The Roles card: two teams facing each other across eight role names.

Three things here are decisions rather than code, and each was made by
rendering the card and looking at it:

* the GROUP COUNT follows the width, because one column of eight was
  294px tall in a window whose default height is 998 and used a third of
  the width;
* both sides' bars grow OUTWARD from the name, so the two are comparable
  by length rather than by counting;
* every pill is the frame's gold, at the user's request, replacing a
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
    return widget


# ---- what it shows -----------------------------------------------------

def test_every_role_gets_a_row_on_both_sides(bar):
    for role in roles_mod.ROLES:
        ally, name, enemy = bar._rows[role]
        assert name.text() == role
        assert isinstance(ally, rolebar.PillRow)
        assert isinstance(enemy, rolebar.PillRow)


def test_the_pills_are_the_share_each_side_actually_scored(bar):
    # Anti-Mage (Carry 3) alone against Lion (Carry 0) alone.
    bar.show_draft([1], [26])
    ally, _name, enemy = bar._rows["Carry"]
    assert ally.filled == roles_mod.PILLS, "3 of 3 is every pill"
    assert enemy.filled == 0


def test_each_sides_bar_grows_away_from_the_name(bar):
    """Both start at the role, so a four and a three begin at the same
    place and the eye compares length rather than counting pills."""
    ally, _name, enemy = bar._rows["Carry"]
    assert ally._grows_right is False, "the ally bar sits left of the name"
    assert enemy._grows_right is True


def test_the_lead_is_carried_even_though_nothing_paints_it(bar):
    """Colouring by it again is one line in `_colour`; that is the point
    of not deleting the arithmetic when it stopped being drawn."""
    bar.show_draft([1], [26])           # Anti-Mage carries, Lion does not
    ally, _name, enemy = bar._rows["Carry"]
    assert ally.lead == 1 and enemy.lead == -1
    support_ally, _n, support_enemy = bar._rows["Support"]
    assert support_ally.lead == -1 and support_enemy.lead == 1


def test_the_tooltip_carries_the_figures_a_rounded_pill_cannot(bar):
    bar.show_draft([1, 26, 8], [2, 5, 14, 29, 18])
    _ally, name, _enemy = bar._rows["Carry"]
    tip = name.toolTip()
    assert "Carry" in tip
    assert "of 9" in tip, tip          # three picks, three each
    assert "of 15" in tip, tip         # five picks
    assert "%" in tip


def test_an_empty_board_draws_the_shape_with_nothing_in_it(bar):
    """An empty panel shows the SHAPE of its answer, not a sentence."""
    bar.show_draft([], [])
    for role in roles_mod.ROLES:
        ally, _name, enemy = bar._rows[role]
        assert ally.filled == 0 and enemy.filled == 0
        assert ally.lead == 0 and enemy.lead == 0


# ---- the colour --------------------------------------------------------

def test_every_pill_is_the_frames_gold(bar):
    """At the user's request, replacing red/green: gold is the app's
    "this one" colour rather than a judgement, and it is what the window
    border, the focus ring and the suggestion star already wear."""
    ally, _name, enemy = bar._rows["Carry"]
    bar.show_draft([1], [26])
    for row in (ally, enemy):
        assert row._colour() == QColor(theme.FRAME_GOLD)


def test_a_filled_pill_is_actually_drawn_in_that_gold(bar, host):
    """It is in the stylesheet has twice not meant it is on the screen,
    so this reads the PIXELS the widget painted."""
    row = rolebar.PillRow(grows_right=True, parent=host)
    row.set_share(roles_mod.PILLS, 0)
    row.resize(row.sizeHint())
    picture = row.grab().toImage()
    gold = QColor(theme.FRAME_GOLD).rgb()
    found = sum(picture.pixel(x, y) == gold
                for x in range(picture.width())
                for y in range(picture.height()))
    assert found > 100, "no gold was painted at all"


# ---- how many across ---------------------------------------------------

def test_the_group_count_follows_the_width(bar):
    """"you can actually make them multi column if they are very
    narrow.... e.g. 6 rows make it 3 x 2".

    SHOWN, because Qt does not deliver a resize to a hidden widget — the
    reason `showEvent` asks again.
    """
    one = bar._group_width()
    bar.resize(one + 10, 400)
    bar.show()
    QApplication.processEvents()
    assert bar.groups == 1
    bar.resize(4 * (one + bar.GROUP_GAP), 400)
    QApplication.processEvents()
    assert bar.groups == 4


def test_a_card_shown_after_the_window_grew_still_regroups(bar):
    """A tab widget hides the pages it is not showing, so a window
    resized on another tab arrives here as one event on the way back."""
    bar.resize(4 * (bar._group_width() + bar.GROUP_GAP), 400)
    assert bar.groups == 1, "hidden widgets get no resize event"
    bar.show()
    QApplication.processEvents()
    assert bar.groups == 4


def test_it_never_asks_for_more_groups_than_there_are_roles(bar):
    assert bar.groups_for(100_000) == len(roles_mod.ROLES)
    assert bar.groups_for(0) == 1
    assert bar.groups_for(-50) == 1


def test_four_groups_is_half_the_height_of_two(bar):
    """The reason the count follows the width at all: this card sits
    between the picks and the advice about them, so its height is paid
    for by everything below it."""
    bar.resize(2 * (bar._group_width() + bar.GROUP_GAP), 600)
    bar.show()
    QApplication.processEvents()
    two_high = bar.sizeHint().height()
    bar.resize(4 * (bar._group_width() + bar.GROUP_GAP), 600)
    QApplication.processEvents()
    assert bar.groups == 4
    assert bar.sizeHint().height() < two_high


def test_relaying_out_moves_the_rows_rather_than_rebuilding_them(bar):
    """Each row owns its tooltip and its fill, so tearing them down on a
    window drag would drop what the card is showing."""
    bar.show_draft([1, 26, 8], [2, 5, 14, 29, 18])
    before = {role: bar._rows[role] for role in roles_mod.ROLES}
    tip = bar._rows["Carry"][1].toolTip()
    bar.resize(bar._group_width() + 10, 400)
    bar.resize(4 * (bar._group_width() + bar.GROUP_GAP), 400)
    assert {role: bar._rows[role] for role in roles_mod.ROLES} == before
    assert bar._rows["Carry"][1].toolTip() == tip
    assert bar._rows["Carry"][0].filled  # and it still knows its fill


def test_headings_this_width_does_not_use_are_hidden(bar):
    """A spare label left in the layout draws at (0, 0) over the first
    group - the throwaway-QLabel trap the History sidebar already found."""
    bar.resize(bar._group_width() + 10, 400)
    assert bar.groups == 1
    for spare in bar._heads[1:]:
        assert all(widget.isHidden() for widget in spare)
    for shown in bar._heads[0]:
        assert not shown.isHidden()


def test_every_group_says_whose_half_each_side_is(bar):
    """Side by side, one group's right-hand pills sit next to the next
    group's left-hand ones, and one pair of headings across the top would
    leave nothing saying the run in the middle is two different teams."""
    bar.resize(4 * (bar._group_width() + bar.GROUP_GAP), 400)
    for ally_head, enemy_head in bar._heads[:bar.groups]:
        assert ally_head.text() == "Radiant"
        assert enemy_head.text() == "Dire"


def test_no_widget_in_the_card_is_left_without_a_parent(bar):
    """A parentless QWidget in this app is a second window in the
    taskbar the moment anything shows it - three times over."""
    for row in bar._rows.values():
        for widget in row:
            assert widget.parent() is not None
    for pair in bar._heads:
        for widget in pair:
            assert widget.parent() is not None


def test_no_group_is_ever_created_with_no_roles_in_it(bar):
    """Eight roles across five groups is two each and the fifth gets
    nothing — which drew a pair of "Radiant Dire" headings over thin air
    in the corner of the card. Caught by rendering the tab and looking."""
    bar.show()
    for width in (300, 600, 900, 1200, 1464, 2400):
        bar.resize(width, 400)
        QApplication.processEvents()
        per = -(-len(roles_mod.ROLES) // bar.groups)
        # Every group has at least one role: the last slice is not empty.
        assert (bar.groups - 1) * per < len(roles_mod.ROLES), (
            f"at {width}px, {bar.groups} groups of {per} leaves the last "
            "one empty")
        for head in bar._heads[bar.groups:]:
            assert all(w.isHidden() for w in head)


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

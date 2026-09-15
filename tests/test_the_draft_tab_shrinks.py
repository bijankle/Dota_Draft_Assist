"""The Draft tab gets narrower when the window does, and so do the picks.

"I also feel like portraits are not scaling down as I make the windows
smaller." They were not, and nothing about the ten portraits was at
fault: the Roles card and the role filter were each laid out at a FIXED
number of columns, so between them the page demanded 1314px against a
window floor of 940. A widget's minimum is the window's minimum — and
inside the Draft tab's scroll area that does not wrap or clip, it simply
stops shrinking. The page stayed 1884px wide at every window size, the
two team panels stayed 925, and a horizontal scrollbar appeared instead.

So the rule this file holds is one line long: **NOTHING ON THE DRAFT TAB
MAY ASK FOR MORE WIDTH THAN THE WINDOW'S OWN FLOOR.** Everything that
cannot fit has to reflow, and the things that reflow have to SAY their
minimum is one column, because Qt otherwise reports whatever layout it
happens to be holding.
"""

import os
import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication, QScrollArea

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from draft_assist.config import RULES_FILE                 # noqa: E402
from draft_assist.model import items as items_mod          # noqa: E402
from draft_assist.ui import teams, theme                   # noqa: E402
from draft_assist.ui.app import MainWindow                 # noqa: E402
from draft_assist.ui.demo import demo_dataset              # noqa: E402
from draft_assist.ui.providers import DemoProvider         # noqa: E402

WIDTHS = (1900, 1610, 1400, 1200, 1000, 940)


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
def window(styled):
    ds = demo_dataset()
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, DemoProvider(ds), rules, meta)
    win.timer.stop()
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


def settle(win, width):
    win.resize(width, 1000)
    for _ in range(6):
        QApplication.processEvents()


def draft_page(win):
    tab = win.tabs.widget(0)
    return tab.widget() if isinstance(tab, QScrollArea) else tab


# ---- the floor ----------------------------------------------------------

def test_the_draft_page_asks_for_no_more_than_the_window_allows(window):
    """**THE ONE THAT WOULD HAVE CAUGHT THIS.** 1314 against 940."""
    page = draft_page(window)
    assert page.minimumSizeHint().width() <= window.minimumWidth(), (
        f"the Draft page wants {page.minimumSizeHint().width()}px, "
        f"the window floor is {window.minimumWidth()}px")


def test_a_team_panel_asks_for_the_tile_FLOOR_not_its_current_tiles(window):
    """The ratchet. `set_edge` uses `setFixedSize`, so the panel's LAYOUT
    reports five of whatever the tiles are right now — widen the window
    and that goes up with them and never comes back down.

    **THE NUMBER THAT MATTERS IS `minimumWidth`, NOT
    `minimumSizeHint`.** Qt has two, and only the explicit one is
    authoritative: `qSmartMinSize` prefers a minimum the widget was
    given over the one its layout worked out. So `minimumSizeHint` goes
    on reporting the ratcheted figure — it is the layout talking — while
    `SetNoConstraint` stops that reaching the widget and
    `setMinimumWidth(minimum_panel_width())` states the real floor once.
    Asserting the hint here fails while the app behaves correctly, which
    is worth a sentence rather than a looser assertion.
    """
    settle(window, 1900)
    panel = window.team_panels["ally"]
    assert panel.minimumWidth() == teams.minimum_panel_width()
    # And the parent believes it: the page's own floor is the proof.
    assert draft_page(window).minimumSizeHint().width() < 2 * 925


def test_no_horizontal_scrollbar_at_any_width(window):
    tab = window.tabs.widget(0)
    assert isinstance(tab, QScrollArea)
    for width in WIDTHS:
        settle(window, width)
        assert tab.horizontalScrollBar().maximum() == 0, (
            f"the Draft tab scrolls sideways at {width}px")


# ---- what the user actually sees ---------------------------------------

def test_the_PORTRAITS_get_smaller_as_the_window_does(window):
    """The whole complaint, measured."""
    sizes = []
    for width in WIDTHS:
        settle(window, width)
        sizes.append(window.team_panels["ally"].slots[0].width())
    assert sizes == sorted(sizes, reverse=True), sizes
    assert sizes[0] > sizes[-1] * 1.5, (
        f"the tiles barely moved across {WIDTHS[0]}..{WIDTHS[-1]}: {sizes}")


def test_both_panels_keep_the_same_size_tiles(window):
    for width in WIDTHS:
        settle(window, width)
        ally = window.team_panels["ally"].slots[0]
        enemy = window.team_panels["enemy"].slots[0]
        assert abs(ally.width() - enemy.width()) <= teams.TeamPanel.STEADY


def test_the_tiles_never_overrun_their_card(window):
    """The damper only refuses to GROW. Refusing to shrink would put five
    tiles two pixels too wide outside the panel the moment the scrollbar
    took its width."""
    for width in WIDTHS:
        settle(window, width)
        panel = window.team_panels["ally"]
        margins = panel.layout().contentsMargins()
        room = (panel.width() - margins.left() - margins.right()
                - 4 * panel.spacing)
        used = sum(t.width() for t in panel.slots)
        assert used <= room, f"{used - room}px of portrait outside the card"


def test_the_two_blocks_reflow_rather_than_forcing_the_width(window):
    """The two roles cards and the role filter are what caused it.

    The FILTER is checked directly rather than through the window,
    because it stopped needing to reflow at any size a window can reach:
    moving it out of the heading's corner and into the card's body (the
    "Suggested picks" header on its own row) handed it the card's whole
    width, and two rows of four fit in that even at the window's floor.
    What still has to hold is that it CAN, since that is what its
    minimum width rests on.
    """
    settle(window, 1900)
    for bar in window.role_bar.bars.values():
        assert bar.columns == 4
    assert window.role_filter.columns == 4     # "two rows of four"

    # The roles cards are half the window each, so they do reflow.
    settle(window, 940)
    for bar in window.role_bar.bars.values():
        assert bar.columns < 4

    box = window.role_filter
    assert box.columns_for(box._cell_width() + 10) == 1
    assert box.minimumSizeHint().width() <= box._cell_width()


# ---- and it must not oscillate -----------------------------------------

def test_resizing_back_and_forth_settles(window):
    """**THIS CLASS OF BUG SEGFAULTS RATHER THAN FAILING.** The page is
    as tall as it is WIDE — 16:9 tiles and a reflowing card — so a page a
    few pixels too tall raises the vertical scrollbar, which takes ~10px
    of width, which shrinks the tiles, which shortens the page, which
    drops the scrollbar. Measured before the damper: the ten tiles
    flipping 80, 78, 80, 78 through Qt's C++ layout until the stack went,
    with a Python traceback naming whichever `show()` was on top.
    """
    for _ in range(3):
        for width in (1000, 940, 1000, 1200):
            settle(window, width)
    settle(window, 1000)
    first = [t.width() for t in window.team_panels["ally"].slots]
    for _ in range(10):
        QApplication.processEvents()
    assert [t.width() for t in window.team_panels["ally"].slots] == first


def test_the_damper_only_refuses_to_grow(window):
    panel = window.team_panels["ally"]
    settle(window, 1200)
    big = panel.slots[0].width()
    # A shrink of one pixel is taken at once...
    panel._resize_tiles(panel.width() - 5)
    assert panel.slots[0].width() < big
    small = panel.slots[0].width()
    # ...and a growth under the threshold is not.
    panel._resize_tiles(panel.width() - 3)
    assert panel.slots[0].width() == small


# ---- the heading, as asked ----------------------------------------------

def test_the_legend_names_each_mark_on_its_own_row(window):
    """"i want a legend added to the title (suggested picks)... so i
    want 1 row below the header to show the symbols and what they mean"
    - and "Remove the hand symbol its pointless".

    Three rows, each with its own count box on its own line, and the
    two marks each standing beside the word for what it means.
    """
    from PyQt6.QtWidgets import QLabel

    from draft_assist.ui.app import MarkLabel

    hearts = [w for w in window.findChildren(MarkLabel) if not w._shield]
    shields = [w for w in window.findChildren(MarkLabel) if w._shield]
    assert len(hearts) == 1 and len(shields) == 1

    def middle(widget):
        return widget.mapTo(window, widget.rect().center()).y()

    rows = [middle(window.suggested_box), middle(window.heart_box),
            middle(window.shield_box)]
    assert rows == sorted(rows), "the three counts are not in three rows"
    assert len(set(rows)) == 3, "two counts share a line"
    assert abs(middle(hearts[0]) - rows[1]) <= 4
    assert abs(middle(shields[0]) - rows[2]) <= 4

    # And the words are there to read, which is the whole of a legend.
    words = {w.text().lower() for w in window._picks_row.findChildren(QLabel)}
    assert {"comfort", "counter"} <= words, words

def test_the_heading_paints_NO_lighter_padding(window, styled):
    """"the suggested picks area has a weird padding background color
    discrepancy (the padding is a lighter color i want it to match the
    background)".

    A bare QWidget takes the base `QWidget` rule, which is the CONTENT
    colour — LIGHTER than the card it sits on — so a container whose only
    job is to hold a layout painted a pale rectangle across the whole
    heading. It is the fault the stylesheet already fixes for every
    QLabel, one widget kind over. Checked against the PIXELS, because
    "it is in the stylesheet" has repeatedly not meant "it is on the
    screen" in this app.
    """
    from PyQt6.QtGui import QColor

    settle(window, 1610)
    picture = window.grab().toImage()
    light = QColor(theme.BG).rgb()
    for name in ("_picks_row", "role_filter"):
        widget = getattr(window, name, None)
        if widget is None:
            continue
        at = widget.mapTo(window, widget.rect().topLeft())
        for dx, dy in ((2, 2), (4, 4), (widget.width() - 3, 2)):
            x, y = at.x() + dx, at.y() + dy
            if 0 <= x < picture.width() and 0 <= y < picture.height():
                assert picture.pixel(x, y) != light, (
                    f"{name} paints the content colour at {x},{y}")


def test_the_containers_say_they_are_bare(window):
    """The property is what the stylesheet rule hangs off, so a new
    container that forgets it brings the pale rectangle straight back."""
    assert window.role_filter.property("bare") is True
    row = getattr(window, "_picks_row", None)
    assert row is None or row.property("bare") is True


# ---- the roles cards ----------------------------------------------------

def test_each_roles_block_shares_a_card_with_its_own_team(window):
    """"see the padding on the background that allows you to know that 5
    heroes at the pick menu are radiant? that padding should encapsulate
    the roles" — and then, when it still did not quite: "i dont like
    that the padding is not joined between the pills and the 5 / 5
    portaits sectrions... they belong in the same section.. obviously
    dire and radiant would stay seperate pads though."

    So it is ONE card per side holding both, rather than two cards lined
    up. Lining them up was the old way of saying this and it is what
    made a side read as two stacked sections; the alignment it needed is
    now free, because they are in the same card.
    """
    for width in (1900, 1610, 1200, 940):
        settle(window, width)
        for side in ("ally", "enemy"):
            panel = window.team_panels[side]
            pills = window.role_bar.bars[side]
            card = window.side_cards[side]
            assert card.isAncestorOf(panel), side
            assert card.isAncestorOf(pills), side
            # The pills sit UNDER the picks, not beside them.
            assert (pills.mapTo(card, pills.rect().topLeft()).y()
                    >= panel.mapTo(card, panel.rect().bottomLeft()).y()), side


def test_the_two_sides_are_still_two_separate_cards(window):
    """"obviously dire and radiant would stay seperate pads though." The
    card is what says which five are whose, so merging the pills into it
    must not merge the sides."""
    settle(window, 1610)
    ally = window.side_cards["ally"]
    enemy = window.side_cards["enemy"]
    assert ally is not enemy
    assert not ally.isAncestorOf(enemy) and not enemy.isAncestorOf(ally)
    left = ally.mapTo(window, ally.rect().topRight()).x()
    right = enemy.mapTo(window, enemy.rect().topLeft()).x()
    assert right > left, "the two sides' cards are touching or overlapping"


def test_neither_roles_card_has_a_heading(window):
    """"you don't need to state roles, it's obvious from the content"."""
    from PyQt6.QtWidgets import QLabel

    from draft_assist.model import roles as roles_mod
    for side in ("ally", "enemy"):
        words = {w.text().strip().lower()
                 for w in window.role_bar.bars[side].findChildren(QLabel)}
        assert "roles" not in words
        # What IS there is the eight role names.
        assert {r.lower() for r in roles_mod.ROLES} <= words


def test_there_is_no_rule_drawn_between_them(window):
    """The gap between two cards is the division now. Drawing a line as
    well would be this tab saying the same thing twice, which is what
    the Radiant/Dire headings were removed for."""
    settle(window, 1610)
    ally = window.side_cards["ally"]
    enemy = window.side_cards["enemy"]
    gap_left = (ally.mapTo(window, ally.rect().topRight()).x())
    gap_right = (enemy.mapTo(window, enemy.rect().topLeft()).x())
    picture = window.grab().toImage()
    y = ally.mapTo(window, ally.rect().center()).y()
    background = picture.pixel(gap_left + 3, y - 40)   # above, outside a card
    for x in range(gap_left + 2, gap_right - 1):
        assert picture.pixel(x, y) == background, (
            f"something is drawn in the gap at x={x}")


# ---- the hand -----------------------------------------------------------

def test_the_top_picks_heading_leads_its_own_grid(window):
    """"i think it would look better if 'suggested picks' header was
    above all the text - shift the rest down so it's all level 1 row
    lower than the header", and then, when the count box beside it still
    did not line up with the two below: "instead of suggested picks, use
    the header 'top picks' and make the required adjustments in the rows
    below so that the input boxes align edges".

    So the heading is row 0 of the SAME grid as the legend, spanning the
    label columns, with its count box in the column the other two are
    in. The legend is still a row lower than the heading — which is what
    the first request asked for — and the boxes now align by
    construction rather than by a gap somebody has to keep right.
    """
    from PyQt6.QtWidgets import QLabel

    settle(window, 1610)
    card = window._picks_row.parent()
    heads = [w for w in card.findChildren(QLabel) if w.text() == "Top picks"]
    assert heads, "the heading is gone"
    head = heads[0]

    for box in (window.heart_box, window.shield_box):
        assert (head.mapTo(window, head.rect().bottomLeft()).y()
                <= box.mapTo(window, box.rect().topLeft()).y() + 2), (
            "the legend is still level with the heading")
    lefts = {b.mapTo(window, b.rect().topLeft()).x()
             for b in (window.suggested_box, window.heart_box,
                       window.shield_box)}
    assert len(lefts) == 1, f"the count boxes do not line up: {lefts}"

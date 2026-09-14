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
    """The Roles card and the role filter are the two that caused it."""
    settle(window, 1900)
    assert window.role_bar.columns == 4
    assert window.role_filter.columns == 4     # "two rows of four"
    settle(window, 940)
    assert window.role_bar.columns < 4
    assert window.role_filter.columns < 4


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

def test_the_hand_is_the_TOP_row_and_the_marks_the_bottom(window):
    """"i want the qty of suggested picks to have a hand symbol to
    symbolize picking and i want it to be the top row of the two, with
    the bottom row being the shield / heart field".

    Stacked rather than strung out along the heading, which is also most
    of the WIDTH this row was costing — and width is what the ten picks
    were being squeezed by.
    """
    from draft_assist.ui.app import MarkLabel

    picks = window.suggested_box
    marks = window.mark_box
    hands = [w for w in window.findChildren(MarkLabel)
             if w._shield == "hand"]
    assert len(hands) == 1, "no hand on the suggestion count"
    hand = hands[0]
    both = [w for w in window.findChildren(MarkLabel) if w._shield is None]
    assert both, "the heart/shield label is gone"

    top = hand.mapTo(window, hand.rect().center()).y()
    bottom = both[0].mapTo(window, both[0].rect().center()).y()
    assert top < bottom, "the hand is not the top row"
    # And each count box sits on its own mark's line.
    assert abs(picks.mapTo(window, picks.rect().center()).y() - top) <= 4
    assert abs(marks.mapTo(window, marks.rect().center()).y() - bottom) <= 4


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

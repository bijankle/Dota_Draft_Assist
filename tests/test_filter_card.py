"""Where the Filter card's controls sit.

At the user's request, drawn on a screenshot: "move the export workbook
button into the bottom right, and make the exclude turbo moved to be
right of the 'ranked only'".
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def tab(qapp):
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    from tools import shoot
    shoot.application()
    shoot.sandbox()
    win, history = shoot.a_history_tab()
    yield win, history
    win.close()


def test_the_two_ticks_share_a_line_with_ranked_first(tab):
    """They were both in the flow, so where each landed depended only on
    how much room was left - which put Exclude Turbo at the end of one
    row and Ranked only at the start of the next, splitting two halves of
    one question across two lines."""
    win, history = tab
    ranked = history.ranked_tick
    turbo = history.turbo_tick
    assert ranked.mapTo(win, ranked.rect().topLeft()).y() == \
        turbo.mapTo(win, turbo.rect().topLeft()).y(), "not on one line"
    assert ranked.mapTo(win, ranked.rect().topLeft()).x() < \
        turbo.mapTo(win, turbo.rect().topLeft()).x(), "Ranked is left"


def test_export_sits_in_the_bottom_right_corner(tab):
    """A FlowLayout packs from the left and has no stretch, so nothing in
    it can be pinned to a corner - which is why this row is an ordinary
    box layout with the stretch doing the pinning."""
    win, history = tab
    card = history._anchors["sample"]
    export = history.export_button
    turbo = history.turbo_tick

    right = export.mapTo(card, export.rect().topRight()).x()
    assert card.width() - right < 40, "not hard against the right edge"
    # And on the ticks' line rather than above it.
    assert export.mapTo(win, export.rect().center()).y() == \
        turbo.mapTo(win, turbo.rect().center()).y()
    # With real space between, which is the stretch doing its job.
    assert export.mapTo(card, export.rect().topLeft()).x() - \
        turbo.mapTo(card, turbo.rect().topRight()).x() > 100


def test_the_pinned_row_does_not_raise_the_WINDOWS_floor(tab):
    """The reason this card wraps at all: a row of fixed controls sets a
    minimum width and a widget's minimum is the window's. Laid across one
    line it once asked for 925px against a 940px window, which put a
    horizontal scrollbar under the whole report.

    Taking three controls out of the flow costs some of that back - 247px
    to 580px measured - so what matters is that it stays under the floor
    the grids already set.
    """
    win, history = tab
    card = history._anchors["sample"]
    assert card.minimumSizeHint().width() < win.minimumSizeHint().width(), (
        "the Filter card now decides how narrow the window can be")

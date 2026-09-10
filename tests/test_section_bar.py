"""The Analysis tab's sidebar: the map of the page, and the switches.

A report is thirteen cards long, so the sections are listed down the
left, the list does not scroll with the page, and the row for whatever
you are reading is lit. The eleven analysis TICK BOXES are on those rows
at the user's request, so the thing that names a section and the thing
that switches it on are one control instead of two.

The tests that matter most here are the ones about ORDER and about
DUPLICATION, because both were faults in the design before it was built:
the page's block order and the `ANALYSES` list disagreed about where the
item block sits, and the tick boxes would otherwise have named the same
eleven analyses in two places.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication              # noqa: E402

from draft_assist.history import analyse, cache       # noqa: E402
from draft_assist.ui.history_tab import HistoryTab    # noqa: E402

from test_history_tab import a_report                 # noqa: E402

FIXED = ["account", "sample", "winning", "contrib"]


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def tab(qapp):
    """A tab with a report on it, laid out so it can actually scroll."""
    made = HistoryTab(settings={})
    made.render(a_report())
    made.resize(940, 600)
    made.show()
    for _ in range(3):
        qapp.processEvents()
    yield made
    made.close()


# ---- the two lists that must agree ------------------------------------

def test_block_order_and_analyses_name_the_same_eleven():
    """One list decides the ORDER, another decides the NAMES.

    They are separate because they answer different questions, so the
    thing to hold is that neither can gain or lose an analysis without
    the other — which is exactly how `ANALYSES` and the hardcoded tuple
    inside `build_blocks` came to disagree about the item block.
    """
    assert set(analyse.BLOCK_ORDER) == set(analyse.NAMES)
    assert len(analyse.BLOCK_ORDER) == len(analyse.NAMES)


def test_the_sidebar_lists_sections_in_the_order_the_page_has_them(tab):
    """A bookmark list in a different order from the page is one that
    lies about where things are."""
    on_the_page = [b.id for b in a_report().blocks]
    in_the_bar = [i for i in tab.sections.order if i not in FIXED]
    assert in_the_bar == list(analyse.BLOCK_ORDER)
    assert on_the_page == [i for i in in_the_bar if i in on_the_page]


def test_every_analysis_has_a_row_and_a_tick(tab):
    for key in analyse.BLOCK_ORDER:
        assert key in tab.sections.rows, key
        assert tab.sections.rows[key].tick is not None, key
    assert set(tab.analysis_ticks) == set(analyse.BLOCK_ORDER)


# ---- no duplication, which is what the user asked for -----------------

def test_the_analysis_ticks_are_not_also_on_the_options_card(tab):
    """"Don't show tick boxes on the main menu in that case - duplication
    will be confusing." Every analysis tick must be inside the sidebar."""
    for key, tick in tab.analysis_ticks.items():
        assert tab.sections.isAncestorOf(tick), (
            f"{key}'s tick box is not on the sidebar")


def test_the_sample_controls_stay_on_the_card(tab):
    """Only the ANALYSIS ticks moved. What matches to measure over is a
    different question and is still answered on the page."""
    for control in (tab.window_box, tab.cap_box,
                    tab.turbo_tick, tab.ranked_tick):
        assert not tab.sections.isAncestorOf(control)


def test_the_ticks_still_drive_the_options(tab):
    tab.analysis_ticks["tod"].setChecked(False)
    assert tab.options().picked["tod"] is False
    tab.analysis_ticks["tod"].setChecked(True)
    assert tab.options().picked["tod"] is True


# ---- what is reachable -------------------------------------------------

def test_before_a_run_only_the_controls_are_reachable(qapp):
    """A row with no card to jump to is dim — one rule covering an
    unticked analysis, an empty findings card and a fresh tab alike."""
    fresh = HistoryTab(settings={})
    try:
        reachable = [i for i, r in fresh.sections.rows.items() if r.reachable]
        assert reachable == ["account", "sample"]
        # The tick still works, because ticking is how you turn a
        # section on in the first place.
        assert fresh.sections.rows["tod"].tick.isEnabled()
    finally:
        fresh.close()


def test_a_full_report_makes_every_row_reachable(tab):
    assert all(row.reachable for row in tab.sections.rows.values())


# ---- jumping and the highlight ----------------------------------------

def test_clicking_a_section_brings_it_to_the_top(tab):
    bar = tab.scroll.verticalScrollBar()
    assert bar.maximum() > 0, "the page must actually scroll to test this"
    tab._jump_to("tod")
    from PyQt6.QtCore import QPoint
    top = tab._anchors["tod"].mapTo(tab.page, QPoint(0, 0)).y()
    assert abs(bar.value() - (top - 8)) <= 1
    assert tab.sections.lit() == "tod"


def test_a_jump_holds_its_highlight_at_the_bottom_of_the_page(tab):
    """The last few sections share the bottom of the page, so a jump to
    any of them scrolls as far as it can go. Without the pin, the
    bottom-of-page rule would light the LAST one whichever was clicked.
    """
    bar = tab.scroll.verticalScrollBar()
    tail = [i for i in tab.sections.order if i in tab._anchors][-3:]
    at_the_end = []
    for ident in tail:
        tab._jump_to(ident)
        assert tab.sections.lit() == ident, ident
        at_the_end.append(bar.value() == bar.maximum())
    # The premise: at least one of those really did hit the bottom stop,
    # or this test is not exercising the case it is named for.
    assert any(at_the_end)


def test_scrolling_releases_the_pin_and_the_highlight_follows(tab):
    bar = tab.scroll.verticalScrollBar()
    tab._jump_to("party")
    bar.setValue(0)
    assert tab.sections.lit() == "account"
    bar.setValue(bar.maximum())
    assert tab.sections.lit() == [i for i in tab.sections.order
                                  if i in tab._anchors][-1]


def test_the_highlight_tracks_an_ordinary_scroll(tab):
    from PyQt6.QtCore import QPoint
    bar = tab.scroll.verticalScrollBar()
    checked = 0
    for ident in ("hero", "tod", "session"):
        top = tab._anchors[ident].mapTo(tab.page, QPoint(0, 0)).y()
        bar.setValue(min(top, bar.maximum()))
        if bar.value() != top:
            continue                            # clamped at the end
        assert tab.sections.lit() == ident, ident
        checked += 1
    assert checked, "every section clamped; nothing was actually tested"


# ---- ticking redraws ---------------------------------------------------

def test_unticking_a_section_removes_it_and_dims_its_row(tab, qapp):
    """Ticking used to write the setting and change nothing on screen.
    With the box ON the bookmark that is unbearable: the row would sit
    there next to a section that never appeared."""
    report = a_report()
    cache.save(report)
    tab._load_cached(report.options.account_id)
    qapp.processEvents()
    assert "tod" in tab._anchors

    tab.analysis_ticks["tod"].setChecked(False)
    qapp.processEvents()
    assert "tod" not in tab._anchors
    assert tab.sections.rows["tod"].reachable is False
    assert all(b.id != "tod" for b in tab.report.blocks)

    tab.analysis_ticks["tod"].setChecked(True)
    qapp.processEvents()
    assert "tod" in tab._anchors
    assert tab.sections.rows["tod"].reachable is True


def test_ticking_keeps_your_place_on_the_page(tab, qapp):
    report = a_report()
    cache.save(report)
    tab._load_cached(report.options.account_id)
    qapp.processEvents()
    bar = tab.scroll.verticalScrollBar()
    bar.setValue(bar.maximum() // 2)
    where = bar.value()
    tab.analysis_ticks["herokda"].setChecked(False)
    qapp.processEvents()
    # The page is genuinely shorter now, so it can only be held to what
    # the page still has room for.
    assert bar.value() == min(where, bar.maximum())


# ---- drawn, not merely declared ---------------------------------------

def test_the_rule_beside_the_sidebar_is_actually_on_the_screen(tab):
    """Checked against PIXELS, because it was declared and invisible.

    It began as `border-right` on the SectionBar, which is a QScrollArea
    with `NoFrame` — frame width nought, so the border had nothing to
    paint into and drew absolutely nothing while reading perfectly well
    in the source. The same class of fault as a stylesheet background on
    a plain QWidget subclass without `WA_StyledBackground`.
    """
    from draft_assist.ui import theme
    image = tab.grab().toImage()
    x = tab.sections.width()
    middle = tab.height() // 2
    assert image.pixelColor(x, middle).name() == theme.BORDER
    assert image.pixelColor(x - 2, middle).name() != theme.BORDER


def test_the_separators_in_the_list_are_actually_drawn(tab):
    """A `QFrame.Shape.HLine` needs its frame to draw the line, and the
    `border: none` that stops the stylesheet drawing a second one takes
    the first away with it. These are plain widgets with a background."""
    from draft_assist.ui import theme
    image = tab.sections.grab().toImage()
    rules = [y for y in range(image.height())
             if image.pixelColor(60, y).name() == theme.BORDER]
    assert len(rules) == 2, f"expected two separators, found {rules}"


def test_the_page_never_scrolls_sideways_at_the_windows_own_floor(tab):
    """The floor is 940 and the sidebar takes 178 of it.

    Laid across one line the "Filter" row asked for 925px,
    so the sidebar put a horizontal scrollbar under the whole report and
    clipped the remembered-accounts dropdown off the right edge. Every
    test passed; it was caught by rendering the tab and looking at it.
    """
    assert tab.scroll.horizontalScrollBar().maximum() == 0
    assert tab.page.minimumSizeHint().width() <= tab.scroll.viewport().width()


# ---- the lesson the Debug tab taught -----------------------------------

def test_the_sidebar_does_not_set_a_floor_under_the_window(tab):
    """Fifteen rows is taller than a short window, and a tall child sets
    the whole window's minimum whether or not anybody is looking at it.
    Inside its own scroll area it asks for nothing."""
    assert tab.sections.minimumSizeHint().height() <= 200
    assert tab.minimumSizeHint().height() <= 400


def test_it_all_holds_inside_the_real_window(qapp):
    """The checks above build the tab on its own; this is the window the
    user actually opens, at the size the defaults open it to."""
    from draft_assist.config import RULES_FILE
    from draft_assist.model import items as items_mod
    from draft_assist.ui.app import MainWindow
    from draft_assist.ui.demo import demo_dataset
    from draft_assist.ui.providers import DemoProvider
    dataset = demo_dataset()
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(dataset, DemoProvider(dataset), rules, meta)
    win.timer.stop()
    try:
        win.resize(940, 998)
        win.show()
        for _ in range(4):
            qapp.processEvents()
        tab = win.history_tab
        assert len(tab.sections.rows) == len(analyse.BLOCK_ORDER) + len(FIXED)
        # The whole point of the wrapping options row: at the window's
        # own derived floor the report must not scroll sideways.
        assert tab.scroll.horizontalScrollBar().maximum() == 0
        # And the sidebar must not have raised the window's height
        # floor. Asserted as the SIDEBAR'S OWN contribution, not as an
        # absolute number for the window: the window's floor measures
        # 709 running this file alone and 813 inside the whole suite,
        # because earlier tests leave module state that moves it — with
        # and without this sidebar alike. An absolute number here would
        # be testing the suite's running order, not the sidebar.
        assert tab.sections.minimumSizeHint().height() <= 200
    finally:
        win.close()

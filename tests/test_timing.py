"""The refresh loop's own stopwatch, and the log it writes into.

Both exist because guessing at what makes the loop stutter has already been
wrong once — the cost that looked like scoring turned out to be a hidden
widget being smooth-scaled four times a second. And a log that rewrites
itself four times a second cannot be selected and copied, which is the one
thing a log is for.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel, QPlainTextEdit  # noqa: E402

from draft_assist.timing import Stopwatch                 # noqa: E402
from draft_assist.ui.app import set_label, set_log        # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def test_stages_are_reported_in_the_order_they_ran():
    """The report is read as a sequence — capture, then recognition, then
    redraw — so alphabetising it would hide where in the tick the time
    goes."""
    watch = Stopwatch()
    for name in ("poll", "rebuild", "debug"):
        with watch.stage(name):
            pass
    assert [row[0] for row in watch.rows()] == ["poll", "rebuild", "debug"]


def test_it_keeps_a_rolling_window_not_a_lifetime_average():
    """An average over an hour in the menu hides the ten seconds of draft
    that were bad."""
    watch = Stopwatch(window=5)
    for ms in range(20):
        watch.record("poll", float(ms))
    _name, last, _mean, peak, count = watch.rows()[0]
    assert count == 5
    assert last == 19.0 and peak == 19.0


def test_the_slowest_stage_is_named_and_it_is_never_the_total():
    watch = Stopwatch()
    watch.record("poll", 200.0)
    watch.record("rebuild", 5.0)
    watch.tick_done(210.0)
    assert watch.slowest().startswith("poll")
    assert "TOTAL" in watch.report()


def test_a_slow_stage_is_flagged_in_the_report():
    from draft_assist.timing import SLOW_MS
    watch = Stopwatch()
    watch.record("recognise", SLOW_MS + 1)
    watch.record("rebuild", 1.0)
    lines = {line.split()[0]: line for line in watch.report().splitlines()}
    assert "<--" in lines["recognise"]
    assert "<--" not in lines["rebuild"]


def test_an_exception_still_records_the_stage():
    """A stage that raised is exactly the one worth seeing in the report."""
    watch = Stopwatch()
    with pytest.raises(ValueError):
        with watch.stage("boom"):
            raise ValueError
    assert [row[0] for row in watch.rows()] == ["boom"]


# ---- the log the user is trying to copy ---------------------------------

def test_a_selection_survives_the_next_tick(qapp):
    """It rewrote itself four times a second, so a selection vanished the
    instant it was made and looked like a Qt bug rather than our refresh."""
    view = QPlainTextEdit()
    set_log(view, "first\nsecond")
    view.selectAll()
    assert view.textCursor().hasSelection()
    set_log(view, "first\nchanged")
    assert view.textCursor().hasSelection()
    assert view.toPlainText() == "first\nsecond", "the text was replaced"


def test_it_still_updates_when_nothing_is_selected(qapp):
    view = QPlainTextEdit()
    set_log(view, "one")
    set_log(view, "two")
    assert view.toPlainText() == "two"


def test_unchanged_text_is_not_rewritten(qapp):
    """Same text through setPlainText still resets the scroll position."""
    view = QPlainTextEdit()
    set_log(view, "\n".join(str(i) for i in range(200)))
    view.verticalScrollBar().setValue(50)
    set_log(view, "\n".join(str(i) for i in range(200)))
    assert view.verticalScrollBar().value() == 50


def test_a_label_selection_is_left_alone(qapp):
    from PyQt6.QtCore import Qt
    label = QLabel("before")
    label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse)
    set_label(label, "after")
    assert label.text() == "after"


def test_the_scroll_position_is_kept_when_the_text_changes(qapp):
    view = QPlainTextEdit()
    view.resize(200, 100)
    set_log(view, "\n".join(str(i) for i in range(200)))
    view.verticalScrollBar().setValue(40)
    set_log(view, "\n".join(str(i) for i in range(201)))
    assert abs(view.verticalScrollBar().value() - 40) <= 1

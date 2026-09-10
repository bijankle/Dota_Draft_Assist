"""The summary: one line per section, its two extremes, its spread.

It began as a ranked list of whatever cleared the significance floor,
which meant four Hero win rate lines could push Party size off the card
entirely — and a section with a real story could be absent because
another had louder ones. At the user's request it is a FIXED list now:
every section once, in section order, carrying its best and its worst,
"even if they seem insignificant".

The tests that earn their place are about the SCALE and about COVERAGE.
Every fault this feature has had was a number arriving wrong while the
picture still looked plausible.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QFontMetrics                  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel      # noqa: E402

from draft_assist.history import analyse              # noqa: E402
from draft_assist.history.analyse import Block, Bucket  # noqa: E402
from draft_assist.history.report import Options, Report  # noqa: E402
from draft_assist.ui.history_tab import HistoryTab    # noqa: E402
from draft_assist.ui.spread_bar import (SpreadBar,    # noqa: E402
                                        WIDEST_LABEL)


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def styled(qapp):
    """The app under its OWN stylesheet, and put back afterwards.

    Some of these check pixels, which needs the real theme — and the
    QApplication is shared by every test in the run, so setting it and
    walking away leaves everything after this file rendering in a
    different font. That is exactly what it did: a width assertion in
    `test_section_bar.py` passed alone and failed in the full suite,
    because this file had made the app's text bigger on the way past.
    Module state gets reset either side of a test in `conftest.py` for
    the same reason; a stylesheet is module state with a longer reach.
    """
    from draft_assist.ui import theme
    was = qapp.styleSheet()
    qapp.setStyleSheet(theme.STYLESHEET)
    yield qapp
    qapp.setStyleSheet(was)


def a_block(rates=(0.40, 0.50, 0.60, 0.70), thin=(), kind="cat",
            ident="hero"):
    """A section whose buckets have known figures. `thin` are under the
    8-game floor, so they must not reach the bar."""
    rows = [Bucket(key=f"k{i}", n=40, rate=r, mean=r * 100, eligible=True)
            for i, r in enumerate(rates)]
    rows += [Bucket(key=f"thin{i}", n=2, rate=r, mean=r * 100, eligible=False)
             for i, r in enumerate(thin)]
    return Block(id=ident, name=ident, desc="", kind=kind, rows=rows,
                 datum=50.0)


def a_report(blocks):
    return Report(options=Options(account_id=1), how="", name="", matches=[],
                  blocks=blocks, dropped={}, sessions=0, returned=0)


# ---- the scale ---------------------------------------------------------

def test_only_buckets_with_enough_games_set_the_bounds():
    """A two-game bucket at 100% would be the "best" of every section it
    appeared in and would stretch the bar to its edge — the same reason
    those rows are muted and sink to the bottom of the tables."""
    spread, best, worst = analyse.section_spread(
        a_block(rates=(0.40, 0.70), thin=(0.00, 1.00)), 0.55)
    assert (spread.low, spread.high) == (0.40, 0.70)
    assert (best.n, worst.n) == (40, 40)
    assert spread.points == [0.40, 0.70]


def test_the_scale_contains_your_usual_figure():
    """The datum can sit outside the eligible range, because the thin
    buckets left out still counted towards it. A tick painted off the end
    of its own bar is worse than a slightly wider bar."""
    below, _, _ = analyse.section_spread(a_block((0.60, 0.70)), 0.30)
    assert (below.low, below.high) == (0.30, 0.70)
    above, _, _ = analyse.section_spread(a_block((0.30, 0.40)), 0.90)
    assert (above.low, above.high) == (0.30, 0.90)


def test_there_is_no_row_when_there_is_nothing_to_compare():
    """A bar with no width says "this is the extreme" about a section
    that has no extremes, which the reader cannot see through."""
    assert analyse.section_spread(a_block((0.5,)), 0.5) is None
    assert analyse.section_spread(a_block(()), 0.5) is None
    assert analyse.section_spread(a_block((0.55, 0.55, 0.55)), 0.55) is None


def test_the_best_and_worst_are_the_extremes_and_are_named():
    spread, best, worst = analyse.section_spread(
        a_block((0.40, 0.55, 0.70)), 0.50)
    assert (best.key, worst.key) == ("k2", "k0")
    assert (spread.best, spread.worst) == (0.70, 0.40)


def test_a_position_is_a_fraction_of_the_range():
    spread, _, _ = analyse.section_spread(a_block((0.40, 0.80)), 0.60)
    assert spread.at(0.40) == pytest.approx(0.0)
    assert spread.at(0.80) == pytest.approx(1.0)
    assert spread.at(0.60) == pytest.approx(0.5)


def test_a_metric_section_is_measured_on_its_own_figures():
    """Win-rate sections read `rate` against your overall rate;
    contribution sections read `mean` against the section's own datum."""
    spread, _, _ = analyse.section_spread(
        a_block(rates=(0.40, 0.70), kind="metric", ident="herodmg"), 0.55)
    assert (spread.low, spread.high, spread.datum) == (40.0, 70.0, 50.0)


# ---- coverage ----------------------------------------------------------

def test_every_section_appears_once_in_section_order():
    """"Make sure there is 1 key result from each section", and "include
    the best and worst mentality for all headers seen in the left
    sidebar". Four Hero win rate lines crowding out Party size was the
    complaint; so was Hero win rates being absent altogether."""
    blocks = [a_block(ident=key,
                      kind="metric" if key in ("herodmg", "herokda") else "cat")
              for key in analyse.BLOCK_ORDER if key != "items"]
    rates, contributions = a_report(blocks).summary_rows()
    # In BLOCK_ORDER, which is ordered by what you can act on: the side
    # you are assigned last, the hero you choose first.
    assert [block.id for block, _s, _b, _w in rates] == [
        "hero", "tod", "session", "tilt", "dow", "party", "length", "side"]
    assert [block.id for block, _s, _b, _w in contributions] == [
        "herodmg", "herokda"]


def test_a_section_with_nothing_significant_still_gets_its_row():
    """Explicitly asked for: "even if they seem insignificant, like
    Radiant/Dire win rate or whatever". Nothing here consults the sigma."""
    flat = a_block(rates=(0.545, 0.55), ident="side")
    assert not any(row.sigma for row in flat.rows)
    rates, _ = a_report([flat]).summary_rows()
    assert len(rates) == 1


def test_items_stay_out_and_that_one_is_statistics():
    """Every item bucket is measured against THAT HERO'S own win rate,
    so the best item on one hero and the worst on another are figures
    against two different datums. One scale would draw a comparison that
    is not there."""
    items = a_block(ident="items", kind="items")
    rates, contributions = a_report([items]).summary_rows()
    assert rates == [] and contributions == []


# ---- what the card draws -----------------------------------------------

def test_one_bar_per_section_and_no_sentences(qapp):
    tab = HistoryTab(settings={})
    try:
        tab.render(a_report([a_block(ident="hero"),
                             a_block(ident="dow")]))
        bars = tab.results.parentWidget().findChildren(SpreadBar)
        assert len(bars) == 2
        said = " ".join(w.text() for w
                        in tab.results.parentWidget().findChildren(QLabel))
        assert "More likely to win" not in said
    finally:
        tab.close()


def test_the_bar_draws_every_bucket_not_just_the_two_named(styled):
    """Best and worst are the extremes of the very set that sets the
    bounds, so those two marks sit on the two ends for ever. Without the
    rest of the buckets between them the bar carries nothing at all."""
    from draft_assist.ui import theme
    spread, _, _ = analyse.section_spread(
        a_block((0.10, 0.45, 0.50, 0.55, 0.90)), 0.50)
    bar = SpreadBar()
    bar.ensurePolished()
    bar.set_spread(spread, "10%", "90%", "50%")
    bar.resize(300, bar.height())
    image = bar.grab().toImage()
    middle = image.height() // 2
    marked = {x for x in range(image.width())
              if image.pixelColor(x, middle - 3).name() != image.pixelColor(
                  2, 2).name()}
    # Five buckets, a datum and two coloured dots: far more than the two
    # ends' worth of ink.
    assert len(marked) > 12, sorted(marked)


def test_the_baseline_comes_from_the_report_being_drawn(qapp):
    """The regression that produced bars all labelled "0%".

    The card read `self.report`, which a tab told to `render` a report it
    had not also been handed does not have — so the datum arrived as 0.0,
    and because the scale is stretched to contain the datum, the bottom
    of every bar collapsed to zero.
    """
    class Measured(Report):
        @property
        def baseline(self) -> float:
            return 0.55

    report = Measured(options=Options(account_id=1), how="", name="",
                      matches=[], blocks=[a_block()], dropped={},
                      sessions=0, returned=0)
    tab = HistoryTab(settings={})
    try:
        assert tab.report is None, "the tab must NOT have been told"
        tab.render(report)
        bar = tab.results.parentWidget().findChildren(SpreadBar)[0]
        assert bar.spread.datum == 0.55, "the datum did not come from it"
        assert bar.spread.low > 0.0, "the scale collapsed to zero again"
        assert bar.low_text != "0%"
    finally:
        tab.close()


def test_the_name_column_is_one_width_across_both_cards(qapp):
    """"Where the result starts is all aligned for each metric." A grid
    aligns its own rows; what it cannot do is agree with the other
    card's grid, and the two sit one above the other."""
    tab = HistoryTab(settings={})
    try:
        rate = a_block(ident="dow")
        rate.name = "aa"
        metric = a_block(ident="herodmg", kind="metric")
        metric.name = "a much longer section name"
        tab.render(a_report([rate, metric]))
        cards = [tab._anchors["winning"], tab._anchors["contrib"]]
        names = [w for card_widget in cards
                 for w in card_widget.findChildren(QLabel)
                 if w.text() in ("aa", "a much longer section name")]
        assert len(names) == 2, [w.text() for w in names]
        assert len({w.width() for w in names}) == 1, \
            [(w.text(), w.width()) for w in names]
        assert names[0].width() >= max(w.sizeHint().width() for w in names)
    finally:
        tab.close()


# ---- drawn, not merely declared ---------------------------------------

def test_a_rule_runs_down_between_the_name_and_the_figures(styled):
    """"Maybe even have a vertical line that runs down in between section
    and result so it's nice and tidy." Checked against the PIXELS,
    because a rule declared in a stylesheet has twice not reached the
    screen in this tab."""
    from draft_assist.ui import theme
    tab = HistoryTab(settings={})
    try:
        tab.render(a_report([a_block(ident="hero"), a_block(ident="dow"),
                             a_block(ident="tod")]))
        card_widget = tab._anchors["winning"]
        card_widget.resize(700, card_widget.sizeHint().height())
        image = card_widget.grab().toImage()
        tall = [x for x in range(image.width())
                if sum(1 for y in range(image.height())
                       if image.pixelColor(x, y).name() == theme.BORDER)
                > image.height() * 0.5]
        assert tall, "no full-height rule anywhere in the card"
    finally:
        tab.close()


def test_the_end_labels_are_sized_in_pixels(styled):
    """This app sets `font-size` in PIXELS, so a widget's font answers
    `pointSizeF() == -1` — and scaling THAT produced a 6px font, at which
    the reserved label column measured narrower than "43%" and every bar
    printed a clipped bound."""
    from draft_assist.ui import theme
    bar = SpreadBar()
    bar.ensurePolished()
    font = bar._font()
    assert font.pixelSize() >= 9, font.pixelSize()
    room = QFontMetrics(font).horizontalAdvance(WIDEST_LABEL)
    for label in ("43%", "100%", "704", "3.56"):
        assert QFontMetrics(font).horizontalAdvance(label) <= room, label

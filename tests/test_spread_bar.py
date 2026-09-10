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

def test_only_buckets_with_enough_games_are_the_best_and_the_worst():
    """A two-game bucket at 100% would be the "best" of every section it
    appeared in — the same reason those rows are muted and sink to the
    bottom of the tables."""
    spread, best, worst = analyse.section_spread(
        a_block(rates=(0.40, 0.70), thin=(0.00, 1.00)), 0.55)
    assert (best.n, worst.n) == (40, 40)
    assert (spread.best, spread.worst) == (0.70, 0.40)
    assert spread.points == [0.40, 0.70]


def test_a_win_rate_is_drawn_nought_to_a_hundred():
    """At the user's request. Scaled to its own buckets, every section
    looked equally spread — Radiant 55% against Dire 44% filled the same
    track as a hero list running 25% to 61%, so the picture said nothing
    about how much was actually at stake."""
    spread, _, _ = analyse.section_spread(a_block((0.44, 0.55)), 0.50)
    assert (spread.low, spread.high) == (0.0, 1.0)
    wide, _, _ = analyse.section_spread(a_block((0.25, 0.61)), 0.50)
    assert (wide.low, wide.high) == (0.0, 1.0)
    # And the DISTANCE between the dots is now the size of the effect.
    assert (wide.at(wide.best) - wide.at(wide.worst)) > \
        (spread.at(spread.best) - spread.at(spread.worst))


def test_a_contribution_section_keeps_its_own_range():
    """"Damage per minute is an average, so it should be somewhere in the
    middle." There is no 100 to scale it against, and inventing a ceiling
    would be a number nobody measured with a real game able to run off
    the end of it."""
    spread, _, _ = analyse.section_spread(
        a_block(rates=(0.40, 0.70), kind="metric", ident="herodmg"), 0.55)
    assert (spread.low, spread.high) == (40.0, 70.0)


def test_a_metric_scale_still_contains_your_usual_figure():
    """The datum can sit outside the eligible range, because the thin
    buckets left out still counted towards it. A tick painted off the end
    of its own bar is worse than a slightly wider bar. Win rates need no
    such care any more — 0 to 100 contains everything."""
    low = a_block(rates=(0.60, 0.70), kind="metric", ident="herodmg")
    low.datum = 30.0
    spread, _, _ = analyse.section_spread(low, 0.0)
    assert (spread.low, spread.high) == (30.0, 70.0)


def test_there_is_no_row_without_two_buckets_to_compare():
    """A section with one bucket has no best and no worst, only a
    figure."""
    assert analyse.section_spread(a_block((0.5,)), 0.5) is None
    assert analyse.section_spread(a_block(()), 0.5) is None


def test_a_flat_win_rate_section_still_draws():
    """It used to be refused, because the bar spanned the buckets and a
    zero-width bar is a lie. On a fixed 0-100 scale two equal figures are
    simply two dots in the same place, which is the truth about them."""
    spread, _, _ = analyse.section_spread(a_block((0.55, 0.55)), 0.55)
    assert spread is not None and spread.at(spread.best) == spread.at(
        spread.worst)


def test_the_best_and_worst_are_the_extremes_and_are_named():
    spread, best, worst = analyse.section_spread(
        a_block((0.40, 0.55, 0.70)), 0.50)
    assert (best.key, worst.key) == ("k2", "k0")
    assert (spread.best, spread.worst) == (0.70, 0.40)


def test_a_position_is_a_fraction_of_the_range():
    spread, _, _ = analyse.section_spread(a_block((0.40, 0.80)), 0.60)
    assert spread.at(0.0) == pytest.approx(0.0)
    assert spread.at(1.0) == pytest.approx(1.0)
    assert spread.at(0.5) == pytest.approx(0.5)


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
    metrics = ("herodmg", "herokda", "towerdmg")
    blocks = [a_block(ident=key, kind="metric" if key in metrics else "cat")
              for key in analyse.BLOCK_ORDER if key != "items"]
    rates, contributions = a_report(blocks).summary_rows()
    # In BLOCK_ORDER, which is ordered by what you can act on: the side
    # you are assigned last, the hero you choose first.
    assert [block.id for block, _s, _b, _w in rates] == [
        "hero", "tod", "session", "tilt", "dow", "party", "length", "side"]
    assert [block.id for block, _s, _b, _w in contributions] == [
        "herodmg", "herokda", "towerdmg"]


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


def test_the_bar_names_its_two_dots_and_draws_no_others(styled):
    """"Get rid of all those small dashes in between — no one knows what
    they mean." The faint per-bucket ticks existed because the old scale
    pinned both dots to the ends for ever; a fixed 0-100 scale removes
    that at the root, so they stop paying for themselves."""
    from draft_assist.ui import theme
    spread, best, worst = analyse.section_spread(
        a_block((0.10, 0.45, 0.50, 0.55, 0.90)), 0.50)
    bar = SpreadBar()
    bar.ensurePolished()
    bar.set_spread(spread, "0%", "100%", "50%",
                   best_text="90% k4", worst_text="10% k0")
    bar.resize(320, bar.height())
    image = bar.grab().toImage()
    seen = {image.pixelColor(x, y).name()
            for x in range(image.width()) for y in range(image.height())}
    assert theme.GOOD in seen and theme.BAD in seen, "the dots never drew"

    # The per-bucket ticks were drawn in TEXT_DIM. Nothing in that colour
    # may stand where the three unnamed buckets fall.
    for figure in (0.45, 0.55):
        x = round(_x_of(bar, spread, figure))
        column = {image.pixelColor(x, y).name()
                  for y in range(image.height())}
        assert theme.TEXT_DIM not in column, \
            f"a bucket tick still stands at {figure}"


def _x_of(bar, spread, figure):
    """Where a figure falls across the bar's own track."""
    from PyQt6.QtGui import QFontMetrics
    from draft_assist.ui.spread_bar import LABEL_GAP, WIDEST_LABEL
    width = QFontMetrics(bar._font()).horizontalAdvance(WIDEST_LABEL)
    left = width + LABEL_GAP
    return left + (bar.width() - 2 * (width + LABEL_GAP)) * spread.at(figure)


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
        # The scale is fixed at 0-100 for a win rate now, so the old
        # symptom (every bound collapsing to zero) shows up on the TICK
        # rather than on the bounds: a datum of 0.0 would sit hard
        # against the left cap.
        assert bar.spread.at(bar.spread.datum) > 0.1
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

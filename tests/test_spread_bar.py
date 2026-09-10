"""The summary lines: short text, and a bar saying where the bucket sits.

Seven full sentences was a paragraph, which is the shape this tab has
been trimmed out of everywhere else. Each finding is three columns now —
the block's name, a short form of the fact, and a bar carrying the range
its block covered with a marker on it.

The tests that earn their place here are the ones about the SCALE. Every
fault this feature had was a number arriving wrong and the picture still
looking plausible: a bound that collapsed to zero, a font measured in the
wrong unit, a label clipped to its last character.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QFontMetrics                  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel      # noqa: E402

from draft_assist.history import analyse              # noqa: E402
from draft_assist.history.analyse import Block, Bucket, Finding  # noqa: E402
from draft_assist.ui.history_tab import HistoryTab    # noqa: E402
from draft_assist.ui.spread_bar import (SpreadBar,    # noqa: E402
                                        WIDEST_LABEL)

from test_history_tab import _report                  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def a_block(rates=(0.40, 0.50, 0.60, 0.70), thin=(), kind="cat"):
    """A block whose buckets have known rates. `thin` are under the floor."""
    rows = [Bucket(key=f"k{i}", n=40, rate=r, mean=r * 100, eligible=True)
            for i, r in enumerate(rates)]
    rows += [Bucket(key=f"thin{i}", n=2, rate=r, mean=r * 100, eligible=False)
             for i, r in enumerate(thin)]
    return Block(id="b", name="Block", desc="", kind=kind, rows=rows,
                 datum=50.0)


def a_finding(value, sigma=3.0):
    return Finding(sigma=sigma, key="k", text="", short="k win rate",
                   value=value, n=40)


# ---- the scale ---------------------------------------------------------

def test_only_buckets_with_enough_games_set_the_bounds():
    """At the user's request. A two-game bucket at 100% would stretch
    every bar in the card to its edge and squash the real ones into the
    middle — the same reason those rows are muted in the tables."""
    block = a_block(rates=(0.40, 0.70), thin=(0.00, 1.00))
    spread = analyse.spread_for(block, a_finding(0.70), 0.55)
    assert (spread.low, spread.high) == (0.40, 0.70)


def test_the_scale_contains_your_usual_figure():
    """The datum can sit outside the eligible buckets' range, because the
    thin buckets left out above still counted towards it. A tick painted
    off the end of its own bar is worse than a slightly wider bar."""
    below = analyse.spread_for(a_block((0.60, 0.70)), a_finding(0.70), 0.30)
    assert below.low == 0.30 and below.high == 0.70
    above = analyse.spread_for(a_block((0.30, 0.40)), a_finding(0.40), 0.90)
    assert above.low == 0.30 and above.high == 0.90


def test_there_is_no_bar_when_there_is_no_range():
    """A bar with no width says "this bucket is at the extreme" about a
    block that has no extremes, which the reader cannot see through."""
    assert analyse.spread_for(a_block((0.5,)), a_finding(0.5), 0.5) is None
    assert analyse.spread_for(a_block(()), a_finding(0.5), 0.5) is None
    flat = a_block((0.55, 0.55, 0.55))
    assert analyse.spread_for(flat, a_finding(0.55), 0.55) is None


def test_a_position_is_a_fraction_of_the_range():
    spread = analyse.spread_for(a_block((0.40, 0.80)), a_finding(0.60), 0.60)
    assert spread.at(0.40) == pytest.approx(0.0)
    assert spread.at(0.80) == pytest.approx(1.0)
    assert spread.at(0.60) == pytest.approx(0.5)


def test_a_metric_block_is_measured_on_its_own_figures():
    """Win-rate blocks read `rate` against your overall rate; contribution
    blocks read `mean` against the block's own datum."""
    block = a_block(rates=(0.40, 0.70), kind="metric")   # means 40 and 70
    spread = analyse.spread_for(block, a_finding(70.0), 0.55)
    assert (spread.low, spread.high, spread.datum) == (40.0, 70.0, 50.0)


# ---- the short form ----------------------------------------------------

def test_a_win_rate_finding_says_bucket_rate_and_nothing_else():
    rows = [Bucket(key=k, n=40, rate=r, sigma=s, eligible=True)
            for k, r, s in (("Tuesday", 0.65, 4.0), ("Friday", 0.34, -4.0))]
    found = analyse.cat_findings(rows, "dow", ())
    assert found[0].short == "Tuesday win rate 65%"
    assert found[0].value == 0.65 and found[0].n == 40


def test_a_contribution_finding_carries_its_short_unit():
    rows = [Bucket(key="Snapfire", n=40, mean=819.0, sigma=4.0,
                   eligible=True)]
    found = analyse.metric_findings(rows, 691.0, "More", "Less", 0,
                                    short="damage/min")
    assert found[0].short == "Snapfire damage/min 819"


def test_the_long_sentence_still_exists_for_the_workbook():
    """The card is short; the exported workbook is read at leisure and
    keeps the sentence, so both are built in one place."""
    rows = [Bucket(key="Tuesday", n=49, rate=0.65, sigma=4.0, eligible=True)]
    found = analyse.cat_findings(rows, "dow", ())
    assert "More likely to win on Tuesdays" in found[0].text
    assert "from 49 games" in found[0].text


# ---- the block names ---------------------------------------------------

def test_the_block_names_are_short_and_of_a_length():
    """"Make them concise as possible, and similar character length so it
    looks proportionally right." They print in a column beside every
    finding, so the longest one sets that column's width for the card."""
    lengths = [len(analyse.NAMES[key]) for key in analyse.BLOCK_ORDER]
    assert max(lengths) <= 16, {analyse.NAMES[k]: len(analyse.NAMES[k])
                                for k in analyse.BLOCK_ORDER}
    assert max(lengths) - min(lengths) <= 6


# ---- what the card draws -----------------------------------------------

def test_every_finding_gets_a_bar_and_no_sentence(qapp):
    tab = HistoryTab(settings={})
    try:
        tab.render(_report([_b("cat", [4.0, -3.0])]))
        bars = tab.results.parentWidget().findChildren(SpreadBar)
        assert len(bars) == 2
        said = " ".join(w.text() for w
                        in tab.results.parentWidget().findChildren(QLabel))
        assert "More likely to win" not in said
    finally:
        tab.close()


def test_the_baseline_comes_from_the_report_being_drawn(qapp):
    """The regression that produced seven bars all labelled "0%".

    `_findings_card` read `self.report`, which a tab told to `render` a
    report it had not also been handed does not have — so the datum
    arrived as 0.0, and because the scale is stretched to contain the
    datum, the bottom of every bar collapsed to zero.
    """
    from draft_assist.history.report import Options, Report

    class Measured(Report):
        """A report whose own win rate is known and is NOT zero, so
        reading the right source and reading none are distinguishable."""

        @property
        def baseline(self) -> float:
            return 0.55

    report = Measured(options=Options(account_id=1), how="", name="",
                      matches=[], blocks=[_b("cat", [4.0])], dropped={},
                      sessions=0, returned=0)
    tab = HistoryTab(settings={})
    try:
        assert tab.report is None, "the tab must NOT have been told"
        tab.render(report)
        bar = tab.results.parentWidget().findChildren(SpreadBar)[0]
        assert bar.spread is not None
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
        report = _report([_b("cat", [4.0], "aa"),
                          _b("metric", [4.0], "a much longer block name")])
        tab.render(report)
        # INSIDE THE TWO SUMMARY CARDS ONLY. Each block's own card
        # further down the page is headed with the same name, so a
        # search over the whole tab finds every name twice.
        cards = [tab._anchors["winning"], tab._anchors["contrib"]]
        names = [w for card_widget in cards
                 for w in card_widget.findChildren(QLabel)
                 if w.text() in ("aa", "a much longer block name")]
        assert len(names) == 2, [w.text() for w in names]
        assert len({w.width() for w in names}) == 1, \
            [(w.text(), w.width()) for w in names]
        # And wide enough for the longest of them, or it is aligned and
        # sliced rather than aligned.
        assert names[0].width() >= max(w.sizeHint().width() for w in names)
    finally:
        tab.close()


def test_a_rule_runs_down_between_the_name_and_the_figure(qapp):
    """"Maybe even have a vertical line that runs down in between section
    and result so it's nice and tidy."

    ONE widget spanning every row, not one per line: a stack of short
    rules with the row spacing showing between them is a dashed line
    rather than a rule. Checked against the PIXELS, because a rule
    declared in a stylesheet has twice now not reached the screen in this
    tab — `border-right` on a frameless scroll area, and
    `QFrame.Shape.HLine` with its own border switched off.
    """
    from draft_assist.ui import theme
    qapp.setStyleSheet(theme.STYLESHEET)
    tab = HistoryTab(settings={})
    try:
        tab.render(_report([_b("cat", [4.0, -3.0, 3.5])]))
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


def test_the_end_labels_are_sized_in_pixels(qapp):
    """This app sets `font-size` in PIXELS, so a widget's font answers
    `pointSizeF() == -1` — and scaling THAT produced a 6px font, at
    which the reserved label column measured narrower than "43%" and
    every bar printed a clipped bound."""
    from draft_assist.ui import theme
    # The app always runs under its own stylesheet, and that is what puts
    # the font on pixels in the first place; without it there is no trap
    # to test for.
    qapp.setStyleSheet(theme.STYLESHEET)
    bar = SpreadBar()
    bar.ensurePolished()
    font = bar._font()
    assert font.pixelSize() >= 9, font.pixelSize()
    room = QFontMetrics(font).horizontalAdvance(WIDEST_LABEL)
    for label in ("43%", "100%", "704", "3.56"):
        assert QFontMetrics(font).horizontalAdvance(label) <= room, label


def _b(kind, sigmas, ident="b"):
    """A block with buckets, findings and a name of the caller's choosing."""
    rows = [Bucket(key=f"{ident}{i}", n=40, rate=r, mean=r * 100,
                   eligible=True)
            for i, r in enumerate((0.40, 0.50, 0.60, 0.70))]
    findings = [Finding(sigma=s, key=f"{ident}{i}", text="",
                        short=f"{ident}{i} win rate",
                        value=(0.70 if s > 0 else 0.40) *
                        (1 if kind == "cat" else 100), n=40)
                for i, s in enumerate(sigmas)]
    return Block(id=ident, name=ident, desc="", kind=kind, rows=rows,
                 datum=50.0, findings=findings)

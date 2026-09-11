"""Win rate against a contribution figure, one dot per hero.

At the user's request: "plot it on an XY graph... the win rate is the Y
axis... and the x axis is the lowest to highest GPM for example. And each
dot has the hero name labeled."
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRectF  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from draft_assist.history import analyse  # noqa: E402
from draft_assist.ui.scatter import ScatterPlot  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def a_plot(points, qapp):
    plot = ScatterPlot()
    plot.resize(600, 260)
    plot.set_points(points, "gold/min")
    return plot


# (name, x, y, eligible, games)
SOLID = [("Tiny", 230.0, 0.30, True, 27),
         ("Lina", 310.0, 0.45, True, 33),
         ("Axe", 530.0, 0.58, True, 37),
         ("Sniper", 600.0, 0.74, True, 19)]


# ---- the axes -----------------------------------------------------------

def test_both_axes_are_scaled_to_the_DATA(qapp):
    """At the user's request: "the highest win rate hero is the max value
    and the lowest is the lowest".

    Deliberately NOT the summary bar's rule, where a win rate is always
    drawn 0 to 100 so the distance between two marks means the same on
    every row. That exists to make rows comparable; this chart is not
    compared with anything, and a correlation squashed into the middle
    third is one nobody can see.
    """
    plot = a_plot(SOLID, qapp)
    assert plot.bounds() == (230.0, 600.0, 0.30, 0.74)


def test_the_faint_heroes_still_set_the_bounds(qapp):
    """The trade the user took when they asked for thin samples to be
    drawn rather than dropped: a three-game hero at 100% stretches the
    axis and squashes everybody else."""
    plot = a_plot(SOLID + [("Pudge", 900.0, 1.0, False, 3)], qapp)
    assert plot.bounds() == (230.0, 900.0, 0.30, 1.0)


def test_one_hero_centres_rather_than_dividing_by_a_zero_span(qapp):
    plot = a_plot([("Tiny", 400.0, 0.5, True, 20)], qapp)
    box = QRectF(0, 0, 600, 260)
    low_x, high_x, low_y, high_y = plot.bounds()
    at = plot._place(box, 400.0, 0.5, low_x, high_x, low_y, high_y)
    assert at.x() == pytest.approx(box.center().x(), abs=1.0)


def test_the_extreme_dots_are_not_drawn_half_outside_the_plot(qapp):
    """A dot centred on the frame is half over its own border and clipped
    at the corners. The inset goes on where the DOTS live rather than on
    the data range, so the axis end still sits under the extreme hero."""
    plot = a_plot(SOLID, qapp)
    box = QRectF(0, 0, 600, 260)
    low_x, high_x, low_y, high_y = plot.bounds()
    left = plot._place(box, low_x, low_y, low_x, high_x, low_y, high_y)
    assert left.x() > box.left()
    assert left.y() < box.bottom()


# ---- the trend line -----------------------------------------------------

def test_the_line_slopes_the_way_the_data_does(qapp):
    plot = a_plot(SOLID, qapp)
    slope, _ = plot.trend()
    assert slope > 0, "more gold went with more winning here"


def test_the_THIN_heroes_are_drawn_but_never_tilt_the_line(qapp):
    """A bucket under MIN_BUCKET is one there is not enough behind to act
    on — it may not produce a finding anywhere else in this tab — so
    letting a three-game hero at 100% pull the fit would be that same
    claim made where nobody can see it."""
    plot = a_plot(SOLID, qapp)
    was, _ = plot.trend()
    loud = a_plot(SOLID + [("Pudge", 240.0, 1.0, False, 2)], qapp)
    now, _ = loud.trend()
    assert now == pytest.approx(was), "the faint hero moved the line"
    assert len(loud.points) == 5, "but it is still plotted"


def test_too_few_solid_heroes_draws_no_line(qapp):
    plot = a_plot(SOLID[:2], qapp)
    assert plot.trend() is None


def test_every_hero_on_one_figure_draws_no_line(qapp):
    """A vertical fit has no slope to report and dividing by the zero
    span would raise rather than decline."""
    plot = a_plot([("A", 400.0, 0.3, True, 20), ("B", 400.0, 0.5, True, 20),
                   ("C", 400.0, 0.7, True, 20)], qapp)
    assert plot.trend() is None


# ---- the figures it is fed ---------------------------------------------

def test_a_metric_bucket_now_carries_a_WIN_RATE(qapp):
    """It did not before. The contribution blocks held n, the mean and
    the sigma and nothing about winning at all, so there was no Y axis to
    plot — this plumbing had to come first."""
    from datetime import datetime
    from draft_assist.history.shape import Match

    matches = [
        Match(match_id=i, start=0, when=datetime(2026, 1, 1), duration=1800,
              slot=0, radiant=True, win=i % 4 != 0, hero_id=1, hero="Axe",
              gold_per_min=500)
        for i in range(12)]
    _datum, _spread, rows, _covered, _total = analyse.metric_split(
        matches, lambda m: m.hero, lambda m: m.gold_per_min)
    axe = rows[0]
    assert axe.n == 12
    assert axe.wins == 9
    assert axe.rate == pytest.approx(0.75)


def test_the_win_rate_counts_only_the_matches_the_MEAN_counts(qapp):
    """A match with no figure for this metric is in neither, or the two
    halves of a dot would be measured over different games."""
    from datetime import datetime
    from draft_assist.history.shape import Match

    def game(win, gpm):
        return Match(match_id=1, start=0, when=datetime(2026, 1, 1),
                     duration=1800, slot=0, radiant=True, win=win,
                     hero_id=1, hero="Axe", gold_per_min=gpm)

    matches = [game(True, 500), game(True, 700), game(False, None)]
    _d, _s, rows, _c, _t = analyse.metric_split(
        matches, lambda m: m.hero, lambda m: m.gold_per_min)
    assert rows[0].n == 2, "the unmeasured game is out"
    assert rows[0].rate == pytest.approx(1.0), "and out of the win rate too"


# ---- it follows the table underneath it --------------------------------

@pytest.fixture()
def tab(qapp):
    """A History tab with a full report drawn on it."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    from tools import shoot
    shoot.application()
    shoot.sandbox()
    win, history = shoot.a_history_tab()
    yield win, history
    win.close()


def plot_of(history, ident):
    card = history._anchors[ident]
    return card.findChild(ScatterPlot)


def test_the_chart_plots_exactly_the_rows_the_TABLE_shows(tab):
    """At the user's request: "it should be filtered according to the
    table below it, which would still have the same filters as before -
    usually set to the top 10 heroes based on my pick rate".

    Two surfaces disagreeing about which heroes they cover is this app's
    most repeated bug, and here they are inches apart on one card.
    """
    from tools import shoot
    win, history = tab
    table = history._tables["gold"][0]
    plot = plot_of(history, "gold")

    assert sorted(p[0] for p in plot.points) == sorted(
        r.key for r in table.drawn_rows)

    table.set_view(top=10, by="games")
    shoot.settle(win)
    assert len(table.drawn_rows) == 10
    assert sorted(p[0] for p in plot.points) == sorted(
        r.key for r in table.drawn_rows), "the cut moved one and not the other"


def test_a_scatter_of_two_dots_is_not_drawn_at_all(tab):
    """Below three heroes there is no shape to read, so the card shows
    the table alone rather than a box with a mark in it."""
    from tools import shoot
    win, history = tab
    table = history._tables["gold"][0]
    plot = plot_of(history, "gold")
    table.set_view(top=3, by="games")
    shoot.settle(win)
    assert plot.isVisible()
    table.set_view(top=2, by="games")
    shoot.settle(win)
    assert not plot.isVisible()


def test_only_the_IMPACT_sections_get_one(tab):
    """The win-rate blocks already plot a win rate - their tables ARE the
    Y axis - so a chart of win rate against win rate would say nothing.
    The summary cards keep their bars: "I think it's fine to leave the
    summary plot how it is"."""
    _win, history = tab
    for ident in ("gold", "xp", "cs", "denies", "herodmg", "herokda",
                  "towerdmg"):
        assert plot_of(history, ident) is not None, ident
    for ident in ("hero", "dow", "tod", "side", "party", "tilt"):
        assert plot_of(history, ident) is None, ident

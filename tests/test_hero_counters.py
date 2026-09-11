"""How counterable each of your heroes is, ranked against the whole pool.

The one section of the History tab that is NOT measured from the user's
own games: the figure is a property of the hero, read out of the ranked
dataset, and the match history only decides which heroes are listed.
"""

import numpy as np
import pytest

from draft_assist.data.store import Dataset
from draft_assist.history import analyse


def a_dataset(ids, matrix, picks=None):
    """A dataset with `matrix` ANTISYMMETRISED, the way ingestion leaves
    it — `normalize` does `d = (d - d.T) / 2` and `sanity_check` refuses
    a matrix that is not, so a test built on a raw one would be testing
    something the app can never be handed."""
    size = len(ids)
    raw = np.asarray(matrix, dtype=float).reshape(size, size)
    if size:
        raw = (raw - raw.T) / 2
        np.fill_diagonal(raw, 0.0)
    return Dataset(
        hero_ids=list(ids), index={h: i for i, h in enumerate(ids)},
        heroes={h: {"name": f"Hero {h}"} for h in ids},
        baseline=np.full(size, 0.5),
        picks=np.asarray(picks if picks is not None else [100] * size,
                         dtype=float),
        delta_vs=raw, delta_with=np.zeros((size, size)), meta={})


def test_a_hero_the_field_beats_ranks_below_one_it_beats():
    """The whole point: sum a hero's matchup delta over the pool, and a
    hero everything beats sinks to the bottom."""
    matrix = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    matrix[0] = [0, -5, -5]          # hero 1 loses to both
    matrix[1] = [5, 0, 0]            # hero 2 beats hero 1
    ds = a_dataset([1, 2, 3], matrix)
    deltas, standing, _datum = analyse.counter_standings(ds)

    assert deltas[1] < deltas[2], "the beaten hero is the counterable one"
    # BIG MEANS HARD TO COUNTER, at the user's request. It read "top 33%"
    # for the best of three, which is the same hero said backwards - and
    # an X axis running strong-to-weak against a Y axis running bad-to-
    # good would draw a real correlation as a downward slope.
    assert standing[max(deltas, key=deltas.get)] == "67%"
    assert standing[min(deltas, key=deltas.get)] == "0%"


def test_a_counter_nobody_picks_counts_for_less():
    """At the user's request — "this should be driven by the community
    data of hero pick rate". Two heroes countered by an IDENTICAL margin
    rank differently when one of those counters is never picked, and an
    unweighted sum cannot tell them apart at all."""
    size = 5
    matrix = [[0] * size for _ in range(size)]
    matrix[0][2] = -10          # hero 1 is crushed by hero 3 (popular)
    matrix[1][3] = -10          # hero 2 is crushed by hero 4 (obscure)

    lopsided = a_dataset([1, 2, 3, 4, 5], matrix,
                         picks=[100, 100, 10000, 100, 100])
    deltas, _s, _d = analyse.counter_standings(lopsided)
    assert deltas[1] < deltas[2], (
        "the hero whose counter is actually picked is the counterable one")

    # The control: with every hero picked equally they are identical,
    # which is exactly what an unweighted sum would say in BOTH cases.
    flat = a_dataset([1, 2, 3, 4, 5], matrix, picks=[100] * 5)
    same, _s, _d = analyse.counter_standings(flat)
    assert same[1] == pytest.approx(same[2])


def test_no_statistics_says_so_rather_than_drawing_an_empty_table():
    """An empty table reads as "nothing counters your heroes", which is a
    measurement nobody made. The cause is one the user can fix."""
    block = analyse.counter_analysis([], None)
    assert block.kind == "counters" and block.rows == []
    assert "Downloads" in block.caveat, "it names the fix"

    empty = a_dataset([], [])
    assert analyse.counter_standings(empty) == ({}, {}, 0.0)


def test_only_heroes_the_dataset_knows_are_listed():
    """A hero played but missing from the statistics has no figure, and
    an invented one would be worse than leaving it out."""
    from draft_assist.history.shape import Match
    from datetime import datetime

    def played(hero_id, name, count):
        return [Match(match_id=n, start=0, when=datetime(2026, 1, 1),
                      duration=1800, slot=0, radiant=True, win=True,
                      hero_id=hero_id, hero=name) for n in range(count)]

    matches = played(1, "Known", 10) + played(99, "Unknown", 10)
    ds = a_dataset([1, 2], [[0, 3], [-3, 0]])
    block = analyse.counter_analysis(matches, ds)
    assert [r.key for r in block.shown] == ["Known"]


def test_the_table_is_ordered_least_counterable_first():
    """"Largest negative score at the bottom", as asked."""
    from draft_assist.history.shape import Match
    from datetime import datetime

    matches = []
    for hero_id, name in ((1, "Beaten"), (2, "Strong"), (3, "Middling")):
        matches += [Match(match_id=hero_id * 100 + n, start=0,
                          when=datetime(2026, 1, 1), duration=1800, slot=0,
                          radiant=True, win=True, hero_id=hero_id,
                          hero=name) for n in range(10)]
    ds = a_dataset([1, 2, 3], [[0, -6, -3], [6, 0, 2], [3, -2, 0]])
    block = analyse.counter_analysis(matches, ds)

    means = [r.mean for r in block.shown]
    assert means == sorted(means, reverse=True)
    assert block.shown[0].key == "Strong"
    assert block.shown[-1].key == "Beaten"
    assert all(r.note.endswith("%") for r in block.shown)
    assert not any(r.note.startswith("top") for r in block.shown), (
        "the old strong-is-small wording is gone")


def test_it_sits_above_the_item_block_and_is_a_section_like_any_other():
    """Placed there at the user's request, and held to the same rules the
    other sections are: one order, one set of keys."""
    assert "counters" in analyse.NAMES
    assert analyse.NAMES["counters"] == "Hero Counters"
    order = list(analyse.BLOCK_ORDER)
    assert order.index("counters") == order.index("items") - 1
    assert set(order) == {key for key, _n, _on, _d in analyse.ANALYSES}


# ---------------------------------------------------------- the shield --

def test_the_shield_needs_no_match_history_at_all():
    """Which is the whole difference between it and the heart. The heart
    is your own record; the shield is a property of the hero, so it can
    mark a hero nobody has ever picked - exactly where it says something
    the strip could not otherwise."""
    ds = a_dataset([1, 2, 3, 4], [[0, 5, 5, 5], [-5, 0, 0, 0],
                                  [-5, 0, 0, 0], [-5, 0, 0, 0]])
    marked = analyse.shielded(ds, floor_pct=70)
    assert 1 in marked, "the hero the field loses to is shielded"
    assert "vs the field" in marked[1] and "%" in marked[1]
    # No matches were passed in anywhere above.


def test_the_bar_is_strictly_above_the_floor():
    """Standing AT the 70th percentile means 70% are at or below you,
    which is the top of the bottom 70% rather than the top 30%. The stars
    learned this the hard way; the shield starts with it."""
    ds = a_dataset([1, 2, 3, 4, 5],
                   [[0, 1, 2, 3, 4], [-1, 0, 1, 2, 3], [-2, -1, 0, 1, 2],
                    [-3, -2, -1, 0, 1], [-4, -3, -2, -1, 0]])
    # Five heroes: the best has 80% at or below it, the second 60%.
    assert set(analyse.shielded(ds, floor_pct=70)) == {1}
    assert set(analyse.shielded(ds, floor_pct=50)) == {1, 2}
    # A floor of 99 is "the very top" and still admits the best hero.
    assert set(analyse.shielded(ds, floor_pct=99)) == set()


def test_no_statistics_means_no_shields_rather_than_all_of_them():
    """A dataset that was never downloaded must not mark every hero as
    hard to counter, which is what an empty ranking would do if the floor
    were applied to nothing."""
    assert analyse.shielded(None, 70) == {}
    assert analyse.shielded(a_dataset([], []), 70) == {}


def test_the_bar_plots_the_RANKING_not_the_raw_figure():
    """At the user's request: "if Sniper is in the top 9% in terms of
    being hard to counter then his score is 91%, a lot of green".

    It also fixes the column at the root. Counterability is clustered -
    a pick-weighted average over ~126 heroes sits within about half a
    point of neutral - so a bar scaled to the raw figures is a few
    pixels for everybody and says nothing. Percentiles are UNIFORM by
    construction, so the column always uses its full width.
    """
    from datetime import datetime
    from draft_assist.history.shape import Match

    size = 100
    ids = list(range(1, size + 1))
    # A ladder: hero 1 beats everyone below it, hero 100 beats nobody.
    matrix = [[(j - i) for j in range(size)] for i in range(size)]
    ds = a_dataset(ids, matrix)

    # The player picks the 9th best and the very worst.
    matches = []
    for hero_id in (9, size):
        matches += [Match(match_id=hero_id * 100 + k, start=0,
                          when=datetime(2026, 1, 1), duration=1800, slot=0,
                          radiant=True, win=True, hero_id=hero_id,
                          hero=f"Hero {hero_id}") for k in range(10)]

    block = analyse.counter_analysis(matches, ds)
    assert block.scale == 50.0, "half the percentile range, always"

    by_hero = {r.key: r for r in block.shown}
    ninth = by_hero["Hero 9"]
    # 9th of 100 => 91 heroes at or below => the 91st percentile, which
    # is +41 on a bar centred at the median.
    assert ninth.delta == pytest.approx(41.0)
    assert ninth.delta > 0, "green: harder to counter than most"
    assert abs(ninth.delta) / block.scale == pytest.approx(0.82)

    worst = by_hero[f"Hero {size}"]
    assert worst.delta == pytest.approx(-50.0), "bottom of the field"
    assert abs(worst.delta) / block.scale == pytest.approx(1.0)


def test_a_clustered_field_still_fills_the_bar_column():
    """The failure this replaces: with the raw figures the whole pool
    lives within a fraction of a point, every bar rounded to nothing and
    the column read as blank. A ranking cannot do that - the spread of
    percentiles does not depend on the spread of the numbers."""
    from datetime import datetime
    from draft_assist.history.shape import Match

    size = 40
    ids = list(range(1, size + 1))
    # Differences a thousand times smaller than a percentage point.
    matrix = [[(j - i) * 0.001 for j in range(size)] for i in range(size)]
    ds = a_dataset(ids, matrix)
    matches = [Match(match_id=k, start=0, when=datetime(2026, 1, 1),
                     duration=1800, slot=0, radiant=True, win=True,
                     hero_id=1, hero="Best")
               for k in range(10)]
    block = analyse.counter_analysis(matches, ds)

    best = block.shown[0]
    assert abs(best.mean) < 0.05, "the raw figure really is tiny"
    assert abs(best.delta) / block.scale > 0.9, (
        "but the bar is nearly full, because it plots the ranking")


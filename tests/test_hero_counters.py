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
    assert standing[max(deltas, key=deltas.get)].startswith("top ")
    # Ranked against EVERY hero in the game, so the best of three is the
    # top third rather than "top 1".
    assert standing[max(deltas, key=deltas.get)] == "top 33%"
    assert standing[min(deltas, key=deltas.get)] == "top 100%"


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
    assert all(r.note.startswith("top ") for r in block.shown)


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
    assert "vs the field" in marked[1] and "top " in marked[1]
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

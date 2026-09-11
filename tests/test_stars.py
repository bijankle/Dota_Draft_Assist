"""Which heroes the Draft tab stars, and why.

The rule is the user's: "rank all the hero picks for that period — only
the heroes that rank in the top 30% pick rate would be a candidate for
the star, same goes for win rate, and if both are satisfied they get a
star". Two percentile floors, both of them theirs to set.
"""

from dataclasses import dataclass

import pytest

from draft_assist.history import stars


@dataclass
class Played:
    hero_id: int
    win: bool


def run(spec: dict) -> list:
    """{hero id: (games, wins)} -> the matches that would produce it."""
    out = []
    for hero_id, (games, wins) in spec.items():
        out += [Played(hero_id, True)] * wins
        out += [Played(hero_id, False)] * (games - wins)
    return out


TEN = {1: (40, 26), 2: (30, 12), 3: (25, 15), 4: (20, 6), 5: (15, 9),
       6: (10, 3), 7: (8, 6), 8: (5, 1), 9: (3, 3), 10: (1, 1)}


def test_both_bars_have_to_be_cleared():
    """Heroes 1 and 3 are in the top 30% by picks AND above the median
    win rate. Hero 2 is played more than 3 and loses on it; hero 7 wins
    on it and is barely played."""
    marked = stars.measure(run(TEN), 70, 50)
    assert sorted(marked.heroes) == [1, 3]
    assert 2 not in marked, "played a lot is not enough"
    assert 7 not in marked, "winning a lot is not enough"


def test_the_setting_is_a_percentile_floor():
    """70 means the 70th percentile, which is the top 30% — the user's
    own worked example. Nought is no bar on that axis."""
    everything = stars.measure(run(TEN), 0, 0)
    # Everything except the one-game hero, which the games floor stops.
    assert sorted(everything.heroes) == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert stars.measure(run(TEN), 99, 99).heroes == frozenset()
    # Picks alone: the top 30% by games, whatever they win.
    assert sorted(stars.measure(run(TEN), 70, 0).heroes) == [1, 2, 3]


def test_a_lucky_handful_of_games_is_not_a_star():
    """The trap every floor in `analyse` exists for: hero 9 is 3 games at
    100% and hero 10 is one game at 100%, so both top the win-rate
    ranking outright and neither is evidence of anything."""
    marked = stars.measure(run(TEN), 70, 50)
    assert 9 not in marked and 10 not in marked
    assert marked.form[9].win_pct == 1.0, "it really did top that ranking"
    assert marked.form[9].pick_pct < 0.7, "the picks bar is what stops it"


def test_the_games_floor_stops_the_degenerate_sample():
    """Three games across three heroes and the top third by win rate is a
    hero played ONCE. The picks percentile nearly handles this by itself
    and 'nearly' is not a floor."""
    tiny = stars.measure(run({1: (1, 1), 2: (1, 0), 3: (1, 0)}), 60, 60)
    assert tiny.heroes == frozenset()


def test_ties_are_starred_alike():
    """Two heroes on the same games and the same rate are the same hero
    as far as this rule can tell; splitting them by whatever `sorted`
    did would star one and not the other on identical evidence."""
    marked = stars.measure(run({1: (10, 5), 2: (10, 5), 3: (2, 0)}), 50, 50)
    assert sorted(marked.heroes) == [1, 2]


def test_it_is_keyed_by_hero_id_not_by_name():
    """The hero block's buckets are keyed by OpenDota's DISPLAY NAME and
    the Draft tab knows its candidates by the numeric id from its own
    dataset. Matching those two strings would be one rename away from a
    strip with no stars and nothing saying why."""
    marked = stars.measure(run(TEN), 70, 50)
    assert all(isinstance(hero, int) for hero in marked.heroes)
    assert 1 in marked and "1" not in marked


def test_nothing_measured_stars_nothing():
    assert stars.measure([], 70, 50).heroes == frozenset()
    assert stars.measure(None, 70, 50).heroes == frozenset()


def test_a_match_with_no_hero_is_skipped():
    """`shape` leaves `hero_id` None when OpenDota did not name one, and
    a bucket keyed on None is a hero that does not exist."""
    matches = run({1: (10, 6)}) + [Played(None, True)]
    marked = stars.measure(matches, 0, 0)
    assert sorted(marked.heroes) == [1]


def test_each_figure_carries_its_own_standing():
    """Each figure says how far inside the bar it is, which is what the
    star itself cannot: "having the star is evidence of this already".

    AS A PERCENTILE, high meaning strong, at the user's request - every
    bar and every standing in this app now reads the same way round, so
    the heart and the shield can be set from the same mental model.
    """
    marked = stars.measure(run(TEN), 70, 50)
    # Hero 1 is the most played of ten, and its 65% is the fourth best.
    assert marked.why(1).splitlines() == [
        "My Pick Rate = 40 games (100th percentile)",
        "My Win Rate = 65% (70th percentile)"]
    assert marked.why(4) == "", "an unstarred tile explains nothing"
    assert "inside" not in marked.why(3), "the star is that evidence"


def test_in_the_top_x_percent_is_not_one_minus_the_percentile():
    """The top hero of ten has every hero at or below it, so its
    percentile is 1.0 and the naive complement reads "top 0%" — a claim
    about nobody. It is in the top ONE of ten."""
    marked = stars.measure(run(TEN), 0, 0)
    assert marked.form[1].pick_pct == 1.0
    assert marked.form[1].pick_top == pytest.approx(0.1)
    # Third by games is in the top three of ten.
    assert marked.form[3].pick_top == pytest.approx(0.3)
    # And the least played is in the top all-of-them, never over it.
    assert marked.form[10].pick_top == pytest.approx(1.0)
    assert all(0 < row.pick_top <= 1.0 and 0 < row.win_top <= 1.0
               for row in marked.form.values())


def test_tied_heroes_read_the_same_standing():
    """They share one percentile because the rule treats them as one
    hero, so the number printed at them has to agree with that."""
    marked = stars.measure(run({1: (10, 5), 2: (10, 5), 3: (2, 0)}), 0, 0)
    assert marked.form[1].pick_top == marked.form[2].pick_top
    assert marked.why(1) == marked.why(2)


def test_rank_fraction_runs_one_to_a_fraction():
    ranks = stars.rank_fraction({1: 10, 2: 5, 3: 1})
    assert ranks[1] == 1.0
    assert ranks[3] == pytest.approx(1 / 3)

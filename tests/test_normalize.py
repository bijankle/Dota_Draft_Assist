"""Normalisation is the easiest thing in the system to silently break, so its
math is pinned down here with hand-computed cases."""

import numpy as np
import pytest

from draft_assist.data import normalize


def make_counts(m, w):
    return (m, w)


def big(m):  # large sample -> shrinkage ~1
    return m * 1_000_000


def test_vs_delta_subtracts_both_baselines():
    # Hero 1 baseline 0.55, hero 2 baseline 0.50.
    # Expected winrate of 1 vs 2 under independence: 0.5 + 0.05 - 0.0 = 0.55.
    # Observed 0.60 -> interaction delta +0.05 (before symmetrisation).
    index = normalize.hero_index([1, 2])
    b = np.array([0.55, 0.50])
    matchups = {
        1: {"vs": {2: (big(1), int(big(1) * 0.60))}, "with": {}},
        2: {"vs": {1: (big(1), int(big(1) * 0.40))}, "with": {}},
    }
    d_vs, _, _, _ = normalize.raw_deltas(index, b, matchups)
    # Row 2's view: observed 0.40, expected 0.5 - 0.05 = 0.45, delta -0.05.
    # Antisymmetrised: (0.05 - (-0.05)) / 2 = 0.05.
    #
    # `raw_deltas` RATHER THAN `build_delta_matrices`, because the stage
    # after it removes whatever main effect the baseline left behind and
    # TWO HEROES CANNOT TELL THE TWO APART: with one pair in the whole
    # matrix, "hero 1 counters hero 2 by 5 points" and "hero 1 is 5
    # points better than the table says" are the same number. See
    # `test_two_heroes_cannot_tell_an_interaction_from_a_main_effect`.
    assert d_vs[0, 1] == pytest.approx(0.05, abs=1e-3)
    assert d_vs[1, 0] == pytest.approx(-0.05, abs=1e-3)


def test_with_delta_subtracts_both_baselines():
    # Both baselines 0.52 -> expected together 0.5 + 0.02 + 0.02 = 0.54.
    # Observed 0.58 -> synergy delta +0.04, symmetric.
    index = normalize.hero_index([1, 2])
    b = np.array([0.52, 0.52])
    matchups = {
        1: {"vs": {}, "with": {2: (big(1), int(big(1) * 0.58))}},
        2: {"vs": {}, "with": {1: (big(1), int(big(1) * 0.58))}},
    }
    _, d_with, _, _ = normalize.raw_deltas(index, b, matchups)
    assert d_with[0, 1] == pytest.approx(0.04, abs=1e-3)
    assert d_with[1, 0] == pytest.approx(0.04, abs=1e-3)


def test_average_hero_shows_no_fake_edge():
    # The whole point: a strong hero (0.55) with NO real interaction must get
    # delta ~0, not inherit its main effect as a fake matchup advantage.
    index = normalize.hero_index([1, 2])
    b = np.array([0.55, 0.50])
    # Observed exactly what baselines predict: 0.55 against hero 2.
    matchups = {
        1: {"vs": {2: (big(1), int(big(1) * 0.55))}, "with": {}},
        2: {"vs": {1: (big(1), int(big(1) * 0.45))}, "with": {}},
    }
    d_vs, _ = normalize.build_delta_matrices(index, b, matchups)
    assert d_vs[0, 1] == pytest.approx(0.0, abs=1e-3)


def test_low_sample_shrinkage():
    index = normalize.hero_index([1, 2])
    b = np.array([0.5, 0.5])
    m = normalize.SHRINK_PRIOR_MATCHES  # shrink factor = m/(m+m) = 0.5
    matchups = {
        1: {"vs": {2: (m, int(m * 0.6))}, "with": {}},
        2: {"vs": {1: (m, int(m * 0.4))}, "with": {}},
    }
    # The SUBTRACTION stage, for the reason the two above take it: two
    # heroes and one pair is the case where a main effect and an
    # interaction are the same number.
    d_vs, _, _, _ = normalize.raw_deltas(index, b, matchups)
    assert d_vs[0, 1] == pytest.approx(0.05, abs=1e-3)  # 0.10 raw * 0.5 shrink


def test_missing_pair_is_zero_information():
    index = normalize.hero_index([1, 2, 3])
    b = np.array([0.5, 0.5, 0.5])
    matchups = {1: {"vs": {2: (big(1), int(big(1) * 0.55))}, "with": {}}}
    d_vs, d_with = normalize.build_delta_matrices(index, b, matchups)
    assert d_vs[0, 2] == 0.0
    assert d_with[0, 1] == 0.0


def test_matrix_structure():
    rng = np.random.default_rng(7)
    ids = list(range(1, 30))
    index = normalize.hero_index(ids)
    b = 0.5 + rng.uniform(-0.05, 0.05, len(ids))
    matchups = {}
    for hid in ids:
        vs, wi = {}, {}
        for oid in ids:
            if oid == hid:
                continue
            m = int(rng.integers(500, 5000))
            vs[oid] = (m, int(m * rng.uniform(0.4, 0.6)))
            wi[oid] = (m, int(m * rng.uniform(0.4, 0.6)))
        matchups[hid] = {"vs": vs, "with": wi}
    d_vs, d_with = normalize.build_delta_matrices(index, b, matchups)
    assert normalize.sanity_check(d_vs, d_with) == []
    assert np.allclose(d_vs, -d_vs.T)
    assert np.allclose(d_with, d_with.T)
    assert np.all(np.diag(d_vs) == 0) and np.all(np.diag(d_with) == 0)


def test_sanity_check_catches_raw_rates():
    # Storing raw ~0.5 win rates instead of deltas must be flagged.
    n = 10
    raw = np.full((n, n), 0.5, dtype=np.float32)
    problems = normalize.sanity_check(raw, np.zeros((n, n), dtype=np.float32))
    assert any("raw" in p for p in problems)


def ring(n, pair=None, points=0.0):
    """n heroes, every pair measured, one pair optionally carrying a
    real interaction of `points`."""
    ids = list(range(n))
    index = normalize.hero_index(ids)
    matchups = {}
    for i in ids:
        vs, with_ = {}, {}
        for j in ids:
            if i == j:
                continue
            extra = points if pair and {i, j} == set(pair) else 0.0
            m = big(1)
            vs[j] = (m, int(m * (0.5 + extra)))
            with_[j] = (m, int(m * (0.5 + extra)))
        matchups[i] = {"vs": vs, "with": with_}
    b = np.full(n, 0.5)
    return index, b, matchups


def test_two_heroes_cannot_tell_an_interaction_from_a_main_effect():
    """And the answer is zero, which is the honest one.

    This is not a defect to fix, it is what the model can support: with
    one pair in the matrix there is no second partner to measure either
    hero against, so "they work well together" and "both heroes are
    better than the table says" are indistinguishable. Real data has 126
    partners per hero - see the test below for what survives there.
    """
    index, b, matchups = ring(2, pair=(0, 1), points=0.04)
    _, d_with = normalize.build_delta_matrices(index, b, matchups)
    assert d_with[0, 1] == pytest.approx(0.0, abs=1e-6)


def test_at_a_real_size_a_single_pair_keeps_almost_all_of_its_edge():
    """The cost of the main-effect removal, measured rather than assumed.

    One genuine +4pp synergy among 127 heroes moves its two heroes' row
    means by a 126th of itself, so that is all the centring can take -
    under 2% of the figure. The same correction removes a baseline error
    whole, because that one is on every pair at once.
    """
    index, b, matchups = ring(127, pair=(3, 9), points=0.04)
    _, d_with = normalize.build_delta_matrices(index, b, matchups)
    assert d_with[3, 9] == pytest.approx(0.04, rel=0.02)
    # And no edge invented between heroes that never interacted.
    assert abs(float(d_with[3, 40])) < 0.001


def test_the_sweep_count_cannot_change_the_answer():
    """THE BUG THIS EXISTS FOR, found by the suite an hour after it
    shipped: the antisymmetric correction took a row's WHOLE mean off,
    which overshoots by n/(n-1) and makes the sweep's multiplier
    -1/(n-1). At two heroes that is exactly -1, so the matchup FLIPPED
    SIGN on every sweep and the stored number came out of the parity of
    `CENTRING_SWEEPS`. See `normalize._damping`.
    """
    d = np.array([[0.0, 0.05], [-0.05, 0.0]])
    seen = d != 0.0
    answers = set()
    try:
        for sweeps in range(1, 8):
            normalize.CENTRING_SWEEPS = sweeps
            answers.add(round(float(normalize._without_main_effect(
                d, seen, antisymmetric=True)[0, 1]), 9))
    finally:
        normalize.CENTRING_SWEEPS = 4
    assert len(answers) == 1, f"the answer moved with the sweeps: {answers}"


@pytest.mark.parametrize("n", [2, 3, 20, 127])
def test_every_row_mean_really_reaches_zero(n):
    """Which is the whole claim: a row mean IS the hero's main effect."""
    index, b, matchups = ring(n)
    rng = np.random.default_rng(n)
    for i in matchups:
        for side in ("vs", "with"):
            for j, (m, _w) in list(matchups[i][side].items()):
                matchups[i][side][j] = (
                    m, int(m * (0.5 + rng.normal(0, 0.03))))
    d_vs, d_with = normalize.build_delta_matrices(index, b, matchups)
    for name, mat in (("vs", d_vs), ("with", d_with)):
        seen = mat != 0.0
        worst = float(np.abs(normalize._row_means(
            mat.astype(np.float64), seen)).max())
        assert worst < 1e-3, f"{name} at n={n}: worst row mean {worst}"

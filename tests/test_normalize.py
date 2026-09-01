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
    d_vs, _ = normalize.build_delta_matrices(index, b, matchups)
    # Row 2's view: observed 0.40, expected 0.5 - 0.05 = 0.45, delta -0.05.
    # Antisymmetrised: (0.05 - (-0.05)) / 2 = 0.05.
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
    _, d_with = normalize.build_delta_matrices(index, b, matchups)
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
    d_vs, _ = normalize.build_delta_matrices(index, b, matchups)
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

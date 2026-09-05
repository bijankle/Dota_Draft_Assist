"""Normalisation of raw pairwise win rates into interaction deltas.

THIS IS THE INVARIANT MOST LIKELY TO BE BROKEN BY A FUTURE CHANGE, so to be
explicit: the stored matrices contain NORMALISED DELTAS, never raw win rates.

A raw matchup win rate is contaminated by the general strength of both heroes
involved: a hero that wins 55% of all its games shows ~55% against most
opponents, which says nothing about the matchup. We want the interaction
term, not the main effects, so at ingestion every figure has the
baseline-predicted value subtracted:

  vs   (i against enemy j): expected = 0.5 + (b_i - 0.5) - (b_j - 0.5)
  with (i alongside ally j): expected = 0.5 + (b_i - 0.5) + (b_j - 0.5)

  delta = observed_winrate - expected

where b_x is hero x's baseline win rate in the target bracket. This linear
additive model is a deliberate approximation; it holds for small
perturbations and the drill-down view exists so the user can catch it
reaching a plausible total for poor reasons.

Additional denoising, also applied here at ingestion:
- low-sample shrinkage: delta is scaled by m / (m + SHRINK_PRIOR_MATCHES) so
  a 60% winrate over 40 games moves the matrix far less than over 4000;
- the vs matrix is antisymmetrised (d[i,j] = (d[i,j] - d[j,i]) / 2) because
  i-beats-j and j-beats-i are the same games seen twice; the with matrix is
  symmetrised the same way.

All functions are pure and operate on plain dicts / numpy arrays so the whole
layer is testable without any network.
"""

import numpy as np

# Pseudo-count of matches at which a pair's delta reaches half weight.
SHRINK_PRIOR_MATCHES = 200


def hero_index(hero_ids: list[int]) -> dict[int, int]:
    """Stable hero id -> matrix row/column index (ids are sparse, ~1..140)."""
    return {hid: i for i, hid in enumerate(sorted(hero_ids))}


def baseline_vector(index: dict[int, int],
                    baselines: dict[int, dict]) -> np.ndarray:
    b = np.full(len(index), 0.5, dtype=np.float64)
    for hid, i in index.items():
        if hid in baselines:
            b[i] = baselines[hid]["winrate"]
    return b


def build_delta_matrices(index: dict[int, int], b: np.ndarray,
                         matchups: dict[int, dict]) -> tuple[np.ndarray, np.ndarray]:
    """Raw pairwise counts -> (delta_vs, delta_with), both NxN float32.

    matchups[hid]["vs"|"with"][other_id] = (match_count, win_count), wins
    from hid's perspective. Missing pairs stay at delta 0 (no information).
    """
    n = len(index)
    d_vs = np.zeros((n, n), dtype=np.float64)
    d_with = np.zeros((n, n), dtype=np.float64)

    for hid, sides in matchups.items():
        if hid not in index:
            continue
        i = index[hid]
        for side, mat in (("vs", d_vs), ("with", d_with)):
            for oid, (m, w) in sides[side].items():
                if oid not in index or m <= 0:
                    continue
                j = index[oid]
                observed = w / m
                sign = -1.0 if side == "vs" else 1.0
                expected = 0.5 + (b[i] - 0.5) + sign * (b[j] - 0.5)
                shrink = m / (m + SHRINK_PRIOR_MATCHES)
                mat[i, j] = (observed - expected) * shrink

    # Same games seen from both sides: enforce the structural symmetry.
    d_vs = (d_vs - d_vs.T) / 2.0
    d_with = (d_with + d_with.T) / 2.0
    np.fill_diagonal(d_vs, 0.0)
    np.fill_diagonal(d_with, 0.0)
    return d_vs.astype(np.float32), d_with.astype(np.float32)


def sanity_check(d_vs: np.ndarray, d_with: np.ndarray,
                 expect_synergy: bool = True) -> list[str]:
    """Cheap invariant checks on freshly built matrices; returns a list of
    problems (empty = fine). Deltas are small interaction terms: values that
    look like raw win rates (~0.5) mean normalisation was skipped."""
    problems = []
    if expect_synergy and not d_with.any():
        problems.append(
            "with: every synergy delta is zero — the source carried no "
            "ally-pair counts, or they were dropped")
    for name, m in (("vs", d_vs), ("with", d_with)):
        if not np.isfinite(m).all():
            problems.append(f"{name}: non-finite entries")
        if abs(float(m.mean())) > 0.02:
            problems.append(
                f"{name}: mean {m.mean():.3f} far from 0 — looks like raw "
                "rates were stored instead of deltas")
        if float(np.abs(m).max()) > 0.30:
            problems.append(
                f"{name}: |max| {np.abs(m).max():.3f} > 0.30 — deltas this "
                "large suggest broken expected-value subtraction")
    if not np.allclose(d_vs, -d_vs.T, atol=1e-6):
        problems.append("vs matrix is not antisymmetric")
    if not np.allclose(d_with, d_with.T, atol=1e-6):
        problems.append("with matrix is not symmetric")
    return problems

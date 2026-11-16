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
                         matchups: dict[int, dict],
                         report: dict | None = None
                         ) -> tuple[np.ndarray, np.ndarray]:
    """Raw pairwise counts -> (delta_vs, delta_with), both NxN float32.

    matchups[hid]["vs"|"with"][other_id] = (match_count, win_count), wins
    from hid's perspective. Missing pairs stay at delta 0 (no information).
    """
    n = len(index)
    d_vs = np.zeros((n, n), dtype=np.float64)
    d_with = np.zeros((n, n), dtype=np.float64)
    seen_vs = np.zeros((n, n), dtype=bool)
    seen_with = np.zeros((n, n), dtype=bool)

    for hid, sides in matchups.items():
        if hid not in index:
            continue
        i = index[hid]
        for side, mat, seen in (("vs", d_vs, seen_vs),
                                ("with", d_with, seen_with)):
            for oid, (m, w) in sides[side].items():
                if oid not in index or m <= 0:
                    continue
                j = index[oid]
                observed = w / m
                sign = -1.0 if side == "vs" else 1.0
                expected = 0.5 + (b[i] - 0.5) + sign * (b[j] - 0.5)
                shrink = m / (m + SHRINK_PRIOR_MATCHES)
                mat[i, j] = (observed - expected) * shrink
                seen[i, j] = True

    # Same games seen from both sides: enforce the structural symmetry.
    d_vs = (d_vs - d_vs.T) / 2.0
    d_with = (d_with + d_with.T) / 2.0
    seen_vs |= seen_vs.T
    seen_with |= seen_with.T
    for mat in (d_vs, d_with, seen_vs, seen_with):
        np.fill_diagonal(mat, 0 if mat.dtype == np.float64 else False)

    # AND WHATEVER MAIN EFFECT THE BASELINE FAILED TO REMOVE. What was
    # taken off each hero is recorded when a caller asks: it is the one
    # number that says WHICH heroes the baseline is wrong about and by
    # how much, and it is measured on the real pull rather than guessed.
    if report is not None:
        before = _row_means(d_vs, seen_vs) + _row_means(d_with, seen_with)
        back = {i: hid for hid, i in index.items()}
        report["main_effects"] = {back[i]: float(before[i] / 2.0)
                                  for i in range(n) if back.get(i) is not None}
    d_vs = _without_main_effect(d_vs, seen_vs, antisymmetric=True)
    d_with = _without_main_effect(d_with, seen_with, antisymmetric=False)
    return d_vs.astype(np.float32), d_with.astype(np.float32)


def _row_means(d: np.ndarray, seen: np.ndarray) -> np.ndarray:
    counts = seen.sum(axis=1)
    return np.where(counts > 0, (d * seen).sum(axis=1) / np.maximum(counts, 1),
                    0.0)


# A hero whose deltas still average this far from zero after the baseline
# has been subtracted is one the baseline is WRONG about: the pair counts
# and the baseline table are not describing the same population. 0.02 is
# two points of win rate, which is far outside the noise on a real pull
# and far inside the seven that produced the +63 this was found by.
MAIN_EFFECT_WARN = 0.02


# How many sweeps of the main-effect removal to run. One pass zeroes every
# row mean exactly when every pair is present; with pairs missing, each
# row's correction perturbs its neighbours' and it converges instead.
# Four is far past the point where it stops moving on real data.
CENTRING_SWEEPS = 4


def _without_main_effect(d: np.ndarray, seen: np.ndarray,
                         antisymmetric: bool) -> np.ndarray:
    """Take each hero's own strength back out of its row.

    SUBTRACTING THE BASELINE IS MEANT TO DO THIS AND CANNOT BE TRUSTED TO.
    It removes `b_i`, the win rate some OTHER table reported for hero i,
    and the pair counts are not always drawn from the same population as
    that table: this app takes its baselines from OpenDota and its
    pairwise counts from whichever source is configured, and the two do
    not bracket matches the same way - "Stratz buckets whole matches by
    average rank; OpenDota counts each player at their own rank". A hero
    whose win rate is flat across brackets barely notices. One whose win
    rate is steep does not, and neither does a hero the baseline table
    has no row for, or one that was reworked between the two pulls.

    WHAT IT LOOKS LIKE IS A HERO THAT SYNERGISES WITH EVERYONE. The error
    is the same constant on every pair that hero appears in, so it does
    not cancel, it SUMS: nine pairs on a drafted board turn a 7-point
    baseline error into a +63 contribution with no interaction behind it
    whatever. Reported as "why is techies synergy score blown out????",
    with Techies at +63.1 beside team-mates at +5 to +13, and reproduced
    here from a 7pp baseline error over data containing no interaction at
    all: +59.1 for the mis-baselined hero and +0.0 for every other.

    THE REMEDY IS THE MODULE'S OWN STATED GOAL. "We want the interaction
    term, not the main effects" - and a hero whose row has a non-zero
    mean still carries a main effect, whatever the baseline said. So the
    mean is measured off the deltas themselves and removed, as a
    per-hero term that keeps each matrix's structure: `d[i,j] -= a_i -
    a_j` cannot break antisymmetry, `d[i,j] -= a_i + a_j` cannot break
    symmetry. It is also the invariant the app already promised
    everywhere else - the score is DRAFT FIT, and the hero's own win
    rate is deliberately not in it.

    Only pairs with data are touched or counted. A missing pair means no
    information and must stay exactly zero.
    """
    out = d.astype(np.float64, copy=True)
    counts = seen.sum(axis=1)
    live = counts > 0
    if not live.any():
        return out
    for _ in range(CENTRING_SWEEPS):
        means = np.where(live, (out * seen).sum(axis=1) / np.maximum(counts, 1),
                         0.0)
        if np.abs(means).max() < 1e-12:
            break
        if antisymmetric:
            shift = means[:, None] - means[None, :]
        else:
            shift = (means - means[live].mean() / 2.0)[:, None]
            shift = shift + shift.T
        out -= np.where(seen, shift, 0.0)
    return out


def recentre(d_vs: np.ndarray, d_with: np.ndarray,
             report: dict | None = None
             ) -> tuple[np.ndarray, np.ndarray]:
    """Take any remaining main effect out of matrices READ BACK OFF DISK.

    THE BUILD ALREADY DOES THIS AND THAT IS NOT ENOUGH. A dataset is
    pulled about twice a month and the app updates itself from `main`
    whenever the owner presses the button, so a copy that takes this fix
    still holds matrices built by the version before it - and would go on
    showing the +63 until somebody happened to re-pull. Pressing Update
    and seeing nothing change is the fault this project has a standing
    rule about: an empty update is indistinguishable from a broken one.

    IT IS IDEMPOTENT, which is what makes it safe to run every load. A
    matrix whose row means are already nought converges on the first
    sweep and the loop breaks; a matrix built before the fix is
    corrected. Same argument as the History tab recomputing its blocks
    on the way in rather than storing them: a cached file written by an
    older version must never be able to show numbers this version would
    not produce.

    WHICH PAIRS HAVE DATA IS RECOVERED FROM THE ZEROS. The `seen` masks
    are not stored - and do not need to be, because a delta of EXACTLY
    0.0 is how this module records "never played together" and a
    measured pair lands there only if `observed` equalled `expected` to
    the last bit of a float. A pair wrongly read as unseen is left
    alone, which leaves it at the nought it already held.

    THE COST OF THAT RECONSTRUCTION IS REAL AND IS BOUNDED BY REALITY.
    A pair read as unseen is also left OUT of its two heroes' row means,
    so a matrix of mostly-exact zeros gives the correction little to
    work with - a synthetic board carrying one hero's offset and
    literally nothing else is only partly corrected here, where the
    build (which holds the true masks) corrects it completely. It does
    not reach real data: a measured pair is a win count over a match
    count times a shrinkage factor, and tens of thousands of those do
    not land on 0.0. The BUILD remains the place this is done properly;
    this is the safety net for a cache an older version wrote.
    """
    seen_vs, seen_with = d_vs != 0.0, d_with != 0.0
    if report is not None:
        # WHAT IT TOOK OFF, measured on whatever is on this machine's
        # disk - which is the only place the question "why THIS hero?"
        # can be answered, since the development machine cannot reach
        # the statistics at all.
        off = (_row_means(d_vs, seen_vs) + _row_means(d_with, seen_with)) / 2.0
        report["main_effects"] = {i: float(off[i]) for i in range(len(off))}
    vs = _without_main_effect(d_vs, seen_vs, antisymmetric=True)
    with_ = _without_main_effect(d_with, seen_with, antisymmetric=False)
    return vs, with_


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

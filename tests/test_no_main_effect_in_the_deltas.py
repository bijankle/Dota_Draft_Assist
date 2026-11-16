"""A hero's own strength must not be in its interaction terms.

Reported as "why is techies synergy score blown out????", with Techies
at +63.1 on the board beside team-mates at +5 to +13, carrying the
Radiant total to +101.2 against Dire's +50.3.

IT IS NOT A PROPERTY OF TECHIES, it is the baseline being wrong about
Techies. Subtracting `b_i` is meant to take a hero's general strength
out of every pair it appears in, and `b_i` comes from a DIFFERENT
population than the pair counts do - this app reads baselines from
OpenDota and pairwise counts from whichever source is configured, and
"Stratz buckets whole matches by average rank; OpenDota counts each
player at their own rank". A hero whose win rate is flat across
brackets barely notices. Techies has about the steepest bracket curve
in the game.

AND THE ERROR SUMS RATHER THAN CANCELS, because it is the same constant
on every pair that hero is in: nine pairs on a drafted board turn a
seven-point baseline error into a +63 contribution with no interaction
behind it at all. Reproduced below.
"""

import numpy as np
import pytest

from draft_assist.data import normalize

N = 20
ALLIES, ENEMIES = [1, 2, 3, 4], [5, 6, 7, 8, 9]


def dataset(true_wr, told_wr, interaction=None):
    """Pair counts generated from `true_wr`, baselines claiming `told_wr`."""
    ids = list(range(len(true_wr)))
    index = normalize.hero_index(ids)
    matchups = {}
    for i in ids:
        vs, with_ = {}, {}
        for j in ids:
            if i == j:
                continue
            m = 3000
            extra = interaction(i, j) if interaction else 0.0
            vs[j] = (m, round(m * (0.5 + (true_wr[i] - 0.5)
                                   - (true_wr[j] - 0.5) + extra)))
            with_[j] = (m, round(m * (0.5 + (true_wr[i] - 0.5)
                                      + (true_wr[j] - 0.5) + extra)))
        matchups[i] = {"vs": vs, "with": with_}
    b = normalize.baseline_vector(
        index, {h: {"winrate": told_wr[h]} for h in ids})
    report: dict = {}
    d_vs, d_with = normalize.build_delta_matrices(index, b, matchups, report)
    return index, d_vs, d_with, report


def net(index, d_vs, d_with, hero):
    """`scoring.net_contributions` for one ally, in percentage points."""
    i = index[hero]
    total = sum(float(d_with[i, index[o]]) for o in ALLIES if o != hero)
    total += sum(float(d_vs[i, index[e]]) for e in ENEMIES)
    return total * 100


def a_wrong_baseline(points=0.07):
    true = np.full(N, 0.50)
    true[0] = 0.50 + points            # hero 0 really wins this much
    told = np.full(N, 0.50)            # the baseline table says 50%
    return true, told


def test_the_reported_blow_out_is_reproduced_without_the_fix():
    """THE PREMISE. Hand-rolled, so it holds even if the fix changes:
    data with no interaction in it at all, and a baseline seven points
    out, puts one hero sixty points clear of the rest."""
    true, told = a_wrong_baseline()
    i, j = 0, 1
    raw = []
    for other in ALLIES + ENEMIES:
        if other == 0:
            continue
        sign = 1.0 if other in ALLIES else -1.0
        observed = 0.5 + (true[0] - 0.5) + sign * (true[other] - 0.5)
        expected = 0.5 + (told[0] - 0.5) + sign * (told[other] - 0.5)
        raw.append(observed - expected)
    assert sum(raw) * 100 > 55, sum(raw) * 100


def test_a_wrong_baseline_no_longer_blows_the_hero_out():
    true, told = a_wrong_baseline()
    index, d_vs, d_with, _ = dataset(true, told)
    assert abs(net(index, d_vs, d_with, 0)) < 1.0
    for honest in (1, 2, 3):
        assert abs(net(index, d_vs, d_with, honest)) < 1.0


def test_a_real_interaction_still_comes_through():
    """The half that matters: this must not flatten everything to zero."""
    true, told = a_wrong_baseline()

    def pairs_well(i, j):
        return 0.04 if {i, j} in ({3, 1}, {3, 2}) else 0.0

    index, d_vs, d_with, _ = dataset(true, told, interaction=pairs_well)
    assert net(index, d_vs, d_with, 3) > 4.0
    assert net(index, d_vs, d_with, 1) > 1.5
    assert abs(net(index, d_vs, d_with, 0)) < 2.0


@pytest.mark.parametrize("points", [0.02, 0.05, 0.07, 0.12])
def test_it_holds_however_wrong_the_baseline_is(points):
    true, told = a_wrong_baseline(points)
    index, d_vs, d_with, _ = dataset(true, told)
    assert abs(net(index, d_vs, d_with, 0)) < 1.0


def test_the_structure_of_each_matrix_survives():
    """`vs` is the same games seen from both sides and `with` is one
    number per pair. A correction that broke either would be worse than
    the fault."""
    true, told = a_wrong_baseline()
    _, d_vs, d_with, _ = dataset(true, told)
    assert np.allclose(d_vs, -d_vs.T, atol=1e-6)
    assert np.allclose(d_with, d_with.T, atol=1e-6)
    assert np.allclose(np.diagonal(d_vs), 0)
    assert np.allclose(np.diagonal(d_with), 0)


def test_it_says_which_hero_the_baseline_was_wrong_about():
    """The answer to "but why Techies specifically?" has to come off the
    user's own pull, not off an argument."""
    true, told = a_wrong_baseline()
    _, _, _, report = dataset(true, told)
    effects = report["main_effects"]
    worst = max(effects, key=lambda h: abs(effects[h]))
    assert worst == 0
    assert effects[0] == pytest.approx(0.07, abs=0.01)
    assert all(abs(v) < normalize.MAIN_EFFECT_WARN
               for h, v in effects.items() if h != 0)


def test_a_correct_baseline_is_left_alone():
    """Nothing to remove means nothing removed."""
    true = np.full(N, 0.50)
    told = true.copy()
    _, _, _, report = dataset(true, told)
    assert all(abs(v) < 0.005 for v in report["main_effects"].values())


def test_a_missing_pair_stays_at_no_information():
    """Zero means "never played together" and must not become a number."""
    ids = list(range(6))
    index = normalize.hero_index(ids)
    matchups = {h: {"vs": {}, "with": {}} for h in ids}
    for i in ids:
        for j in ids:
            if i == j or {i, j} == {0, 1}:
                continue
            matchups[i]["vs"][j] = (3000, 1500)
            matchups[i]["with"][j] = (3000, 1500)
    b = normalize.baseline_vector(index, {h: {"winrate": 0.5} for h in ids})
    d_vs, d_with = normalize.build_delta_matrices(index, b, matchups)
    assert d_vs[index[0], index[1]] == 0.0
    assert d_with[index[0], index[1]] == 0.0


def test_one_offset_predicts_the_whole_reported_board():
    """9a on the hero, 1a on each team-mate, 13a on the side total.

    This is the measurement that closes the diagnosis: at a = 7.0 points
    it gives 63.0 / 7.0 / 91.0 against a reported Techies of +63.1,
    team-mates of +5 to +16 and a Radiant total of +101.2. It also
    answers "he is 6 times bigger than everyone elses total" - the hero
    with the bad baseline meets the error NINE times and each team-mate
    meets it ONCE.
    """
    a = 0.07
    n = 10
    vs = np.zeros((n, n))
    with_ = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            oi = a if i == 0 else 0.0
            oj = a if j == 0 else 0.0
            vs[i, j] = oi - oj
            with_[i, j] = oi + oj

    def ally_net(i):
        t = sum(with_[i, j] for j in range(5) if j != i)
        t += sum(vs[i, e] for e in range(5, 10))
        return t * 100

    assert ally_net(0) == pytest.approx(63.0, abs=0.1)
    for mate in range(1, 5):
        assert ally_net(mate) == pytest.approx(7.0, abs=0.1)
    assert sum(ally_net(i) for i in range(5)) == pytest.approx(91.0, abs=0.1)

    # AND THE FIX TAKES IT OUT. Measured deltas carry noise, so the
    # board above is given some: `recentre` reads which pairs have data
    # off the non-zeros, and a matrix of exact zeros tells it almost
    # nothing (see its docstring). Real pair rates never land on 0.0.
    rng = np.random.default_rng(11)
    jitter = rng.normal(0, 0.004, (n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            vs[i, j] += (jitter[i, j] - jitter[j, i]) / 2
            with_[i, j] += (jitter[i, j] + jitter[j, i]) / 2
    out_vs, out_with = normalize.recentre(vs, with_)
    for i in range(5):
        t = sum(out_with[i, j] for j in range(5) if j != i)
        t += sum(out_vs[i, e] for e in range(5, 10))
        assert abs(t * 100) < 2.0, f"hero {i} still at {t * 100:+.1f}"
    assert np.allclose(out_vs, -out_vs.T, atol=1e-9)
    assert np.allclose(out_with, out_with.T, atol=1e-9)


def test_the_offset_hero_no_longer_leads_every_suggestion_list():
    """The invariant at the top of CLAUDE.md, which this had broken.

    "A baseline term floats the strong heroes to the top of every list
    regardless of the draft, which is the one thing the list is not
    for" - and a row offset is exactly such a term, because `score_all`
    ranks on `vs_total + with_total` and those are rows of these
    matrices. So this was never only the board's totals.
    """
    from draft_assist.data import store
    from draft_assist.model import scoring

    size, offset = 20, 0.07
    rng = np.random.default_rng(2)
    jit = rng.normal(0, 0.012, (size, size))
    vs = np.zeros((size, size))
    with_ = np.zeros((size, size))
    for i in range(size):
        for j in range(size):
            if i == j:
                continue
            oi = offset if i == 7 else 0.0
            oj = offset if j == 7 else 0.0
            vs[i, j] = (oi - oj) + (jit[i, j] - jit[j, i]) / 2
            with_[i, j] = (oi + oj) + (jit[i, j] + jit[j, i]) / 2

    draft = scoring.DraftState(allies=[0, 1], enemies=[2, 3, 4])

    def leader(dv, dw):
        ds = store.Dataset(
            hero_ids=list(range(size)), index={h: h for h in range(size)},
            heroes={h: {"name": f"hero {h}"} for h in range(size)},
            baseline=np.full(size, 0.5),
            picks=np.full(size, 5000, dtype=np.int64),
            delta_vs=dv, delta_with=dw, meta={"pulled_at": 0.0})
        best = scoring.score_all(ds, draft)[0]
        return best.hero_id, (best.vs_total + best.with_total) * 100

    who, fit = leader(vs, with_)
    assert who == 7 and fit > 25, "the premise: the offset hero led the list"

    who, fit = leader(*normalize.recentre(vs, with_))
    assert who != 7, "the offset hero still leads every draft's suggestions"
    assert fit < 10

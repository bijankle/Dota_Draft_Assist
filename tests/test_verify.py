"""Bracket-index verification against a synthetic two-source world with a
known ground-truth alignment.

The realistic complications are modelled explicitly: neighbouring brackets
have near-identical hero win rates, rank-graded hero popularity, an empty
OpenDota Immortal tier, and — crucially — Stratz bucketing whole matches by
average rank, which smooths every bracket toward its more populous
neighbour. The checker must pass a correct mapping under all of that, and
still fail a genuine off-by-one in either direction."""

import numpy as np
import pytest

from draft_assist.data import verify

POPS = np.array([900_000, 2_200_000, 3_600_000, 3_900_000,
                 3_200_000, 1_900_000, 700_000, 260_000], dtype=float)
N_HEROES = 120
ORDER = verify.BRACKET_ORDER


class World:
    """Ground truth: per-bracket hero pick counts and win rates."""

    def __init__(self, seed: int = 5):
        rng = np.random.default_rng(seed)
        base_share = rng.dirichlet(np.full(N_HEROES, 5.0))
        popularity_grad = rng.normal(0, 0.5, N_HEROES)  # rank-graded picks
        hero_eff = rng.normal(0, 0.025, N_HEROES)
        skill_sens = rng.normal(0, 0.012, N_HEROES)     # rank-graded winrate
        self.counts = np.zeros((8, N_HEROES))
        self.wr = np.zeros((8, N_HEROES))
        for b in range(8):
            tilt = (b - 3.5) / 3.5
            share = base_share * np.exp(popularity_grad * tilt)
            share /= share.sum()
            self.counts[b] = POPS[b] * share
            self.wr[b] = np.clip(0.5 + hero_eff + skill_sens * tilt,
                                 0.05, 0.95)


def od_hero_stats(world: World, od_shift: int = 0,
                  immortal_empty: bool = True, seed: int = 7):
    """OpenDota heroStats fields; od_shift=+1 means field t actually holds
    bracket t+1's games (a real off-by-one bug), etc."""
    rng = np.random.default_rng(seed)
    hero_stats = []
    for h in range(N_HEROES):
        entry = {"id": h + 1}
        for t in range(1, 9):
            b = t - 1 + od_shift
            if not 0 <= b < 8 or (immortal_empty and b == 7):
                picks = 0
            else:
                picks = max(0, int(world.counts[b, h] * rng.normal(1, 0.02)))
            wins = int(picks * world.wr[min(max(t - 1 + od_shift, 0), 7), h])
            entry[f"{t}_pick"], entry[f"{t}_win"] = picks, wins
        hero_stats.append(entry)
    return hero_stats


def stratz_counts(world: World, smoothed: bool, seed: int = 9):
    """Stratz per-bracket counts; smoothed=True models match-average
    bucketing: each bracket is a population-weighted mixture of itself and
    its neighbours."""
    rng = np.random.default_rng(seed)
    out = {}
    for b, bracket in enumerate(ORDER):
        if smoothed:
            mix = np.zeros(N_HEROES)
            wr_acc = np.zeros(N_HEROES)
            for nb, kernel in ((b - 1, 0.25), (b, 0.5), (b + 1, 0.25)):
                if 0 <= nb < 8:
                    w = kernel * POPS[nb]
                    mix += w * world.counts[nb] / POPS[nb]
                    wr_acc += w * world.counts[nb] / POPS[nb] * world.wr[nb]
            wr = wr_acc / np.maximum(mix, 1e-9)
            counts = mix / mix.sum() * POPS[b] * 0.4
        else:
            counts = world.counts[b] * 0.4
            wr = world.wr[b]
        entry = {}
        for h in range(N_HEROES):
            m = max(1, int(counts[h] * rng.normal(1, 0.02)))
            wins = int(np.clip(rng.normal(wr[h], 0.5 / np.sqrt(m)), 0, 1) * m)
            entry[h + 1] = (m, wins)
        out[bracket] = entry
    return out


def run_verify(monkeypatch, hero_stats, counts):
    monkeypatch.setattr(verify.stratz, "fetch_bracket_counts",
                        lambda bracket, take=14: counts[bracket])
    return verify.verify_tier_mapping(hero_stats, ("ANCIENT", "DIVINE"))


def test_correct_mapping_clean_sources_passes(monkeypatch):
    world = World()
    report = run_verify(monkeypatch, od_hero_stats(world, 0),
                        stratz_counts(world, smoothed=False))
    assert report["passed"], verify.format_report(report)
    assert report["volume_check"]["ok"]
    assert report["pickshare_check"]["ok"]


def test_correct_mapping_with_match_average_smoothing_passes(monkeypatch):
    # Stratz brackets as symmetric neighbour mixtures: the offset fit must
    # land near 0, well under the off-by-one threshold.
    world = World()
    report = run_verify(monkeypatch, od_hero_stats(world, 0),
                        stratz_counts(world, smoothed=True))
    assert report["passed"], verify.format_report(report)
    ma = report["winrate_offset_fit"]["median_alpha"]
    assert ma is not None and abs(ma) < 0.875


def stratz_counts_half_notch(world: World, seed: int = 11):
    """Stratz brackets whose boundaries sit half a notch below OpenDota's:
    each bracket is a 50/50 blend of its tier and the tier below — the
    regime observed on real data (uniform small tilt toward shift -1)."""
    rng = np.random.default_rng(seed)
    out = {}
    for b, bracket in enumerate(ORDER):
        lo = max(0, b - 1)
        counts = 0.5 * world.counts[b] + 0.5 * world.counts[lo]
        wr = ((0.5 * world.counts[b] * world.wr[b]
               + 0.5 * world.counts[lo] * world.wr[lo])
              / np.maximum(counts, 1e-9))
        counts = counts / counts.sum() * POPS[b] * 0.4
        entry = {}
        for h in range(N_HEROES):
            m = max(1, int(counts[h] * rng.normal(1, 0.02)))
            wins = int(np.clip(rng.normal(wr[h], 0.5 / np.sqrt(m)), 0, 1) * m)
            entry[h + 1] = (m, wins)
        out[bracket] = entry
    return out


def test_half_notch_convention_offset_passes(monkeypatch):
    # A bucketing-convention offset must be measured (~ -0.5), reported,
    # and NOT read as an off-by-one.
    world = World()
    report = run_verify(monkeypatch, od_hero_stats(world, 0),
                        stratz_counts_half_notch(world))
    assert report["passed"], verify.format_report(report)
    ma = report["winrate_offset_fit"]["median_alpha"]
    assert ma is not None and -0.875 < ma <= -0.25
    assert any("convention" in w for w in report["warnings"])


def test_off_by_one_fails_clean(monkeypatch):
    world = World()
    report = run_verify(monkeypatch, od_hero_stats(world, 1),
                        stratz_counts(world, smoothed=False))
    assert not report["passed"], verify.format_report(report)


def test_off_by_one_fails_other_direction(monkeypatch):
    world = World()
    report = run_verify(monkeypatch, od_hero_stats(world, -1),
                        stratz_counts(world, smoothed=False))
    assert not report["passed"], verify.format_report(report)


def test_off_by_one_fails_even_with_smoothing(monkeypatch):
    world = World()
    report = run_verify(monkeypatch, od_hero_stats(world, 1),
                        stratz_counts(world, smoothed=True))
    assert not report["passed"], verify.format_report(report)


def test_empty_immortal_is_reported_not_fatal(monkeypatch):
    world = World()
    report = run_verify(monkeypatch, od_hero_stats(world, 0,
                                                   immortal_empty=True),
                        stratz_counts(world, smoothed=True))
    assert report["passed"]
    assert any("zero games" in w for w in report["warnings"])


def test_report_is_printable(monkeypatch):
    world = World()
    report = run_verify(monkeypatch, od_hero_stats(world, 0),
                        stratz_counts(world, smoothed=True))
    text = verify.format_report(report)
    assert "pick-share alignment" in text
    assert "win-rate offset fit" in text

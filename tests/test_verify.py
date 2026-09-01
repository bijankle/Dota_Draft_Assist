"""Bracket-index verification against a synthetic two-source world with a
known ground-truth alignment. The checker must accept the correct mapping
(including with realistic near-identical neighbour win rates) and reject an
off-by-one — the failure mode that would silently skew every baseline."""

import numpy as np
import pytest

from draft_assist.data import verify

# True population pyramid per bracket (games in some window).
POPS = {"HERALD": 900_000, "GUARDIAN": 2_200_000, "CRUSADER": 3_600_000,
        "ARCHON": 3_900_000, "LEGEND": 3_200_000, "ANCIENT": 1_900_000,
        "DIVINE": 700_000, "IMMORTAL": 260_000}
N_HEROES = 120


def synth_world(od_shift: int = 0, immortal_empty: bool = False, seed: int = 5):
    """Returns (hero_stats, stratz_counts_by_bracket).

    od_shift shifts which bracket's data lands in OpenDota field "<t>_pick":
    0 = the assumed mapping is true; +1 = every OD field actually holds the
    next-lower bracket (an off-by-one bug).
    """
    rng = np.random.default_rng(seed)
    share = rng.dirichlet(np.full(N_HEROES, 5.0))          # hero pick shares
    hero_eff = rng.normal(0, 0.025, N_HEROES)              # hero strength
    skill_sens = rng.normal(0, 0.012, N_HEROES)            # bracket tilt
    order = verify.BRACKET_ORDER

    def winrate(h: int, b_idx: int) -> float:
        # Neighbouring brackets differ only slightly — the realistic regime
        # where naive per-bracket correlation is useless.
        tilt = (b_idx - 3.5) / 3.5
        return float(np.clip(0.5 + hero_eff[h] + skill_sens[h] * tilt,
                             0.05, 0.95))

    hero_stats = []
    for h in range(N_HEROES):
        entry = {"id": h + 1}
        for t in range(1, 9):
            b_idx = t - 1 + od_shift
            if not 0 <= b_idx < 8 or (immortal_empty and order[b_idx] == "IMMORTAL"):
                picks = 0
            else:
                pop = POPS[order[b_idx]]
                picks = max(0, int(pop * share[h]
                                   * rng.normal(1, 0.03)))
            wins = int(picks * winrate(h, min(max(t - 1 + od_shift, 0), 7)))
            entry[f"{t}_pick"], entry[f"{t}_win"] = picks, wins
        hero_stats.append(entry)

    stratz_counts = {}
    for b_idx, bracket in enumerate(order):
        counts = {}
        for h in range(N_HEROES):
            m = max(1, int(POPS[bracket] * 0.4 * share[h]
                           * rng.normal(1, 0.05)))
            w = int(np.clip(rng.normal(winrate(h, b_idx),
                                       0.5 / np.sqrt(m)), 0, 1) * m)
            counts[h + 1] = (m, w)
        stratz_counts[bracket] = counts
    return hero_stats, stratz_counts


def run_verify(monkeypatch, hero_stats, stratz_counts):
    monkeypatch.setattr(verify.stratz, "fetch_bracket_counts",
                        lambda bracket, take=14: stratz_counts[bracket])
    return verify.verify_tier_mapping(hero_stats, ("ANCIENT", "DIVINE"))


def test_correct_mapping_passes(monkeypatch):
    hero_stats, stratz_counts = synth_world(od_shift=0)
    report = run_verify(monkeypatch, hero_stats, stratz_counts)
    assert report["volume_check"]["best_shift"] == 0
    assert report["volume_check"]["decisive"]
    assert report["passed"], verify.format_report(report)


def test_off_by_one_fails(monkeypatch):
    hero_stats, stratz_counts = synth_world(od_shift=1)
    report = run_verify(monkeypatch, hero_stats, stratz_counts)
    assert not report["passed"], verify.format_report(report)


def test_off_by_one_other_direction_fails(monkeypatch):
    hero_stats, stratz_counts = synth_world(od_shift=-1)
    report = run_verify(monkeypatch, hero_stats, stratz_counts)
    assert not report["passed"], verify.format_report(report)


def test_empty_immortal_tier_still_passes(monkeypatch):
    # The real OpenDota feed showed a near-empty tier 8; a missing top tier
    # must not break alignment of the tiers we actually use.
    hero_stats, stratz_counts = synth_world(od_shift=0, immortal_empty=True)
    report = run_verify(monkeypatch, hero_stats, stratz_counts)
    assert report["volume_check"]["best_shift"] == 0
    assert report["passed"], verify.format_report(report)


def test_report_is_printable(monkeypatch):
    hero_stats, stratz_counts = synth_world()
    report = run_verify(monkeypatch, hero_stats, stratz_counts)
    text = verify.format_report(report)
    assert "volume alignment" in text and "PASSED" in text

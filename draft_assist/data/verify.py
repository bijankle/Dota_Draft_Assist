"""Empirical cross-source verification of OpenDota tier indexing.

The heroStats per-tier fields ("6_pick" etc.) carry no labels, and an
off-by-one in the assumed tier -> bracket mapping would silently skew every
baseline. So we don't trust it: per-hero win rates from each OpenDota tier
index are correlated against per-hero win rates from Stratz's *named*
brackets. Hero win rates differ enough between brackets that the correct
alignment shows a clearly higher correlation than off-by-one candidates.
"""

import numpy as np

from . import opendota, stratz


def _correlate(a: dict[int, float], b: dict[int, float]) -> tuple[float, int]:
    common = sorted(set(a) & set(b))
    if len(common) < 50:
        return float("nan"), len(common)
    va = np.array([a[h] for h in common])
    vb = np.array([b[h] for h in common])
    return float(np.corrcoef(va, vb)[0, 1]), len(common)


def verify_tier_mapping(hero_stats: list[dict],
                        brackets: tuple[str, ...] = ("ANCIENT", "DIVINE"),
                        margin: float = 0.03) -> dict:
    """For each named Stratz bracket, find the best-correlating OpenDota tier
    index and compare with the assumed mapping. Returns a report dict with
    'passed' plus per-bracket detail; raises nothing (caller decides)."""
    report = {"passed": True, "brackets": {}}
    for bracket in brackets:
        stratz_wr = stratz.fetch_bracket_winrates(bracket)
        assumed = opendota.NAME_TO_TIER[bracket]
        corrs = {}
        for tier in range(1, 9):
            od_wr = opendota.per_tier_winrates(hero_stats, tier)
            corr, n = _correlate(od_wr, stratz_wr)
            corrs[tier] = corr
        best = max(corrs, key=lambda t: (corrs[t]
                                         if np.isfinite(corrs[t]) else -2))
        others = [c for t, c in corrs.items()
                  if t != best and np.isfinite(c)]
        decisive = bool(np.isfinite(corrs[best])
                        and corrs[best] - max(others) >= margin) if others else False
        ok = best == assumed
        report["brackets"][bracket] = {
            "assumed_tier": assumed,
            "best_tier": best,
            "correlations": {t: (round(c, 4) if np.isfinite(c) else None)
                             for t, c in corrs.items()},
            "decisive": decisive,
            "ok": ok,
        }
        if not ok:
            report["passed"] = False
    return report


def format_report(report: dict) -> str:
    lines = []
    for bracket, r in report["brackets"].items():
        lines.append(
            f"{bracket}: assumed tier {r['assumed_tier']}, best-correlating "
            f"tier {r['best_tier']} "
            f"({'OK' if r['ok'] else 'MISMATCH'}"
            f"{', decisive' if r['decisive'] else ', margin small'})")
        lines.append(f"  correlations by tier: {r['correlations']}")
    lines.append("PASSED" if report["passed"] else
                 "FAILED — do not build baselines until this is resolved")
    return "\n".join(lines)

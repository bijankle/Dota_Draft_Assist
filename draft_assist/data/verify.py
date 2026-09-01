"""Empirical cross-source verification of OpenDota tier indexing.

The heroStats per-tier fields ("6_pick" etc.) carry no labels, and an
off-by-one in the assumed tier -> bracket mapping would silently skew every
baseline. Naive per-bracket win-rate correlation cannot settle it: adjacent
brackets' hero win rates correlate ~0.96+ with each other, well inside
sampling noise. So two sharper signals decide, both computed against
Stratz's *named* brackets:

1. VOLUME ALIGNMENT (primary): the number of games per bracket forms a
   distinctive population pyramid. Log match-volumes per Stratz bracket are
   correlated against OpenDota per-tier pick totals at shifts -1/0/+1; the
   true alignment stands out by a wide margin where win rates cannot. This
   also exposes structural surprises (e.g. an OpenDota tier with no games).

2. COMBINED WIN-RATE CHECK (secondary): what the app actually consumes is
   the Ancient+Divine AGGREGATE, so the combined Stratz vector is compared
   (sample-weighted) against candidate OpenDota tier pairs. Combining
   doubles the sample and cancels most of the neighbour-attenuation noise.

Verdict: FAIL if the volume alignment prefers a shifted mapping, or if the
win-rate check prefers a different pair DECISIVELY. A merely ambiguous
win-rate margin with a decisive volume match passes with a warning.
"""

import math

import numpy as np

from . import opendota, stratz

BRACKET_ORDER = ("HERALD", "GUARDIAN", "CRUSADER", "ARCHON",
                 "LEGEND", "ANCIENT", "DIVINE", "IMMORTAL")
VOLUME_DECISIVE_MARGIN = 0.10   # log-volume correlation gap
PAIR_DECISIVE_MARGIN = 0.005    # weighted win-rate correlation gap


def _weighted_corr(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> float:
    w = w / w.sum()
    mx, my = float((w * x).sum()), float((w * y).sum())
    cov = float((w * (x - mx) * (y - my)).sum())
    vx = float((w * (x - mx) ** 2).sum())
    vy = float((w * (y - my) ** 2).sum())
    if vx <= 0 or vy <= 0:
        return float("nan")
    return cov / math.sqrt(vx * vy)


def _od_tier_volumes(hero_stats: list[dict]) -> dict[int, int]:
    return {t: sum(int(e[f"{t}_pick"]) for e in hero_stats)
            for t in range(1, 9)}


def _volume_alignment(od_volumes: dict[int, int],
                      stratz_volumes: dict[str, int]) -> dict:
    """Correlate log volumes across shifts; shift 0 = assumed mapping."""
    corrs = {}
    for shift in (-1, 0, 1):
        xs, ys = [], []
        for bracket, sv in stratz_volumes.items():
            tier = opendota.NAME_TO_TIER[bracket] + shift
            ov = od_volumes.get(tier, 0)
            if sv > 0 and ov > 0:
                xs.append(math.log(ov))
                ys.append(math.log(sv))
        corrs[shift] = (float(np.corrcoef(xs, ys)[0, 1])
                        if len(xs) >= 5 else float("nan"))
    finite = {s: c for s, c in corrs.items() if np.isfinite(c)}
    best = max(finite, key=finite.get) if finite else None
    others = [c for s, c in finite.items() if s != best]
    margin = (finite[best] - max(others)) if best is not None and others else 0.0
    return {"correlation_by_shift": {s: (round(c, 4) if np.isfinite(c) else None)
                                     for s, c in corrs.items()},
            "best_shift": best,
            "decisive": bool(best is not None
                             and margin >= VOLUME_DECISIVE_MARGIN),
            "ok": best == 0}


def _combined_pair_check(hero_stats: list[dict],
                         stratz_counts: dict[str, dict[int, tuple[int, int]]],
                         target: tuple[str, ...]) -> dict:
    """Weighted win-rate correlation of the combined target brackets against
    candidate OpenDota tier pairs (assumed, and shifted by +-1)."""
    combined: dict[int, list[int]] = {}
    for bracket in target:
        for hid, (m, w) in stratz_counts[bracket].items():
            a = combined.setdefault(hid, [0, 0])
            a[0] += m
            a[1] += w
    stratz_wr = {hid: w / m for hid, (m, w) in combined.items() if m > 0}
    stratz_m = {hid: m for hid, (m, _) in combined.items()}

    assumed = tuple(opendota.NAME_TO_TIER[b] for b in target)
    corrs = {}
    for shift in (-1, 0, 1):
        tiers = tuple(t + shift for t in assumed)
        if not all(1 <= t <= 8 for t in tiers):
            corrs[shift] = float("nan")
            continue
        rows = []
        for e in hero_stats:
            hid = int(e["id"])
            picks = sum(int(e[f"{t}_pick"]) for t in tiers)
            wins = sum(int(e[f"{t}_win"]) for t in tiers)
            if picks > 0 and hid in stratz_wr:
                rows.append((wins / picks, stratz_wr[hid],
                             min(picks, stratz_m[hid])))
        if len(rows) < 50:
            corrs[shift] = float("nan")
            continue
        x, y, w = (np.array([r[i] for r in rows]) for i in range(3))
        corrs[shift] = _weighted_corr(x, y, w)

    finite = {s: c for s, c in corrs.items() if np.isfinite(c)}
    best = max(finite, key=finite.get) if finite else None
    others = [c for s, c in finite.items() if s != best]
    margin = (finite[best] - max(others)) if best is not None and others else 0.0
    return {"correlation_by_shift": {s: (round(c, 4) if np.isfinite(c) else None)
                                     for s, c in corrs.items()},
            "best_shift": best,
            "decisive": bool(best is not None
                             and margin >= PAIR_DECISIVE_MARGIN),
            "ok": best == 0}


def verify_tier_mapping(hero_stats: list[dict],
                        brackets: tuple[str, ...] = ("ANCIENT", "DIVINE")) -> dict:
    """Returns a report dict with 'passed', 'warning', and the evidence for
    both checks plus raw volume tables for eyeballing."""
    stratz_counts = {b: stratz.fetch_bracket_counts(b) for b in BRACKET_ORDER}
    stratz_volumes = {b: sum(m for m, _ in c.values())
                      for b, c in stratz_counts.items()}
    od_volumes = _od_tier_volumes(hero_stats)

    volume = _volume_alignment(od_volumes, stratz_volumes)
    pair = _combined_pair_check(hero_stats, stratz_counts, brackets)

    # Volume is the primary signal. The win-rate check can only veto when it
    # is decisively wrong; an ambiguous margin with good volume passes.
    passed = bool(volume["ok"]
                  and (pair["ok"] or not pair["decisive"]))
    warning = None
    if passed and not volume["decisive"]:
        warning = "volume alignment correct but not decisive"
    if passed and not pair["ok"]:
        warning = ("win-rate check ambiguous (prefers shift "
                   f"{pair['best_shift']} by < {PAIR_DECISIVE_MARGIN}); "
                   "volume alignment carries the verdict")

    return {
        "passed": passed,
        "warning": warning,
        "target_brackets": list(brackets),
        "volume_check": volume,
        "pair_winrate_check": pair,
        "opendota_tier_volumes": od_volumes,
        "stratz_bracket_volumes": stratz_volumes,
    }


def format_report(report: dict) -> str:
    lines = ["OpenDota per-tier pick totals vs Stratz per-bracket match totals:"]
    for bracket in BRACKET_ORDER:
        tier = opendota.NAME_TO_TIER[bracket]
        lines.append(f"  tier {tier} <-> {bracket:9s}  "
                     f"OD {report['opendota_tier_volumes'].get(tier, 0):>12,}  "
                     f"Stratz {report['stratz_bracket_volumes'].get(bracket, 0):>12,}")
    v, p = report["volume_check"], report["pair_winrate_check"]
    lines.append(f"volume alignment: best shift {v['best_shift']} "
                 f"({'decisive' if v['decisive'] else 'weak'}) "
                 f"corr by shift {v['correlation_by_shift']}")
    lines.append(f"combined {'+'.join(report['target_brackets'])} win-rate: "
                 f"best shift {p['best_shift']} "
                 f"({'decisive' if p['decisive'] else 'ambiguous'}) "
                 f"corr by shift {p['correlation_by_shift']}")
    if report.get("warning"):
        lines.append(f"note: {report['warning']}")
    lines.append("PASSED" if report["passed"] else
                 "FAILED — do not build baselines until this is resolved; "
                 "send this report to Claude")
    return "\n".join(lines)

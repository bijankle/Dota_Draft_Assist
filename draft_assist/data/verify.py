"""Empirical cross-source verification of OpenDota tier indexing.

The heroStats per-tier fields ("6_pick" etc.) carry no labels, and an
off-by-one in the assumed tier -> bracket mapping would silently skew every
baseline. Verification runs three signals against Stratz's *named* brackets,
each robust to a different failure mode:

1. VOLUME ALIGNMENT: log match-volumes per bracket form a distinctive
   population pyramid; correlated at shifts -1/0/+1. Detects gross
   misalignment and structural surprises (an empty tier: OpenDota currently
   reports zero Immortal games — a missing top bucket, not a shift).

2. PICK-SHARE ALIGNMENT: per-hero pick shares per bracket. Hero popularity
   is strongly rank-graded and, at millions of games, essentially
   noise-free, and it does not depend on win-rate semantics at all.

3. WIN-RATE RIDGE: per-bracket weighted win-rate correlation at each shift,
   for ALL brackets. This one needs careful reading, because the two sites
   bucket differently: Stratz buckets whole matches by average rank while
   OpenDota counts each player at their own rank, so every Stratz bracket
   is a smoothed mixture of its neighbours, skewed toward the more populous
   side. A REAL off-by-one shows the same preferred shift in every bracket;
   the smoothing artifact shows mixed directions that track the population
   pyramid's slope. Only a consistent non-zero shift fails this check.

The combined Ancient+Divine comparison (the aggregate the app consumes) is
reported for information; it sits in the flattest part of the win-rate
curve and is expected to tilt with the smoothing, so it carries no veto.
"""

import math

import numpy as np

from . import opendota, stratz

BRACKET_ORDER = ("HERALD", "GUARDIAN", "CRUSADER", "ARCHON",
                 "LEGEND", "ANCIENT", "DIVINE", "IMMORTAL")
SHIFTS = (-1, 0, 1)
PICKSHARE_DECISIVE_MARGIN = 0.005
# A non-zero shift must win in at least this fraction of usable brackets to
# count as consistent (i.e. a real off-by-one).
RIDGE_CONSISTENT_FRAC = 0.75


def _weighted_corr(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> float:
    w = w / w.sum()
    mx, my = float((w * x).sum()), float((w * y).sum())
    cov = float((w * (x - mx) * (y - my)).sum())
    vx = float((w * (x - mx) ** 2).sum())
    vy = float((w * (y - my) ** 2).sum())
    if vx <= 0 or vy <= 0:
        return float("nan")
    return cov / math.sqrt(vx * vy)


def _round_map(d: dict) -> dict:
    return {k: (round(v, 4) if v is not None and np.isfinite(v) else None)
            for k, v in d.items()}


def _best_shift(corrs: dict) -> tuple[int | None, float]:
    finite = {s: c for s, c in corrs.items()
              if c is not None and np.isfinite(c)}
    if not finite:
        return None, 0.0
    best = max(finite, key=finite.get)
    others = [c for s, c in finite.items() if s != best]
    return best, (finite[best] - max(others)) if others else 0.0


def _od_tier_data(hero_stats: list[dict]):
    """(volumes per tier, picks[tier][hid], wins[tier][hid])."""
    picks = {t: {} for t in range(1, 9)}
    wins = {t: {} for t in range(1, 9)}
    for e in hero_stats:
        hid = int(e["id"])
        for t in range(1, 9):
            picks[t][hid] = int(e[f"{t}_pick"])
            wins[t][hid] = int(e[f"{t}_win"])
    volumes = {t: sum(picks[t].values()) for t in range(1, 9)}
    return volumes, picks, wins


def _volume_alignment(od_volumes: dict[int, int],
                      stratz_volumes: dict[str, int]) -> dict:
    corrs = {}
    for shift in SHIFTS:
        xs, ys = [], []
        for bracket, sv in stratz_volumes.items():
            ov = od_volumes.get(opendota.NAME_TO_TIER[bracket] + shift, 0)
            if sv > 0 and ov > 0:
                xs.append(math.log(ov))
                ys.append(math.log(sv))
        corrs[shift] = (float(np.corrcoef(xs, ys)[0, 1])
                        if len(xs) >= 5 else None)
    best, margin = _best_shift(corrs)
    return {"correlation_by_shift": _round_map(corrs), "best_shift": best,
            "margin": round(margin, 4), "ok": best == 0}


def _pickshare_alignment(od_picks: dict[int, dict[int, int]],
                         stratz_counts: dict[str, dict[int, tuple[int, int]]]
                         ) -> dict:
    stratz_share = {}
    for bracket, counts in stratz_counts.items():
        total = sum(m for m, _ in counts.values())
        if total > 0:
            stratz_share[bracket] = {h: m / total
                                     for h, (m, _) in counts.items()}
    corrs = {}
    for shift in SHIFTS:
        vals = []
        for bracket, sshare in stratz_share.items():
            tier = opendota.NAME_TO_TIER[bracket] + shift
            tier_picks = od_picks.get(tier, {})
            total = sum(tier_picks.values())
            if total <= 0:
                continue
            common = sorted(set(sshare) & set(tier_picks))
            if len(common) < 50:
                continue
            x = np.array([tier_picks[h] / total for h in common])
            y = np.array([sshare[h] for h in common])
            vals.append(float(np.corrcoef(x, y)[0, 1]))
        corrs[shift] = float(np.mean(vals)) if len(vals) >= 5 else None
    best, margin = _best_shift(corrs)
    return {"correlation_by_shift": _round_map(corrs), "best_shift": best,
            "margin": round(margin, 4),
            "decisive": bool(best is not None
                             and margin >= PICKSHARE_DECISIVE_MARGIN),
            "ok": best == 0}


def _winrate_ridge(od_picks, od_wins, stratz_counts) -> dict:
    """Per-bracket win-rate correlation at each shift. Fails only on a
    CONSISTENT non-zero preferred shift (see module docstring)."""
    per_bracket = {}
    for bracket, counts in stratz_counts.items():
        s_wr = {h: w / m for h, (m, w) in counts.items() if m > 0}
        s_m = {h: m for h, (m, _) in counts.items()}
        corrs = {}
        for shift in SHIFTS:
            tier = opendota.NAME_TO_TIER[bracket] + shift
            if not 1 <= tier <= 8 or sum(od_picks[tier].values()) <= 0:
                corrs[shift] = None
                continue
            rows = [(od_wins[tier][h] / od_picks[tier][h], s_wr[h],
                     min(od_picks[tier][h], s_m[h]))
                    for h in s_wr
                    if od_picks[tier].get(h, 0) > 0]
            if len(rows) < 50:
                corrs[shift] = None
                continue
            x, y, w = (np.array([r[i] for r in rows]) for i in range(3))
            corrs[shift] = _weighted_corr(x, y, w)
        best, _ = _best_shift(corrs)
        # Only count brackets where all three shifts were computable —
        # otherwise edge brackets trivially prefer the inward shift.
        usable = all(corrs[s] is not None for s in SHIFTS)
        per_bracket[bracket] = {"correlation_by_shift": _round_map(corrs),
                                "best_shift": best if usable else None}

    votes = [r["best_shift"] for r in per_bracket.values()
             if r["best_shift"] is not None]
    consistent_shift = None
    for s in SHIFTS:
        if s != 0 and votes and votes.count(s) >= max(
                3, math.ceil(RIDGE_CONSISTENT_FRAC * len(votes))):
            consistent_shift = s
    return {"per_bracket": per_bracket, "votes": votes,
            "consistent_shift": consistent_shift,
            "ok": consistent_shift is None}


def _combined_pair_info(od_picks, od_wins, stratz_counts,
                        target: tuple[str, ...]) -> dict:
    combined: dict[int, list[int]] = {}
    for bracket in target:
        for hid, (m, w) in stratz_counts[bracket].items():
            a = combined.setdefault(hid, [0, 0])
            a[0] += m
            a[1] += w
    s_wr = {h: w / m for h, (m, w) in combined.items() if m > 0}
    s_m = {h: m for h, (m, _) in combined.items()}
    assumed = tuple(opendota.NAME_TO_TIER[b] for b in target)
    corrs = {}
    for shift in SHIFTS:
        tiers = tuple(t + shift for t in assumed)
        if not all(1 <= t <= 8 and sum(od_picks[t].values()) > 0
                   for t in tiers):
            corrs[shift] = None
            continue
        rows = []
        for h in s_wr:
            picks = sum(od_picks[t].get(h, 0) for t in tiers)
            wins = sum(od_wins[t].get(h, 0) for t in tiers)
            if picks > 0:
                rows.append((wins / picks, s_wr[h], min(picks, s_m[h])))
        if len(rows) < 50:
            corrs[shift] = None
            continue
        x, y, w = (np.array([r[i] for r in rows]) for i in range(3))
        corrs[shift] = _weighted_corr(x, y, w)
    best, margin = _best_shift(corrs)
    return {"correlation_by_shift": _round_map(corrs), "best_shift": best,
            "margin": round(margin, 4)}


def verify_tier_mapping(hero_stats: list[dict],
                        brackets: tuple[str, ...] = ("ANCIENT", "DIVINE")) -> dict:
    stratz_counts = {b: stratz.fetch_bracket_counts(b) for b in BRACKET_ORDER}
    stratz_volumes = {b: sum(m for m, _ in c.values())
                      for b, c in stratz_counts.items()}
    od_volumes, od_picks, od_wins = _od_tier_data(hero_stats)

    volume = _volume_alignment(od_volumes, stratz_volumes)
    pickshare = _pickshare_alignment(od_picks, stratz_counts)
    ridge = _winrate_ridge(od_picks, od_wins, stratz_counts)
    pair = _combined_pair_info(od_picks, od_wins, stratz_counts, brackets)

    passed = bool(volume["ok"] and pickshare["ok"] and ridge["ok"])
    warnings = []
    if passed and not pickshare["decisive"]:
        warnings.append("pick-share margin small")
    if passed and pair["best_shift"] not in (0, None):
        warnings.append(
            f"combined {'+'.join(brackets)} win-rate tilts to shift "
            f"{pair['best_shift']} — expected from match-average bracket "
            "smoothing; structural checks carry the verdict")
    empty_tiers = [t for t, v in od_volumes.items() if v == 0]
    if empty_tiers:
        warnings.append(f"OpenDota tiers with zero games: {empty_tiers}")

    return {
        "passed": passed,
        "warnings": warnings,
        "target_brackets": list(brackets),
        "volume_check": volume,
        "pickshare_check": pickshare,
        "winrate_ridge": ridge,
        "pair_winrate_info": pair,
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
    v, p, r = (report["volume_check"], report["pickshare_check"],
               report["winrate_ridge"])
    lines.append(f"volume alignment:     best shift {v['best_shift']} "
                 f"(margin {v['margin']}) {v['correlation_by_shift']}")
    lines.append(f"pick-share alignment: best shift {p['best_shift']} "
                 f"(margin {p['margin']}) {p['correlation_by_shift']}")
    lines.append(f"win-rate ridge votes by bracket: {r['votes']} -> "
                 f"consistent shift: {r['consistent_shift']}")
    for bracket, row in r["per_bracket"].items():
        lines.append(f"  {bracket:9s} best {str(row['best_shift']):>4s} "
                     f"{row['correlation_by_shift']}")
    pi = report["pair_winrate_info"]
    lines.append(f"combined {'+'.join(report['target_brackets'])} win-rate "
                 f"(informational): best shift {pi['best_shift']} "
                 f"{pi['correlation_by_shift']}")
    for w in report.get("warnings", []):
        lines.append(f"note: {w}")
    lines.append("PASSED" if report["passed"] else
                 "FAILED — do not build baselines until this is resolved; "
                 "send this report to Claude")
    return "\n".join(lines)

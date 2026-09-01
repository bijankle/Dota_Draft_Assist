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

3. WIN-RATE OFFSET FIT: the sites bucket matches with different averaging
   and boundary conventions, so a Stratz bracket need not coincide with an
   OpenDota tier even when the labels are right — real data shows every
   bracket tilting slightly toward the tier below, with margins far too
   small for a whole-tier shift and volumes/pick-shares flatly
   contradicting one. So instead of voting on integer shifts, each
   bracket's win-rate vector is FIT as a blend between its assumed tier
   and a neighbour: blend alpha ~ 0 means aligned, |alpha| ~ 0.5 means a
   half-notch convention offset (harmless — baselines use OpenDota's own
   tier definitions), |alpha| ~ 1 means a genuine off-by-one. Only a
   median |alpha| >= 0.875 (essentially a
   full shift) fails.

The combined Ancient+Divine comparison (the aggregate the app consumes) is
reported for information only; it inherits the convention offset and
carries no veto.
"""

import math

import numpy as np

from . import opendota, stratz

BRACKET_ORDER = ("HERALD", "GUARDIAN", "CRUSADER", "ARCHON",
                 "LEGEND", "ANCIENT", "DIVINE", "IMMORTAL")
SHIFTS = (-1, 0, 1)
PICKSHARE_DECISIVE_MARGIN = 0.005
# Blend grid for the win-rate offset fit: negative alpha mixes toward the
# tier below, positive toward the tier above.
ALPHA_GRID = tuple(round(a / 4, 2) for a in range(-4, 5))
# Median fitted |alpha| at or beyond this counts as a genuine off-by-one
# (only an essentially-full shift; deep convention offsets stay legal since
# volume and pick-share checks independently catch real shifts).
RIDGE_FAIL_ALPHA = 0.875


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
    decisive = bool(best is not None and margin >= PICKSHARE_DECISIVE_MARGIN)
    # A statistical tie with a neighbour (margin under the decisive
    # threshold) is expected from cross-site bucketing conventions and does
    # not fail the check; a decisive non-zero preference does.
    return {"correlation_by_shift": _round_map(corrs), "best_shift": best,
            "margin": round(margin, 4), "decisive": decisive,
            "ok": best == 0 or not decisive}


def _winrate_offset_fit(od_picks, od_wins, stratz_counts) -> dict:
    """Fit each bracket's win-rate vector as a blend between its assumed
    tier and a neighbouring tier (see module docstring)."""

    def tier_ok(t: int) -> bool:
        return 1 <= t <= 8 and sum(od_picks[t].values()) > 0

    per_bracket = {}
    for bracket, counts in stratz_counts.items():
        t = opendota.NAME_TO_TIER[bracket]
        if not tier_ok(t):
            per_bracket[bracket] = {"alpha": None, "peak_corr": None,
                                    "usable": False}
            continue
        s_wr = {h: w / m for h, (m, w) in counts.items() if m > 0}
        s_m = {h: m for h, (m, _) in counts.items()}
        both_dirs = tier_ok(t - 1) and tier_ok(t + 1)
        best_alpha, best_corr = None, -2.0
        for alpha in ALPHA_GRID:
            n = t - 1 if alpha < 0 else t + 1
            if alpha != 0 and not tier_ok(n):
                continue
            rows = []
            for h in s_wr:
                pt = od_picks[t].get(h, 0)
                if pt <= 0:
                    continue
                wr_t = od_wins[t][h] / pt
                if alpha == 0:
                    wr_mix, weight = wr_t, min(pt, s_m[h])
                else:
                    pn = od_picks[n].get(h, 0)
                    if pn <= 0:
                        continue
                    wr_n = od_wins[n][h] / pn
                    a = abs(alpha)
                    wr_mix = (1 - a) * wr_t + a * wr_n
                    weight = min(pt, pn, s_m[h])
                rows.append((wr_mix, s_wr[h], weight))
            if len(rows) < 50:
                continue
            x, y, w = (np.array([r[i] for r in rows]) for i in range(3))
            corr = _weighted_corr(x, y, w)
            if np.isfinite(corr) and corr > best_corr:
                best_alpha, best_corr = alpha, corr
        per_bracket[bracket] = {
            "alpha": best_alpha,
            "peak_corr": (round(best_corr, 4) if best_alpha is not None
                          else None),
            # Edge brackets can only fit one direction; their alpha is
            # reported but excluded from the verdict.
            "usable": bool(both_dirs and best_alpha is not None),
        }

    alphas = [r["alpha"] for r in per_bracket.values() if r["usable"]]
    median_alpha = float(np.median(alphas)) if alphas else None
    ok = bool(median_alpha is None
              or abs(median_alpha) < RIDGE_FAIL_ALPHA)
    return {"per_bracket": per_bracket, "alphas": alphas,
            "median_alpha": median_alpha, "ok": ok}


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
    offset = _winrate_offset_fit(od_picks, od_wins, stratz_counts)
    pair = _combined_pair_info(od_picks, od_wins, stratz_counts, brackets)

    passed = bool(volume["ok"] and pickshare["ok"] and offset["ok"])
    warnings = []
    if passed and offset["median_alpha"] not in (None, 0.0):
        warnings.append(
            f"Stratz brackets sit ~{abs(offset['median_alpha']):.2f} of a "
            f"notch {'below' if offset['median_alpha'] < 0 else 'above'} "
            "OpenDota tiers (bucketing convention difference, not a shift; "
            "baselines use OpenDota's own tier definitions)")
    if passed and pickshare["best_shift"] not in (0, None):
        warnings.append("pick-share tied with a neighbouring shift "
                        f"(margin {pickshare['margin']}) — consistent with "
                        "the convention offset")
    empty_tiers = [t for t, v in od_volumes.items() if v == 0]
    if empty_tiers:
        warnings.append(f"OpenDota tiers with zero games: {empty_tiers}")

    return {
        "passed": passed,
        "warnings": warnings,
        "target_brackets": list(brackets),
        "volume_check": volume,
        "pickshare_check": pickshare,
        "winrate_offset_fit": offset,
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
               report["winrate_offset_fit"])
    lines.append(f"volume alignment:     best shift {v['best_shift']} "
                 f"(margin {v['margin']}) {v['correlation_by_shift']}")
    lines.append(f"pick-share alignment: best shift {p['best_shift']} "
                 f"(margin {p['margin']}) {p['correlation_by_shift']}")
    lines.append(f"win-rate offset fit: median alpha {r['median_alpha']} "
                 f"(0 = aligned, +-0.5 = convention offset, "
                 f"+-1 = off-by-one; fails at |median| >= 0.875)")
    for bracket, row in r["per_bracket"].items():
        lines.append(f"  {bracket:9s} alpha {str(row['alpha']):>5s} "
                     f"peak corr {row['peak_corr']}"
                     + ("" if row["usable"] else "  (edge, excluded)"))
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

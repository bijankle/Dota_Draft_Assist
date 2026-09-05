"""OpenDota pulls: hero constants (ids, names, portrait asset paths) and
heroStats (pick/win counts split by rank tier) for bracket-filtered baseline
win rates.

Field names here were written against dumps produced by tools/inspect_apis.py
and are re-validated on every pull; see schema.SchemaError.

Rank-tier indexing is the dangerous part. heroStats exposes per-tier fields
named "<k>_pick"/"<k>_win" for k in 1..8. The ASSUMED mapping (matching
OpenDota's rank_tier tens digit) is below, but it is an assumption: an
off-by-one would silently skew every baseline. tools/verify_brackets.py
cross-checks it empirically against Stratz per-bracket hero win rates, and
the matrix build refuses to run until that check has passed once (recorded in
the cache metadata) or is explicitly overridden.
"""

import json
import time
from typing import Any

import requests

from ..config import RAW_DUMP_DIR
from .schema import require

BASE = "https://api.opendota.com/api"

# ASSUMED tier-index -> bracket-name mapping; verified empirically, see above.
TIER_NAMES = {
    1: "HERALD", 2: "GUARDIAN", 3: "CRUSADER", 4: "ARCHON",
    5: "LEGEND", 6: "ANCIENT", 7: "DIVINE", 8: "IMMORTAL",
}
NAME_TO_TIER = {v: k for k, v in TIER_NAMES.items()}


def _get(path: str, dump_name: str | None = None) -> Any:
    resp = requests.get(f"{BASE}/{path}", timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if dump_name:
        RAW_DUMP_DIR.mkdir(parents=True, exist_ok=True)
        (RAW_DUMP_DIR / dump_name).write_text(
            json.dumps(data, indent=2), encoding="utf-8")
    time.sleep(1.0)  # be polite; OpenDota free tier is rate limited
    return data


def fetch_heroes() -> dict[int, dict]:
    """Hero id -> {name, internal_name, img, icon} from /constants/heroes."""
    raw = _get("constants/heroes", "opendota_constants_heroes.json")
    require(isinstance(raw, dict) and raw, "OpenDota constants/heroes",
            f"expected non-empty dict keyed by hero id, got {type(raw).__name__}")
    heroes: dict[int, dict] = {}
    for key, entry in raw.items():
        require(isinstance(entry, dict) and "id" in entry
                and "localized_name" in entry,
                "OpenDota constants/heroes",
                f"entry '{key}' missing id/localized_name")
        heroes[int(entry["id"])] = {
            "name": entry["localized_name"],
            # e.g. "npc_dota_hero_antimage" -> used for portrait asset URLs
            "internal_name": entry.get("name", ""),
            "img": entry.get("img", ""),
            "icon": entry.get("icon", ""),
            # Loose role tags ("Carry", "Support", ...) used only for the
            # UI's queued-role highlight, never for filtering.
            "roles": entry.get("roles", []),
        }
    require(len(heroes) > 100, "OpenDota constants/heroes",
            f"only {len(heroes)} heroes parsed, expected 120+")
    return heroes


def fetch_hero_stats() -> list[dict]:
    raw = _get("heroStats", "opendota_herostats.json")
    require(isinstance(raw, list) and len(raw) > 100, "OpenDota heroStats",
            f"expected list of 120+ hero entries, got {type(raw).__name__} "
            f"len {len(raw) if isinstance(raw, list) else '?'}")
    sample = raw[0]
    for k in range(1, 9):
        require(f"{k}_pick" in sample and f"{k}_win" in sample,
                "OpenDota heroStats",
                f"per-tier fields '{k}_pick'/'{k}_win' missing; keys were "
                f"{sorted(sample.keys())}")
    return raw


def baseline_winrates(hero_stats: list[dict],
                      bracket_names: tuple[str, ...]) -> dict[int, dict]:
    """Per-hero baseline for the given brackets COMBINED:
    summed wins / summed picks across the tiers (deliberate aggregation of
    adjacent brackets for sample size).

    Returns hero_id -> {picks, wins, winrate}.
    """
    tiers = [NAME_TO_TIER[b] for b in bracket_names]
    out: dict[int, dict] = {}
    for entry in hero_stats:
        require("id" in entry, "OpenDota heroStats", "hero entry missing 'id'")
        picks = sum(int(entry[f"{k}_pick"]) for k in tiers)
        wins = sum(int(entry[f"{k}_win"]) for k in tiers)
        require(wins <= picks, "OpenDota heroStats",
                f"hero {entry['id']}: wins {wins} > picks {picks} in tiers "
                f"{tiers} — tier field semantics are not what we assume")
        out[int(entry["id"])] = {
            "picks": picks,
            "wins": wins,
            "winrate": (wins / picks) if picks else 0.5,
        }
    return out


def per_tier_winrates(hero_stats: list[dict], tier: int) -> dict[int, float]:
    """Single-tier hero winrates, used only by the bracket verification."""
    out = {}
    for entry in hero_stats:
        picks = int(entry[f"{tier}_pick"])
        if picks > 0:
            out[int(entry["id"])] = int(entry[f"{tier}_win"]) / picks
    return out


def fetch_matchups(hero_ids: list[int]) -> dict[int, dict]:
    """Pairwise counts from /heroes/{id}/matchups, in Stratz's shape.

    Returns hero_id -> {"vs": {other: (matches, wins)}, "with": {}} so the
    normaliser does not care which source produced it. Raw counts only;
    deltas happen in normalize.py.

    TWO THINGS THIS SOURCE CANNOT DO, and neither is a bug to fix here:

    * **No ally pairs.** OpenDota publishes matchups (hero against hero) and
      nothing equivalent for two heroes on the SAME side, so "with" comes
      back empty and the synergy matrix is all zeroes. The app says so
      rather than showing an empty grid as if it were a neutral one.
    * **No bracket filter.** The endpoint takes no rank argument, so these
      counts are all brackets pooled — not the Ancient+Divine the baselines
      are built for. Mixing a pooled interaction term with a bracketed
      baseline is a real approximation, and the build records it.

    Both are why Stratz remains the default.
    """
    out: dict[int, dict] = {}
    for n, hid in enumerate(hero_ids, 1):
        rows = _get(f"heroes/{hid}/matchups",
                    "opendota_matchups_sample.json" if n == 1 else None)
        require(isinstance(rows, list) and len(rows) > 50,
                "OpenDota heroes/{id}/matchups",
                f"hero {hid}: expected one row per other hero (120+), got "
                f"{type(rows).__name__} "
                f"len {len(rows) if isinstance(rows, list) else '?'} — if the "
                "endpoint has changed, adapt this from the raw dump")
        vs: dict[int, tuple[int, int]] = {}
        for row in rows:
            require(isinstance(row, dict) and "hero_id" in row
                    and "games_played" in row and "wins" in row,
                    "OpenDota heroes/{id}/matchups",
                    f"hero {hid}: row fields were "
                    f"{sorted(row.keys()) if isinstance(row, dict) else row}")
            matches, wins = int(row["games_played"]), int(row["wins"])
            require(0 <= wins <= matches, "OpenDota heroes/{id}/matchups",
                    f"hero {hid} vs {row['hero_id']}: wins {wins} outside "
                    f"0..games_played {matches}")
            vs[int(row["hero_id"])] = (matches, wins)
        out[hid] = {"vs": vs, "with": {}}
        if n % 10 == 0 or n == len(hero_ids):
            print(f"  matchups: {n}/{len(hero_ids)} heroes")
    return out

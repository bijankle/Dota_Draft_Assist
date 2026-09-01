"""Stratz GraphQL pulls: bracket-filtered pairwise matchup ('vs') and synergy
('with') counts — the primary source for interaction data.

Nothing here is trusted from memory. Before the first real pull, introspect()
asks the live schema which arguments heroStats.matchUp actually accepts and
which bracket enum values exist, and choose_bracket_filter() picks the closest
expressible filter to the target (ANCIENT+DIVINE):

- if matchUp accepts a full per-bracket argument, filter exactly;
- if it only accepts the coarser paired enum (e.g. LEGEND_ANCIENT /
  DIVINE_IMMORTAL), use the pair(s) covering the target and record that the
  pairwise data spans Legend..Immortal. Baselines still come from OpenDota at
  exactly Ancient+Divine; deltas are interaction terms, where the wider
  bracket costs little. The filter actually used is written into the cache
  metadata so it is never ambiguous.

Every response is dumped to data_cache/raw/ and shape-validated loudly.
"""

import json
import time
from typing import Any

import requests

from ..config import RAW_DUMP_DIR, stratz_api_key
from .schema import require

URL = "https://api.stratz.com/graphql"
_PAUSE = 0.35  # seconds between requests; free tier allows ~20/min bursts


def _post(query: str, dump_name: str | None = None) -> dict:
    resp = requests.post(
        URL,
        json={"query": query},
        headers={
            "Authorization": f"Bearer {stratz_api_key()}",
            # Stratz rejects requests without a UA; they ask for this value.
            "User-Agent": "STRATZ_API",
        },
        timeout=60,
    )
    resp.raise_for_status()
    payload = resp.json()
    if dump_name:
        RAW_DUMP_DIR.mkdir(parents=True, exist_ok=True)
        (RAW_DUMP_DIR / dump_name).write_text(
            json.dumps(payload, indent=2), encoding="utf-8")
    require("errors" not in payload, "Stratz",
            f"GraphQL errors: {json.dumps(payload.get('errors'))[:800]}")
    require("data" in payload, "Stratz", "response has no 'data' key")
    time.sleep(_PAUSE)
    return payload["data"]


def introspect() -> dict:
    """Discover matchUp's argument names/types and bracket enum values from
    the live schema. Returns {"args": {name: type_desc}, "enums": {enum_name:
    [values]}}."""
    data = _post(
        """
        query {
          heroStatsType: __type(name: "HeroStatsQuery") {
            fields { name args { name type
              { kind name ofType { kind name ofType { kind name } } } } }
          }
        }
        """,
        "stratz_introspect_herostats.json",
    )
    t = data.get("heroStatsType")
    require(t and t.get("fields"), "Stratz introspection",
            "type HeroStatsQuery not found — top-level schema changed")
    matchup_field = next((f for f in t["fields"]
                          if f["name"].lower() == "matchup"), None)
    require(matchup_field is not None, "Stratz introspection",
            "heroStats has no matchUp field; fields were "
            f"{[f['name'] for f in t['fields']]}")

    def type_leaf(tt: dict) -> str:
        while tt and tt.get("name") is None:
            tt = tt.get("ofType") or {}
        return (tt or {}).get("name", "?")

    args = {a["name"]: type_leaf(a["type"]) for a in matchup_field["args"]}

    enum_names = {v for v in args.values() if v and "bracket" in v.lower()}
    enums: dict[str, list[str]] = {}
    for name in enum_names:
        data = _post(
            '{ __type(name: "%s") { enumValues { name } } }' % name,
            f"stratz_enum_{name}.json",
        )
        vals = (data.get("__type") or {}).get("enumValues")
        require(vals, "Stratz introspection", f"enum {name} has no values")
        enums[name] = [v["name"] for v in vals]
    return {"args": args, "enums": enums}


def choose_bracket_filter(schema: dict,
                          target: tuple[str, ...]) -> dict:
    """Pick the matchUp bracket argument + values that best express the target
    brackets. Returns {"arg": name, "values": [...], "exact": bool,
    "covers": [...]}, raising if nothing bracket-like exists."""
    args, enums = schema["args"], schema["enums"]
    bracket_args = {a: t for a, t in args.items() if t in enums}
    require(bracket_args, "Stratz introspection",
            f"matchUp has no bracket-typed argument; args were {args}")

    # Prefer an argument whose enum contains the target values verbatim.
    for arg, enum_name in bracket_args.items():
        values = enums[enum_name]
        if all(t in values for t in target):
            return {"arg": arg, "values": list(target), "exact": True,
                    "covers": list(target)}

    # Otherwise use paired values (e.g. LEGEND_ANCIENT) covering the target.
    for arg, enum_name in bracket_args.items():
        values = enums[enum_name]
        chosen = [v for v in values if any(t in v.split("_") for t in target)]
        if chosen:
            covers = sorted({part for v in chosen for part in v.split("_")})
            return {"arg": arg, "values": chosen, "exact": False,
                    "covers": covers}

    raise_args = {a: enums[t] for a, t in bracket_args.items()}
    require(False, "Stratz introspection",
            f"no bracket argument can express {target}; available: {raise_args}")
    raise AssertionError  # unreachable


def fetch_matchups(hero_ids: list[int], bracket_filter: dict,
                   batch: int = 4) -> dict[int, dict]:
    """Pairwise counts for every hero: hero_id -> {"vs": {other_id: (matches,
    wins)}, "with": {other_id: (matches, wins)}}.

    'vs' wins are wins BY hero_id against other_id; 'with' wins are wins of
    the pair on the same team. Raw counts only — normalisation to deltas
    happens in normalize.py at ingestion into the matrix.
    """
    arg, values = bracket_filter["arg"], bracket_filter["values"]
    bracket_arg = f'{arg}: [{", ".join(values)}]'
    out: dict[int, dict] = {}
    for i in range(0, len(hero_ids), batch):
        chunk = hero_ids[i:i + batch]
        aliases = "\n".join(
            f"""h{hid}: matchUp(heroId: {hid}, take: 200, {bracket_arg}) {{
                  heroId
                  vs {{ heroId2 matchCount winCount }}
                  with {{ heroId2 matchCount winCount }}
                }}"""
            for hid in chunk
        )
        dump = ("stratz_matchup_sample.json" if i == 0 else None)
        data = _post("query { heroStats { %s } }" % aliases, dump)
        stats = data.get("heroStats")
        require(stats is not None, "Stratz matchUp", "heroStats came back null")
        for hid in chunk:
            rows = stats.get(f"h{hid}")
            require(isinstance(rows, list) and rows, "Stratz matchUp",
                    f"alias h{hid} missing/empty for heroId {hid}")
            row = rows[0]
            require(int(row.get("heroId", -1)) == hid, "Stratz matchUp",
                    f"asked for heroId {hid}, got {row.get('heroId')}")
            entry = {"vs": {}, "with": {}}
            for side in ("vs", "with"):
                side_rows = row.get(side)
                require(isinstance(side_rows, list) and len(side_rows) > 50,
                        "Stratz matchUp",
                        f"hero {hid} '{side}' has "
                        f"{len(side_rows) if isinstance(side_rows, list) else '?'} "
                        "rows, expected one per other hero (120+) — check "
                        "the 'take' argument semantics in the raw dump")
                for r in side_rows:
                    require("heroId2" in r and "matchCount" in r
                            and "winCount" in r, "Stratz matchUp",
                            f"row fields were {sorted(r.keys())}")
                    m, w = int(r["matchCount"]), int(r["winCount"])
                    require(0 <= w <= m, "Stratz matchUp",
                            f"hero {hid} {side} {r['heroId2']}: winCount {w} "
                            f"outside 0..matchCount {m}")
                    entry[side][int(r["heroId2"])] = (m, w)
            out[hid] = entry
        print(f"  matchups: {min(i + batch, len(hero_ids))}/{len(hero_ids)} heroes")
    return out


def fetch_bracket_counts(bracket: str, take: int = 14) -> dict[int, tuple[int, int]]:
    """Per-hero (matches, wins) in ONE named bracket, for the OpenDota
    tier-index cross-check. Uses heroStats.winDay summed over recent days."""
    data = _post(
        """
        query {
          heroStats {
            winDay(take: %d, bracketIds: [%s]) { heroId matchCount winCount }
          }
        }
        """ % (take, bracket),
        f"stratz_windays_{bracket}.json",
    )
    rows = (data.get("heroStats") or {}).get("winDay")
    require(isinstance(rows, list) and len(rows) > 100, "Stratz winDay",
            f"expected 100+ rows, got {type(rows).__name__} "
            f"len {len(rows) if isinstance(rows, list) else '?'} — if the "
            "field or its bracketIds argument is gone, adapt this query from "
            "the introspection dump")
    acc: dict[int, list[int]] = {}
    for r in rows:
        require("heroId" in r and "matchCount" in r and "winCount" in r,
                "Stratz winDay", f"row fields were {sorted(r.keys())}")
        a = acc.setdefault(int(r["heroId"]), [0, 0])
        a[0] += int(r["matchCount"])
        a[1] += int(r["winCount"])
    return {hid: (m, w) for hid, (m, w) in acc.items() if m > 0}

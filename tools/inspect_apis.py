"""Dump raw API responses to data_cache/raw/ so schema assumptions can be
checked against reality before (and after) writing parsing code.

Run this whenever a pull fails with SchemaError, or after a patch, and read
the JSON files it writes.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draft_assist.config import RAW_DUMP_DIR  # noqa: E402
from draft_assist.data import opendota, stratz  # noqa: E402


def main() -> None:
    RAW_DUMP_DIR.mkdir(parents=True, exist_ok=True)

    print("OpenDota constants/heroes ...")
    heroes = opendota.fetch_heroes()
    print(f"  {len(heroes)} heroes parsed OK")

    print("OpenDota heroStats ...")
    hero_stats = opendota.fetch_hero_stats()
    sample = {k: v for k, v in hero_stats[0].items()}
    print("  first hero entry keys:")
    print("  " + ", ".join(sorted(sample.keys())))

    print("Stratz introspection (matchUp args + bracket enums) ...")
    schema = stratz.introspect()
    print(json.dumps(schema, indent=2))
    chosen = stratz.choose_bracket_filter(schema, ("ANCIENT", "DIVINE"))
    print(f"  chosen bracket filter: {chosen}")

    print("Stratz sample matchUp (2 heroes) ...")
    sample_ids = sorted(heroes)[:2]
    matchups = stratz.fetch_matchups(sample_ids, chosen)
    hid = sample_ids[0]
    vs = matchups[hid]["vs"]
    some = list(vs.items())[:3]
    print(f"  hero {hid}: {len(vs)} vs-rows, first entries "
          f"(other_id -> (matches, wins)): {some}")

    print(f"\nRaw dumps written to {RAW_DUMP_DIR}")


if __name__ == "__main__":
    main()

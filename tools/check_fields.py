"""Say which OpenDota fields actually ARRIVE, and which come back empty.

`opendota.FIELDS` names every field the analyses read, and sends each one
as a `project` parameter. Two different things can then go wrong, and
they look identical from the outside — a column of nothing:

  * the field is only populated on matches OpenDota has PARSED, which is
    a minority of them (`lane_role` is the known one, and is why that
    analysis was removed); or
  * OpenDota does not accept that name in `project` and DROPS IT
    SILENTLY, so the app asked for something it was never going to get.

The second is a bug in this repository and the first is a fact about the
data, so telling them apart decides whether there is anything to fix.
The tell is `hero_damage` against `tower_damage`: they come from the same
place, so if one is full and the other is empty, it is the projection.

Reads the cached runs off disk. No network, no account id, no key.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draft_assist import console                                # noqa: E402
from draft_assist.history import cache                          # noqa: E402
from draft_assist.history.opendota import FIELDS                # noqa: E402
from draft_assist.history.shape import Match                    # noqa: E402

# Read off the row rather than guessed at, so a field added to FIELDS
# appears here without anybody remembering to add it.
DERIVED = {"player_slot": "slot", "radiant_win": "win",
           "start_time": "start"}
ITEM_FIELDS = {f"item_{n}" for n in range(6)}


def runs() -> list[Path]:
    """Only the RUNS. `cache.NAMES_FILE` lives in the same folder and is
    an item id -> name map with no matches in it at all, so a plain
    `*.json` here raises `KeyError: 'matches'` on a real cache."""
    return sorted(cache.run_files(cache.cache_dir()))


def main() -> int:
    console.plain_output()
    import json

    files = runs()
    if not files:
        console.say(f"No cached runs in {cache.cache_dir()}.")
        console.say("Open the History tab and run an account first - this "
                    "reads what that run stored, and makes no requests of "
                    "its own.")
        return 1

    rows = []
    for path in files:
        try:
            with open(path, encoding="utf-8") as handle:
                rows += json.load(handle).get("matches") or []
        except (OSError, ValueError) as error:
            console.say(f"Could not read {path.name}: {error}")

    if not rows:
        console.say("The cached runs hold no matches.")
        return 1

    console.say(f"{len(rows)} matches across {len(files)} cached run(s), "
                f"from {cache.cache_dir()}")
    console.say("")

    known = {f.name for f in Match.__dataclass_fields__.values()}
    empty = []
    seen = set()
    for field in FIELDS:
        name = DERIVED.get(field, field)
        if field in ITEM_FIELDS:
            name = "items"          # six API slots land in ONE list field
        if name not in known or name in seen:
            continue
        seen.add(name)
        filled = sum(1 for row in rows if row.get(name) is not None)
        share = 100.0 * filled / len(rows)
        console.say(f"  {name:<16} {filled:>5}/{len(rows):<5} {share:6.1f}")
        if share == 0.0:
            empty.append(name)

    console.say("")
    if not empty:
        console.say("Every field arrives. Nothing to fix.")
        return 0

    console.say(f"EMPTY: {', '.join(sorted(set(empty)))}")
    if "hero_damage" not in empty and "tower_damage" in empty:
        console.say("hero_damage arrives and tower_damage does not, and the "
                    "two come from the same place - so this is the `project` "
                    "parameter in opendota.FIELDS, not parsed matches. The "
                    "field names need checking against a real response "
                    "(tools/inspect_apis.py).")
    elif set(empty) == {"lane_role"}:
        console.say("Only lane_role, which is parse-gated and expected. "
                    "Nothing to fix.")
    else:
        console.say("Either these are parse-gated, or `project` is dropping "
                    "the names. tools/inspect_apis.py dumps a real response, "
                    "which is the only thing that settles it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

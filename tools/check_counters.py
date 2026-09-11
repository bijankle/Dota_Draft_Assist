"""Show what the Hero Counters section computes on THIS machine.

The figures are small and clustered by nature - a pick-weighted average
over ~126 heroes, most of which are near neutral - so "the bars look
wrong" has several possible causes that all appear the same on screen:
no statistics downloaded at all, a dataset with no matchups in it, or a
real but narrow spread. This prints the numbers behind the column so the
three can be told apart.

Reads only: the dataset off disk and the cached runs beside it. No
network, no account id, no key.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draft_assist import console                                # noqa: E402
from draft_assist.history import analyse, cache                 # noqa: E402


def main() -> int:
    console.plain_output()
    ds = analyse.ranked_dataset()
    if ds is None or getattr(ds, "is_empty", True):
        console.say("No hero statistics on this machine, so the section "
                    "has nothing to measure against.")
        console.say("Settings > Downloads > Statistics fetches them.")
        return 1

    console.say(f"dataset: {len(ds.hero_ids)} heroes, "
                f"brackets {ds.meta.get('target_brackets', '?')}")
    deltas, standing, datum = analyse.counter_standings(ds)
    if not deltas:
        console.say("The dataset has heroes but no usable matchups or pick "
                    "counts, so every hero would score the same.")
        return 1

    values = sorted(deltas.values())
    reach = max(abs(v - datum) for v in deltas.values())
    console.say(f"pool average : {datum:+.4f}")
    console.say(f"most counterable  : {values[0]:+.4f}")
    console.say(f"least counterable : {values[-1]:+.4f}")
    console.say(f"bar reaches +/- {reach:.4f} from the average")
    if reach < 0.05:
        console.say("")
        console.say("THAT IS A VERY NARROW SPREAD. Every bar will be a few "
                    "pixels whatever the scale, because the heroes really "
                    "are that close together.")

    import json
    files = cache.run_files(cache.cache_dir())
    if not files:
        console.say("")
        console.say("No cached run, so no heroes would be listed. Run an "
                    "account in the History tab.")
        return 0

    rows = []
    for path in files:
        try:
            with open(path, encoding="utf-8") as handle:
                rows += json.load(handle).get("matches") or []
        except (OSError, ValueError):
            pass
    played = {}
    for row in rows:
        hid = row.get("hero_id")
        if hid is not None:
            played[hid] = played.get(hid, 0) + 1

    console.say("")
    console.say(f"{'hero':22} {'games':>5} {'vs field':>9} {'bar':>6}  standing")
    known = [(h, c) for h, c in played.items() if h in deltas]
    for hero_id, count in sorted(known, key=lambda kv: -kv[1])[:15]:
        value = deltas[hero_id]
        span = 0.0 if not reach else min(abs(value - datum) / reach, 1.0)
        console.say(f"{ds.name(hero_id)[:22]:22} {count:5d} {value:+9.3f} "
                    f"{span * 100:5.0f}%  {standing[hero_id]}")
    missing = len(played) - len(known)
    if missing:
        console.say(f"({missing} played heroes are not in the dataset)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

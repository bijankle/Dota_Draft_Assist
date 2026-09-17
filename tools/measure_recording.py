"""Measure a recording: where the pick bar really is, and whose five is whose.

A recording already holds everything needed to answer both of the
questions this app still has open, and nobody has ever read it for them.
`record.py` saves frames from the moment a session starts - so they span
HERO SELECTION as well as strategy time - beside every payload Dota sent.

    python tools/measure_recording.py recordings/2026-09-17_2031

THE PICK BAR. The shipped crop boxes were measured entirely from
STRATEGY TIME screenshots, and hero selection is the screen the app
exists for. Whether a filled hero-selection bar sits where the
strategy-time bar does has been open in the notes for months, and no
screenshot in the sample could answer it: the only two hero-selection
frames in it were taken before anybody had picked, so their bar was
empty. A recording is the sample that was missing.

The trick that makes it measurable is that the ten heroes are named ONCE,
at strategy time, by the minimap - and they are the same ten that were on
the bar during hero selection. So the names come from the END of the
recording and are searched for at the BEGINNING of it.

WHOSE FIVE. The minimap says which ten and not whose five. One rule
decides it outright - your own team stands on the strategy map's lane
slots - and it requires exactly five there, so a team where somebody
never chose a lane falls through it, through the pairs rule below it, and
lands on splitting the ten in list order, which is a coin flip and is
known to invert. This prints the positions so that case can be told from
the others rather than guessed at.

NOTHING HERE WRITES ANYTHING. It reads a folder and prints; no
calibration, no settings, no recording is touched.
"""

import argparse
import statistics
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from draft_assist import console                         # noqa: E402
from draft_assist import record as record_mod            # noqa: E402
from draft_assist.data import store                      # noqa: E402
from draft_assist.gsi import minimap as minimap_mod      # noqa: E402
from draft_assist.gsi import state as gsi_state          # noqa: E402
from draft_assist.vision import autocal                  # noqa: E402
from draft_assist.vision import layout as layout_mod     # noqa: E402
from draft_assist.vision import lineup as lineup_mod     # noqa: E402

# How many frames to measure. Each one is a full portrait search - the
# scale grid plus ten passes - so this is seconds apiece, not milliseconds.
DEFAULT_FRAMES = 8
# The six numbers that say where the crop boxes go, in the order the
# calibration file lists them.
FRACTIONS = ("radiant_x", "dire_x", "y", "slot_w", "slot_h", "pitch")
# Two measurements of one fraction this far apart are the same answer.
# It is `find_portraits.AGREE_WITHIN`, deliberately: two tools disagreeing
# about what "agrees" is one of them being read as contradicting the other.
AGREE_WITHIN = 0.01


def read_image(path: Path):
    """Decode from bytes - `cv2.imread` goes through Windows' ANSI
    codepage and cannot open every path a recording folder can have."""
    import cv2

    try:
        data = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    except OSError:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def phase_boundary(states: list[dict]) -> float | None:
    """Elapsed seconds at which HERO SELECTION last appeared.

    The state log carries `at` (seconds since the session started) and the
    game state for every tick, so the phases are in it. Frames do NOT
    carry their own tick, which is why this is a boundary in TIME that
    frame timestamps are then compared against, rather than a label read
    off each frame.
    """
    last = None
    for row in states:
        if "HERO_SELECTION" in str(row.get("game_state") or ""):
            last = float(row.get("at") or 0.0)
    return last


def frame_seconds(frames: list[Path]) -> dict[Path, float]:
    """Each frame's age in seconds from the first one, by file time.

    APPROXIMATE AND SAID TO BE. The writer is a queue on its own thread,
    so a frame's mtime is when it was WRITTEN rather than when it was
    captured. Over phases lasting tens of seconds that lag does not move
    a frame across a boundary, and it is the only clock the two files
    share - `state.jsonl` counts from the session's start and a frame
    carries nothing but its number.
    """
    try:
        first = min(path.stat().st_mtime for path in frames)
    except (OSError, ValueError):
        return {}
    out = {}
    for path in frames:
        try:
            out[path] = path.stat().st_mtime - first
        except OSError:
            pass
    return out


def strategy_payload(folder: Path):
    """The last STRATEGY TIME payload that carried ten placed heroes.

    The LAST rather than the first, which is the opposite of what
    `GsiProvider` latches - and right here for the opposite reason. The
    app wants the earliest complete reading because the order wobbles
    later; this wants the fullest picture of where everybody stood, and
    is reading it once rather than every tick.
    """
    import json

    best = None
    for path in sorted((folder / "gsi").glob("gsi_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        state = str((payload.get("map") or {}).get("game_state") or "")
        if "STRATEGY_TIME" not in state:
            continue
        if len(minimap_mod.hero_entries(payload)) >= 2 * minimap_mod.TEAM_SIZE:
            best = payload
    return best


def say_teams(payload, dataset) -> list[int]:
    """Print where the ten stood, and which rule that leaves the app on.

    Returns the ten hero ids, which is also what the pick-bar half needs -
    the names are stated once, by the game, at strategy time.
    """
    print("\n=== WHOSE FIVE ARE YOURS ===\n")
    if payload is None:
        print("  no strategy-time payload here carried ten placed heroes,")
        print("  so this recording cannot answer the teams question.")
        return []

    name_to_id = gsi_state._hero_id_by_internal_name(dataset)
    player = (payload.get("player") or {})
    hero = (payload.get("hero") or {})
    my_name = str(hero.get("name") or "")
    my_id = name_to_id.get(my_name)
    print(f"  player      {player.get('name') or 'unknown'}")
    print(f"  your hero   {dataset.name(my_id) if my_id else my_name or '?'}")
    print(f"  your team   {player.get('team_name') or 'not reported'}")

    # THE APP'S OWN TEN, not every hero object in the payload. The raw
    # minimap also carries duplicates of your own hero and, in one
    # recording, a hero that was not in the match at all - all of them at
    # the origin. `hero_entries` drops those, and draws origin entries
    # back in ONLY when fewer than ten were placed, which is exactly the
    # case being diagnosed here: a team-mate who chose no lane. Reading
    # the raw list instead reported four heroes at the origin where one
    # was, which is the junk being counted as evidence.
    entries = minimap_mod.hero_entries(payload)
    raw = minimap_mod.hero_entries(payload, drop_origin=False)
    junked = len(raw) - len(entries)
    on_slots, at_origin, in_world = [], [], []
    print("\n  where each hero stood on the strategy map:\n")
    for index, name, position in entries:
        pair = (position[0], position[1])
        hero_id = name_to_id.get(name)
        label = dataset.name(hero_id) if hero_id else name
        if tuple(pair) in minimap_mod.LANE_SLOTS:
            where, bucket = "LANE SLOT", on_slots
        elif pair == (0, 0):
            where, bucket = "origin", at_origin
        else:
            where, bucket = "out in the world", in_world
        bucket.append((index, hero_id, label))
        print(f"    o{index:<4} {label:<22} {str(pair):<18} {where}")

    if junked:
        print(f"\n  ({junked} other hero object(s) ignored - duplicates and "
              "pick-screen junk)")
    print(f"\n  on a lane slot: {len(on_slots)}   "
          f"at the origin: {len(at_origin)}   "
          f"out in the world: {len(in_world)}")

    team = minimap_mod.TEAM_SIZE
    if len(on_slots) == team and len(in_world) + len(at_origin) == team:
        print("\n  -> the strategy-slot rule fits: five on the slots and "
              "five off them.")
        print("     The app can state the teams outright on this one.")
    else:
        print(f"\n  -> the strategy-slot rule needs exactly {team} on the "
              f"slots and {team} off;")
        print(f"     this frame has {len(on_slots)} on. IT DECLINES, and "
              "the app falls")
        print("     through to splitting the ten in list order, which is a "
              "coin flip.")
        if at_origin:
            print(f"     {len(at_origin)} hero(es) stand at the origin - a "
                  "team-mate who chose")
            print("     no lane. Those are almost certainly YOURS.")

    ten = [hid for _i, hid, _n in
           (on_slots + at_origin + in_world) if hid is not None]
    return ten[:2 * team] if len(ten) >= 2 * team else []


def measure_frames(folder: Path, ten: list[int], count: int,
                   boundary: float | None) -> list[dict]:
    """Search each sampled frame for the ten, and measure what it finds."""
    frames = sorted((folder / "frames").glob("*.png"))
    if not frames:
        print("\n  no frames in this recording - nothing to measure.")
        return []
    ages = frame_seconds(frames)
    step = max(1, len(frames) // max(1, count))
    chosen = frames[::step][:count]

    art = autocal.base_portraits(ten)
    missing = [hid for hid in ten if hid not in art]
    if missing:
        names = ", ".join(str(hid) for hid in missing)
        print(f"\n  no downloaded portrait for hero id(s) {names} - "
              "run the artwork download first.")
        return []

    current = layout_mod.load_layout()
    rows = []
    for number, path in enumerate(chosen, start=1):
        console.progress(number / len(chosen), "measuring frames")
        frame = read_image(path)
        if frame is None:
            continue
        height, width = frame.shape[:2]
        found = autocal.locate(frame, art)
        fitted = autocal.layout_from(found, width, height)
        placed = lineup_mod.read_placed(frame, ten, current, art)
        age = ages.get(path)
        phase = "?"
        if age is not None and boundary is not None:
            phase = "picking" if age <= boundary else "strategy"
        rows.append({
            "name": path.name, "phase": phase, "age": age,
            "size": (width, height), "found": len(found),
            "layout": fitted.layout, "note": fitted.note,
            "matched": getattr(placed, "matched", 0),
            "boxes_ok": bool(getattr(placed, "ok", False)),
        })
    return rows


def say_bar(rows: list[dict]) -> None:
    print("\n\n=== WHERE THE PICK BAR REALLY IS ===\n")
    if not rows:
        print("  nothing measured.")
        return

    print(f"  {'frame':<12}{'phase':<10}{'at':>7}{'found':>7}"
          f"{'boxes':>8}   measured y / slot_h")
    for row in rows:
        age = f"{row['age']:.0f}s" if row["age"] is not None else "-"
        layout = row["layout"]
        measured = (f"{layout.y:.4f} / {layout.slot_h:.4f}"
                    if layout is not None else f"-  ({row['note']})")
        print(f"  {row['name']:<12}{row['phase']:<10}{age:>7}"
              f"{row['found']:>7}{row['matched']:>5}/10   {measured}")

    good = [row for row in rows if row["layout"] is not None]
    if not good:
        print("\n  no frame located enough portraits to measure.")
        return

    print("\n  the six fractions, median over the frames that located:\n")
    current = layout_mod.load_layout()
    for name in FRACTIONS:
        values = [getattr(row["layout"], name) for row in good]
        median = statistics.median(values)
        spread = max(values) - min(values)
        now = getattr(current, name)
        flag = "" if abs(median - now) <= AGREE_WITHIN else "   <-- differs"
        print(f"    {name:<11} measured {median:.4f}   "
              f"in use {now:.4f}   spread {spread:.4f}{flag}")

    picking = [r for r in good if r["phase"] == "picking"]
    strategy = [r for r in good if r["phase"] == "strategy"]
    print("\n  DOES THE BAR MOVE BETWEEN THE TWO SCREENS?\n")
    if not picking or not strategy:
        have = f"{len(picking)} while picking, {len(strategy)} at strategy"
        print(f"    cannot say - {have}. Both are needed, and only a")
        print("    recording that ran through hero selection has the first.")
        return
    for name in ("y", "slot_h"):
        a = statistics.median([getattr(r["layout"], name) for r in picking])
        b = statistics.median([getattr(r["layout"], name) for r in strategy])
        verdict = ("the same place" if abs(a - b) <= AGREE_WITHIN
                   else "DIFFERENT - the bar moves")
        print(f"    {name:<8} picking {a:.4f}   strategy {b:.4f}   "
              f"-> {verdict}")


def main() -> None:
    console.plain_output()
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", help="a folder under recordings/")
    parser.add_argument("--frames", type=int, default=DEFAULT_FRAMES,
                        help=f"how many frames to measure "
                             f"(default {DEFAULT_FRAMES}; seconds each)")
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.is_dir():
        raise SystemExit(f"no such folder: {folder}")

    states = record_mod.read_states(folder)
    frames = sorted((folder / "frames").glob("*.png"))
    payloads = sorted((folder / "gsi").glob("gsi_*.json"))
    seen = []
    for row in states:
        name = str(row.get("game_state") or "").replace(
            "DOTA_GAMERULES_STATE_", "")
        if name and name not in seen:
            seen.append(name)

    print(f"=== {folder.name} ===\n")
    print(f"  frames    {len(frames)}")
    print(f"  payloads  {len(payloads)}")
    print(f"  states    {', '.join(seen) or 'none logged'}")
    boundary = phase_boundary(states)
    if boundary is None:
        print("  NOTE: no HERO_SELECTION tick in the state log, so frames "
              "cannot be")
        print("        told apart by phase. Record from before the draft "
              "starts.")
    else:
        print(f"  hero selection ran until {boundary:.0f}s into the session")

    dataset = store.load()
    ten = say_teams(strategy_payload(folder), dataset)
    if not ten:
        print("\n  without the ten heroes the game named, the pick bar "
              "cannot be measured.")
        return
    say_bar(measure_frames(folder, ten, args.frames, boundary))
    print("\nNothing was written. This tool only reads.")


if __name__ == "__main__":
    main()

"""Mark the portrait engine against the game's own answer key.

WHY A BOT MATCH BEATS A FOLDER OF SCREENSHOTS. A recording holds both
halves of the problem at once:

    recordings/<stamp>/frames/00042.png    what was on screen
    recordings/<stamp>/gsi/gsi_00203.json  what the GAME said was on it

From STRATEGY_TIME the minimap names all ten heroes (see
`gsi/minimap.py`), so every frame from that phase arrives with the
answer already written on the back. The engine can therefore mark its
own homework - on hundreds of frames, automatically, with nobody
squinting at crops and nobody waiting on a round trip.

That is the whole reason this exists rather than more screenshots. A
screenshot proves where the boxes landed only if a person looks at it.
A recorded frame proves it against the game.

WHAT IT SCORES, in the order the chain runs:

    located   the sweep found a pick bar at all
    boxed     the ten boxes were derived from it
    named     the recogniser committed to a hero in a slot
    RIGHT     that hero is one the game says is in this match
    WRONG     it is not - the expensive kind of failure, because the
              app would give advice against a hero nobody picked

A slot the recogniser DECLINES is not counted wrong. An unknown slot is
a legitimate state in this app ("silent about one slot beats wrong about
one slot"), so it is reported apart from both.

    python tools/score_recording.py recordings/2026-09-13_2031
    python tools/score_recording.py recordings/... --every 5 --proof 3

The proof sheets and any frame it names ARE Valve's artwork, like the
recording they come from. Attach them, never commit them.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from draft_assist import console                      # noqa: E402
from draft_assist.gsi import minimap                  # noqa: E402
from draft_assist.history import store as _store      # noqa: E402
import numpy as np                                  # noqa: E402

from draft_assist.vision import autocal, library      # noqa: E402
from draft_assist.vision.phash import phash           # noqa: E402
from tools import find_portraits as fp                # noqa: E402

STRATEGY = "STRATEGY_TIME"
# A LINE THE APP CAN READ, and a plain one a person can too. Progress was
# printed with a carriage return so it overwrote itself in a console -
# which does nothing whatever in the dialog's text box, where the run
# showed as a long silence with no percentage anywhere. A prefix and a
# newline work in both places.
STEP = "PROGRESS"


def step(share: float, what: str) -> None:
    print(f"{STEP} {share:.0%}  {what}", flush=True)


def hero_names(dataset) -> dict[str, int]:
    """Dota's internal name -> hero id, from whatever the app has.

    The dataset if it is on disk, and the portrait filenames otherwise -
    they are named `<hero id>_<internal name>.png`, so the library is a
    complete name map that needs no network and no API key. Same
    layering `fetch_custom_portraits` had to learn.
    """
    out = {}
    try:
        data = dataset or _store.load()
        for hero in getattr(data, "heroes", []) or []:
            name = getattr(hero, "internal_name", None) or getattr(
                hero, "name", None)
            if name:
                out[str(name)] = int(hero.id)
    except Exception:
        pass
    if out:
        return out
    for path in sorted(library.BASE_DIR.glob("*.png")):
        stem = path.stem
        number, _, rest = stem.partition("_")
        if number.isdigit() and rest:
            out[f"npc_dota_hero_{rest}"] = int(number)
    return out


def answer_key(folder: Path, names: dict[str, int]) -> tuple[set, str]:
    """The ten hero ids the GAME named, from the fullest strategy payload.

    Read through `minimap.read_lineups` rather than by picking the JSON
    apart here: that function is where every guard about what the minimap
    does and does not carry already lives, and a second reading of the
    same block is one of them going stale.
    """
    best, note = set(), "no strategy-time payload named ten heroes"
    for path in sorted((folder / "gsi").glob("gsi_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        state = str(((payload.get("map") or {}).get("game_state")) or "")
        if STRATEGY not in state:
            continue
        mine = ((payload.get("hero") or {}).get("id"))
        out = minimap.read_lineups(payload, names, mine, game_state=state)
        if out.complete:
            return set(out.allies) | set(out.enemies), f"from {path.name}"
    return best, note


def slot_distances(crop, lib):
    """Hamming distance from this crop to EVERY hero, best entry per hero.

    `recognize.match_crop` answers only "which one, and did it clear the
    thresholds". That is the right answer for the app and the wrong one
    for fixing it: when a slot comes out wrong, what decides the fix is
    WHERE THE CORRECT HERO CAME - first but under the margin, or
    twentieth. The first is a threshold to loosen; the second is a crop
    in the wrong place, and loosening anything would only turn a
    declined slot into a wrong one.
    """
    if crop is None or crop.size == 0:
        return {}
    bits = phash(crop, lib.hash_size)
    raw = np.count_nonzero(lib.bits != bits, axis=1)
    out = {}
    for hero_id, distance in zip(lib.hero_ids, raw):
        hero_id = int(hero_id)
        if hero_id not in out or distance < out[hero_id]:
            out[hero_id] = int(distance)
    return out


def verdict(distances: dict, truth: set, max_distance: int,
            min_margin: int):
    """What the recogniser WOULD say at these thresholds, and whether it
    is right. Separated from the sweep so a threshold can be tried
    without re-cropping or re-hashing anything."""
    if not distances:
        return "declined", None, None
    order = sorted(distances.items(), key=lambda kv: kv[1])
    best_id, best_d = order[0]
    others = [d for hid, d in order if hid != best_id]
    margin = (others[0] - best_d) if others else min_margin
    if best_d > max_distance or margin < min_margin:
        return "declined", best_id, best_d
    if not truth:
        return "named", best_id, best_d
    return ("right" if best_id in truth else "wrong"), best_id, best_d


def key_rank(distances: dict, truth: set):
    """(the answer-key hero that matched best, its distance, its RANK).

    Rank 1 with a slot still declined means the thresholds are wrong.
    Rank 40 means the crop is not on that portrait, and no threshold
    anywhere will fix it.
    """
    if not distances or not truth:
        return None, None, None
    order = sorted(distances.items(), key=lambda kv: kv[1])
    for place, (hero_id, distance) in enumerate(order, 1):
        if hero_id in truth:
            return hero_id, distance, place
    return None, None, None


def tune(samples: list, truth: set, params) -> None:
    """Sweep the two thresholds over every slot already measured.

    The expensive half - locate, crop, hash - has been done once. Trying
    a threshold after that is arithmetic, so the whole grid costs less
    than one more frame. This is the auto half of the loop the user
    asked for: "see where you went wrong, and correct it, whether that
    be iteratively yourself (auto) or manually".
    """
    if not samples or not truth:
        return
    print("\nWHAT THE THRESHOLDS ARE COSTING")
    print("-" * 66)
    print(f"  shipped: max_distance {params.max_distance}, "
          f"min_margin {params.min_margin}")
    ranks = [key_rank(d, truth)[2] for d in samples]
    reachable = sum(1 for r in ranks if r == 1)
    print(f"  the correct hero is the CLOSEST match in "
          f"{reachable} of {len(samples)} slots")
    if reachable < len(samples):
        far = sorted(r for r in ranks if r and r > 1)[:8]
        print(f"  where it is not, it ranks: "
              f"{', '.join(str(r) for r in far)}"
              + ("  <- ranks in the tens mean the CROP is wrong, "
                 "not the threshold" if far and far[-1] > 5 else ""))
    best = None
    print(f"\n  {'max_d':>6} {'margin':>7} {'right':>7} {'wrong':>7} "
          f"{'declined':>9}")
    for max_distance in range(max(4, params.max_distance - 8),
                              params.max_distance + 13, 2):
        for min_margin in range(0, max(2, params.min_margin + 7), 2):
            tally = Counter(verdict(d, truth, max_distance, min_margin)[0]
                            for d in samples)
            # A WRONG SLOT COSTS MORE THAN A DECLINED ONE, which is this
            # app's oldest rule: "silent about one slot beats wrong about
            # one slot". So the score charges four for a wrong answer.
            rank = tally["right"] - 4 * tally["wrong"]
            if best is None or rank > best[0]:
                best = (rank, max_distance, min_margin, tally)
    for max_distance, min_margin in (
            (params.max_distance, params.min_margin),
            (best[1], best[2])):
        tally = Counter(verdict(d, truth, max_distance, min_margin)[0]
                        for d in samples)
        mark = "  <- shipped" if max_distance == params.max_distance and \
               min_margin == params.min_margin else "  <- best found"
        print(f"  {max_distance:>6} {min_margin:>7} {tally['right']:>7} "
              f"{tally['wrong']:>7} {tally['declined']:>9}{mark}")
    if (best[1], best[2]) != (params.max_distance, params.min_margin):
        print(f"\n  Settings > Advanced, or edit recognition.json: "
              f"max_distance {best[1]}, min_margin {best[2]}")


def score(folder: Path, every: int, proofs: int, out: Path,
          last: int = 0, sweeps: int = 4) -> int:
    step(0.0, "loading the portraits")
    art = fp.load_art()
    if len(art) < 50:
        raise SystemExit(
            f"Only {len(art)} hero portrait(s) in {library.BASE_DIR}.\n"
            "Open the app and run Settings > Downloads > All artwork.")
    params = library.load_params()
    # PASS THE FOLDERS, NEVER RELY ON THE MODULE ATTRIBUTE. `library.load`
    # takes them as DEFAULT ARGUMENTS, which Python binds once at import -
    # so repointing `library.BASE_DIR` afterwards changes nothing and the
    # load silently reads the real install instead. Same trap this repo
    # already documents for `load_layout` and `ui_settings.load`.
    cache = library.PORTRAITS_DIR / "library.npz"
    try:
        lib = library.load(path=cache, expected_hash_size=params.hash_size,
                           base_dir=library.BASE_DIR,
                           variants_dir=library.VARIANTS_DIR)
    except FileNotFoundError:
        # BUILD IT RATHER THAN REFUSING. On the user's own machine the app
        # has already written one; anywhere else, telling somebody to go
        # and run another tool first is a step to forget.
        print("no portrait library yet - building one from the art ...",
              flush=True)
        lib = library.rebuild(params.hash_size, library.BASE_DIR,
                              library.VARIANTS_DIR, cache)
    names = hero_names(None)
    truth, where = answer_key(folder, names)
    print(f"{len(art)} portraits, library of {len(lib)} entries")
    if truth:
        back = {hid: nm for nm, hid in names.items()}
        print(f"ANSWER KEY ({len(truth)} heroes, {where}):")
        print("  " + ", ".join(sorted(
            fp.hero_name(back.get(h, str(h))) for h in truth)))
    else:
        print(f"NO ANSWER KEY: {where}")
        print("  Scoring will still say where the boxes landed, but not "
              "whether the heroes are right.")

    frames = sorted((folder / "frames").glob("*.png"))
    if last:
        frames = frames[-last:]
    if not frames:
        raise SystemExit(f"No frames in {folder / 'frames'}")

    # LOCATE ONCE, IDENTIFY MANY. The pick bar does not move during a
    # match, and locating it is the whole cost - a full sweep of 126
    # heroes at two dozen sizes is about twenty seconds a frame, where
    # identifying ten crops in boxes already known is milliseconds. Doing
    # it per frame made a 489-frame recording a two-hour job, which is
    # not a tool anybody runs twice.
    #
    # ACROSS THE WHOLE RECORDING, and this corrects a wrong guess. An
    # earlier version swept only the second half, on the reasoning that
    # frames start when recording does so the draft must be at the end.
    # It is not: recording stops a minute AFTER the draft, so a session
    # runs queue -> loading -> DRAFT -> game, and the draft is in the
    # middle. Sweeping the tail put every probe on the loading screen or
    # in the game - where the top scoreboard carries ten hero portraits
    # of its own, which is exactly the sort of thing that matches
    # inconsistently.
    stride = max(1, len(frames) // max(1, sweeps))
    probes = frames[::stride][:sweeps]
    print(f"{len(frames)} frame(s); sweeping {len(probes)} of them for the "
          f"bar, then reading the rest with what it finds\n")

    geometries, probe_shapes = [], None
    for number, path in enumerate(probes, 1):
        step(0.05 + 0.45 * (number - 1) / max(1, len(probes)),
             f"looking for the pick bar, frame {number} of {len(probes)}")
        frame = fp.read_image(path)
        if frame is None:
            continue
        found = fp.hunt(autocal._grey(frame), art)
        banks = fp.banks_from(found[2], found[0]) if found else None
        if found and banks:
            probe_shapes = frame.shape[:2]
            geometries.append((banks[0], banks[1], banks[2], found[0],
                               banks[3], found[1]))
            print(f"  swept {path.name}: slot {found[0]}x{found[1]}, "
                  f"pitch {banks[2]}, radiant x {banks[0]}, "
                  f"dire x {banks[1]}, top {banks[3]}", flush=True)
        else:
            print(f"  swept {path.name}: no bar found", flush=True)

    if not geometries:
        raise SystemExit(
            "\nNo frame in this recording showed a pick bar the sweep could "
            "find.\nRun with --sweeps 12 to try more of them, or send me "
            "a -strip.png from debug_out.")

    # THE MEDIAN OF WHAT THE SWEEPS AGREED ON. One frame can be unlucky;
    # the spread across several is also the confidence, and it is printed
    # because a wide one means the geometry below is not to be trusted.
    # THE BIGGEST AGREEING CLUSTER, not the median of everything. Probes
    # land in different phases, and only the ones that saw the DRAFT can
    # agree with each other - a loading screen and an in-game scoreboard
    # each produce their own answer and have nothing to agree with. So
    # geometries are grouped by whether they describe the same bar, and
    # the largest group wins. The median of all four would be a number
    # no frame ever measured.
    def alike(a, b):
        return (abs(a[0] - b[0]) <= max(6, 0.12 * a[3])
                and abs(a[2] - b[2]) <= max(4, 0.10 * a[3])
                and abs(a[3] - b[3]) <= max(4, 0.10 * a[3]))

    groups = []
    for item in geometries:
        for group in groups:
            if alike(group[0], item):
                group.append(item)
                break
        else:
            groups.append([item])
    groups.sort(key=len)
    agreed = groups[-1]
    if len(agreed) < len(geometries):
        print(f"\n  {len(agreed)} of {len(geometries)} sweeps agree with "
              "each other; the rest saw a different screen.")
    columns = list(zip(*agreed))
    geom = [int(np.median(column)) for column in columns]
    spread = [int(max(column) - min(column)) for column in columns]
    names = ("radiant x", "dire x", "pitch", "slot w", "top", "slot h")
    print(f"\nGEOMETRY from {len(geometries)} sweep(s)")
    print("-" * 58)
    for name, value, wide in zip(names, geom, spread):
        flag = "" if wide <= 2 else ("  <- sweeps disagree by "
                                     f"{wide}px")
        print(f"  {name:<12} {value:>6}{flag}")
    # A GEOMETRY THE SWEEPS DISAGREE ABOUT IS NOT A GEOMETRY. The bar
    # does not move during a match, so four sweeps of one recording must
    # give four nearly identical answers; a wide spread means each sweep
    # locked onto something different, and applying the median of four
    # wrong answers to 489 frames is a minute spent producing numbers
    # that cannot mean anything. The first version printed the spread and
    # carried on regardless, which is worse than not measuring it at all.
    if len(agreed) < 2:
        print("\n  REFUSING to score: no two sweeps found the same bar, so "
              "there is\n  nothing here that two frames agree about.")
        out.mkdir(parents=True, exist_ok=True)
        for path in probes:
            frame = fp.read_image(path)
            if frame is not None:
                fp.strip_of(frame, path, out)
        print(f"\n  Strips written to {out} - send me one.")
        print("  Or run with --sweeps 12 to look at more of the recording.")
        return 1
    loose = [name for name, wide in zip(names, spread)
             if wide > max(6, 0.12 * geom[3])]
    if loose:
        print(f"\n  REFUSING to score with this: {', '.join(loose)} "
              "disagree across the sweeps.")
        print("  Four sweeps of one match must agree - the bar does not")
        print("  move. Each found something different, so none found it.")
        out.mkdir(parents=True, exist_ok=True)
        wrote = []
        for path in probes:
            frame = fp.read_image(path)
            if frame is not None:
                fp.strip_of(frame, path, out)
                wrote.append(f"{path.stem}-strip.png")
        print(f"\n  Written to {out}:")
        for name in wrote:
            print(f"    {name}")
        print("\n  SEND ME ONE OF THESE. It is the band that was searched,")
        print("  and it is the one thing that settles what is up there.")
        return 1

    radiant_x, dire_x, pitch, slot_w, top, slot_h = geom
    rects = fp.boxes_of(radiant_x, dire_x, pitch, slot_w, top, slot_h)

    frames = frames[::max(1, every)]
    print(f"\nreading {len(frames)} frame(s) with those boxes\n")

    tally = Counter()
    wrong_heroes = Counter()
    worst = []
    samples = []          # one distance vector per slot, for tuning
    misplaced = 0
    for number, path in enumerate(frames, 1):
        if number % 20 == 0 or number == len(frames):
            step(0.55 + 0.45 * number / max(1, len(frames)),
                 f"reading heroes, frame {number} of {len(frames)}")
        frame = fp.read_image(path)
        if frame is None:
            tally["unreadable"] += 1
            continue
        if probe_shapes and frame.shape[:2] != probe_shapes:
            # A frame a different size from the one measured is a
            # different window, and the boxes do not describe it.
            tally["wrong size"] += 1
            continue
        reads = fp.identify(frame, rects, lib, params)
        tally["located"] += 1
        right = declined = wrong = 0
        for (x, y, w, h), (hero_id, name, _ref, _d, _m) in zip(rects, reads):
            crop = frame[max(0, y):y + h, max(0, x):x + w]
            distances = slot_distances(crop, lib)
            if distances:
                samples.append(distances)
                _who, _dist, place = key_rank(distances, truth)
                # RANK IS THE DIAGNOSIS. The correct hero being the
                # closest match means any failure here is a threshold;
                # it being twentieth means the box is not on a portrait
                # and no threshold will help.
                if place is not None and place > 3:
                    misplaced += 1
            if not hero_id or hero_id == library.EMPTY_SLOT:
                declined += 1
            elif not truth or hero_id in truth:
                right += 1
            else:
                wrong += 1
                wrong_heroes[name] += 1
        tally["right"] += right
        tally["declined"] += declined
        tally["wrong"] += wrong
        worst.append((right, path, frame, rects, reads))

    step(1.0, "done")
    print("HOW IT DID")
    print("-" * 58)
    slots = 10 * max(1, tally["located"])
    print(f"  frames located          {tally['located']} of {len(frames)}")
    for key in ("not located", "no banks", "unreadable"):
        if tally[key]:
            print(f"  {key:<22}  {tally[key]}")
    if tally["located"]:
        print(f"  slots RIGHT             {tally['right']:>5}  "
              f"({tally['right'] / slots:.0%})")
        print(f"  slots declined          {tally['declined']:>5}  "
              f"({tally['declined'] / slots:.0%})   "
              "not an error - an unknown slot is legitimate")
        print(f"  slots WRONG             {tally['wrong']:>5}  "
              f"({tally['wrong'] / slots:.0%})   "
              "the expensive kind: advice against a hero nobody picked")
    if truth and samples:
        print(f"  slots whose crop is OFF   {misplaced:>5}  "
              f"({misplaced / max(1, len(samples)):.0%})   "
              "the correct hero is not even close - geometry, not "
              "thresholds")
    if wrong_heroes:
        print("\n  heroes it named that are NOT in this match:")
        for name, count in wrong_heroes.most_common(8):
            print(f"    {count:>4}x  {name}")

    tune(samples, truth, params)

    # THE BEST FRAME IS THE ONE THAT ANSWERS THE QUESTION.
    # Frames start at the BUTTON PRESS, not at the draft (see
    # `record.FRAME_INTERVAL`), so a recording opens with the queue, the
    # loading screen and a hero-select bar that is still filling up. An
    # empty slot cannot match a hero, so those frames drag every average
    # down and say nothing about whether the geometry is right. What
    # says that is the best frame: if ONE frame reads all ten, the boxes
    # are on the portraits and everything else here is phase.
    graded = [item for item in worst if item[3] is not None]
    if graded:
        graded.sort(key=lambda item: item[0])
        top = graded[-1]
        spread = Counter(item[0] for item in graded)
        print("\nPER FRAME, best first")
        print("-" * 58)
        print(f"  best frame              {top[0]}/10 right  ({top[1].name})")
        print("  how many frames got each score:")
        for got in sorted(spread, reverse=True):
            print(f"    {got:>2}/10   {'#' * min(40, spread[got])} "
                  f"{spread[got]}")
        # THE VERDICT COMES FROM "IS THE CORRECT HERO CLOSEST", never
        # from the right-count. A run can name almost nothing and still
        # have every box dead on the portraits - that is a threshold
        # story - and the right-count cannot tell it from boxes landing
        # on the wrong thing, which is the one distinction this whole
        # report exists to draw.
        closest = sum(1 for d in samples if key_rank(d, truth)[2] == 1)
        share = closest / max(1, len(samples))
        if top[0] >= 8:
            print("  -> the boxes are on the portraits AND the thresholds "
                  "are right. Nothing to fix here.")
        elif share >= 0.5:
            print(f"  -> the boxes ARE on the portraits: the correct hero "
                  f"is the closest match in {share:.0%} of slots. What is "
                  "costing the reads is the THRESHOLDS, above.")
        else:
            print(f"  -> the correct hero is closest in only {share:.0%} "
                  "of slots, so the boxes are NOT on the portraits. This "
                  "is geometry, and no threshold will fix it.")

    # PROOF SHEETS FOR THE WORST, not for the best. A sheet of a frame
    # that worked shows nothing that the tally has not already said.
    out.mkdir(parents=True, exist_ok=True)
    made = []
    # THE BEST ONE FIRST, and it is not optional. The worst frames in a
    # recording are the queue and the loading screen - sheets of those
    # show an empty HUD and answer nothing. The best frame is the one
    # that says whether this works at all.
    if graded:
        right, path, frame, rects, reads = graded[-1]
        fp.proof(frame, rects, reads, path, out,
                 f"BEST  {path.name}   {right}/10 right")
        made.append(f"{path.stem}-proof.png  (the BEST frame, "
                    f"{right}/10)")
    worst.sort(key=lambda item: item[0])
    for right, path, frame, rects, reads in worst:
        if len(made) > proofs:
            break
        if graded and path == graded[-1][1]:
            continue
        if rects is None:
            fp.strip_of(frame, path, out)
            made.append(f"{path.stem}-strip.png  (located nothing)")
        else:
            fp.proof(frame, rects, reads, path, out,
                     f"{path.name}   {right}/10 right")
            made.append(f"{path.stem}-proof.png  ({right}/10)")
    print(f"\nPictures -> {out}")
    for line in made:
        print(f"  {line}")
    print("  SEND ME THE BEST ONE FIRST - it is the frame that says "
          "whether the boxes are on the portraits.")
    return 0 if tally["located"] else 1


def main() -> None:
    console.plain_output()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("recording", nargs="?", default="",
                        help="a recordings/<stamp> folder; the NEWEST one "
                             "if you leave it out")
    parser.add_argument("--every", type=int, default=4,
                        help="score one frame in every N (default 4)")
    parser.add_argument("--sweeps", type=int, default=8,
                        help="how many frames to run the full (slow) "
                             "portrait sweep on; the rest reuse what it "
                             "finds, since the bar does not move")
    parser.add_argument("--last", type=int, default=0,
                        help="score only the last N frames - the draft is "
                             "at the END of a recording, since frames "
                             "start when recording does")
    parser.add_argument("--proof", type=int, default=3,
                        help="how many proof sheets to write")
    parser.add_argument("--art", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    # THE NEWEST RECORDING, because that is the one somebody has just
    # made. Asking for the folder meant listing a directory and copying a
    # timestamp across by hand, between finishing a bot match and finding
    # out whether it worked.
    if args.recording:
        folder = Path(args.recording).expanduser()
    else:
        made = sorted((ROOT / "recordings").glob("*/"),
                      key=lambda p: p.stat().st_mtime)
        made = [p for p in made if (p / "frames").is_dir()]
        if not made:
            raise SystemExit(
                f"No recordings with frames in {ROOT / 'recordings'}.\n"
                "Play a bot match with the app open - it records the draft "
                "by itself - then run this again.")
        folder = made[-1]
        print(f"scoring the newest recording: {folder.name}")
    if not folder.is_dir():
        raise SystemExit(f"Not a folder: {folder}")
    if args.art:
        # The art folder carries its own library and variants, so a test
        # run cannot read or write the real install's.
        library.BASE_DIR = Path(args.art).expanduser()
        library.PORTRAITS_DIR = library.BASE_DIR.parent
        library.VARIANTS_DIR = library.BASE_DIR.parent / "variants"
    out = Path(args.out) if args.out else ROOT / "debug_out" / "scored"
    raise SystemExit(score(folder, args.every, args.proof, out,
                       last=args.last, sweeps=args.sweeps))


if __name__ == "__main__":
    main()

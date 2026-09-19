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


def timeline(states: list[dict]) -> list[tuple[float, str]]:
    """(seconds, game state) for every tick, in order.

    THE PHASE IS LOOKED UP, NOT GUESSED FROM ONE BOUNDARY. The first
    version kept only the moment hero selection ended and called
    everything after it "strategy" - so on a real recording the loading
    screen and PRE_GAME were labelled strategy time too, and the frames
    where the pick bar has gone were compared against the ones where it
    is up. A recording runs through five states and the log names all of
    them.
    """
    out = []
    for row in states:
        name = str(row.get("game_state") or "").replace(
            "DOTA_GAMERULES_STATE_", "")
        if name:
            out.append((float(row.get("at") or 0.0), name))
    out.sort()
    return out


# How long a state may be carried forward past the last tick that named
# it. The log is written every tick while the app is running, so a gap
# means the app stopped hearing from Dota - the match ended, the user
# quit, Dota closed. A few seconds is the feed stuttering; past that,
# nothing knows what is on the screen.
STATE_EXPIRES = 20.0

# The states with a pick bar on the screen, DERIVED from the app's own
# set rather than typed out again - `timeline` strips the
# `DOTA_GAMERULES_STATE_` prefix, so the comparison has to be against
# the short spelling and two hand-written lists would be one of them
# going stale the next time Valve renames a state.
BAR_IS_UP = {name.replace("DOTA_GAMERULES_STATE_", "")
             for name in gsi_state.DRAFTING_STATES}

# What a frame past the end is called. Not a state, on purpose: it is
# the absence of one.
PAST_THE_END = "after the log"


def state_at(marks: list[tuple[float, str]], seconds: float | None) -> str:
    """The game state that was live this many seconds into the session.

    **A STATE EXPIRES, AND NOT HAVING ONE IS WHY A REAL RUN MEASURED
    RUBBISH.** This carried the last named state forward for ever, so a
    recording whose state log stopped at 32 seconds - the user closed
    Dota a few seconds into strategy time, exactly as asked - labelled
    frames taken at 164s, 328s and on to 1149s as STRATEGY_TIME. Seven
    of the eight frames measured were of the Dota menu with no pick bar
    on the screen at all, the search found small bright rectangles in
    them, and the run printed six fractions and a verdict that "the bar
    moves between the two screens".

    Which is this project's oldest fault wearing its best disguise: an
    answer assembled out of our own bookkeeping, printed in the column
    where a measurement goes. The frames were never the problem and
    neither was the recording; the tool asserted a phase it had no
    evidence for.

    So a frame more than `STATE_EXPIRES` past the last tick that named a
    state is `PAST_THE_END`, and `measure_frames` does not measure it.
    """
    if seconds is None or not marks:
        return "?"
    if seconds > marks[-1][0] + STATE_EXPIRES:
        return PAST_THE_END
    name = marks[0][1]
    for at, this in marks:
        if at > seconds:
            break
        name = this
    return name


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
    # WHICH RULE TAKES IT IS THE APP'S ANSWER, NOT THIS TOOL'S.
    # The first version worked it out from the slot counts and printed
    # "IT DECLINES, and the app falls through to splitting the ten in
    # list order" - which is true only when the PAIRS rule declines too,
    # and the very first real recording was the paired case: ten heroes
    # two to a slot, which `_split_by_lane_pairs` handles perfectly well.
    # So the tool told the user the app had flipped a coin when it had
    # not. That is this project's oldest shape of mistake - an answer
    # assembled out of our own rules wearing the clothes of a
    # measurement - inside the tool written to stop it.
    reading = minimap_mod.read_lineups(
        payload, name_to_id, my_id,
        game_state="DOTA_GAMERULES_STATE_STRATEGY_TIME")
    print(f"\n  the rule that decided it: {reading.split_rule or 'none'}")
    print(f"  certain about the sides:  "
          f"{'YES' if reading.sides_certain else 'NO - a coin flip'}")
    if reading.allies:
        print("\n    yours   " + ", ".join(
            dataset.name(h) for h in reading.allies))
        print("    theirs  " + ", ".join(
            dataset.name(h) for h in reading.enemies))
    for note in reading.notes:
        print(f"    note: {note}")

    if len(on_slots) == 2 * team:
        print(f"\n  -> ALL TEN stand on the lane slots, two to a slot. "
              "That is the")
        print("     PAIRED case: your team at the lanes you chose, theirs "
              "at the")
        print("     lanes you predicted. The pairing gives a clean 5-5, and "
              "which")
        print("     HALF of each pair is yours is the part nothing has ever "
              "settled.")
    elif len(on_slots) == team and len(in_world) + len(at_origin) == team:
        print("\n  -> five on the slots and five off them: the "
              "strategy-slot rule")
        print("     fits, and it cannot invert. This one is decided.")
    elif at_origin:
        print(f"\n  -> {len(on_slots)} on the slots and {len(at_origin)} at "
              "the origin - a")
        print("     team-mate who chose no lane. The strategy-slot rule "
              "wants exactly")
        print(f"     {team} on, so it declines. A hero at the origin is "
              "almost")
        print("     certainly YOURS: the strategy screen has nothing to "
              "draw the")
        print("     enemy from unless you predicted them.")

    ten = [hid for _i, hid, _n in
           (on_slots + at_origin + in_world) if hid is not None]
    return ten[:2 * team] if len(ten) >= 2 * team else []


def measure_frames(folder: Path, ten: list[int], count: int,
                   marks: list[tuple[float, str]]) -> list[dict]:
    """Search each sampled frame for the ten, and measure what it finds."""
    frames = sorted((folder / "frames").glob("*.png"))
    if not frames:
        print("\n  no frames in this recording - nothing to measure.")
        return []
    ages = frame_seconds(frames)
    # **ONLY FRAMES WITH A PICK BAR ON THEM.** This used to spread its
    # sample across the WHOLE recording, and a recording is a session
    # rather than a draft: 600 frames over twenty minutes, of which the
    # draft is the first dozen. Seven of eight frames in a real run were
    # of the menu, the search found something in each, and the tool
    # printed six fractions measured off them.
    #
    # `BAR_IS_UP` is the app's own answer to "is the pick bar up",
    # so it is the one asked here too - spelled once, in `gsi.state`,
    # rather than as a list of names this tool keeps in step by hand.
    on_the_bar = [f for f in frames
                  if state_at(marks, ages.get(f)) in BAR_IS_UP]
    if not on_the_bar:
        seen = sorted({state_at(marks, ages.get(f)) for f in frames})
        print("\n  NOT ONE FRAME was taken while the pick bar was up.")
        print(f"  The frames here are: {', '.join(seen)}.")
        print("  A recording is a SESSION, not a draft - if the app kept")
        print("  running after the game ended, most of its frames are of")
        print("  the menu. Record again and stop it once the draft is")
        print("  over, or check that the game feed was live while you")
        print("  were picking.")
        return []
    if len(on_the_bar) < len(frames):
        print(f"\n  {len(on_the_bar)} of {len(frames)} frames were taken "
              "while the pick bar was up;")
        print("  the rest are menu or post-game and are not measured.")
    frames = on_the_bar
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
        phase = state_at(marks, age)
        rows.append({
            "size": (width, height),
            "name": path.name, "phase": phase, "age": age,
            "size": (width, height), "found": len(found),
            "layout": fitted.layout, "note": fitted.note,
            "matched": getattr(placed, "matched", 0),
            "boxes_ok": bool(getattr(placed, "ok", False)),
        })
    return rows


# How far the frames of ONE recording may disagree before a table row is
# refused. Much tighter than `AGREE_WITHIN`, and deliberately: that one
# compares readings taken on DIFFERENT displays, where the notes already
# record a real 0.005-0.007 step between aspect groups. Every frame here
# is the same display in the same match, so anything past a few
# ten-thousandths is a bad fit rather than a difference.
# The fewest hero-selection frames that may name a verdict. A median of
# one is that one frame, which is how `find_portraits._vertical` came to
# refuse a ranking below its own floor.
MIN_PICKING = 2

ROW_AGREE = 0.004


# What the window chrome added to the captured buffer, measured on three
# displays from three real recordings: 1366x768 came back 1375x800,
# 1920x1080 came back 1929x1112, 3440x1440 came back 3449x1472.
CHROME = (9, 32)


def looks_padded(width: int, height: int) -> bool:
    """Was this frame the WINDOW rather than the client area?

    **AN ODD WIDTH IS NOT A DISPLAY RESOLUTION.** Every mode a monitor
    has ever offered is even in both axes, so an odd one is arithmetic
    that happened to something - and all three padded recordings came
    back odd (1375, 1929, 3449) while every clean one is even. That is a
    fact about the number rather than a guess about the cause, which is
    what makes it safe to refuse a row on.

    The app crops to the client area now (`CaptureSession._crop_to_
    client`), so this only ever fires on a recording made before that.
    """
    return bool(width % 2 or height % 2)


def say_padded(width: int, height: int) -> None:
    """Refuse the row, and say what the frame really was."""
    guess = (width - CHROME[0], height - CHROME[1])
    print(f"  NO ROW. {width}x{height} is not a display resolution - an "
          "odd width or")
    print("  height is arithmetic that happened to the frame, and what "
          "happened")
    print("  is that the capture handed back the WINDOW rather than its "
          "client")
    print("  area. Every fraction above is therefore divided by a number "
          "that is")
    print("  a couple of per cent too big, and the aspect is wrong too, "
          "which on")
    print("  some displays picks the wrong row of the shipped table "
          "outright.")
    if guess[0] % 2 == 0 and guess[1] % 2 == 0:
        print(f"\n  Less the {CHROME[0]}x{CHROME[1]} of window chrome "
              f"measured on three real")
        print(f"  displays, this was probably {guess[0]}x{guess[1]}.")
    print("\n  The app crops to the client area now. Record this draft "
          "again and")
    print("  the frame size will be the one Dota is running at.")


def say_row(rows: list[dict]) -> None:
    """Print the line to paste into `vision/measured.py`'s `EXACT`.

    **ALL TEN OR THE FRAME DOES NOT VOTE**, the same rule
    `_remember_measured_layout` and `bugreport.repair` already follow:
    `autocal.layout_from` reads a bank's origin off the FIRST portrait it
    finds in that bank, so a single missed leading portrait shifts that
    whole bank by one pitch and every box after it. Nine located is
    enough to answer whose five is whose; it takes ten to answer where
    the boxes go, and this row is a number every install of this app
    inherits.

    `radiant_x` is not emitted. The bar is centred on the HUD span, and
    the mirror of the right bank lands within 1 to 4 pixels of the
    measured left origin on every frame that has ever located ten -
    while measuring it directly is the one reading with that missed-
    portrait failure in it. `measured.Reading` derives it.
    """
    print("\n\n=== A ROW FOR THE SHIPPED TABLE ===\n")
    ten = [row for row in rows
           if row["layout"] is not None and row["found"] == 10]
    if not ten:
        located = max((row["found"] for row in rows), default=0)
        print(f"  NO ROW. The best frame located {located} of 10 portraits, "
              "and a row")
        print("  needs all ten - a missed portrait at the start of a bank "
              "moves that")
        print("  whole bank by one pitch and nothing says which.")
        return

    sizes = {row["size"] for row in ten}
    if len(sizes) != 1:
        named = ", ".join(f"{w}x{h}" for w, h in sorted(sizes))
        print(f"  NO ROW. These frames are {named} - one recording has to "
              "be one")
        print("  display, or the row would name a resolution it did not "
              "measure.")
        return
    width, height = sizes.pop()
    if looks_padded(width, height):
        say_padded(width, height)
        return

    values = {name: [getattr(row["layout"], name) for row in ten]
              for name in FRACTIONS}
    apart = {name: max(vals) - min(vals) for name, vals in values.items()
             if name != "radiant_x"}
    loose = {name: gap for name, gap in apart.items() if gap > ROW_AGREE}
    if loose:
        print(f"  NO ROW. {len(ten)} frame(s) of {width}x{height}, and "
              "they disagree:")
        for name, gap in sorted(loose.items()):
            print(f"    {name:<11} spread {gap:.4f}   "
                  f"(at most {ROW_AGREE:.4f})")
        print("  That is a bad fit on at least one frame, not a property "
              "of the")
        print("  display. Re-run with more frames, or record another draft.")
        return

    median = {name: statistics.median(vals) for name, vals in values.items()}
    print(f"  {len(ten)} frame(s) of {width}x{height} located all ten and "
          f"agree to")
    print(f"  {max(apart.values()):.4f}. Paste this into EXACT in "
          "draft_assist/vision/measured.py:\n")
    print(f"    ({width}, {height}): Reading(")
    for name in ("dire_x", "y", "slot_w", "slot_h", "pitch"):
        print(f"        {name}={median[name]:.4f},")
    print(f'        source="bot draft at {width}x{height}",')
    print(f"        frames={len(ten)},")
    print("    ),")
    mirrored = 1.0 - (median["dire_x"] + 4 * median["pitch"]
                      + median["slot_w"])
    print(f"\n  (radiant_x is derived as {mirrored:.4f}; this recording "
          f"measured it")
    print(f"  at {statistics.median(values['radiant_x']):.4f}, and the two "
          "should be within a")
    print("  few pixels of each other. A big gap means a bank's leading "
          "portrait")
    print("  was missed on some frame.)")


def say_bar(rows: list[dict]) -> None:
    print("\n\n=== WHERE THE PICK BAR REALLY IS ===\n")
    if not rows:
        print("  nothing measured.")
        return

    print(f"  {'frame':<12}{'phase':<18}{'at':>7}{'found':>7}"
          f"{'boxes':>8}   measured y / slot_h")
    for row in rows:
        age = f"{row['age']:.0f}s" if row["age"] is not None else "-"
        layout = row["layout"]
        measured = (f"{layout.y:.4f} / {layout.slot_h:.4f}"
                    if layout is not None else f"-  ({row['note']})")
        print(f"  {row['name']:<12}{row['phase']:<18}{age:>7}"
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

    picking = [r for r in good if r["phase"] == "HERO_SELECTION"]
    strategy = [r for r in good if r["phase"] == "STRATEGY_TIME"]
    print("\n  DOES THE BAR MOVE BETWEEN THE TWO SCREENS?\n")
    if picking and strategy:
        fits = {}
        for name in ("y", "slot_h"):
            a = statistics.median(
                [getattr(r["layout"], name) for r in picking])
            b = statistics.median(
                [getattr(r["layout"], name) for r in strategy])
            fits[name] = (a, b)
            verdict = ("the same place" if abs(a - b) <= AGREE_WITHIN
                       else "DIFFERENT - the bar moves")
            print(f"    {name:<8} picking {a:.4f}   strategy {b:.4f}   "
                  f"-> {verdict}")
        # **A SMALLER PORTRAIT IS A DIFFERENT ROW OF ARTWORK, NOT A BAR
        # THAT HAS MOVED**, and without this the tool told a real user
        # "the bar moves" off a single frame taken at second zero.
        #
        # The CHOOSE YOUR HERO grid is on screen throughout hero
        # selection and is full of hero portraits, so a frame whose own
        # pick bar is still empty has something else for the search to
        # lock onto - which is the failure `bar_shape` exists to refuse
        # and has let through before. Both real cases read `slot_h`
        # around 0.0435 against 0.0611 at strategy time: a THIRD smaller.
        #
        # A bar that had genuinely moved would still be the pick bar, so
        # its portraits would still be the same size. `y` alone differing
        # is evidence; `slot_h` differing with it says the two frames did
        # not fit the same artwork, and then nothing here is comparable.
        # **AND FRAMES THAT DISAGREE WITH EACH OTHER HAVE NO MEDIAN.**
        # A 1280x1024 recording read `y` at 0.1023, 0.1023, 0.1065 and
        # 0.0743 across its four hero-selection frames - a spread of
        # 0.032 against a tolerance of 0.01 - and the tool took the
        # middle of them and announced that the bar had moved. Four
        # frames of one screen a few seconds apart cannot legitimately
        # disagree by that much, so what they fitted was not one thing,
        # and a median over them is not a measurement of anything.
        spread = max(getattr(r["layout"], "y") for r in picking) - min(
            getattr(r["layout"], "y") for r in picking)
        y_apart = abs(fits["y"][0] - fits["y"][1]) > AGREE_WITHIN
        size_apart = abs(fits["slot_h"][0] - fits["slot_h"][1]) > AGREE_WITHIN
        if y_apart and spread > AGREE_WITHIN:
            print(f"\n    IGNORE BOTH LINES. The {len(picking)} "
                  "hero-selection frames do not agree")
            print(f"    with EACH OTHER - `y` spreads {spread:.4f} across "
                  f"them against a")
            print(f"    tolerance of {AGREE_WITHIN:.4f} - so they did not "
                  "all fit the same")
            print("    thing and their median measures nothing. The boxes "
                  "below are the")
            print("    half of this that does not need a fit at all.")
        elif y_apart and size_apart:
            print("\n    IGNORE BOTH LINES. The portraits are a different "
                  "SIZE on the two")
            print("    screens, and a bar that had merely moved would "
                  "still be the pick")
            print("    bar - so these frames did not fit the same artwork. "
                  "A pick bar")
            print("    that is still empty leaves the search the CHOOSE "
                  "YOUR HERO grid")
            print("    to lock onto, which is smaller and lower. The boxes "
                  "below are")
            print("    the half of this that does not need a fit at all.")
        elif len(picking) < MIN_PICKING:
            print(f"\n    Read with care: {len(picking)} hero-selection "
                  "frame(s) located, and a")
            print(f"    median of fewer than {MIN_PICKING} is that frame "
                  "rather than a measurement.")
    else:
        have = f"{len(picking)} while picking, {len(strategy)} at strategy"
        print(f"    not from the fitted layouts - {have} located well")
        print("    enough to measure. The boxes below answer it instead.")

    # THE BOXES ANSWER IT WHERE THE FITTED LAYOUTS CANNOT, and on the
    # first real recording they are the only half that did.
    #
    # `read_placed` scores the ten CALIBRATED crop boxes against the ten
    # heroes the game named at strategy time - so a box landing on a
    # portrait during HERO SELECTION is direct evidence that the boxes
    # are on the hero-selection bar, whatever the search made of that
    # frame. It needs no second phase to compare against and no fit at
    # all, which is why it survives frames the search declines.
    #
    # ONLY THE BEST COUNT MEANS ANYTHING. Early in the draft most slots
    # are still empty, so a box over an empty slot correctly matches
    # nothing: the count RISES as the picks land, and it is the top of
    # that climb that says whether the geometry is right.
    picked_rows = [r for r in rows if r["phase"] == "HERO_SELECTION"]
    print("\n  DO THE CROP BOXES LAND DURING HERO SELECTION?\n")
    if not picked_rows:
        print("    no hero-selection frames in this recording.")
        return
    climb = " -> ".join(f"{r['matched']}" for r in picked_rows)
    best = max(r["matched"] for r in picked_rows)
    print(f"    boxes holding a named hero, over the draft:  {climb}  "
          "of 10")
    if best >= lineup_mod.BOXES_PROVE_THE_GEOMETRY:
        print(f"\n    {best} of the ten boxes landed on a portrait while "
              "you were still")
        print("    picking. A whole bank's worth is not something a wrong "
              "geometry")
        print("    does by accident - the boxes are one rigid set at one "
              "pitch - so")
        print("    THE BAR IS IN THE SAME PLACE ON BOTH SCREENS, and this "
              "machine's")
        print("    calibration is right for hero selection as well as for "
              "strategy.")
    else:
        print(f"\n    only {best} of the ten ever landed. Either the boxes "
              "are wrong for")
        print("    this screen, or the draft never filled up in the frames "
              "sampled.")


def main() -> None:
    console.plain_output()
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", help="a folder under recordings/")
    parser.add_argument("--frames", type=int, default=DEFAULT_FRAMES,
                        help=f"how many frames to measure "
                             f"(default {DEFAULT_FRAMES}; seconds each)")
    parser.add_argument(
        "--row", action="store_true",
        help="also print a line to paste into vision/measured.py's EXACT, "
             "so this resolution is right on a fresh install's FIRST draft")
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
    marks = timeline(states)
    if not any(name == "HERO_SELECTION" for _at, name in marks):
        print("  NOTE: no HERO_SELECTION tick in the state log, so frames "
              "cannot be")
        print("        told apart by phase. Record from before the draft "
              "starts.")
    else:
        spans = []
        for name in ("HERO_SELECTION", "STRATEGY_TIME"):
            times = [at for at, this in marks if this == name]
            if times:
                spans.append(f"{name} {min(times):.0f}-{max(times):.0f}s")
        print("  phases   " + "   ".join(spans))

    dataset = store.load()
    ten = say_teams(strategy_payload(folder), dataset)
    if not ten:
        print("\n  without the ten heroes the game named, the pick bar "
              "cannot be measured.")
        return
    rows = measure_frames(folder, ten, args.frames, marks)
    say_bar(rows)
    if args.row:
        say_row(rows)
    print("\nNothing was written. This tool only reads.")


if __name__ == "__main__":
    main()

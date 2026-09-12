"""Find the ten draft portraits in a frame BY RECOGNISING THEM.

WHY THIS NO LONGER FITS EDGES. The first two versions looked for the
only periodic feature a pick bar has - the seams between portraits - and
fitted (start, pitch, width) against the column edge profile, the way
`autocal.measure_bank` does inside a rectangle the user has drawn. Swept
over a whole frame with nothing pinning it, that method has one failure
it cannot avoid, and every one of the user's 23 screenshots hit it:

    CHOOSE HERO      DARK WI[LLOW]      ENTERING BATTLE      LION

It locks onto TEXT. Letters are the strongest regularly spaced vertical
edges on the screen by a wide margin - stronger than any seam between
two portraits - and a row of words has near-uniform letter spacing, so
it satisfies a pitch fit better than the thing being looked for. Every
frame reported the bar between 12% and 17% down the window, which is a
line of interface text, and not one of them ever looked at the top.
Tightening the slot-to-pitch ratio did not help and could not: the fault
is that an edge profile cannot tell a letter from a portrait.

SO IT MATCHES THE ARTWORK. Valve's own portrait for every hero is
already on disk (`assets/portraits/base/`, downloaded by
`build_library`), so the question becomes "where in this frame is a hero
portrait", which the word LION cannot answer yes to. It sweeps a range
of sizes, matches all 126 heroes at each, and keeps the size that yields
the most distinct confident hits - the right size gives about ten in two
banks and every wrong size gives noise.

It differs from `autocal.locate` in the two ways that matter here.
`locate` sizes its search against the 16:9 HUD BOX, which is the model
being tested, so this works in fractions of the WINDOW; and `find_scale`
probes with `list(greys)[:2]`, two ARBITRARY heroes - fine in the live
path, where the probes are heroes the minimap has just named, and wrong
here, where nothing says those two are in the picture at all.

IT SHOWS ITS WORK, which is the whole point: "I'm expecting you to show
me snippets of what you think the 10 portraits are in each snippet."

    python tools/find_portraits.py <folder> [--out DIR] [--json FILE]

The annotated pictures ARE Valve's artwork, like the screenshots they
come from. Attach them, never commit them.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from draft_assist import console                     # noqa: E402
from draft_assist.vision import autocal              # noqa: E402
from draft_assist.vision import library              # noqa: E402
from draft_assist.vision.layout import hud_box       # noqa: E402

SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
WORK_WIDTH = 960          # the hunt runs on a picture this wide
# THE BAR IS AT THE TOP OF THE WINDOW - "no, heroes are always at the
# top" - and of the WINDOW rather than of the 16:9 HUD box, since the box
# is the model under suspicion. A third is generous; every frame measured
# so far puts the whole bar inside the top 15%.
TOP_REACH = 0.33
# A portrait's width as a share of the WINDOW's width. Wide, because the
# whole question is what this actually is on each aspect ratio.
WIDTH_FRACS = tuple(round(0.022 + 0.004 * i, 4) for i in range(24))
PORTRAIT_ASPECT = autocal.PORTRAIT_ASPECT
# How well a portrait must match before it counts as found. Higher than
# `autocal.MIN_SCORE` (0.35) on purpose: that one is applied when the ten
# heroes are already KNOWN, so a weak best-of-ten is still informative.
# Here 126 templates are swept against a frame that holds ten of them, so
# 116 of every 126 matches are wrong by construction and the floor is
# what keeps them out.
HIT_FLOOR = 0.45
MIN_HITS = 4              # fewer than this is not a pick bar


def read_image(path: Path):
    """Decode from bytes - `cv2.imread` cannot open a path carrying the
    multiplication sign the Snipping Tool puts in its filenames."""
    try:
        data = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    except OSError:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def load_art() -> dict[int, "np.ndarray"]:
    """Every base portrait on disk, in grey, keyed by hero id."""
    out = {}
    for path in sorted(library.BASE_DIR.glob("*.png")):
        match = re.match(r"(\d+)_", path.name)
        if not match:
            continue
        image = read_image(path)
        if image is None or not image.size:
            continue
        out[int(match.group(1))] = autocal._grey(image)
    return out


def _one_row(hits, apart: int):
    """The single best ROW of hits, strongest first, one per position.

    Two constraints, and both are facts about a pick bar rather than
    tuning. Ten portraits stand on ONE line, so hits at different heights
    are not ten heroes, they are one hero matched well and nine matched
    somewhere else; the row carrying the most distinct heroes wins. And
    two heroes cannot occupy the same place, so a second template landing
    on one already kept is that same portrait matched by the wrong hero -
    which is the normal case when 126 templates are swept over a frame
    holding ten of them.

    An earlier version suppressed on x OR y, which let a hit at the same
    x and a different y through as a separate hero and reported thirteen
    portraits in a bar of ten.
    """
    if not hits:
        return []
    tolerance = max(2, int(apart * 0.15))
    best = None
    for anchor in sorted({hit[2] for hit in hits}):
        kept = []
        for hit in sorted(hits, reverse=True):
            if abs(hit[2] - anchor) > tolerance:
                continue
            if all(abs(hit[1] - other[1]) >= apart * 0.7 for other in kept):
                kept.append(hit)
        rank = (len(kept), sum(hit[0] for hit in kept))
        if best is None or rank > best[0]:
            best = (rank, kept)
    return best[1] if best else []


def hunt(grey, art: dict, note=None):
    """(slot_w, slot_h, hits) in this picture's own pixels, or None.

    One sweep of every hero at every candidate SIZE. The size is what is
    really being searched for: portraits are all one size on screen, so
    the right one produces about ten confident hits standing apart from
    each other and every wrong one produces a handful of accidents. That
    count is the discriminator, and it is why this cannot be fooled by a
    line of text the way an edge fit is - a word does not correlate with
    Lion's portrait however evenly its letters are spaced.
    """
    rows, width = grey.shape[:2]
    band = grey[:max(16, int(rows * TOP_REACH))]
    shrink = max(1.0, width / WORK_WIDTH)
    small = cv2.resize(band, (int(width / shrink),
                              max(1, int(band.shape[0] / shrink))),
                       interpolation=cv2.INTER_AREA) if shrink > 1 else band

    best = None
    for frac in WIDTH_FRACS:
        box_w = int(round(frac * small.shape[1]))
        box_h = int(round(box_w / PORTRAIT_ASPECT))
        if box_w < 10 or box_h < 8 or box_h >= small.shape[0]:
            continue
        hits = []
        for hero_id, template in art.items():
            found = autocal._best_at(small, template, box_w, box_h)
            if found is None:
                continue
            score, (x, y) = found
            if score >= HIT_FLOOR:
                hits.append((score, x, y, hero_id))
        keep = _one_row(hits, box_w)
        if note is not None and keep:
            note(f"    {frac:.3f}  box {box_w}x{box_h}  {len(keep)} hit(s)")
        if len(keep) < MIN_HITS:
            continue
        # MOST HITS WINS, and the total score only breaks a tie. A size
        # one pixel out still matches a few heroes very well; what it
        # cannot do is match ten of them.
        rank = (len(keep), sum(hit[0] for hit in keep))
        if best is None or rank > best[0]:
            best = (rank, box_w, box_h, keep)
    if best is None:
        return None
    _rank, box_w, box_h, keep = best

    # THE COARSE GRID ONLY HAS TO FIND THE NEIGHBOURHOOD. Its step is
    # 0.4% of the window, which is five pixels at 1280 wide - enough to
    # report an 80px portrait as 75. So the size is walked a pixel at a
    # time at FULL resolution, on the hero that matched best, exactly as
    # `autocal.find_scale` does after its own decimated pass.
    scale = width / float(small.shape[1])
    full_w = max(10, int(round(box_w * scale)))
    full_h = max(8, int(round(box_h * scale)))
    anchor = max(keep)[3]
    full_w, full_h, _score = autocal._refine(
        band, art[anchor], full_w, full_h, reach=max(3, int(scale) + 2))

    # And the positions are re-read at that exact size, for the heroes
    # already known to be there - ten matches rather than another sweep.
    exact = []
    for _s, _x, _y, hero_id in keep:
        hit = autocal._best_at(band, art[hero_id], full_w, full_h)
        if hit is None or hit[0] < HIT_FLOOR:
            continue
        exact.append((hit[0], hit[1][0], hit[1][1], hero_id))
    exact = _one_row(exact, full_w)
    if len(exact) < MIN_HITS:
        return None
    return full_w, full_h, exact


def banks_from(hits, slot_w: int):
    """(radiant_x, dire_x, pitch, top) from where the heroes were found.

    A pick bar is two banks of five, so the ten x positions hold one gap
    far bigger than the rest - the space between the teams - and that is
    where they split. Pitch is the MEDIAN step inside a bank rather than
    the mean: a missing hero leaves a double-width step, and a median
    over the rest is unmoved by it where a mean is dragged out.
    """
    xs = sorted(hit[1] for hit in hits)
    if len(xs) < MIN_HITS:
        return None
    steps = [b - a for a, b in zip(xs, xs[1:])]
    if not steps:
        return None
    split = steps.index(max(steps)) + 1
    if not (2 <= split <= len(xs) - 2):
        return None
    left, right = xs[:split], xs[split:]
    within = [b - a for bank in (left, right)
              for a, b in zip(bank, bank[1:])]
    if not within:
        return None
    # A GAP OF TWO SLOTS IS STILL ONE PITCH. Heroes the sweep missed
    # leave a step that is a whole multiple of the pitch, so each step is
    # divided by how many pitches it plausibly spans before the median.
    unit = min(within)
    singles = [step / max(1, round(step / unit)) for step in within]
    pitch = float(np.median(singles))
    if pitch <= 0:
        return None
    top = int(round(float(np.median([hit[2] for hit in hits]))))
    return int(left[0]), int(right[0]), int(round(pitch)), top


def boxes_of(radiant_x: int, dire_x: int, pitch: int, slot_w: int,
             top: int, slot_h: int) -> list:
    """The ten rectangles: five from each bank's own measured start.

    NOT MIRRORED about the centre any more. Mirroring was the edge fit's
    own assumption - it searched for a start and reflected it, so the two
    banks could not disagree and a fit that was wrong was wrong twice
    symmetrically. Here each bank is found independently, and letting
    them differ is what makes a lopsided result visible instead of tidy.
    """
    out = [(radiant_x + i * pitch, top, slot_w, slot_h)
           for i in range(autocal.TEAM_SIZE)]
    out += [(dire_x + i * pitch, top, slot_w, slot_h)
            for i in range(autocal.TEAM_SIZE)]
    return out


def measure(path: Path, into: Path, art: dict, loud=False) -> dict:
    frame = read_image(path)
    if frame is None:
        return {"file": path.name, "why": "not an image this build can read"}
    height, width = frame.shape[:2]
    row = {"file": path.name, "w": width, "h": height,
           "aspect": round(width / height, 4)}

    note = (lambda line: print(line, flush=True)) if loud else None
    found = hunt(autocal._grey(frame), art, note=note)
    if found is None:
        row["why"] = (f"no hero portrait recognised in the top "
                      f"{TOP_REACH:.0%} of this frame")
        return row
    slot_w, slot_h, hits = found

    banks = banks_from(hits, slot_w)
    if banks is None:
        row["why"] = (f"recognised {len(hits)} portrait(s) but they do not "
                      "fall into two banks")
        row["heroes"] = len(hits)
        return row
    radiant_x, dire_x, pitch, top = banks

    rects = boxes_of(radiant_x, dire_x, pitch, slot_w, top, slot_h)
    left, span = hud_box(width, height)
    row.update({
        "heroes": len(hits),
        "bar_top_px": top, "slot_h_px": slot_h,
        "radiant_x_px": radiant_x, "dire_x_px": dire_x,
        "slot_w_px": slot_w, "pitch_px": pitch,
        # BOTH READINGS, so the model can be derived rather than assumed.
        "x_of_width": round(radiant_x / width, 5),
        "x_of_hudbox": round((radiant_x - left) / span, 5) if span else None,
        "pitch_of_width": round(pitch / width, 5),
        "pitch_of_hudbox": round(pitch / span, 5) if span else None,
        "slot_w_of_hudbox": round(slot_w / span, 5) if span else None,
        "y_of_window": round(top / height, 5),
        "y_of_hudbox": round(top / (span / (16 / 9)), 5) if span else None,
        "slot_h_of_window": round(slot_h / height, 5),
        "boxes": rects,
    })
    draw(frame, rects, path, into)
    slices(frame, rects, path, into)
    return row


def slices(frame, rects, path: Path, into: Path) -> None:
    """The TEN CROPS, side by side and enlarged, exactly as cut.

    At the user's request: "I want you to show me snippets of what each
    portrait looks like according to where the image recognition engine
    thinks the portraits are."

    This is the check that matters and the one a box drawn on a wide
    screenshot cannot give. A fit that is half a portrait out still draws
    a tidy row of rectangles at a glance; cut the crops out and stand
    them next to each other and it is obvious at once, because every one
    of them is half a hero and half the gap.

    Numbered 1 to 10, left bank first, on the order they are cut in - so
    a crop that is empty or doubled names its own slot.
    """
    tall = 120
    tiles = []
    for x, y, w, h in rects:
        crop = frame[max(0, y):y + h, max(0, x):x + w]
        if crop.size == 0:
            crop = np.zeros((max(1, h), max(1, w), 3), np.uint8)
        factor = tall / max(1, crop.shape[0])
        tiles.append(cv2.resize(
            crop, (max(1, int(crop.shape[1] * factor)), tall),
            interpolation=cv2.INTER_NEAREST))

    gap = 6
    width = sum(t.shape[1] for t in tiles) + gap * (len(tiles) + 1)
    sheet = np.full((tall + 34 + gap * 2, width, 3), 24, np.uint8)
    at = gap
    for index, tile in enumerate(tiles):
        sheet[gap:gap + tall, at:at + tile.shape[1]] = tile
        # GREEN FOR THE LEFT BANK, RED FOR THE RIGHT, the same two
        # colours the boxes are drawn in, so the two pictures can be read
        # against each other without a legend.
        colour = (90, 220, 90) if index < 5 else (80, 80, 240)
        cv2.putText(sheet, str(index + 1), (at + 4, tall + gap + 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, colour, 2, cv2.LINE_AA)
        at += tile.shape[1] + gap
    into.mkdir(parents=True, exist_ok=True)
    ok, buffer = cv2.imencode(".png", sheet)
    if ok:
        (into / f"{path.stem}-slices.png").write_bytes(buffer.tobytes())


def draw(frame, rects, path: Path, into: Path) -> None:
    """The ten boxes, over the picture, cropped to the bar and its
    surroundings so the file is small enough to attach."""
    height, width = frame.shape[:2]
    shot = frame.copy()
    for index, (x, y, w, h) in enumerate(rects):
        colour = (90, 220, 90) if index < 5 else (80, 80, 240)
        cv2.rectangle(shot, (x, y), (x + w, y + h), colour, 2)
        cv2.putText(shot, str(index + 1), (x + 3, y + h - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 1, cv2.LINE_AA)
    top = max(0, min(r[1] for r in rects) - 60)
    bottom = min(height, max(r[1] + r[3] for r in rects) + 60)
    shot = shot[top:bottom]
    if shot.shape[1] > 1400:
        factor = 1400 / shot.shape[1]
        shot = cv2.resize(shot, (1400, max(1, int(shot.shape[0] * factor))),
                          interpolation=cv2.INTER_AREA)
    into.mkdir(parents=True, exist_ok=True)
    ok, buffer = cv2.imencode(".png", shot)
    if ok:
        (into / f"{path.stem}-found.png").write_bytes(buffer.tobytes())


def main() -> None:
    console.plain_output()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("folder")
    parser.add_argument("--out", default=str(ROOT / "debug_out" / "found"))
    parser.add_argument("--json", default="")
    parser.add_argument("--skip", default="",
                        help="comma-separated names already done, or a "
                             "filename to resume AFTER")
    parser.add_argument("--only", default="",
                        help="comma-separated names to do and nothing else")
    parser.add_argument("--loud", action="store_true",
                        help="print every size tried and what it matched")
    args = parser.parse_args()

    folder = Path(args.folder).expanduser()
    if not folder.is_dir():
        raise SystemExit(f"Not a folder: {folder}")
    shots = sorted(p for p in folder.iterdir()
                   if p.suffix.lower() in SUFFIXES)
    if not shots:
        raise SystemExit(f"No images in {folder}")

    # RESUMING IS THE NORMAL CASE, not an edge one. A run is minutes
    # long and a console is one Ctrl+C away from losing all of it, so
    # there has to be a way back in that does not redo what is done.
    if args.only:
        want = {n.strip().lower() for n in args.only.split(",") if n.strip()}
        shots = [p for p in shots if p.name.lower() in want]
    elif args.skip:
        marks = [n.strip().lower() for n in args.skip.split(",") if n.strip()]
        names = [p.name.lower() for p in shots]
        if len(marks) == 1 and marks[0] in names:
            shots = shots[names.index(marks[0]) + 1:]   # resume AFTER it
        else:
            shots = [p for p in shots if p.name.lower() not in set(marks)]

    # THE ARTWORK IS THE METHOD, so its absence is refused rather than
    # worked around. Without it this tool has nothing to recognise and
    # would fall back to guessing, which is what the edge fit was.
    art = load_art()
    if len(art) < 50:
        raise SystemExit(
            f"Only {len(art)} hero portrait(s) in {library.BASE_DIR}.\n"
            "This tool RECOGNISES the portraits, so it needs them on disk.\n"
            "Open the app and run Settings > Downloads > All artwork, then "
            "try again.")

    into = Path(args.out)
    print(f"{len(art)} hero portraits loaded")
    print(f"{len(shots)} picture(s) to do in {folder}\n")
    head = ("file", "WxH", "aspect", "seen", "bar top", "slot h", "rad x",
            "dire x", "slot w", "pitch", "x/hud", "w/hud", "pitch/hud",
            "y/win")
    widths = (24, 11, 7, 5, 8, 7, 7, 7, 7, 6, 8, 8, 9, 8)
    print("  ".join(h.ljust(w) for h, w in zip(head, widths)))
    print("-" * (sum(widths) + 2 * len(widths)))

    rows = []
    for number, shot in enumerate(shots, 1):
        # SAY WHICH ONE IT IS ON. The first version printed only
        # finished rows, so a minute of work per picture was
        # indistinguishable from a hang - "is it loading, or is it an
        # empty table?" - and the honest answer took a stopwatch.
        print(f"[{number}/{len(shots)}] {shot.name} ...",
              end="", flush=True)
        row = measure(shot, into, art, loud=args.loud)
        print("\r" + " " * 60 + "\r", end="", flush=True)
        rows.append(row)
        if "why" in row:
            print(f"{row['file'][:24].ljust(24)}  "
                  f"{row.get('w','?')}x{row.get('h','?')}   -- {row['why']}",
                  flush=True)
            continue
        cells = (row["file"][:24], f"{row['w']}x{row['h']}",
                 f"{row['aspect']:.3f}", row["heroes"], row["bar_top_px"],
                 row["slot_h_px"], row["radiant_x_px"], row["dire_x_px"],
                 row["slot_w_px"], row["pitch_px"],
                 f"{row['x_of_hudbox']:.5f}", f"{row['slot_w_of_hudbox']:.5f}",
                 f"{row['pitch_of_hudbox']:.5f}",
                 f"{row['y_of_window']:.5f}")
        print("  ".join(str(c).ljust(w) for c, w in zip(cells, widths)),
              flush=True)

    good = [r for r in rows if "why" not in r]
    print(f"\n{len(good)} of {len(rows)} located.")
    for key in ("x_of_width", "x_of_hudbox", "slot_w_of_hudbox",
                "pitch_of_hudbox", "y_of_window", "y_of_hudbox",
                "slot_h_of_window"):
        values = [r[key] for r in good if r.get(key) is not None]
        if values:
            print(f"  {key:<18} {min(values):.5f} to {max(values):.5f}"
                  f"   spread {max(values) - min(values):.5f}")
    print(f"\nPictures -> {into}")
    print("  <name>-found.png   the ten boxes drawn on the frame")
    print("  <name>-slices.png  the ten crops, side by side, enlarged")
    print("CHECK THE SLICES. A fit half a portrait out still draws a tidy "
          "row of boxes; cut the crops out and it is obvious at once.")
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1),
                                   encoding="utf-8")


if __name__ == "__main__":
    main()

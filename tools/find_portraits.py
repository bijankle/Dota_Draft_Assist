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
from draft_assist.vision import recognize            # noqa: E402
from draft_assist.vision.layout import hud_box       # noqa: E402

SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
WORK_WIDTH = 960          # the hunt runs on a picture this wide
# THE BAR IS AT THE TOP OF THE WINDOW - "no, heroes are always at the
# top" - and of the WINDOW rather than of the 16:9 HUD box, since the box
# is the model under suspicion. A third is generous; every frame measured
# so far puts the whole bar inside the top 15%.
TOP_REACH = 0.18
# A portrait's width as a share of the WINDOW's width. Wide, because the
# whole question is what this actually is on each aspect ratio.
# MEASURED OFF A REAL STRATEGY SCREEN, not assumed. On a 3440x1440
# client the ten pick-bar portraits are about 90px wide - 0.026 of the
# window - and the old range ran to 0.114, which is 392px. That slack is
# what let the sweep report a "portrait" 343px wide starting at x=-26.
WIDTH_FRACS = tuple(round(0.014 + 0.002 * i, 4) for i in range(24))
# AND THE BAR'S PORTRAITS ARE NOT 16:9. Valve's base art is 256x144, but
# the tile the HUD draws in the pick bar is close to SQUARE - measured
# at roughly 90x97. Assuming the source aspect searched for a box twice
# as wide as the thing on screen. Several are tried because this is one
# measurement from one client, and a wrong constant here cannot be seen
# in the output - it just never finds anything.
ASPECTS = (0.93, 1.33, 16 / 9)
PORTRAIT_ASPECT = autocal.PORTRAIT_ASPECT
HIT_FLOOR = 0.30
MIN_HITS = 4              # fewer than this is not a pick bar
# A BANK IS FIVE. Ten is the whole bar, so a row carrying more than this
# is not a pick bar at all - it is a row of the hero roster, which is the
# single thing most likely to be mistaken for one because every tile in
# it is a real portrait.
MOST_HITS = 2 * autocal.TEAM_SIZE
# MATCH THE MIDDLE OF THE ART, NOT ALL OF IT. Dota draws a frame around
# each portrait in the pick bar, and a template that covers the whole
# picture necessarily overlaps that frame - which is the one kind of HUD
# damage that measurably breaks this. Measured over a strip of ten
# portraits with a border painted on: whole-portrait templates located
# 6 of the 10 slots, centre-76% templates located 10 of 10, and the
# margin between the right hero and the best wrong one went from -0.064
# to +0.120. Costs nothing on an undamaged frame (0.987 against 1.000).
INSET = 0.12


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


def _template(art, inset: float = INSET):
    """The middle of a portrait — see INSET."""
    if inset <= 0:
        return art
    rows, cols = art.shape[:2]
    return art[int(rows * inset):rows - int(rows * inset),
               int(cols * inset):cols - int(cols * inset)]


def _sweep(strip, art: dict, box_w: int, box_h: int):
    """Every hero's best hit at one portrait size, in SLOT coordinates.

    The template covers the middle of the art, so what `matchTemplate`
    returns is where that middle is; the slot's own corner is an inset
    further out. Reporting the inset rectangle as the slot would put
    every box 12% of a portrait down and to the right.
    """
    inner_w = max(8, int(round(box_w * (1 - 2 * INSET))))
    inner_h = max(8, int(round(box_h * (1 - 2 * INSET))))
    back_x = int(round(box_w * INSET))
    back_y = int(round(box_h * INSET))
    hits = []
    for hero_id, whole in art.items():
        found = autocal._best_at(strip, _template(whole), inner_w, inner_h)
        if found is None:
            continue
        score, (x, y) = found
        if score >= HIT_FLOOR:
            hits.append((score, x - back_x, y - back_y, hero_id))
    return hits


def bar_shape(keep, apart: int):
    """Rank a row as a PICK BAR, or refuse it. (hits, score) or None.

    Ranking by "most distinct heroes" is what lost to the hero grid: a
    grid row holds fifteen or twenty real portraits and beats a bar of
    ten on that measure every time, while being just as genuinely made
    of hero art. Counting cannot tell them apart. SHAPE can - a pick bar
    is TWO BANKS OF AT MOST FIVE with a wide gap between the teams, and
    a roster row is one long even run that no split makes five-and-five.

    So the test is the shape, and the count only orders the rows that
    pass it.
    """
    xs = sorted(hit[1] for hit in keep)
    if not (MIN_HITS <= len(xs) <= MOST_HITS):
        return None
    steps = [b - a for a, b in zip(xs, xs[1:])]
    if not steps:
        return None
    split = steps.index(max(steps)) + 1
    left, right = xs[:split], xs[split:]
    if max(len(left), len(right)) > autocal.TEAM_SIZE:
        return None
    # THE GAP BETWEEN THE TEAMS IS THE TELL, and it has to be clear of
    # the ordinary spacing - in an evenly spaced run the biggest step is
    # whatever rounding made largest, which would "split" a grid row
    # anywhere at all.
    others = [step for index, step in enumerate(steps)
              if index != split - 1] or [apart]
    if max(steps) < 1.35 * max(sorted(others)[len(others) // 2], 1):
        return None
    return len(xs), sum(hit[0] for hit in keep)


def hunt(grey, art: dict, note=None):
    """(slot_w, slot_h, hits) in this picture's own pixels, or None.

    One sweep of every hero at every candidate SIZE. The size is what is
    really being searched for: portraits are all one size on screen, so
    the right one produces about ten confident hits standing apart from
    each other and every wrong one produces a handful of accidents. That
    count is the discriminator, and it is why this cannot be fooled by a
    line of text the way an edge fit is - a word does not correlate with
    Lion's portrait however evenly its letters are spaced.

    **WHAT IS BEING ASKED FOR IS GEOMETRY, NOT IDENTITY**, and that is
    why this works at thresholds that would be far too loose for
    recognition. Measured against a strip with a HUD border painted over
    every portrait, whole-portrait templates named the right hero in 0
    of 10 slots and still found 10 of 10 POSITIONS - because the thing a
    wrong hero's portrait correlates best with is another portrait, and
    a misidentified slot is still a slot. `recognize.py` is what answers
    "which hero"; this only has to say where to look.
    """
    rows, width = grey.shape[:2]
    band = grey[:max(16, int(rows * TOP_REACH))]
    shrink = max(1.0, width / WORK_WIDTH)
    small = cv2.resize(band, (int(width / shrink),
                              max(1, int(band.shape[0] / shrink))),
                       interpolation=cv2.INTER_AREA) if shrink > 1 else band

    best = None
    for frac in WIDTH_FRACS:
      for aspect in ASPECTS:
        box_w = int(round(frac * small.shape[1]))
        box_h = int(round(box_w / aspect))
        if box_w < 12 or box_h < 10 or box_h >= small.shape[0]:
            continue
        keep = _one_row(_sweep(small, art, box_w, box_h), box_w)
        if note is not None and keep:
            note(f"    {frac:.3f}  box {box_w}x{box_h}  {len(keep)} hit(s)"
                 f"  best {max(keep)[0]:.2f}")
        # SHAPED LIKE A BAR FIRST, counted second. See `bar_shape`.
        rank = bar_shape(keep, box_w)
        if rank is None:
            continue
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
    full_w = max(12, int(round(box_w * scale)))
    full_h = max(10, int(round(box_h * scale)))
    anchor = _template(art[max(keep)[3]])
    inner_w, inner_h, _score = autocal._refine(
        band, anchor, max(8, int(full_w * (1 - 2 * INSET))),
        max(8, int(full_h * (1 - 2 * INSET))), reach=max(3, int(scale) + 2))
    full_w = int(round(inner_w / (1 - 2 * INSET)))
    full_h = int(round(inner_h / (1 - 2 * INSET)))

    # And the positions are re-read at that exact size, for the heroes
    # already known to be there - ten matches rather than another sweep.
    exact = _one_row(
        _sweep(band, {hid: art[hid] for _s, _x, _y, hid in keep},
               full_w, full_h), full_w)
    if bar_shape(exact, full_w) is None:
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


def measure(path: Path, into: Path, art: dict, loud=False,
            strips=False, lib=None, params=None) -> dict:
    frame = read_image(path)
    if frame is None:
        return {"file": path.name, "why": "not an image this build can read"}
    height, width = frame.shape[:2]
    row = {"file": path.name, "w": width, "h": height,
           "aspect": round(width / height, 4)}

    note = (lambda line: print(line, flush=True)) if loud else None
    if strips:
        strip_of(frame, path, into)
    found = hunt(autocal._grey(frame), art, note=note)
    if found is None:
        row["why"] = (f"no hero portrait recognised in the top "
                      f"{TOP_REACH:.0%} of this frame")
        # A FAILURE WRITES ITS OWN EVIDENCE. Without the strip, "found
        # nothing" is unanswerable: it could be the sweep, the artwork,
        # or a screenshot whose pick slots are simply still empty.
        strip_of(frame, path, into)
        return row
    slot_w, slot_h, hits = found

    banks = banks_from(hits, slot_w)
    if banks is None:
        strip_of(frame, path, into)
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
        "slot_h_of_hudbox": round(slot_h / (span / (16 / 9)), 5)
        if span else None,
        # THE THIRD MODEL, and the only one that hurts. The two above
        # differ by the bar's own fraction of the slack - 4px for the
        # top edge on 1920x1200 - which is nothing. If Dota instead
        # LETTERBOXES a 16:9 HUD into a taller display, the bar starts
        # half the slack down, which is 56px there: most of a portrait,
        # and the boxes miss. Measured, because guessing which of these
        # three is right is what CLAUDE.md says not to do.
        "y_of_hudbox_centred": round(
            (top - (height - span / (16 / 9)) / 2) / (span / (16 / 9)), 5)
        if span else None,
        "boxes": rects,
    })
    draw(frame, rects, path, into)
    slices(frame, rects, path, into)
    if lib is not None:
        reads = identify(frame, rects, lib, params)
        row["read"] = [
            {"slot": i + 1, "hero_id": r[0], "name": r[1],
             "distance": r[3], "margin": r[4]}
            for i, r in enumerate(reads)]
        row["named"] = sum(1 for r in reads if r[0])
        proof(frame, rects, reads, path, into,
              f"{path.name}  {width}x{height}   slot {slot_w}x{slot_h}"
              f"   pitch {pitch}   radiant x {radiant_x}   dire x {dire_x}"
              f"   top {top}   named {row['named']}/10")
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


NAME_OF = {}          # hero id -> display name, read off the library labels


def hero_name(label: str) -> str:
    """'base/26_lion.png' -> 'Lion'. The library's own filenames are the
    only hero-name list this tool needs, so there is nothing to keep in
    step with anything."""
    stem = Path(label).stem
    parts = stem.split("_", 1)
    words = (parts[1] if len(parts) > 1 else stem).replace("_", " ")
    return words.title()


def identify(frame, rects, lib, params):
    """(hero id, name, reference image, distance, margin) per slot.

    Uses the app's OWN recogniser rather than a second one written here.
    Two implementations of "which hero is this" is one of them drifting,
    and the point of this exercise is to find out whether the one the app
    ships works once the boxes are in the right place.
    """
    out = []
    for x, y, w, h in rects:
        crop = frame[max(0, y):y + h, max(0, x):x + w]
        if crop.size == 0:
            out.append((None, "(off screen)", None, -1, -1))
            continue
        hero_id, label, distance, margin = recognize.match_crop(
            crop, lib, params)
        reference = None
        guess = Path(library.PORTRAITS_DIR) / label
        if guess.is_file():
            reference = read_image(guess)
        name = hero_name(label) if hero_id else f"? ({hero_name(label)})"
        out.append((hero_id, name, reference, distance, margin))
    return out


def proof(frame, rects, reads, path: Path, into: Path, caption: str) -> None:
    """ONE PICTURE THAT SHOWS THE WHOLE CHAIN, at the user's request:
    "I want to see you flash up on the screen what the portrait locations
    are... and provide feedback at each stage with visual images so I can
    say - yes that is correct."

    Four bands, top to bottom:
      1  the strip that was searched, with the ten boxes on it
      2  the ten crops, exactly as cut
      3  what the recogniser says each one is, as ITS OWN PICTURE
      4  the name and how confident, in words

    Band 3 is the one that makes this checkable without trusting
    anything: a crop beside the reference portrait it was matched to is
    a comparison anybody can make by eye in a second, where a hero name
    in a table is a claim you have to take on faith.
    """
    tall, pad, foot = 120, 8, 46
    tiles = []
    for (x, y, w, h), (hero_id, name, reference, dist, margin) in zip(
            rects, reads):
        crop = frame[max(0, y):y + h, max(0, x):x + w]
        if crop.size == 0:
            crop = np.zeros((max(1, h), max(1, w), 3), np.uint8)
        scale = tall / max(1, crop.shape[0])
        wide = max(1, int(crop.shape[1] * scale))
        tiles.append((cv2.resize(crop, (wide, tall),
                                 interpolation=cv2.INTER_NEAREST),
                      reference, name, hero_id, dist, margin))

    sheet_w = max(sum(t[0].shape[1] for t in tiles) + pad * (len(tiles) + 1),
                  900)
    head = frame[:max(16, int(frame.shape[0] * TOP_REACH))].copy()
    for index, (x, y, w, h) in enumerate(rects):
        colour = (90, 220, 90) if index < 5 else (80, 80, 240)
        cv2.rectangle(head, (x, y), (x + w, y + h), colour, 2)
        cv2.putText(head, str(index + 1), (x + 3, y + h - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 1, cv2.LINE_AA)
    factor = sheet_w / head.shape[1]
    head = cv2.resize(head, (sheet_w, max(1, int(head.shape[0] * factor))),
                      interpolation=cv2.INTER_AREA)

    body = tall * 2 + pad * 3 + foot
    sheet = np.full((head.shape[0] + 34 + body, sheet_w, 3), 22, np.uint8)
    sheet[:head.shape[0]] = head
    cv2.putText(sheet, caption, (pad, head.shape[0] + 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220, 220, 220), 1,
                cv2.LINE_AA)

    top = head.shape[0] + 34
    at = pad
    for index, (tile, reference, name, hero_id, dist, margin) in enumerate(
            tiles):
        wide = tile.shape[1]
        sheet[top:top + tall, at:at + wide] = tile
        band = top + tall + pad
        if reference is not None and reference.size:
            sheet[band:band + tall, at:at + wide] = cv2.resize(
                reference, (wide, tall), interpolation=cv2.INTER_AREA)
        else:
            cv2.putText(sheet, "no ref", (at + 4, band + tall // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 120, 120), 1,
                        cv2.LINE_AA)
        # GREEN MEANS IT COMMITTED, AMBER MEANS IT DECLINED. An unknown
        # slot is a legitimate state in this app, so it must not be drawn
        # as the same kind of answer as a confident one.
        colour = (90, 220, 90) if hero_id else (70, 190, 240)
        cv2.rectangle(sheet, (at, top), (at + wide, band + tall),
                      (90, 220, 90) if index < 5 else (80, 80, 240), 1)
        line = band + tall + 18
        cv2.putText(sheet, f"{index + 1}. {name[:16]}", (at + 2, line),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, colour, 1, cv2.LINE_AA)
        cv2.putText(sheet, f"d{dist} m{margin}", (at + 2, line + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (150, 150, 150), 1,
                    cv2.LINE_AA)
        at += wide + pad

    into.mkdir(parents=True, exist_ok=True)
    ok, buffer = cv2.imencode(".png", sheet)
    if ok:
        (into / f"{path.stem}-proof.png").write_bytes(buffer.tobytes())


def strip_of(frame, path: Path, into: Path) -> None:
    """The band that was searched, saved as a picture.

    EVERY CONCLUSION ABOUT THIS BAR HAS BEEN A SIMULATION. How much the
    HUD alters a portrait decides whether matching the artwork can work
    at all - a tint costs nothing, a border costs everything unless the
    template is inset, something drawn ON the art breaks it outright -
    and which of those is true of Dota cannot be reasoned out from here.
    One look at the real strip answers it, so a failed frame writes one
    without being asked.
    """
    height = frame.shape[0]
    band = frame[:max(16, int(height * TOP_REACH))]
    if band.shape[1] > 1600:
        factor = 1600 / band.shape[1]
        band = cv2.resize(band, (1600, max(1, int(band.shape[0] * factor))),
                          interpolation=cv2.INTER_AREA)
    into.mkdir(parents=True, exist_ok=True)
    ok, buffer = cv2.imencode(".png", band)
    if ok:
        (into / f"{path.stem}-strip.png").write_bytes(buffer.tobytes())


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


def _consensus(good: list) -> None:
    """Do the 23 screenshots AGREE? That is the check that needs no eyes.

    Dota lays its HUD out in fractions of a 16:9 box, so the same three
    numbers - where a bank starts, how wide a portrait is, how far apart
    they sit - must come out the SAME on 800x600 and on 3440x1440. The
    resolutions are therefore not 23 separate problems; they are 23
    independent measurements of one constant, and their spread is a
    correctness signal on its own.

    It has already earned its keep: the edge-fitting version reported a
    spread of 0.314 on `x_of_hudbox`, which said the answers were wrong
    before a single crop had been looked at. A right answer is a tight
    cluster, and whatever sits outside it names the frame to open.
    """
    keys = ("x_of_hudbox", "slot_w_of_hudbox", "pitch_of_hudbox")
    values = {k: [r[k] for r in good if r.get(k) is not None] for k in keys}
    if not all(values[k] for k in keys):
        return
    print("\nDO THE RESOLUTIONS AGREE? (they are one constant measured "
          f"{len(good)} times)")
    middle = {}
    for key in keys:
        column = np.array(values[key], dtype=float)
        middle[key] = float(np.median(column))
        off = float(np.max(np.abs(column - middle[key])))
        verdict = ("consistent" if off <= 0.01 else
                   "loose" if off <= 0.03 else "NOT CONSISTENT")
        print(f"  {key:<18} median {middle[key]:.4f}   worst miss "
              f"{off:.4f}   {verdict}")
    rogue = [(max(abs(r[k] - middle[k]) for k in keys), r["file"])
             for r in good if all(r.get(k) is not None for k in keys)]
    rogue.sort(reverse=True)
    bad = [item for item in rogue if item[0] > 0.01]
    if bad:
        print("  frames furthest from the consensus - open these first:")
        for off, name in bad[:6]:
            print(f"    {off:.4f}  {name}")
    _vertical(good)


# 16:9 to four decimal places. A shot at this aspect cannot vote on the
# question below, because there the HUD box IS the window and the two
# candidate readings are arithmetically the same number.
SIXTEEN_NINE = 16 / 9
ASPECT_SLACK = 0.01


def _vertical(good: list) -> None:
    """WHICH WAY IS `y` MEASURED? The one thing about the layout that has
    never been settled, and the only thing standing between this app and
    the resolutions it has not been used at.

    `SlotRect.to_pixels` reads `y` and `slot_h` as fractions of the
    WINDOW height. Horizontally the HUD is known to pillarbox - measured
    on a real 3440x1440 client - and if Dota scales its HUD by WIDTH,
    which pillarboxing implies, then the vertical should be a fraction
    of the HUD BOX's height instead. On 16:9 the two are the same number
    and nothing can tell them apart. On 1920x1200 they are 60px apart,
    which is most of a portrait.

    CLAUDE.md says to settle it with a real frame rather than by
    reasoning, and these screenshots ARE real frames at nine different
    aspects. The bar is one constant, so whichever reading is the same
    across aspects is the one Dota uses - and the loser will be spread
    by exactly the letterboxing it failed to account for.

    THREE candidates, not two, and the third is the one that matters.
    Window-height and top-hung-HUD differ only by the bar's own fraction
    of the vertical slack - 4px for the top edge on 1920x1200, which
    nobody would notice. A LETTERBOXED HUD starts half the slack down,
    56px there, which misses the portraits outright.

    It REFUSES rather than guesses when the sample cannot answer: every
    shot at 16:9 makes all three readings identical, so a verdict from
    that set would be an arithmetic identity wearing the clothes of a
    measurement. So does a display WIDER than 16:9 - there the HUD box
    is the full height and the slack is nought - which is why the user's
    own 3440x1440 has never been able to settle this.
    """
    pairs = (
        ("the WINDOW's height", "y_of_window", "slot_h_of_window"),
        ("a HUD BOX hung at the TOP", "y_of_hudbox", "slot_h_of_hudbox"),
        ("a HUD BOX CENTRED (letterboxed)", "y_of_hudbox_centred",
         "slot_h_of_hudbox"),
    )
    usable = [r for r in good
              if all(r.get(k) is not None
                     for _label, *ks in pairs for k in ks)]
    if len(usable) < 2:
        return
    print("\nIS THE BAR'S TOP A FRACTION OF THE WINDOW, OR OF THE HUD BOX?")
    # TALLER THAN 16:9 IS THE ONLY THING THAT VOTES. At 16:9 the HUD box
    # is the window; WIDER than 16:9 it is pillarboxed horizontally and
    # still the full height, so the vertical slack is nought there too
    # and all three readings collapse to one number. That is exactly why
    # the user's own 3440x1440 has never been able to settle this, and
    # why a set of ultrawide shots must be refused rather than answered.
    taller = [r for r in usable
              if r["aspect"] < SIXTEEN_NINE - ASPECT_SLACK]
    if not taller:
        print("  UNDECIDABLE from this set: no picture is TALLER than "
              "16:9, and only those can tell the readings apart - at "
              "16:9 and wider the HUD box is the full height of the "
              "window, so all three are the same number by arithmetic.")
        print("  Add one shot at 16:10 (1920x1200, 1680x1050, 1440x900) "
              "or 4:3 (1600x1200, 1280x960) and run this again.")
        return
    spreads = {}
    for label, y_key, h_key in pairs:
        worst = 0.0
        for key in (y_key, h_key):
            column = np.array([r[key] for r in usable], dtype=float)
            worst = max(worst, float(np.max(column) - np.min(column)))
        spreads[label] = worst
        print(f"  measured against {label:<22} spread {worst:.5f}")
    order = sorted(spreads, key=spreads.get)
    best, runner_up = order[0], order[1]
    print(f"  {len(taller)} of {len(usable)} pictures are taller than "
          "16:9, so the readings are genuinely different here.")
    if spreads[runner_up] < 2 * spreads[best] or spreads[best] > 0.02:
        print("  NO VERDICT: the leaders are too close to separate, or the "
              "best of them is still loose. Do not change anything on this.")
        return
    print(f"  -> the bar is measured against {best}.")
    if best == "the WINDOW's height":
        print("     That is what `SlotRect.to_pixels` already does, so "
              "nothing needs changing and every resolution is covered.")
    else:
        print("     That is NOT what `SlotRect.to_pixels` does today. "
              "Changing it silently invalidates every saved "
              "calibration_local.json, so read CLAUDE.md first.")


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
    parser.add_argument("--art", default="",
                        help="folder of base portraits (default: the app's "
                             "own assets/portraits/base)")
    parser.add_argument("--no-read", action="store_true",
                        help="locate only; do not try to name the heroes")
    parser.add_argument("--strips", action="store_true",
                        help="also save the searched band of every frame, "
                             "not only the ones that fail")
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
    if args.art:
        library.BASE_DIR = Path(args.art).expanduser()
    art = load_art()
    if len(art) < 50:
        raise SystemExit(
            f"Only {len(art)} hero portrait(s) in {library.BASE_DIR}.\n"
            "This tool RECOGNISES the portraits, so it needs them on disk.\n"
            "Open the app and run Settings > Downloads > All artwork, then "
            "try again.")

    # THE APP'S OWN RECOGNISER, not a second one written here. Two
    # implementations of "which hero is this" is one of them drifting,
    # and the question being asked is whether the one that ships works
    # once the boxes are in the right place.
    lib = params = None
    if not args.no_read:
        params = library.load_params()
        lib = library.load(expected_hash_size=params.hash_size)

    into = Path(args.out)
    print(f"{len(art)} hero portraits loaded"
          + (f", library of {len(lib)} entries" if lib else ""))
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
        row = measure(shot, into, art, loud=args.loud,
                      strips=args.strips, lib=lib, params=params)
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
    _consensus(good)
    print(f"\n{len(good)} of {len(rows)} located.")
    for key in ("x_of_width", "x_of_hudbox", "slot_w_of_hudbox",
                "pitch_of_hudbox", "y_of_window", "y_of_hudbox",
                "slot_h_of_window"):
        values = [r[key] for r in good if r.get(key) is not None]
        if values:
            print(f"  {key:<18} {min(values):.5f} to {max(values):.5f}"
                  f"   spread {max(values) - min(values):.5f}")
    named = sum(r.get("named", 0) for r in good)
    if any("named" in r for r in good):
        print(f"\n{named} of {10 * len(good)} slots were given a hero name.")
    print(f"\nPictures -> {into}")
    print("  <name>-found.png   the ten boxes drawn on the frame")
    print("  <name>-slices.png  the ten crops, side by side, enlarged")
    print("  <name>-strip.png   the band that was searched (failures "
          "always; all of them with --strips)")
    print("CHECK THE SLICES. A fit half a portrait out still draws a tidy "
          "row of boxes; cut the crops out and it is obvious at once.")
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1),
                                   encoding="utf-8")


if __name__ == "__main__":
    main()

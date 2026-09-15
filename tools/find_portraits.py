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

AND WHEN IT FINDS NOTHING, ASK IT WHAT SIZES IT LOOKED AT. `--grid`
maps the best match at every size in the APP's own 2-D search grid
(`autocal.WIDTHS` x `autocal.HEIGHTS`) rather than this tool's 24
widths x 3 aspects, and says whether the winner is a size the ordinary
sweep can reach at all. Use it on one picture; it is four times the
work.

    python tools/find_portraits.py <folder> --only "1920 x 1080.png" --grid

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
from draft_assist.config import CALIBRATION_FILE     # noqa: E402
from draft_assist.vision import autocal              # noqa: E402
from draft_assist.vision import layout as layout_mod  # noqa: E402
from draft_assist.vision import library              # noqa: E402
from draft_assist.vision import recognize            # noqa: E402
from draft_assist.vision.layout import (DraftLayout,  # noqa: E402
                                        hud_box)

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
# WIDTH AND HEIGHT ARE SWEPT INDEPENDENTLY, and MEASUREMENT says so
# rather than reasoning. `--grid` mapped the app's own 2-D grid over a
# real 1024x768 screenshot - one that the three-aspect sweep could not
# read - and every bar-shaped cell it found sat at an aspect between
# 1.31 and 2.03, the best at 73x36: aspect 2.03, and 0.076 of the
# window, OUTSIDE a range that stopped at 0.072. The aspects tried were
# 0.93, 1.33 and 1.78 and the nearest was five pixels out in height on a
# 36px box. A grid of guessed aspects cannot be nudged into a shape
# nobody has measured, so there are no guessed aspects any more.
#
# This is `autocal.find_scale`'s search - the one that produced the
# shipped `DraftLayout` off a real client: widths as a fraction of the
# HUD SPAN, heights as an INDEPENDENT fraction of the frame. Three
# departures from its numbers, all measured:
#   - heights start at 0.034 rather than 0.050, because located
#     screenshots measured 0.0350 (800x600) and 0.0410 (1280x1024),
#     both under that floor;
#   - the steps are coarser, 0.006 and 0.012 against 0.003 and 0.006,
#     which holds the cost at 100 passes against the 90 three aspects
#     cost. Safe HERE, and the map is why: cells at 0.076, 0.079 and
#     0.082 across three different heights were ALL bar-shaped at peaks
#     of 0.81 to 0.92, so the peak is broad rather than sharp - and
#     `_refine` is given a reach that covers half a grid step, so what
#     the grid steps over the walk still reaches;
#   - the floor is 0.028 of the span rather than 0.014 of the window,
#     which also ends a whole class of nonsense: a 26x20 box matches
#     texture everywhere, and rows of twenty such blobs were what the
#     old diagnosis kept reporting as a hero roster.
WIDTH_FRACS = tuple(round(0.028 + 0.006 * i, 4) for i in range(10))
HEIGHT_FRACS = tuple(round(0.034 + 0.012 * i, 4) for i in range(10))
# How much of one picture's progress the coarse size sweep accounts for.
# Measured rather than guessed: the sweep is 72 passes over every hero
# and the refine that follows is a handful over one, so the sweep is
# nearly all of it - but not all, and a bar that reaches 100% before the
# work ends is a silence with a number on it.
SWEEP_SHARE = 0.9
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


# A LINE THE APP CAN READ, AND A PLAIN ONE A PERSON CAN TOO. This is
# `score_recording.STEP` spelled a second time on purpose - the two are
# separate programs and a shared import for one format string is not
# worth the coupling - but the LESSON behind it is the same one, and
# this tool shipped without it: "there is no ability to see what the
# program is thinking".
#
# Two faults, and the second is the one that made it silent. A run is
# about a minute PER PICTURE, and the only thing printed in that minute
# was a `[3/23] name ...` written with `end=""` and then erased with a
# carriage return. `TaskDialog` reads the child's output with `for raw in
# proc.stdout`, which yields LINES - so a write with no newline is not
# emitted at all until the next one arrives, and the erase produces
# nothing but junk in a text box. A prefix and a NEWLINE work in both
# places.
STEP = "PROGRESS"


def step(share: float, what: str) -> None:
    print(f"{STEP} {min(100, max(0, round(share * 100)))}%  {what}",
          flush=True)


# THE SNIPPING TOOL WRITES A MULTIPLICATION SIGN, and nobody types one.
# `1920 x 1080.png` and `1920 × 1080.png` name the same picture to every
# person who ever looks at them, and only one of the two can be typed at
# a Windows prompt without going and finding the character. This is the
# tail of the bug `read_image` exists for: there, twenty of twenty-two
# screenshots could not be OPENED because their names carried U+00D7;
# here, the one picture worth re-running cannot be NAMED for the same
# reason. Spaces go too, since a name is copied out of a table as often
# as it is typed.
SAME = {"\u00d7": "x", "\u2715": "x", "\u2716": "x", "\u00a0": " "}


def same_name(name: str) -> str:
    """One spelling of a filename, for `--only` and `--skip` to match on."""
    text = name.strip().lower()
    for odd, plain in SAME.items():
        text = text.replace(odd, plain)
    return "".join(text.split())


def read_image(path: Path):
    """Decode from bytes - `cv2.imread` cannot open a path carrying the
    multiplication sign the Snipping Tool puts in its filenames."""
    try:
        data = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    except OSError:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def size_of(path: Path):
    """(width, height) from the file's HEADER, without decoding it.

    Deciding WHICH pictures are worth a minute each must not itself cost
    a decode of every picture in the folder. A PNG states its size in
    the first 24 bytes; anything else falls back to a full read, which
    is what the folder holds in practice anyway.
    """
    try:
        with path.open("rb") as handle:
            head = handle.read(32)
    except OSError:
        return None
    if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
        return (int.from_bytes(head[16:20], "big"),
                int.from_bytes(head[20:24], "big"))
    image = read_image(path)
    if image is None or not image.size:
        return None
    return int(image.shape[1]), int(image.shape[0])


def spread_over_spans(shots, sizes, how_many: int):
    """`how_many` pictures SPREAD across the range of HUD spans.

    ONE PICTURE CANNOT DEMONSTRATE SCALING AT ALL - a single point fits
    any constant you care to name, so "slot_w = k x span" measured on
    one screenshot is not a law, it is a definition of k. What shows
    the law is the same k predicting a span it never saw, which needs
    points at DIFFERENT spans and gets better the further apart they
    are.

    It does not need all fourteen. The folder holds eight distinct
    spans from 800 to 1920 - a 2.4x range - and five of them spread
    across it cover that range exactly as well as fourteen do, in a
    third of the time. Which is the whole reason this exists: fourteen
    minutes to re-derive a constant that five minutes establishes.

    The ENDS are always taken, because the range is what is being
    tested and an interpolation between two close points proves the
    least.
    """
    known = [(sizes[shot][0] * 1.0 if sizes.get(shot) else 0.0, shot)
             for shot in shots]
    by_span = {}
    for width, shot in known:
        if width:
            # hud_box needs both, and every candidate here is already
            # taller than 16:9, where the span IS the width.
            size = sizes[shot]
            _left, span = hud_box(size[0], size[1])
            by_span.setdefault(round(span), shot)
    spans = sorted(by_span)
    if not spans or how_many <= 0 or how_many >= len(spans):
        return list(shots)
    if how_many == 1:
        return [by_span[spans[0]]]
    step = (len(spans) - 1) / (how_many - 1)
    want = sorted({spans[round(i * step)] for i in range(how_many)})
    return [by_span[span] for span in want]


# THE SMALLEST AND THE WIDEST A DOTA CLIENT CAN PLAUSIBLY BE.
# 640x480 is under every resolution Dota offers; 5:4 (1.25) is the
# narrowest monitor anybody drafts on and 32:9 (3.56) the widest.
CLIENT_MIN = (640, 480)
CLIENT_ASPECT = (1.20, 3.70)

# EVERY DISPLAY RESOLUTION A DOTA CLIENT IS PLAUSIBLY FULL-SCREEN AT.
#
# **THIS IS THE CHECK THAT WAS MISSING, and a whole run went past
# without it.** Pointed at a general Screenshots folder, `--boxes-only`
# cut ten tidy rectangles out of a shopping site, File Explorer, a chat
# window and this app's own title bar, and stacked them into a proof
# sheet that looks exactly like a measurement: "way off". Every one of
# those passed the size and aspect test above — 1272x549, 1489x804,
# 934x598 are all bigger than 640x480 and inside 5:4 to 32:9.
#
# What separates them is that a FULL-SCREEN capture is at a resolution a
# monitor actually offers, and a window snip is at whatever size the
# window happened to be. None of those thirteen is a display resolution;
# not one is even close to one.
# `--any-size` keeps them, because windowed Dota at an odd size is a
# real thing and the layout is fractions of the window either way — but
# it has to be asked for, since the commoner case by far is the wrong
# folder.
STANDARD = {
    (640, 480), (800, 600), (1024, 768), (1152, 864), (1280, 960),
    (1400, 1050), (1600, 1200), (1920, 1440), (2048, 1536),          # 4:3
    (1280, 1024), (1600, 1280),                                      # 5:4
    (1280, 800), (1440, 900), (1680, 1050), (1920, 1200),
    (2560, 1600), (2880, 1800), (3840, 2400),                        # 16:10
    (1280, 720), (1360, 768), (1366, 768), (1600, 900), (1760, 990),
    (1920, 1080), (2048, 1152), (2560, 1440), (3200, 1800),
    (3840, 2160),                                                    # 16:9
    (2560, 1080), (3440, 1440), (3840, 1600), (5120, 2160),          # 21:9
    (3840, 1080), (5120, 1440),                                      # 32:9
}


def not_a_resolution(width: int, height: int) -> str:
    """Why this size cannot be a full-screen shot, or "".

    Separate from `not_a_client` because it is the SOFTER test of the
    two and `--any-size` turns it off: a windowed client really can be
    1489x804, and the crop boxes are fractions so they would still be in
    the right place. What it catches is the folder being wrong, which is
    what actually happened.
    """
    if (width, height) in STANDARD:
        return ""
    return (f"{width}x{height} is not a display resolution - a window "
            f"snip rather than a full-screen shot (--any-size keeps it)")


def not_a_client(width: int, height: int, *, any_size: bool = False) -> str:
    """Why this picture cannot be a screenshot of the game, or "".

    **THE CROP BOXES ARE FRACTIONS, SO THEY "WORK" ON ANYTHING.** Six
    numbers times a width and a height will happily cut ten rectangles
    out of a 296x43 snip of a chat window, and the sheet then shows ten
    rows of nothing with no hint that the folder was wrong. That is a
    tool reporting an answer to a question it was never asked — the
    fault this file already carries two notes about, where a refusal
    assembled out of our own rules got printed as a claim about the
    picture.
    `--boxes-only` made it worse by design: skipping the search skips
    every check that would have noticed, because the search is what
    normally fails loudly on a frame with no pick bar in it. So the
    shape is checked directly. It cannot tell Dota from any other
    full-screen application - nothing but recognition can - but it
    catches the cases that actually turn up in a Screenshots folder:
    Snipping Tool crops, windowed captures and portrait-shaped ones.
    """
    if width < CLIENT_MIN[0] or height < CLIENT_MIN[1]:
        return (f"{width}x{height} is smaller than any resolution Dota "
                f"runs at - a crop or a window, not a client")
    aspect = width / height if height else 0.0
    low, high = CLIENT_ASPECT
    if aspect < low:
        return (f"{aspect:.2f}:1 is taller than it is wide - no monitor "
                f"is this shape")
    if aspect > high:
        return (f"{aspect:.2f}:1 is wider than 32:9 - a strip or a crop "
                f"rather than a whole screen")
    return "" if any_size else not_a_resolution(width, height)


def can_vote(width: int, height: int) -> bool:
    """Can a display this shape settle the VERTICAL convention?

    ONLY IF IT IS TALLER THAN 16:9, and that is arithmetic rather than a
    preference. Dota fits the largest 16:9 box that will go in the
    window (`layout.hud_box`, `scale = min(width/16, height/9)`), so at
    16:9 and WIDER the box is the full height and there is no vertical
    slack at all — the bar's top as a fraction of the window, of a 16:9
    box hung at the top, and of one centred are then THE SAME NUMBER,
    and a picture cannot distinguish readings that are equal. Taller
    than 16:9 the slack is real and the three separate by up to half of
    it, which is 56px on 1920x1200.

    So a sweep over twenty 16:9 screenshots is twenty minutes spent on a
    question none of them can answer. This is what `--tall` cuts.
    """
    return bool(height) and width / height < SIXTEEN_NINE - ASPECT_SLACK


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


def _rows(hits, apart: int):
    """EVERY candidate row of hits, most populous first.

    THE PICK BAR IS NOT THE BIGGEST ROW ON A HERO SELECTION SCREEN, and
    keeping only the biggest is what threw ten of fourteen real
    screenshots away. Each reported "portraits matched but not in the
    shape of a pick bar: the best row held 19/20/21/22 ... a roster row,
    not a pick bar", at peaks of 0.89 to 0.93 — the tool found the hero
    GRID, said so correctly, and gave up on the picture without ever
    looking at the bar standing above it.

    `bar_shape` was written for exactly this — "ranking by most distinct
    heroes is what lost to the hero grid ... SHAPE can tell them apart"
    — and it was applied one step too late: the row was already chosen
    by COUNT before the shape was consulted, so the shape test could
    only ever reject the winner, never promote the right one.

    So the anchors are all returned and the caller picks by shape. Rows
    are de-duplicated by their x positions, since two anchors a pixel
    apart describe one row.
    """
    if not hits:
        return []
    tolerance = max(2, int(apart * 0.15))
    out, seen = [], set()
    for anchor in sorted({hit[2] for hit in hits}):
        kept = []
        for hit in sorted(hits, reverse=True):
            if abs(hit[2] - anchor) > tolerance:
                continue
            if all(abs(hit[1] - other[1]) >= apart * 0.7 for other in kept):
                kept.append(hit)
        if not kept:
            continue
        key = tuple(sorted(hit[1] for hit in kept))
        if key in seen:
            continue
        seen.add(key)
        out.append(kept)
    out.sort(key=lambda row: (len(row), sum(hit[0] for hit in row)),
             reverse=True)
    return out


def best_bar(hits, apart: int):
    """The best BAR-SHAPED row and its rank, or None. See `_rows`."""
    best = None
    for row in _rows(hits, apart):
        rank = bar_shape(row, apart)
        if rank is not None and (best is None or rank > best[0]):
            best = (rank, row)
    return best


def _one_row(hits, apart: int):
    """The single most populous row. See `_rows`.

    Kept for the DIAGNOSIS - "the best row held 22" is a fact about the
    picture worth printing - and never for choosing the bar.

    Two constraints inside a row, and both are facts about a pick bar
    rather than tuning. Ten portraits stand on ONE line, so hits at
    different heights are not ten heroes. And two heroes cannot occupy
    the same place, so a second template landing on one already kept is
    that same portrait matched by the wrong hero - the normal case when
    126 templates are swept over a frame holding ten of them.

    An earlier version suppressed on x OR y, which let a hit at the same
    x and a different y through as a separate hero and reported thirteen
    portraits in a bar of ten.
    """
    rows = _rows(hits, apart)
    return rows[0] if rows else []


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
    # THE BEST SCORE IS REPORTED EVEN WHEN NOTHING CLEARS THE FLOOR.
    # "Found nothing" has two quite different causes - a frame with no
    # pick bar in it, and a pick bar at a size this sweep never tried -
    # and they are indistinguishable from an empty list. A peak of 0.08
    # says there is no hero art here at all; a peak of 0.62 at the very
    # edge of the size range says there is, and the range is wrong.
    best_raw = 0.0
    for hero_id, whole in art.items():
        found = autocal._best_at(strip, _template(whole), inner_w, inner_h)
        if found is None:
            continue
        score, (x, y) = found
        best_raw = max(best_raw, score)
        if score >= HIT_FLOOR:
            hits.append((score, x - back_x, y - back_y, hero_id))
    return hits, best_raw


def why_not_a_bar(keep, apart: int):
    """Why this row is not a pick bar, in a sentence, or None if it is.

    THE REFUSAL IS THE EVIDENCE. `bar_shape` answered None for five
    quite different reasons and `measure` printed one sentence for all
    of them - "no hero portrait recognised in the top 18% of this
    frame" - which is a claim about the PICTURE made from a fact about
    our own rules. It is the same fault as the calibration refusal that
    said there was no picture of the game when what was missing was our
    own attribute name: a message about the state of the world that was
    really about us, and one the reader cannot act on. Each rule now
    says which rule it was and with what numbers.
    """
    xs = sorted(hit[1] for hit in keep)
    if len(xs) < MIN_HITS:
        return (f"only {len(xs)} portrait(s) stood in one row and a bar "
                f"needs {MIN_HITS}")
    if len(xs) > MOST_HITS:
        return (f"{len(xs)} portraits in one row, more than the {MOST_HITS} "
                f"a pick bar holds - a roster row, not a pick bar")
    steps = [b - a for a, b in zip(xs, xs[1:])]
    if not steps:
        return "one portrait only"
    split = steps.index(max(steps)) + 1
    left, right = xs[:split], xs[split:]
    if max(len(left), len(right)) > autocal.TEAM_SIZE:
        return (f"the widest gap splits them {len(left)}/{len(right)} and a "
                f"bank holds at most {autocal.TEAM_SIZE}")
    # THE GAP BETWEEN THE TEAMS IS THE TELL, and it has to be clear of
    # the ordinary spacing - in an evenly spaced run the biggest step is
    # whatever rounding made largest, which would "split" a grid row
    # anywhere at all.
    others = [step for index, step in enumerate(steps)
              if index != split - 1] or [apart]
    typical = max(sorted(others)[len(others) // 2], 1)
    if max(steps) < 1.35 * typical:
        return (f"no gap between two banks: the widest step is "
                f"{max(steps)}px against a typical {typical}px, so these "
                f"{len(xs)} sit in one even run")
    return None


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
    if why_not_a_bar(keep, apart) is not None:
        return None
    return len(keep), sum(hit[0] for hit in keep)


def map_order(cell: dict):
    """BAR-SHAPED FIRST, then the count, then the score.

    Not cosmetic. A box a third of a portrait wide matches PART of every
    one of them and reports fourteen hits in a bar of ten, so ranking by
    count alone puts a size that cannot be right at the top of the map -
    which is the same mistake `bar_shape` exists to stop the sweep
    making. `why_not_a_bar` is what tells them apart, so it decides the
    order here too.
    """
    return bool(cell["bar"]), cell["row"], cell["peak"]


def size_map(grey, art: dict, span: int, tick=None, top: int = 12) -> list:
    """The best correlation at EVERY size, not only the ones swept.

    WHY THIS EXISTS. The normal sweep tries 24 widths as a fraction of
    the WINDOW crossed with THREE fixed aspects, and the app's own
    `autocal.find_scale` — which found the shipped layout on a real
    3440x1440 client — searches a strictly larger box: 19 widths as a
    fraction of the HUD SPAN crossed with 17 INDEPENDENT heights as a
    fraction of the frame. Those are not the same search, and the
    difference is not academic. The live measurement says the pick tile
    is SQUARE (slot_w 0.0525 of the span against slot_h 0.0930 of the
    height, which is 1.00 at 16:9); the nearest aspect this tool tries
    is 0.93, and on a 134px tile that is ten pixels out in height —
    which, at the scale sensitivity measured for this matcher (0.99 at
    the true size, 0.12 four pixels out), finds nothing whatever.

    So this is the instrument that answers "is the portrait at a size
    the sweep can even reach", with a number, instead of by reasoning.
    Run it on ONE picture:

        python tools/find_portraits.py <folder> --only "1920 x 1080.png"
            --grid

    It is about four times the work of one ordinary picture, which is
    why it is not what the sweep does.
    """
    rows, width = grey.shape[:2]
    band = grey[:max(16, int(rows * TOP_REACH))]
    shrink = max(1.0, width / WORK_WIDTH)
    small = cv2.resize(band, (int(width / shrink),
                              max(1, int(band.shape[0] / shrink))),
                       interpolation=cv2.INTER_AREA) if shrink > 1 else band

    cells = []
    total = len(autocal.WIDTHS) * len(autocal.HEIGHTS)
    tried = 0
    for width_frac in autocal.WIDTHS:
        for height_frac in autocal.HEIGHTS:
            tried += 1
            if tick is not None:
                tick(tried / total)
            box_w = int(round(span * width_frac / shrink))
            box_h = int(round(rows * height_frac / shrink))
            if box_w < 12 or box_h < 10 or box_h >= small.shape[0]:
                continue
            hits, raw = _sweep(small, art, box_w, box_h)
            keep = _one_row(hits, box_w)
            cells.append({
                "w_of_span": width_frac, "h_of_frame": height_frac,
                "box": [box_w, box_h], "peak": round(raw, 3),
                "row": len(keep),
                "w_of_window": round(box_w * shrink / width, 5),
                "aspect": round(box_w / max(1, box_h), 3),
                "bar": keep and why_not_a_bar(keep, box_w) is None,
            })
    cells.sort(key=map_order, reverse=True)
    return cells[:top]


def print_size_map(cells: list) -> None:
    """The map, and whether the ordinary sweep could have got there."""
    if not cells:
        print("  the grid tried nothing - the band is smaller than a "
              "portrait")
        return
    head = ("w/span", "h/frame", "box", "aspect", "w/window", "row", "peak",
            "bar?")
    widths = (8, 8, 10, 7, 9, 4, 6, 5)
    print("  " + "  ".join(h.ljust(w) for h, w in zip(head, widths)))
    for cell in cells:
        print("  " + "  ".join(str(c).ljust(w) for c, w in zip(
            (f"{cell['w_of_span']:.4f}", f"{cell['h_of_frame']:.4f}",
             f"{cell['box'][0]}x{cell['box'][1]}", f"{cell['aspect']:.2f}",
             f"{cell['w_of_window']:.4f}", cell["row"],
             f"{cell['peak']:.2f}", "yes" if cell["bar"] else "no"), widths)))
    best = cells[0]
    lo, hi = WIDTH_FRACS[0], WIDTH_FRACS[-1]
    low_h, high_h = HEIGHT_FRACS[0], HEIGHT_FRACS[-1]
    in_w = lo <= best["w_of_span"] <= hi
    in_h = low_h <= best["h_of_frame"] <= high_h
    box_w, box_h = best["box"]
    print(f"\n  The best cell is {box_w}x{box_h}, aspect "
          f"{best['aspect']:.2f}, {best['w_of_span']:.4f} of the HUD span "
          f"by {best['h_of_frame']:.4f} of the frame.")
    print(f"  The ordinary sweep tries widths {lo:.3f} to {hi:.3f} of the "
          f"span ({'IN range' if in_w else 'OUT OF RANGE'}) and heights "
          f"{low_h:.3f} to {high_h:.3f} of the frame "
          f"({'IN range' if in_h else 'OUT OF RANGE'}).")
    if in_w and in_h:
        print("  So the sweep can reach it. If it still finds nothing the "
              "fault is in what is KEPT, not in where it looked.")


def miss_rank(row):
    """How close a row came to being a PICK BAR, for the diagnosis.

    THE BIGGEST ROW IS NOT THE NEAREST MISS, and reporting it as one
    sent this analysis down a blind alley. The sweep tries boxes from
    0.014 of the width upward, and a 26x20 box matches texture
    everywhere — so the most populous row over all sizes is always one
    of the smallest boxes, carrying twenty-odd hits that are not
    portraits at all. Ten real screenshots reported exactly that, and
    `why_not_a_bar` dutifully called each one "a roster row, not a pick
    bar", which reads as a statement about the PICTURE and was a
    statement about the smallest box in our own grid.

    So the diagnosis reports the row that came CLOSEST to being a bar:
    inside the count gate first, then near ten, then by mean score. On
    the same run that is the difference between "22 portraits in one row
    at 26x20" and "8 at 96x51, split 2/6" — the second is a lead and the
    first is noise wearing a number.
    """
    count = len(row)
    inside = MIN_HITS <= count <= MOST_HITS
    mean = sum(hit[0] for hit in row) / max(1, count)
    return (inside, -abs(count - 2 * autocal.TEAM_SIZE), mean)


def _diagnose(diag, peak, nearest, stage: str) -> None:
    """Say why the hunt came back with nothing, with the numbers.

    THE TOOL SPENT A MINUTE ON THE PICTURE AND HAS TO SAY WHAT IT SAW.
    A sweep that finds no bar has already measured everything needed to
    tell the causes apart, and threw all of it away: a peak correlation
    of 0.08 means there is no hero artwork in the top of this frame at
    all - the wrong screen, or a pick bar further down - while a peak of
    0.62 means there is one and the rules rejected it, and a peak at the
    very END of the swept size range means the portrait is probably
    outside the range rather than absent. Eighteen of twenty-two frames
    reported one sentence for all three.
    """
    if diag is None:
        return
    score, frac, aspect, box_w, box_h = peak
    lo, hi = WIDTH_FRACS[0], WIDTH_FRACS[-1]
    diag.update({"stage": stage, "peak": round(score, 3), "peak_frac": frac,
                 "peak_aspect": round(aspect, 3),
                 "peak_box": [box_w, box_h]})
    if nearest is None or score < HIT_FLOOR:
        why = (f"nothing in the top {TOP_REACH:.0%} of this frame looks like "
               f"a hero portrait at any of the {len(WIDTH_FRACS)}x"
               f"{len(HEIGHT_FRACS)} sizes tried: the strongest match "
               f"anywhere "
               f"was {score:.2f}, against a floor of {HIT_FLOOR:.2f}")
        at = frac
    else:
        (_rank, count, at, row_aspect, row_w, row_h, row_best,
         refused) = nearest
        diag.update({"row": count, "row_frac": at,
                     "row_aspect": round(row_aspect, 3),
                     "row_box": [row_w, row_h], "row_best": round(row_best, 3),
                     "refused": refused})
        why = (f"portraits matched but not in the shape of a pick bar: the "
               f"NEAREST MISS was {count} in a row at {at:.3f} of the width "
               f"({row_w}x{row_h}, best {row_best:.2f}) - {refused}")
    # AT THE END OF THE RANGE IS A DIFFERENT ANSWER, and it is the one
    # that says what to change. The sweep can only find a size it tries.
    if score >= HIT_FLOOR and at in (lo, hi):
        which = "bottom" if at == lo else "top"
        why += (f". That size is the {which} END of the range swept "
                f"({lo:.3f} to {hi:.3f} of the window), so the real "
                f"portraits may be outside it rather than absent")
    if stage != "the size sweep":
        why += f". Refused by {stage}"
    diag["why"] = why


def hunt(grey, art: dict, note=None, tick=None, diag=None):
    """(slot_w, slot_h, hits) in this picture's own pixels, or None.

    `diag`, when given a dict, is filled with WHY it came back None -
    see `why_not_a_bar` and `_diagnose`. A refusal that names one cause
    for five is a refusal nobody can act on.

    `tick` is called with 0..1 as the size sweep walks, because that
    sweep IS the minute this tool spends on a picture: 24 widths x 3
    aspects x 126 heroes. Without it the whole minute is one silence,
    and a silence is indistinguishable from a hang.

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
    peak = (0.0, 0.0, 0.0, 0, 0)      # score, frac, aspect, box_w, box_h
    nearest = None                    # the row that came CLOSEST to a bar
    tried = 0
    total = len(WIDTH_FRACS) * len(HEIGHT_FRACS)
    # WIDTHS OF THE HUD SPAN, heights of the FRAME - `autocal`'s own
    # units, so the two searches are one search. At 16:9 and taller the
    # span IS the window; only wider than 16:9 do they differ, and there
    # the pillarboxing is exactly what the span accounts for.
    _left, span = hud_box(width, rows)
    for frac in WIDTH_FRACS:
      for height_frac in HEIGHT_FRACS:
        tried += 1
        if tick is not None:
            # THE COARSE SWEEP IS NOT THE WHOLE JOB, so it does not get
            # the whole bar: the refine and the exact re-read after it
            # are real work too, and a bar that hits 100% and then sits
            # there is the same silence wearing a number.
            tick(SWEEP_SHARE * tried / total)
        box_w = int(round(span * frac / shrink))
        box_h = int(round(rows * height_frac / shrink))
        aspect = box_w / max(1, box_h)
        if box_w < 12 or box_h < 10 or box_h >= small.shape[0]:
            continue
        hits, raw = _sweep(small, art, box_w, box_h)
        if raw > peak[0]:
            peak = (raw, frac, aspect, box_w, box_h)
        # SHAPED LIKE A BAR FIRST, counted second — and across EVERY row
        # in the frame, not only the most populous one. On a hero
        # selection screen the biggest row is the roster grid, and the
        # bar is a shorter row above it. See `_rows`.
        found_bar = best_bar(hits, box_w)
        keep = _one_row(hits, box_w)
        refused = why_not_a_bar(keep, box_w) if keep else "nothing matched"
        for row in _rows(hits, box_w):
            why = why_not_a_bar(row, box_w)
            rank = miss_rank(row)
            if nearest is None or rank > nearest[0]:
                nearest = (rank, len(row), frac, aspect, box_w, box_h,
                           max(row)[0], why)
        if note is not None and keep:
            note(f"    {frac:.3f}  box {box_w}x{box_h}  {len(keep)} hit(s)"
                 f"  best {max(keep)[0]:.2f}"
                 + ("  -- BAR" if found_bar else f"  -- {refused}"))
        if found_bar is None:
            continue
        rank, row = found_bar
        if best is None or rank > best[0]:
            best = (rank, box_w, box_h, row)
    if best is None:
        _diagnose(diag, peak, nearest, "the size sweep")
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
    # REACH HALF A GRID STEP, at least. The grid is deliberately coarse -
    # 0.006 of the span and 0.012 of the frame - so the true size can sit
    # up to half a step from the nearest cell in either axis, and a walk
    # that cannot cross that gap turns the coarseness into a miss.
    step_w = 0.5 * (WIDTH_FRACS[1] - WIDTH_FRACS[0]) * span
    step_h = 0.5 * (HEIGHT_FRACS[1] - HEIGHT_FRACS[0]) * rows
    reach = max(3, int(scale) + 2, int(step_w) + 1, int(step_h) + 1)
    inner_w, inner_h, _score = autocal._refine(
        band, anchor, max(8, int(full_w * (1 - 2 * INSET))),
        max(8, int(full_h * (1 - 2 * INSET))), reach=reach)
    full_w = int(round(inner_w / (1 - 2 * INSET)))
    full_h = int(round(inner_h / (1 - 2 * INSET)))

    # And the positions are re-read at that exact size, for the heroes
    # already known to be there - ten matches rather than another sweep.
    if tick is not None:
        tick(SWEEP_SHARE + (1 - SWEEP_SHARE) * 0.5)
    exact_hits, exact_raw = _sweep(
        band, {hid: art[hid] for _s, _x, _y, hid in keep}, full_w, full_h)
    if exact_raw > peak[0]:
        peak = (exact_raw, full_w / max(1, width), full_w / max(1, full_h),
                full_w, full_h)
    exact_bar = best_bar(exact_hits, full_w)
    exact = exact_bar[1] if exact_bar else _one_row(exact_hits, full_w)
    if tick is not None:
        tick(1.0)
    if exact_bar is None:
        # THE COARSE PASS FOUND A BAR AND THE EXACT RE-READ DID NOT,
        # which is a different failure from never finding one and has to
        # read as one: the size walked somewhere the portraits are not.
        _diagnose(
            diag, peak,
            (miss_rank(exact) if exact else (False, -99, 0.0),
             len(exact), box_w / max(1, small.shape[1]),
             box_w / max(1, box_h), full_w, full_h,
             max(exact)[0] if exact else 0.0,
             why_not_a_bar(exact, full_w) if exact else "nothing matched"),
            f"the re-read at the refined size ({full_w}x{full_h})")
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


def app_boxes(width: int, height: int) -> list:
    """Where the SHIPPED crop boxes land on a frame this size.

    THIS IS THE OTHER QUESTION, and the sheet was only ever answering
    one of them. Everything else in this tool SEARCHES for the pick bar
    and reports what it found, which measures Dota; these are the six
    fractions the app actually cuts with, put through the app's own
    `SlotRect.to_pixels`. A run can therefore say both "the tool could
    not find the bar here" and "and here is what the app would have
    grabbed anyway", which are different faults with different fixes and
    looked identical while only the first was drawn.

    It needs no search and cannot fail, so it is available on the
    pictures where the search came back with nothing — which are exactly
    the ones worth looking at.
    """
    return [slot.to_pixels(width, height) for slot in DraftLayout().slots()]


def measure(path: Path, into: Path, art: dict, loud=False,
            strips=False, lib=None, params=None, tick=None,
            boxes_only: bool = False) -> dict:
    frame = read_image(path)
    if frame is None:
        return {"file": path.name, "why": "not an image this build can read"}
    height, width = frame.shape[:2]
    row = {"file": path.name, "w": width, "h": height,
           "aspect": round(width / height, 4)}
    # BEFORE ANYTHING CAN FAIL. Every early return below is a search that
    # did not find the bar, and those are the frames where "what does the
    # app grab here" is the question actually being asked.
    row["app_crops"] = crop_row(frame, app_boxes(width, height),
                                context=BOX_CONTEXT)
    if boxes_only:
        # NOTHING BELOW IS NEEDED TO ANSWER "WHAT DOES THE APP GRAB
        # HERE". The search is what costs a minute a picture, and it
        # answers a different question — where Dota actually put the
        # bar. The shipped crop boxes are six fractions and a multiply,
        # so a whole folder is seconds, and that is the question
        # somebody looking at a wrong-looking draft is asking.
        return row

    note = (lambda line: print(line, flush=True)) if loud else None
    if strips:
        strip_of(frame, path, into)
    diag: dict = {}
    found = hunt(autocal._grey(frame), art, note=note, tick=tick, diag=diag)
    if found is None:
        row["diag"] = diag
        row["why"] = diag.get(
            "why", f"no hero portrait recognised in the top "
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
        # THE SECOND BANK'S OWN ORIGIN. `banks_from` has always measured
        # it and the row kept only Radiant's, so `dire_x` was the one
        # shipped fraction nothing here could check.
        "dire_x_of_hudbox": round((dire_x - left) / span, 5) if span else None,
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
    row["crops"] = slices(frame, rects, path, into)
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
    sheet = crop_row(frame, rects)
    into.mkdir(parents=True, exist_ok=True)
    ok, buffer = cv2.imencode(".png", sheet)
    if ok:
        (into / f"{path.stem}-slices.png").write_bytes(buffer.tobytes())
    return sheet


# HOW MUCH OF THE PICTURE AROUND A BOX THE SHEET SHOWS. A crop cut
# exactly to the box answers "what did the app grab" and NOTHING about
# what it should have grabbed, so a row that came back holding the
# player's name is equally consistent with a box half a portrait too
# low, a box twice too tall, and a screenshot of the wrong screen
# altogether - three faults with three different fixes, and the first
# real sheet could not tell them apart. With half a box of context
# either side and the box itself drawn on it, the portrait it missed is
# in the same tile as the miss.
BOX_CONTEXT = 0.6


def crop_row(frame, rects, tall: int = 120, context: float = 0.0):
    """The ten crops of ONE picture, side by side, numbered.

    `context` widens each crop by that fraction of the box's own size on
    every side and DRAWS the box inside it, so the tile shows the box
    against what is around it. Nought is the bare crop, which is what
    the located-portrait rows want: there the rectangle came FROM the
    picture, so there is nothing to check it against.
    """
    tiles = []
    for index, (x, y, w, h) in enumerate(rects):
        pad_x, pad_y = int(round(w * context)), int(round(h * context))
        left, top = max(0, x - pad_x), max(0, y - pad_y)
        crop = frame[top:y + h + pad_y, left:x + w + pad_x]
        if crop.size == 0:
            crop = np.zeros((max(1, h), max(1, w), 3), np.uint8)
        elif context:
            # The box's place INSIDE this tile, which is not the padding
            # whenever the crop was clamped at an edge of the frame -
            # the first box of a bank is often hard against the left.
            crop = crop.copy()
            colour = (90, 220, 90) if index < 5 else (80, 80, 240)
            cv2.rectangle(crop, (x - left, y - top),
                          (x - left + w - 1, y - top + h - 1), colour, 1)
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
    return sheet


LABEL_W = 150
SHEET_NAME = "proof-sheet.png"
# A MARKED LINE, like PROGRESS, so the window can act on it rather than
# scan ordinary output for something that looks like a path.
SHEET = "SHEET"


def proof_sheet(rows: list, into: Path):
    """ONE picture: every resolution's ten crops, a labelled row each.

    At the user's request, and it is the only form of the answer that
    can be checked at a glance: "if there are five different
    resolutions, I want to show me five sets of 10 portraits that you
    have snipped out of the example screenshots".

    Per-picture `-slices.png` files have existed throughout and were no
    use for this - fourteen files in a folder, opened one at a time, is
    not a comparison. Stacked, a resolution whose fit is half a portrait
    out is the one row that does not look like the others.
    """
    strips = [(name, image) for name, image in rows if image is not None]
    if not strips:
        return None
    # A BAD FIT MAKES A VERY WIDE ROW. Every crop is scaled to the same
    # HEIGHT, so a fit that came back a quarter of the true height is
    # blown up four times as wide - and ten of those is a row thousands
    # of pixels across, from the one resolution whose answer is worth
    # the least. Rows are cut to the widest SENSIBLE one so the sheet
    # stays a picture somebody can open.
    ceiling = int(np.median([image.shape[1] for _n, image in strips]) * 2)
    strips = [(name, image[:, :ceiling] if image.shape[1] > ceiling
               else image) for name, image in strips]
    width = LABEL_W + max(image.shape[1] for _n, image in strips)
    height = sum(image.shape[0] + 8 for _n, image in strips) + 8
    sheet = np.full((height, width, 3), 18, np.uint8)
    at = 8
    for name, image in strips:
        sheet[at:at + image.shape[0], LABEL_W:LABEL_W + image.shape[1]] = image
        cv2.putText(sheet, name, (8, at + image.shape[0] // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (235, 235, 235), 1,
                    cv2.LINE_AA)
        at += image.shape[0] + 8
    into.mkdir(parents=True, exist_ok=True)
    where = into / SHEET_NAME
    # NEVER FATAL, and it took a fourteen-minute run down to prove it.
    # The sheet is the LAST thing written, after every measurement is
    # already on screen, so a failure here must cost the picture and
    # nothing else - the rule `Recorder` has always followed, that a
    # full disk costs the recording and never the draft. It says what
    # went wrong and names the exact path, because "Invalid argument"
    # on a path nobody can see is unanswerable.
    try:
        ok, buffer = cv2.imencode(".png", sheet)
        if not ok:
            print(f"  (the proof sheet would not encode: "
                  f"{sheet.shape[1]}x{sheet.shape[0]})")
            return None
        where.write_bytes(buffer.tobytes())
    except (OSError, ValueError, cv2.error) as bad:
        print(f"  (the proof sheet could not be written to {where!r}: "
              f"{type(bad).__name__}: {bad})")
        return None
    return where


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


def _scaling(good: list, middle: dict) -> None:
    """PREDICT each resolution from the constant, and show the error.

    "I want you to instil confidence that this portrait recognition is
    working and that it follows simple math in terms of the scaling
    with resolution." A spread of 0.0019 is a correct answer to that and
    an unreadable one: it is a fraction of a fraction, with no units
    anybody can check.

    So the claim is made in the form it would be USED in. One constant
    times the HUD span is a prediction in PIXELS for a resolution the
    constant never saw, and the error is a whole number of pixels beside
    the measurement. A law that predicts eight screenshots to within a
    pixel or two is a law; one that needs a different number per
    resolution is a lookup table with ambitions.
    """
    keys = (("slot width", "slot_w_of_hudbox", "slot_w_px"),
            ("pitch", "pitch_of_hudbox", "pitch_px"))
    rows = [r for r in good
            if all(r.get(k) is not None for _n, _f, k in keys)]
    if not rows:
        return
    print("\nDOES IT FOLLOW SIMPLE MATHS? "
          "(one constant x the HUD span, predicted in PIXELS)")
    for name, frac_key, _px in keys:
        print(f"  {name:<11} = {middle[frac_key]:.5f} x span")
    head = ("file", "span", "slot w", "predicted", "out",
            "pitch", "predicted", "out")
    widths = (18, 6, 7, 10, 5, 6, 10, 5)
    print("  " + "  ".join(h.ljust(w) for h, w in zip(head, widths)))
    for row in rows:
        _left, span = hud_box(row["w"], row["h"])
        cells = [row["file"][:18], f"{span:.0f}"]
        for _name, frac_key, px_key in keys:
            want = round(middle[frac_key] * span)
            got = row[px_key]
            cells += [str(got), str(want), f"{got - want:+d}"]
        print("  " + "  ".join(c.ljust(w) for c, w in zip(cells, widths)))
    # THE HEADLINE IS HOW MANY AGREE, not the worst single frame. One
    # bad fit among eleven made the summary read NOT CONSISTENT while
    # ten resolutions were being predicted to within a pixel - a true
    # sentence that says the opposite of what the measurement shows.
    # A median is already robust to an outlier; the VERDICT has to be
    # too, and the outlier is named rather than averaged away.
    errors = {}
    for row in rows:
        _left, span = hud_box(row["w"], row["h"])
        errors[row["file"]] = max(
            abs(row[px] - round(middle[frac] * span))
            for _n, frac, px in keys)
    agree = sorted(v for v in errors.values() if v <= SCALES_TO)
    print(f"  {len(agree)} of {len(errors)} resolutions predicted to "
          f"within {SCALES_TO}px"
          + (f", worst of them {max(agree)}px." if agree else "."))
    rogue = sorted(((v, k) for k, v in errors.items() if v > SCALES_TO),
                   reverse=True)
    for off, name in rogue:
        print(f"    OUTLIER {off:>4}px  {name} - that fit disagrees with "
              f"every other resolution, so read its row on the sheet.")
    print("  A law predicts a resolution it never saw; a lookup table "
          "needs a new number for each.")


def _consensus(good: list, apply: bool = False) -> None:
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
    # ONLY A FULL READING VOTES, and the two that were not full were
    # wrecking the verdict on their own. `banks_from` takes a bank's
    # origin off the FIRST portrait it found in it, so a frame that
    # located five of ten has its bank starts, its pitch and its top
    # edge read off whichever five those were - the same reason
    # `_remember_measured_layout` refuses to save a layout from nine.
    # On the run that found ten of fourteen, the eight full readings
    # agreed to a spread of 0.0028 on the pitch and 0.0066 on the slot
    # width; adding the two five-portrait frames took those to 0.0400
    # and 0.0413 and turned every verdict into NOT CONSISTENT. A
    # partial fit is not a quieter measurement, it is a different one.
    whole = [r for r in good
             if r.get("heroes") == 2 * autocal.TEAM_SIZE]
    partial = len(good) - len(whole)
    if not whole:
        print("\nNo frame located all ten portraits, so there is nothing "
              "here that can be called a measurement.")
        return
    good = whole
    values = {k: [r[k] for r in good if r.get(k) is not None] for k in keys}
    if not all(values[k] for k in keys):
        return
    print("\nDO THE RESOLUTIONS AGREE? (they are one constant measured "
          f"{len(good)} times)")
    if partial:
        print(f"  {partial} frame(s) located fewer than ten and do not "
              f"vote - a bank's origin is read off the first portrait "
              f"found in it, so a partial fit measures something else.")
    middle = {}
    for key in keys:
        column = np.array(values[key], dtype=float)
        middle[key] = float(np.median(column))
        off = float(np.max(np.abs(column - middle[key])))
        verdict = ("consistent" if off <= 0.01 else
                   "loose" if off <= 0.03 else "NOT CONSISTENT")
        print(f"  {key:<18} median {middle[key]:.4f}   worst miss "
              f"{off:.4f}   {verdict}")
    _scaling(good, middle)
    rogue = [(max(abs(r[k] - middle[k]) for k in keys), r["file"])
             for r in good if all(r.get(k) is not None for k in keys)]
    rogue.sort(reverse=True)
    bad = [item for item in rogue if item[0] > 0.01]
    if bad:
        print("  frames furthest from the consensus - open these first:")
        for off, name in bad[:6]:
            print(f"    {off:.4f}  {name}")
    _vertical(good)
    _boxes_against_the_bar(good)
    _fitted_layout(good, apply=apply)


# 16:9 to four decimal places. A shot at this aspect cannot vote on the
# question below, because there the HUD box IS the window and the two
# candidate readings are arithmetically the same number.
# HOW CLOSE THE PREDICTION HAS TO BE to count as agreement. Measured:
# on the thirteen-of-fourteen run, ten of eleven full readings came in
# at 4px or better and the eleventh at 46px. There is no middle ground
# in the data, which is what makes a threshold here honest rather than
# a knob.
SCALES_TO = 4

SIXTEEN_NINE = 16 / 9
ASPECT_SLACK = 0.01
# A bar top measured in single figures of pixels cannot separate two
# models: rounding alone moves it further than they differ. Measured -
# on the ten-of-fourteen run the tops ran 4 to 7 pixels while the
# portrait heights ran 46 to 74.
TOP_IS_COARSE = 20


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
    # THE TWO QUANTITIES ARE REPORTED APART, because only one of them
    # can decide anything. The bar's TOP is 4 to 7 pixels down on these
    # frames, so a single pixel of rounding is 14% to 25% of the whole
    # reading and it cannot separate two models that differ by less
    # than that. The portrait's HEIGHT is 46 to 74 pixels, where
    # rounding is under 2%. Folding them together with a max() hid
    # which one was talking - and the run that did so printed a verdict
    # telling the reader to change `SlotRect.to_pixels`, on evidence
    # that was entirely the height's.
    tops = [r["bar_top_px"] for r in usable if r.get("bar_top_px")]
    coarse = tops and max(tops) < TOP_IS_COARSE
    spreads, impossible = {}, {}
    for label, y_key, h_key in pairs:
        parts = {}
        for what, key in (("top", y_key), ("height", h_key)):
            column = np.array([r[key] for r in usable], dtype=float)
            parts[what] = float(np.max(column) - np.min(column))
        # The DECIDING spread is the height's when the top is too few
        # pixels to mean anything, and the worse of the two otherwise.
        spreads[label] = (parts["height"] if coarse
                          else max(parts.values()))
        # A READING THAT PUTS THE BAR ABOVE THE TOP OF THE HUD BOX IS
        # NOT A LOOSE MEASUREMENT, IT IS A REFUTED MODEL. A negative y
        # says the portraits are outside the box the model claims Dota
        # draws them in, which no amount of sample can rescue - so it is
        # struck out rather than ranked. This is what finally kills the
        # letterboxed candidate: on real 4:3 and 16:10 screenshots it
        # lands at -0.20 of the HUD box's height.
        low = float(np.min(np.array([r[y_key] for r in usable],
                                    dtype=float)))
        if low < -0.005:
            impossible[label] = low
        print(f"  measured against {label:<22} "
              f"top {parts['top']:.5f}  height {parts['height']:.5f}"
              + (f"   IMPOSSIBLE: puts the bar {abs(low):.4f} ABOVE the "
                 f"top of that box" if low < -0.005 else ""))
    print(f"  {len(taller)} of {len(usable)} pictures are taller than "
          "16:9, so the readings are genuinely different here.")
    if coarse:
        print(f"  The bar's top is only {min(tops)}-{max(tops)} PIXELS "
              f"down, so one pixel of rounding is a large share of it: "
              f"the HEIGHT decides this, not the top.")
    order = [label for label in sorted(spreads, key=spreads.get)
             if label not in impossible]
    if not order:
        print("  NO VERDICT: every candidate puts the bar outside its own "
              "box, so the fits are wrong before the models are.")
        return
    if len(order) == 1:
        print(f"  -> only {order[0]} survives; the others put the bar "
              f"outside their own box.")
        _name_the_winner(order[0])
        return
    best, runner_up = order[0], order[1]
    if spreads[runner_up] < 2 * spreads[best] or spreads[best] > 0.02:
        print("  NO VERDICT between the survivors: the leaders are too "
              "close to separate, or the best is still loose.")
        if impossible:
            print("     What IS settled is the struck-out model above - "
                  "and that was the only one that would have missed the "
                  "portraits.")
        return
    _name_the_winner(best)


def _name_the_winner(best: str) -> None:
    """What to do about the model that won."""
    print(f"  -> the bar is measured against {best}.")
    if best == "the WINDOW's height":
        print("     That is what `SlotRect.to_pixels` already does, so "
              "nothing needs changing and every resolution is covered.")
    else:
        print("     That is NOT what `SlotRect.to_pixels` does today. "
              "Changing it silently invalidates every saved "
              "calibration_local.json, so read CLAUDE.md first.")


# The six fractions a `DraftLayout` is made of, each with the reading it
# is expressed in. The SPAN ones are fractions of Dota's 16:9 HUD box -
# settled from a real 3440x1440 client, where a fraction of the full
# width landed the boxes 440px left of the portraits. The HEIGHT ones
# are fractions of the whole window, which is what `SlotRect.to_pixels`
# does and what the proof sheet says is landing low.
FRACTIONS = (
    ("radiant_x", "x_of_hudbox", "span"),
    ("dire_x", "dire_x_of_hudbox", "span"),
    ("slot_w", "slot_w_of_hudbox", "span"),
    ("pitch", "pitch_of_hudbox", "span"),
    ("y", "y_of_window", "height"),
    ("slot_h", "slot_h_of_window", "height"),
)

# THE TWO THIS TOOL CANNOT MEASURE, named rather than left out. They
# are the ranked-role icon's offset below a portrait and its height, and
# everything here searches for HERO PORTRAITS - so there is nothing in a
# located bar that says where a role icon sits. Declaring them is what
# keeps the guard sharp: a SEVENTH fraction added to `DraftLayout` still
# fails `test_every_fraction_the_app_ships_is_measured`, which is how
# `dire_x` was found to be the one shipped number nothing here checked.
NOT_MEASURED_HERE = ("role_dy", "role_h")

# What the table converts to pixels against. 16:9, so the span IS the
# width and the two readings cannot be confused in the arithmetic - the
# column is there to turn a fraction into something a person can judge,
# not to make a claim about a resolution.
AT = (1920, 1080)


def _boxes_against_the_bar(good: list) -> None:
    """THE PROOF SHEET AS NUMBERS, which is the half it cannot give.

    The sheet shows what the app's own boxes cut out, and a row that has
    caught the player's name instead of the portrait is obvious at a
    glance - but "obvious" is where this went wrong last time. A crop
    that looks low is not a measurement, and a measurement is what it
    takes to move six numbers that every saved calibration depends on.

    Every frame here has BOTH: `app_boxes` put the shipped fractions
    through `SlotRect.to_pixels`, and the search found where Dota
    actually drew the bar. The difference is the fix, in pixels, per
    picture - and it has been computed on every run since the sheet was
    written and never once printed.

    A POSITIVE NUMBER MEANS THE APP'S BOX IS LOWER, TALLER OR FURTHER
    RIGHT than the bar it is supposed to be on.
    """
    # EVERY key this needs, not a couple of them. A row reaches here
    # from several paths and a partial one is normal; asking for the
    # two that were convenient and indexing the rest is how this block
    # took out fourteen tests whose fixtures carry only the fractions.
    needs = ("bar_top_px", "slot_h_px", "radiant_x_px", "slot_w_px",
             "w", "h")
    rows = [r for r in good if all(r.get(k) is not None for k in needs)]
    if not rows:
        return
    print("\nWHERE THE SHIPPED BOXES LAND AGAINST THE BAR THAT WAS FOUND")
    print("  (+ is the app's box lower / taller / further right than "
          "Dota's own)")
    print(f"  {'picture':<24}{'top':>8}{'height':>9}{'first x':>10}"
          f"{'width':>8}")
    offs = {"top": [], "height": [], "x": [], "width": []}
    for r in sorted(rows, key=lambda r: (r["w"], r["h"])):
        ax, ay, aw, ah = app_boxes(r["w"], r["h"])[0]
        d = {"top": ay - r["bar_top_px"], "height": ah - r["slot_h_px"],
             "x": ax - r["radiant_x_px"], "width": aw - r["slot_w_px"]}
        for k, v in d.items():
            offs[k].append(v)
        print(f"  {r['file'][:23]:<24}{d['top']:>+8}{d['height']:>+9}"
              f"{d['x']:>+10}{d['width']:>+8}")
    print(f"  {'median of ' + str(len(rows)):<24}"
          + "".join(f"{int(round(float(np.median(offs[k])))):>+{w}}"
                    for k, w in (("top", 8), ("height", 9), ("x", 10),
                                 ("width", 8))))


def _fitted_layout(good: list, apply: bool = False) -> None:
    """THE SIX FRACTIONS THESE SCREENSHOTS MEASURE, beside the six shipped.

    This is the number the whole exercise has been circling. `_consensus`
    prints how TIGHTLY the frames agree and `_vertical` prints which
    reading is most consistent; neither has ever printed WHAT the
    agreed value is, so a run could say "consistent to 0.0057" about a
    figure nobody could compare with the one in the code.

    It REPORTS AND DOES NOT WRITE, which is the rule the whole tool
    follows: changing these silently invalidates every saved
    `calibration_local.json`, and a median over a handful of frames is a
    measurement rather than a decision. The line at the bottom is there
    to be read and pasted by somebody who has decided, not applied by
    this.

    Each fraction carries its own WORST MISS, because a median is only
    worth pasting if the frames behind it agree - and the two that do
    not (800x600, 1440x900) are excluded here for the same reason
    `_consensus` excludes them: a bank's origin is read off the first
    portrait found in it, so a partial fit measures something else.
    """
    shipped = DraftLayout()
    rows = []
    for name, key, against in FRACTIONS:
        column = [r[key] for r in good if r.get(key) is not None]
        if not column:
            return
        column = np.array(column, dtype=float)
        mid = float(np.median(column))
        rows.append((name, mid, float(np.max(np.abs(column - mid))),
                     getattr(shipped, name), against))
    print(f"\nWHAT THESE {len(good)} PICTURES MEASURE THE SIX FRACTIONS "
          f"TO BE")
    print(f"  {'fraction':<11}{'measured':>10}{'shipped':>10}"
          f"{'worst miss':>12}    at {AT[0]}x{AT[1]}")
    for name, mid, miss, now, against in rows:
        scale = AT[0] if against == "span" else AT[1]
        print(f"  {name:<11}{mid:>10.4f}{now:>10.4f}{miss:>12.4f}"
              f"    {round((mid - now) * scale):>+5} px")
    print("  " + ", ".join(f"{name}={mid:.4f}" for name, mid, *_ in rows))
    if not apply:
        print("  NOT APPLIED. These are what the pictures say; changing "
              "the shipped six invalidates every saved "
              "calibration_local.json, so it is a decision rather than a "
              "readout. Re-run with --apply to write them to this "
              "machine's own calibration.")
        return
    _write_calibration(rows)


# HOW FAR THE FRAMES MAY DISAGREE AND STILL BE WRITTEN. `_consensus`
# already calls 0.01 "consistent" and 0.03 "loose", and this takes the
# tighter of the two: a median is a measurement only while the pictures
# behind it agree, and writing a loose one would put a number on this
# machine that no single screenshot supports.
AGREE_WITHIN = 0.01


def _write_calibration(rows: list) -> None:
    """Put the measured six on THIS MACHINE, and never the shipped six.

    The tool's standing rule is that it reports and does not write, and
    that rule is about `DraftLayout`'s defaults in the source - six
    numbers every install inherits, which a median over a handful of one
    person's screenshots is not evidence enough to move.
    `calibration_local.json` is the opposite kind of file: gitignored,
    one machine's own, already overwritten by the app's own measurement
    at the next strategy time, and the exact thing `load_layout` exists
    to read. Writing it is what turns "here are the numbers, paste them
    somewhere" into a fix.

    **THE TWO FRACTIONS THIS CANNOT MEASURE ARE KEPT, NOT ZEROED.** The
    role icon's offset and height are not in `FRACTIONS` because nothing
    in a located pick bar says where a role strip sits, so they come
    from `DraftLayout()` - a file naming four of six would leave the
    other two at whatever `float()` made of nothing.
    """
    loose = [(name, miss) for name, _mid, miss, *_ in rows
             if miss > AGREE_WITHIN]
    if loose:
        print("  NOT WRITTEN: these pictures do not agree closely enough "
              "to be one measurement - "
              + ", ".join(f"{name} misses by {miss:.4f}"
                          for name, miss in loose)
              + f" against a ceiling of {AGREE_WITHIN:.2f}.")
        print("  Open the frames named above: a bank's origin is read off "
              "the first portrait found in it, so one bad fit moves the "
              "median for every resolution.")
        return
    measured = DraftLayout(**{name: round(mid, 4) for name, mid, *_ in rows})
    layout_mod.save_calibration(measured)
    print(f"  WRITTEN to {CALIBRATION_FILE}. The app reads it at the next "
          "start, and its own measurement at the next strategy time "
          "replaces it.")


def _failures(bad: list) -> None:
    """One line per picture that located nothing, with its own numbers.

    EIGHTEEN REFUSALS ARE A PATTERN OR THEY ARE NOTHING. Read one at a
    time they are eighteen sentences; read as a column of peaks and best
    rows they say at once whether the frames hold no hero art (every
    peak under the floor - the wrong screen, or a bar below the band) or
    hold it at a size this sweep does not try (peaks high, and at the
    end of the range).
    """
    if not bad:
        return
    print(f"\n{len(bad)} located nothing:")
    head = ("file", "WxH", "peak", "at", "box", "best row", "why")
    widths = (24, 11, 6, 7, 9, 9, 0)
    print("  " + "  ".join(h.ljust(w) for h, w in zip(head, widths)))
    floor = 0
    for row in bad:
        diag = row.get("diag") or {}
        peak = diag.get("peak")
        if peak is not None and peak < HIT_FLOOR:
            floor += 1
        box = diag.get("peak_box") or []
        cells = (row["file"][:24],
                 f"{row.get('w', '?')}x{row.get('h', '?')}",
                 f"{peak:.2f}" if peak is not None else "-",
                 f"{diag['peak_frac']:.3f}" if diag.get("peak_frac") else "-",
                 f"{box[0]}x{box[1]}" if len(box) == 2 else "-",
                 str(diag.get("row", "-")),
                 diag.get("refused") or "nothing cleared the floor")
        print("  " + "  ".join(str(c).ljust(w)
                               for c, w in zip(cells, widths)))
    if floor == len(bad):
        print(f"  ALL {len(bad)} peaked below the {HIT_FLOOR:.2f} floor: "
              "there is no hero artwork in the searched band of any of "
              "them. Look at a -strip.png before changing the sweep.")


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
    parser.add_argument("--sample", type=int, default=0,
                        help="do this many pictures SPREAD across the "
                             "range of HUD spans, rather than all of "
                             "them. One cannot demonstrate scaling at "
                             "all; five cover the folder's 2.4x range "
                             "as well as fourteen, in a third of the "
                             "time. 0 means all.")
    parser.add_argument("--tall", action="store_true",
                        help="only the pictures TALLER than 16:9 - the "
                             "only ones that can settle the vertical "
                             "convention. At 16:9 and wider the three "
                             "readings are arithmetically the same "
                             "number, so those minutes buy nothing.")
    parser.add_argument("--boxes-only", action="store_true",
                        dest="boxes_only",
                        help="skip the search: just cut the APP'S OWN crop "
                             "boxes out of every picture and stack them. "
                             "Seconds rather than a minute a picture, and "
                             "it works at every resolution rather than only "
                             "the ones that can settle the vertical. This is "
                             "the one that answers 'what is the app actually "
                             "grabbing at 1440x900'.")
    parser.add_argument("--any-size", action="store_true", dest="any_size",
                        help="keep pictures whose size is not a display "
                             "resolution. Windowed Dota really can be "
                             "1489x804 — but so can a snip of a web page, "
                             "and the crop boxes are fractions, so they cut "
                             "ten tidy rectangles out of either. Off by "
                             "default because the commoner cause is the "
                             "wrong folder.")
    parser.add_argument("--grid", action="store_true",
                        help="instead of locating, map the best match at "
                             "every size in the app's own 2-D search grid. "
                             "Answers whether the portraits are at a size "
                             "the ordinary sweep can reach. Four times the "
                             "work, so use it with --only on one picture.")
    parser.add_argument("--apply", action="store_true",
                        help="write the six fractions these pictures "
                             "measure to this machine's own "
                             "calibration_local.json, when they agree "
                             "closely enough to be one measurement. The "
                             "shipped defaults in the source are never "
                             "touched. Needs the search, so it is "
                             "refused with --boxes-only.")
    args = parser.parse_args()

    # A WRITE NEEDS A MEASUREMENT, and `--boxes-only` deliberately makes
    # none - it cuts the shipped fractions out and stops, which is the
    # question "what does the app grab" rather than "where is the bar".
    # Asked for both, say so rather than writing the numbers that are
    # already in the file.
    if args.apply and args.boxes_only:
        raise SystemExit("--apply needs the search, so it cannot be used "
                         "with --boxes-only. Drop --boxes-only (about a "
                         "minute a picture) and it will measure, then "
                         "write.")

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
        want = {same_name(n) for n in args.only.split(",") if n.strip()}
        shots = [p for p in shots if same_name(p.name) in want]
    elif args.skip:
        marks = [same_name(n) for n in args.skip.split(",") if n.strip()]
        names = [same_name(p.name) for p in shots]
        if len(marks) == 1 and marks[0] in names:
            shots = shots[names.index(marks[0]) + 1:]   # resume AFTER it
        else:
            shots = [p for p in shots if same_name(p.name) not in set(marks)]

    # SAY WHAT THIS RUN WILL COST AND WHAT IT CAN ANSWER, before it is
    # started rather than after. "The time to run these tests seems to
    # be increasing dramatically" is the honest reading of a tool that
    # spends a minute each on twenty-two pictures without ever saying
    # that fifteen of them cannot answer the open question.
    sizes = {p: size_of(p) for p in shots}

    # WHAT CANNOT BE A GAME SCREENSHOT IS SAID SO AND SET ASIDE, before
    # anything is measured or cut. A Screenshots folder is where the
    # Snipping Tool puts things too, and the crop boxes cannot tell: they
    # are fractions, so they cut ten tidy rectangles out of a 296x43 snip
    # and the sheet reports them as though they meant something. A whole
    # run over the wrong folder is worse than no run, because it looks
    # like a result.
    refused = []
    keep = []
    for shot in shots:
        size = sizes.get(shot)
        why = (not_a_client(*size, any_size=args.any_size) if size
               else "not an image this build can read")
        (refused if why else keep).append((shot, why) if why else shot)
    if refused:
        print(f"{len(refused)} of {len(shots)} cannot be a Dota client:")
        for shot, why in refused[:12]:
            print(f"  {shot.name[:34].ljust(34)}  {why}")
        if len(refused) > 12:
            print(f"  ... and {len(refused) - 12} more")
        print()
    if not keep:
        raise SystemExit(
            "NONE of these pictures is the shape of a game screenshot, so "
            "there is nothing here to measure.\n"
            "This is almost always the wrong folder. Dota's own screenshots "
            "(F12) go to Steam's userdata, not to Pictures;\n"
            "Windows' PrintScreen and Win+Shift+S go to Pictures, but only "
            "a FULL-SCREEN capture of the draft is any use here.")
    shots = keep

    tall = [p for p in shots
            if sizes.get(p) and can_vote(*sizes[p])]
    print(f"{len(shots)} picture(s) in {folder}; {len(tall)} taller than "
          f"16:9.")
    print("Only a display taller than 16:9 can settle the vertical "
          "convention - see `can_vote`.")
    if args.boxes_only:
        print("--boxes-only: no search, so this is seconds rather than "
              "minutes, and EVERY picture counts rather than only the "
              "tall ones.")
    else:
        print(f"About a minute each: ~{len(shots)} min for all, "
              f"~{len(tall)} min with --tall.")
    if args.tall:
        if not tall:
            raise SystemExit(
                "None of these pictures is taller than 16:9, so none of "
                "them can settle it.\nA 4:3 (1024x768), 5:4 (1280x1024) "
                "or 16:10 (1920x1200, 1680x1050) shot would.")
        shots = tall
    if args.sample and not args.only:
        picked = spread_over_spans(shots, sizes, args.sample)
        if len(picked) < len(shots):
            print(f"  Doing {len(picked)} of them, spread across the "
                  f"range of HUD spans - see `spread_over_spans`. "
                  f"Drop --sample for all of them.")
            shots = picked
    print()

    # THE ARTWORK IS THE METHOD, so its absence is refused rather than
    # worked around. Without it this tool has nothing to recognise and
    # would fall back to guessing, which is what the edge fit was.
    if args.art:
        library.BASE_DIR = Path(args.art).expanduser()
    # --boxes-only NEEDS NO ARTWORK AT ALL. It cuts six fractions out of
    # a picture; it recognises nothing. Demanding the library there would
    # refuse the one run that still works on a fresh install.
    art = {} if args.boxes_only else load_art()
    if not args.boxes_only and len(art) < 50:
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
    if not args.no_read and not args.grid and not args.boxes_only:
        params = library.load_params()
        lib = library.load(expected_hash_size=params.hash_size)

    into = Path(args.out)
    print(f"{len(art)} hero portraits loaded"
          + (f", library of {len(lib)} entries" if lib else ""))
    print(f"{len(shots)} picture(s) to do\n")
    head = ("file", "WxH", "aspect", "seen", "bar top", "slot h", "rad x",
            "dire x", "slot w", "pitch", "x/hud", "w/hud", "pitch/hud",
            "y/win")
    widths = (24, 11, 7, 5, 8, 7, 7, 7, 7, 6, 8, 8, 9, 8)
    if not args.boxes_only:
        print("  ".join(h.ljust(w) for h, w in zip(head, widths)))
        print("-" * (sum(widths) + 2 * len(widths)))

    if args.grid:
        # ONE PICTURE, unless you named others. The map is four times the
        # work of an ordinary sweep because it runs the app's whole 2-D
        # grid, and it answers a question about the SEARCH rather than
        # about any particular screenshot - so mapping fourteen of them
        # is an hour spent re-deriving one answer. A tall one is picked
        # when there is one, since those are the frames with anything
        # left to settle.
        if not args.only and len(shots) > 1:
            pick = tall[0] if tall else shots[0]
            print(f"Mapping ONE picture: {pick.name}. The map answers a "
                  f"question about the search, not about a screenshot, "
                  f"so one is enough.")
            print("Name another with --only if you want a different one.\n")
            shots = [pick]
        for number, shot in enumerate(shots, 1):
            done = (number - 1) / len(shots)
            each = 1.0 / len(shots)
            step(done, f"{shot.name}  ({number} of {len(shots)})")
            frame = read_image(shot)
            if frame is None:
                print(f"{shot.name}: not an image this build can read")
                continue
            height, width = frame.shape[:2]
            _left, span = hud_box(width, height)
            print(f"\n{shot.name}  {width}x{height}  "
                  f"aspect {width / height:.3f}  HUD span {span}")
            cells = size_map(
                autocal._grey(frame), art, span,
                tick=lambda share, at=done, size=each: step(
                    at + size * share, "mapping sizes"))
            print_size_map(cells)
        step(1.0, "done")
        return

    rows = []
    for number, shot in enumerate(shots, 1):
        # SAY WHICH ONE IT IS ON, AND HOW FAR INTO IT. The first version
        # printed only finished rows, so a minute of work per picture
        # was indistinguishable from a hang - "is it loading, or is it
        # an empty table?" The second printed a `[3/23] name ...` with
        # `end=""` and erased it with a carriage return, which is worse
        # in the place this is actually run from: the dialog reads the
        # child's output LINE BY LINE, so a write with no newline never
        # arrives at all and the erase is junk. "There is no ability to
        # see what the program is thinking" was exactly that.
        done = (number - 1) / len(shots)
        each = 1.0 / len(shots)
        step(done, f"{shot.name}  ({number} of {len(shots)})")
        row = measure(
            shot, into, art, loud=args.loud, strips=args.strips,
            lib=lib, params=params, boxes_only=args.boxes_only,
            tick=lambda share, at=done, size=each, name=shot.name:
                step(at + size * share, name))
        rows.append(row)
        if args.boxes_only:
            print(f"{row['file'][:24].ljust(24)}  "
                  f"{row.get('w','?')}x{row.get('h','?')}", flush=True)
            continue
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

    step(1.0, "done")
    good = [r for r in rows if "why" not in r]
    # NONE OF THE MEASUREMENT EXISTS IN --boxes-only, so none of it is
    # reported. A consensus printed over rows that were never measured
    # would be a verdict about nothing, which is the fault this tool
    # already carries two notes about.
    if not args.boxes_only:
        _consensus(good, apply=args.apply)
        print(f"\n{len(good)} of {len(rows)} located.")
        for key in ("x_of_width", "x_of_hudbox", "slot_w_of_hudbox",
                    "pitch_of_hudbox", "y_of_window", "y_of_hudbox",
                    "slot_h_of_window"):
            values = [r[key] for r in good if r.get(key) is not None]
            if values:
                print(f"  {key:<18} {min(values):.5f} to {max(values):.5f}"
                      f"   spread {max(values) - min(values):.5f}")
        _failures([r for r in rows if "why" in r])
    # THE PROOF, IN ONE PICTURE. Written last so it carries every
    # resolution this run located, in the order they were done.
    # THE LABEL CARRIES THE COUNT, so a row of rubbish explains itself
    # rather than looking like the recognition failing. The two frames
    # that located five of ten produced exactly that, and the reader had
    # to cross-reference a table to know which rows to disbelieve.
    # TWO ROWS PER PICTURE, and the second one is the app.
    # "app boxes" is what the shipped fractions actually cut out of this
    # frame - the thing a change to `SlotRect.to_pixels` moves, and the
    # thing somebody asking "show me what it captures at 1440x900" is
    # asking about. "found" is what this tool's own search located, which
    # measures DOTA rather than us. They fail independently and for
    # different reasons, so a sheet carrying only one of them cannot say
    # which is at fault. EVERY picture gets the app row, including the
    # ones the search gave up on - those are the interesting ones.
    lines = []
    for r in rows:
        size = f"{r.get('w','?')}x{r.get('h','?')}"
        if r.get("app_crops") is not None:
            lines.append((size if args.boxes_only else f"{size}  app boxes",
                          r["app_crops"]))
        if args.boxes_only:
            continue
        if "why" in r:
            lines.append((f"{size}  found: none", None))
            continue
        lines.append((
            f"{size}  found"
            + ("" if r.get("heroes") == 2 * autocal.TEAM_SIZE
               else f" ({r.get('heroes', 0)} of "
                    f"{2 * autocal.TEAM_SIZE} - set aside)"),
            r.get("crops")))
    where = proof_sheet(lines, into)
    if where is not None:
        print(f"\n{SHEET} {where}")
        if args.boxes_only:
            print("  One row per picture: the ten crops the APP'S OWN box "
                  "fractions cut out of it.")
            print("  Ten whole centred heads is a working geometry. A "
                  "sliced or stretched row is not, and the resolution "
                  "beside it names itself.")
        else:
            print("  Two rows per picture: what the APP's own crop boxes "
                  "cut out, and what this tool's search located.")
            print("  A box that is off the portraits is the row that does "
                  "not look like the others - a sliced or stretched crop "
                  "rather than ten whole heads.")
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
        # THE CROPS ARE PIXELS, not a field. `json.dumps` cannot encode
        # an ndarray and would take the whole report down with it at the
        # very last line of a twenty-minute run.
        Path(args.json).write_text(
            json.dumps([{k: v for k, v in r.items() if k != "crops"}
                        for r in rows], indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

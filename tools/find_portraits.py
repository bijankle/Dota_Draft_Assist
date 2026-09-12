"""Find the ten draft portraits ANYWHERE in a frame, and draw what it found.

WHY THIS IS NOT `autocal.find_banks`. That one searches the top 15% of
Dota's 16:9 HUD box, because it is built for the live path where being
fast matters and where the bar has always been at the top. It refused
the user's real screenshots outright - "nothing in the top of this frame
looks like two banks of five portraits" - and their read of it is the
obvious one: "I think the search area is too small, so when we change
the aspect ratio the portraits spill out into other areas."

So this makes NO assumption about where the bar is. It scans the whole
frame for a horizontal row of two mirrored banks of five, over the FULL
width rather than the 16:9 box - because the 16:9 box is exactly the
model under suspicion, and a search restricted to it could only ever
confirm what it already believes.

IT SHOWS ITS WORK. For every picture it writes an annotated copy with
the ten boxes it settled on drawn over them, because a table of numbers
cannot be checked by eye and this is a calibration nobody should take on
trust: "I'm expecting you to show me snippets of what you think the 10
portraits are in each snippet."

    python tools/find_portraits.py <folder> [--out DIR] [--json FILE]

The annotated pictures ARE Valve's artwork, like the screenshots they
come from. Attach them, never commit them.
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from draft_assist import console                     # noqa: E402
from draft_assist.vision import autocal              # noqa: E402
from draft_assist.vision.layout import hud_box       # noqa: E402

SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
WORK_WIDTH = 960          # the scan runs on a picture this wide
BAND = 9                  # rows averaged for one horizontal fit
STEP = 2                  # how far the band moves each try, in work pixels
# GENEROUS, because the whole point is not to assume. `autocal` looks for
# a bank starting 2% to 26% across the HUD BOX; over the full width of a
# letterboxed frame the same bar can start further in, and a pitch can be
# wider than its range allows once the HUD is not the whole screen.
BANK_START = (0.01, 0.40)
BANK_PITCH = (0.025, 0.140)


def read_image(path: Path):
    """Decode from bytes - `cv2.imread` cannot open a path carrying the
    multiplication sign the Snipping Tool puts in its filenames."""
    try:
        data = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    except OSError:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def scan(grey: np.ndarray):
    """(score, y, start, pitch, slot_w) in this picture's own pixels.

    One horizontal fit per candidate row band, all the way down the
    frame. The band is thin: `_edge_profile` averages the column
    differences over its rows, so any band lying INSIDE the portraits
    carries their borders, and a thin one cannot be diluted by the rows
    above and below the bar.
    """
    rows, width = grey.shape[:2]
    starts = np.arange(int(width * BANK_START[0]), int(width * BANK_START[1]))
    pitches = range(int(width * BANK_PITCH[0]), int(width * BANK_PITCH[1]) + 1)
    if not starts.size or not len(pitches):
        return None

    best = None
    for top in range(0, rows - BAND, STEP):
        band = grey[top:top + BAND]
        raw = autocal._edge_profile(band)
        fit = autocal._mirrored_fit(autocal._tolerant(raw), raw, width,
                                    starts, pitches)
        if fit is None:
            continue
        score = fit[0]
        if best is None or score > best[0]:
            best = (score, top, fit[1], fit[2], fit[3])
    return best


def boxes_of(start: int, pitch: int, slot_w: int, width: int,
             top: int, height: int) -> list:
    """The ten rectangles, left bank then right, MIRRORED about the
    centre - which is how the bar is built and how the fit found it."""
    out = []
    for i in range(autocal.TEAM_SIZE):
        out.append((start + i * pitch, top, slot_w, height))
    for i in range(autocal.TEAM_SIZE):
        right = width - (start + i * pitch) - slot_w
        out.append((right, top, slot_w, height))
    return sorted(out)


def measure(path: Path, into: Path) -> dict:
    frame = read_image(path)
    if frame is None:
        return {"file": path.name, "why": "not an image this build can read"}
    height, width = frame.shape[:2]
    row = {"file": path.name, "w": width, "h": height,
           "aspect": round(width / height, 4)}

    shrink = max(1.0, width / WORK_WIDTH)
    small = cv2.resize(autocal._grey(frame),
                       (int(width / shrink), int(height / shrink)),
                       interpolation=cv2.INTER_AREA)
    found = scan(small)
    if found is None:
        row["why"] = "no row of five-plus-five found anywhere in this frame"
        return row

    _score, sy, sstart, spitch, swide = found
    # Back to full resolution. The scan only has to find the
    # NEIGHBOURHOOD; the vertical fit below reads the real edges.
    scale = width / float(small.shape[1])
    start = int(round(sstart * scale))
    pitch = int(round(spitch * scale))
    slot_w = int(round(swide * scale))
    band_top = int(round(sy * scale))

    # THE TOP AND HEIGHT OFF THE PICTURE, from the bank columns only, in a
    # window round where the scan landed rather than from the top of the
    # frame - `_vertical_fit` pulls towards the top of whatever it is
    # given, which would drag the answer back up to y=0.
    reach = max(40, int(pitch * 2))
    y0 = max(0, band_top - reach)
    y1 = min(height, band_top + reach)
    columns = np.concatenate([
        np.arange(start + i * pitch, min(width, start + i * pitch + slot_w))
        for i in range(autocal.TEAM_SIZE)])
    columns = columns[columns < width]
    vertical = autocal._vertical_fit(
        autocal._grey(frame)[y0:y1], columns, slot_w)
    if vertical is None:
        top, slot_h = band_top, int(slot_w / autocal.PORTRAIT_ASPECT)
    else:
        top, slot_h = y0 + vertical[0], vertical[1]

    rects = boxes_of(start, pitch, slot_w, width, top, slot_h)
    left, span = hud_box(width, height)
    row.update({
        "bar_top_px": top, "slot_h_px": slot_h,
        "radiant_x_px": rects[0][0], "dire_x_px": rects[5][0],
        "slot_w_px": slot_w, "pitch_px": pitch,
        # BOTH READINGS, so the model can be derived rather than assumed.
        "x_of_width": round(rects[0][0] / width, 5),
        "x_of_hudbox": round((rects[0][0] - left) / span, 5) if span else None,
        "y_of_window": round(top / height, 5),
        "y_of_hudbox": round(top / (span / (16 / 9)), 5) if span else None,
        "slot_h_of_window": round(slot_h / height, 5),
        "boxes": rects,
    })
    draw(frame, rects, path, into)
    return row


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
    args = parser.parse_args()

    folder = Path(args.folder).expanduser()
    if not folder.is_dir():
        raise SystemExit(f"Not a folder: {folder}")
    shots = sorted(p for p in folder.iterdir()
                   if p.suffix.lower() in SUFFIXES)
    if not shots:
        raise SystemExit(f"No images in {folder}")

    into = Path(args.out)
    print(f"{len(shots)} picture(s) in {folder}\n")
    head = ("file", "WxH", "aspect", "bar top", "slot h", "rad x", "dire x",
            "slot w", "pitch", "x/width", "x/hud", "y/win", "y/hud")
    widths = (24, 11, 7, 8, 7, 8, 8, 7, 7, 8, 8, 8, 8)
    print("  ".join(h.ljust(w) for h, w in zip(head, widths)))
    print("-" * (sum(widths) + 2 * len(widths)))

    rows = []
    for shot in shots:
        row = measure(shot, into)
        rows.append(row)
        if "why" in row:
            print(f"{row['file'][:24].ljust(24)}  "
                  f"{row.get('w','?')}x{row.get('h','?')}   -- {row['why']}")
            continue
        cells = (row["file"][:24], f"{row['w']}x{row['h']}",
                 f"{row['aspect']:.3f}", row["bar_top_px"], row["slot_h_px"],
                 row["radiant_x_px"], row["dire_x_px"], row["slot_w_px"],
                 row["pitch_px"], f"{row['x_of_width']:.5f}",
                 f"{row['x_of_hudbox']:.5f}", f"{row['y_of_window']:.5f}",
                 f"{row['y_of_hudbox']:.5f}")
        print("  ".join(str(c).ljust(w) for c, w in zip(cells, widths)))

    good = [r for r in rows if "why" not in r]
    print(f"\n{len(good)} of {len(rows)} located.")
    for key in ("x_of_width", "x_of_hudbox", "y_of_window", "y_of_hudbox",
                "slot_h_of_window"):
        values = [r[key] for r in good if r.get(key) is not None]
        if values:
            print(f"  {key:<18} {min(values):.5f} to {max(values):.5f}"
                  f"   spread {max(values) - min(values):.5f}")
    print(f"\nAnnotated pictures -> {into}")
    print("CHECK THEM BY EYE. A fit that is one portrait out still scores "
          "well and still prints a tidy table.")
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1),
                                   encoding="utf-8")


if __name__ == "__main__":
    main()

"""Measure the pick bar in a folder of screenshots, and report NUMBERS.

WHAT THIS IS FOR. `layout.hud_box` says of itself: "THE NARROW HALF IS
NOT CONFIRMED... `SlotRect.to_pixels` reads `y` and `h` as fractions of
the WINDOW height, so on a 1920x1200 panel it places the bar 11% lower
and draws it 11% taller than on 1920x1080. If Dota scales its HUD by the
width - which is what pillarboxing on the wide side implies - that is
wrong... Settle it with a real 16:10 frame, not with reasoning."

This is the reasoning-free way to settle it. Point it at screenshots of
the draft taken at several resolutions and it prints, per picture, where
the bar ACTUALLY IS in absolute pixels, then the same measurement
expressed under both competing conventions:

    window   - y as a fraction of the window height (what the app assumes)
    hudbox   - y as a fraction of the 16:9 box's height

Whichever column holds STEADY across differing aspect ratios is the one
Dota uses. One frame cannot tell them apart, because on 16:9 they are
the same number; a 16:10 or 5:4 frame separates them outright.

NO PICTURE LEAVES THE MACHINE. It prints a table and writes a JSON file
of the same figures - both artwork-free, both safe to paste into a chat
or attach. That is deliberate: a Dota screenshot is full of Valve's
artwork, which this repository does not carry and must never be asked to.
Do not commit the screenshots; put them anywhere outside the repo, or in
`debug_out/`, which is gitignored.

    python tools/measure_screens.py C:\\path\\to\\shots
    python tools/measure_screens.py C:\\path\\to\\shots --json out.json

It does NOT need Dota, a portrait library, hero statistics or an API key:
`autocal.find_banks` reads the bar's own periodic edges, so a picture is
all it wants.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2                                          # noqa: E402

from draft_assist import console                    # noqa: E402
from draft_assist.vision.autocal import find_banks  # noqa: E402
from draft_assist.vision.layout import hud_box      # noqa: E402

SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
HUD_ASPECT = 16.0 / 9.0


def measure(path: Path) -> dict:
    """One picture, or a row saying why it could not be read."""
    frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if frame is None:
        return {"file": path.name, "why": "not an image this build can read"}
    height, width = frame.shape[:2]
    left, span = hud_box(width, height)
    # The HUD box's own HEIGHT, which is the other candidate denominator.
    # On 16:9 it equals the window height, which is exactly why a 16:9
    # screenshot cannot settle the question.
    box_h = span / HUD_ASPECT

    row = {"file": path.name, "w": width, "h": height,
           "aspect": round(width / height, 4),
           "hud_left": round(left, 1), "hud_span": round(span, 1),
           "hud_height": round(box_h, 1)}

    layout, note = find_banks(frame)
    if layout is None:
        row["why"] = note
        return row

    # BACK TO ABSOLUTE PIXELS, which is the only form that means the same
    # thing whatever convention produced it. Everything derived below is
    # derived from these, so a mistake in the conventions cannot hide in
    # the raw measurement.
    top_px = layout.y * height
    slot_h_px = layout.slot_h * height
    row.update({
        "bar_top_px": round(top_px, 1),
        "slot_h_px": round(slot_h_px, 1),
        "radiant_x_px": round(left + layout.radiant_x * span, 1),
        "dire_x_px": round(left + layout.dire_x * span, 1),
        "slot_w_px": round(layout.slot_w * span, 1),
        "pitch_px": round(layout.pitch * span, 1),
        # THE TWO READINGS OF THE SAME PIXELS. Steady down a column is
        # the answer; drifting with the aspect ratio is the refutation.
        "y_of_window": round(top_px / height, 5),
        "y_of_hudbox": round(top_px / box_h, 5) if box_h else None,
        "slot_h_of_window": round(slot_h_px / height, 5),
        "slot_h_of_hudbox": round(slot_h_px / box_h, 5) if box_h else None,
        "note": note,
    })
    return row


def main() -> None:
    console.plain_output()
    parser = argparse.ArgumentParser(
        description="Measure the pick bar in each screenshot in a folder.")
    parser.add_argument("folder", help="where the screenshots are")
    parser.add_argument("--json", default="", help="also write the figures here")
    args = parser.parse_args()

    folder = Path(args.folder).expanduser()
    if not folder.is_dir():
        raise SystemExit(f"Not a folder: {folder}")
    shots = sorted(p for p in folder.iterdir()
                   if p.suffix.lower() in SUFFIXES)
    if not shots:
        raise SystemExit(
            f"No images in {folder}. Looked for: {', '.join(SUFFIXES)}")

    print(f"{len(shots)} picture(s) in {folder}\n")
    head = ("file", "WxH", "aspect", "bar top", "slot h", "rad x", "dire x",
            "slot w", "pitch", "y/win", "y/hud", "h/win", "h/hud")
    widths = (26, 11, 7, 8, 7, 8, 8, 7, 7, 8, 8, 8, 8)
    print("  ".join(name.ljust(w) for name, w in zip(head, widths)))
    print("-" * (sum(widths) + 2 * len(widths)))

    rows = []
    for shot in shots:
        row = measure(shot)
        rows.append(row)
        if "why" in row:
            print(f"{row['file'][:26].ljust(26)}  "
                  f"{row.get('w', '?')}x{row.get('h', '?')}"
                  f"   -- {row['why']}")
            continue
        cells = (row["file"][:26], f"{row['w']}x{row['h']}",
                 f"{row['aspect']:.3f}", f"{row['bar_top_px']:.1f}",
                 f"{row['slot_h_px']:.1f}", f"{row['radiant_x_px']:.1f}",
                 f"{row['dire_x_px']:.1f}", f"{row['slot_w_px']:.1f}",
                 f"{row['pitch_px']:.1f}", f"{row['y_of_window']:.5f}",
                 f"{row['y_of_hudbox']:.5f}",
                 f"{row['slot_h_of_window']:.5f}",
                 f"{row['slot_h_of_hudbox']:.5f}")
        print("  ".join(str(c).ljust(w) for c, w in zip(cells, widths)))

    good = [r for r in rows if "why" not in r]
    print(f"\n{len(good)} of {len(rows)} measured.")
    if good:
        _verdict(good)
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1),
                                   encoding="utf-8")
        print(f"\nFigures written to {args.json} - no picture in it.")


def _verdict(rows: list) -> None:
    """Say which convention held steadier, without deciding anything.

    A spread is only meaningful across DIFFERING aspect ratios: on 16:9
    the two denominators are the same number, so a folder of 16:9 shots
    agrees with itself under both and settles nothing.
    """
    ratios = {r["aspect"] for r in rows}
    print(f"aspect ratios present: "
          f"{', '.join(f'{a:.3f}' for a in sorted(ratios))}")
    if len(ratios) < 2:
        print("ONE aspect ratio only - this cannot separate the two "
              "conventions. A 16:10 or 5:4 shot is what settles it.")
        return
    for label, key in (("y", "y_of_window"), ("y", "y_of_hudbox"),
                       ("slot_h", "slot_h_of_window"),
                       ("slot_h", "slot_h_of_hudbox")):
        values = [r[key] for r in rows if r.get(key) is not None]
        if not values:
            continue
        spread = max(values) - min(values)
        print(f"  {key:<18} {min(values):.5f} to {max(values):.5f}"
              f"   spread {spread:.5f}")
    print("\nThe STEADIER pair is the convention Dota uses. Send this "
          "table; the decision is not this tool's to make.")


if __name__ == "__main__":
    main()

"""Replay path: run the full vision (and optionally scoring) pipeline against
saved frames from disk instead of live capture. Turns a bug reproducible only
during a live draft into a one-second offline run, and feeds the
self-training loop:

  --harvest    confidently-resolved slot crops are saved into
               assets/portraits/variants/<hero_id>/ so real-world appearances
               (dim states, new patch art) grow the library;
               UNKNOWN slot crops are saved into debug_out/unlabeled/ for
               manual labeling with tools/label_slot.py.

Usage:
    python tools/replay.py captures/probe [--harvest] [--score]
"""

import argparse
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draft_assist.config import DEBUG_OUT  # noqa: E402
from draft_assist.vision import debug, library  # noqa: E402
from draft_assist.vision.layout import load_layout  # noqa: E402
from draft_assist.vision.library import EMPTY_SLOT  # noqa: E402
from draft_assist.vision.recognize import read_draft  # noqa: E402

# Harvest only crops that matched clearly but not trivially: distance far
# under the ceiling (definitely right) yet nonzero (a genuinely new
# appearance worth remembering). Auto-adding borderline matches would poison
# the library.
HARVEST_MIN_D, HARVEST_MAX_D_FRAC = 3, 0.15


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frames", help="frame image file or directory of them")
    parser.add_argument("--harvest", action="store_true")
    parser.add_argument("--score", action="store_true",
                        help="also print hero recommendations per frame")
    args = parser.parse_args()

    src = Path(args.frames)
    paths = sorted(src.glob("*.png")) + sorted(src.glob("*.jpg")) \
        if src.is_dir() else [src]
    if not paths:
        raise SystemExit(f"no frames found at {src}")

    layout = load_layout()
    params = library.load_params()
    lib = library.load(expected_hash_size=params.hash_size)

    names = None
    ds = None
    if args.score:
        from draft_assist.data import store
        from draft_assist.model import scoring
        ds = store.load()
        names = {hid: ds.name(hid) for hid in ds.hero_ids}

    harvested = 0
    for path in paths:
        frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if frame is None:
            print(f"{path.name}: unreadable, skipped")
            continue
        read = read_draft(frame, layout, lib, params, keep_crops=True)
        folder = debug.dump(frame, read, names)
        resolved = 10 - read.unknown_count()
        print(f"{path.name}: {resolved}/10 slots resolved "
              f"({sum(1 for s in read.slots if s.hero_id == EMPTY_SLOT)} "
              f"empty) -> {folder}")

        if args.harvest:
            for s in read.slots:
                if s.crop is None or not s.crop.size:
                    continue
                tag = f"{path.stem}_{s.rect.team}{s.rect.slot}"
                if s.hero_id is None:
                    dest = DEBUG_OUT / "unlabeled" / f"{tag}.png"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    cv2.imwrite(str(dest), s.crop)
                elif (s.hero_id != EMPTY_SLOT
                      and HARVEST_MIN_D <= s.distance
                      <= round(HARVEST_MAX_D_FRAC * params.bits)):
                    dest = (library.VARIANTS_DIR / str(s.hero_id)
                            / f"{tag}.png")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    cv2.imwrite(str(dest), s.crop)
                    harvested += 1

        if args.score and ds is not None:
            from draft_assist.model import scoring
            draft = scoring.DraftState(
                allies=read.team_ids("radiant"),
                enemies=read.team_ids("dire"),
                unknown_slots=read.unknown_count())
            top = scoring.score_all(ds, draft)[:8]
            for s in top:
                print(f"    {s.name:22s} {s.score:.3f} "
                      f"(base {s.baseline:.3f}, vs {s.vs_total:+.3f}, "
                      f"with {s.with_total:+.3f})")

    if args.harvest:
        print(f"harvested {harvested} confident crops into variants/; "
              "rebuild the library to include them: "
              "python tools/build_library.py")


if __name__ == "__main__":
    main()

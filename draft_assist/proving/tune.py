"""Self-training entry point: generate a labeled synthetic corpus, grid-search
recognition parameters (hash size, distance ceiling, margin floor), and save
the best operating point for the live recogniser.

Objective is lexicographic: any WRONG match disqualifies a candidate before
unknown-rate is even considered — a tool silent about a slot beats one that
asserts the wrong hero.

Run with real downloaded portraits (default, after tools/build_library.py)
or --procedural for a network-less smoke run:

    python -m draft_assist.proving.tune --frames 120
"""

import argparse
import itertools

import numpy as np

from ..vision.layout import load_layout
from ..vision.library import (EMPTY_SLOT, RecognitionParams, rebuild,
                              save_params)
from ..vision import library as library_mod
from .evaluate import build_library_from_images, evaluate
from .synth import (SynthCase, empty_slot_image, generate_case,
                    procedural_portrait_set)

HASH_SIZES = (8, 16)
MAX_DISTANCE_FRACS = (0.20, 0.25, 0.30, 0.35)
MIN_MARGIN_FRACS = (0.02, 0.04, 0.06, 0.10)


def _load_real_portraits() -> dict[int, np.ndarray] | None:
    """Real library source images, keyed by an entry index -> (hero_id, img),
    or None when none are downloaded yet."""
    import cv2
    portraits: dict[int, np.ndarray] = {}
    variants: dict[int, list[np.ndarray]] = {}
    try:
        for hid, label, path in library_mod._iter_source_images():
            img = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if img is None:
                continue
            if label.startswith("base/"):
                portraits[hid] = img
            else:
                variants.setdefault(hid, []).append(img)
    except (FileNotFoundError, ValueError):
        return None
    if not portraits:
        return None
    # Variants ride along as extra library entries via _extra_variants.
    _load_real_portraits.variants = variants  # type: ignore[attr-defined]
    return portraits


def make_cases(portraits: dict[int, np.ndarray], n_frames: int,
               seed: int) -> list[SynthCase]:
    layout = load_layout()
    rng = np.random.default_rng(seed)
    return [generate_case(portraits, layout, rng) for _ in range(n_frames)]


def tune(portraits: dict[int, np.ndarray], n_frames: int = 120,
         seed: int = 1, variants: dict[int, list[np.ndarray]] | None = None,
         verbose: bool = True) -> tuple[RecognitionParams, dict]:
    layout = load_layout()
    train = make_cases(portraits, n_frames, seed)
    holdout = make_cases(portraits, max(20, n_frames // 4), seed + 999)

    extra = dict(variants or {})
    extra.setdefault(EMPTY_SLOT, []).append(empty_slot_image())

    results = []
    for hs in HASH_SIZES:
        lib = build_library_from_images(portraits, hs, extra)
        for md, mm in itertools.product(MAX_DISTANCE_FRACS, MIN_MARGIN_FRACS):
            params = RecognitionParams(hash_size=hs, max_distance_frac=md,
                                       min_margin_frac=mm)
            rep = evaluate(train, layout, lib, params)
            results.append((params, rep))
            if verbose:
                print(f"  hash={hs:2d} maxd={md:.2f} margin={mm:.2f}  "
                      f"{rep.summary()}")

    def key(item):
        params, rep = item
        return (rep.wrong, rep.unknown, -params.min_margin_frac)

    best_params, best_train = min(results, key=key)
    lib = build_library_from_images(portraits, best_params.hash_size, extra)
    best_holdout = evaluate(holdout, layout, lib, best_params)

    detail = {"train": best_train, "holdout": best_holdout}
    if verbose:
        print(f"\nBest: hash={best_params.hash_size} "
              f"maxd={best_params.max_distance_frac} "
              f"margin={best_params.min_margin_frac}")
        print(f"  train:   {best_train.summary()}")
        print(f"  holdout: {best_holdout.summary()}")
        if best_holdout.wrong:
            print("  WARNING: wrong matches on holdout — inspect confusions "
                  f"{best_holdout.confusions[:10]} before trusting this.")
    return best_params, detail


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--procedural", action="store_true",
                        help="use deterministic fake portraits (no downloads)")
    parser.add_argument("--no-save", action="store_true",
                        help="report only; don't write recognition params")
    args = parser.parse_args()

    variants = None
    if args.procedural:
        portraits = procedural_portrait_set()
        print("Using procedural portraits (smoke run — params NOT saved "
              "unless --procedural runs are all you have).")
    else:
        portraits = _load_real_portraits()
        if portraits is None:
            raise SystemExit(
                "No downloaded portraits found. Run `python tools/"
                "build_library.py` first, or pass --procedural for a smoke run.")
        variants = getattr(_load_real_portraits, "variants", None)
        print(f"Using {len(portraits)} real portraits "
              f"(+{sum(len(v) for v in (variants or {}).values())} variants).")

    best, detail = tune(portraits, args.frames, args.seed, variants)
    if not args.no_save:
        save_params(best)
        print(f"Saved to {library_mod.PARAMS_FILE}")
        if not args.procedural:
            rebuild(best.hash_size)
            print(f"Rebuilt {library_mod.LIBRARY_FILE} at hash_size="
                  f"{best.hash_size}")


if __name__ == "__main__":
    main()

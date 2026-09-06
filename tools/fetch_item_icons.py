"""Download just the item icons, and say exactly what happened.

The full update pulls statistics, portraits, the recognition library and
these, so one quiet failure in the middle is easy to miss. This does the
icons alone and prints the URL it tried, so "the icons are still blank"
has an answer rather than a shrug.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draft_assist.config import ITEMS_DIR  # noqa: E402


def main() -> None:
    from tools.build_library import download_item_icons

    before = len(list(ITEMS_DIR.glob("*.png"))) if ITEMS_DIR.is_dir() else 0
    print(f"assets/items: {before} icons before")
    try:
        download_item_icons(verbose=True)
    except Exception as exc:
        print(f"\nFAILED: {type(exc).__name__}: {exc}")
        print("The item list comes from OpenDota's /constants/items. If the "
              "shape has changed, data_cache/raw/opendota_constants_items.json "
              "holds exactly what came back.")
        raise SystemExit(1)
    after = len(list(ITEMS_DIR.glob("*.png"))) if ITEMS_DIR.is_dir() else 0
    print(f"assets/items: {after} icons now ({ITEMS_DIR})")
    if after == 0:
        raise SystemExit(
            "Nothing was written. The download reported no failures, which "
            "means the item list itself came back empty — check the raw dump.")


if __name__ == "__main__":
    main()

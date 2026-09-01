"""Label an unknown slot crop harvested by tools/replay.py --harvest.

Moves a crop from debug_out/unlabeled/ into the variants library under the
hero you name, so the next rebuild recognises that appearance (this is how
personas/arcanas and odd UI states accumulate into regression coverage).

    python tools/label_slot.py debug_out/unlabeled/frame_0003_dire1.png "Anti-Mage"
    python tools/label_slot.py debug_out/unlabeled/frame_0004_dire2.png empty
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draft_assist.data import store  # noqa: E402
from draft_assist.vision import library  # noqa: E402


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    crop_path, hero_name = Path(sys.argv[1]), sys.argv[2]
    if not crop_path.exists():
        raise SystemExit(f"{crop_path} not found")

    if hero_name.lower() == "empty":
        folder = library.VARIANTS_DIR / "empty"
    else:
        ds = store.load()
        matches = [hid for hid in ds.hero_ids
                   if ds.name(hid).lower() == hero_name.lower()]
        if not matches:
            close = [ds.name(hid) for hid in ds.hero_ids
                     if hero_name.lower() in ds.name(hid).lower()]
            raise SystemExit(f"No hero named '{hero_name}'."
                             + (f" Did you mean: {close}?" if close else ""))
        folder = library.VARIANTS_DIR / str(matches[0])

    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / crop_path.name
    shutil.move(str(crop_path), dest)
    print(f"{crop_path.name} -> {dest}")
    print("Rebuild to include it: python tools/build_library.py")


if __name__ == "__main__":
    main()

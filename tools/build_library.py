"""Download hero portraits (via OpenDota constants -> Steam CDN) into
assets/portraits/base/ and build the perceptual-hash library.

Persona/arcana variant portraits are not on the CDN in a discoverable form;
they accumulate instead in assets/portraits/variants/<hero_id>/ — harvested
from real frames by tools/replay.py --harvest or dropped in by hand — and
are picked up automatically on every rebuild (many-to-one, same hero id).

Needs network. Re-run after a patch adds a hero.
"""

import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draft_assist.data.opendota import fetch_heroes, fetch_items  # noqa: E402
from draft_assist.ui.item_icons import ITEMS_DIR, slug  # noqa: E402
from draft_assist.vision import library  # noqa: E402

CDN = "https://cdn.cloudflare.steamstatic.com"


def main() -> None:
    heroes = fetch_heroes()
    library.BASE_DIR.mkdir(parents=True, exist_ok=True)
    library.VARIANTS_DIR.mkdir(parents=True, exist_ok=True)
    (library.VARIANTS_DIR / "empty").mkdir(exist_ok=True)

    downloaded = skipped = 0
    for hid, h in sorted(heroes.items()):
        img_path = h.get("img", "")
        if not img_path:
            print(f"  hero {hid} ({h['name']}): no img path in constants, skipping")
            continue
        short = h["internal_name"].removeprefix("npc_dota_hero_") or str(hid)
        dest = library.BASE_DIR / f"{hid}_{short}.png"
        if dest.exists():
            skipped += 1
            continue
        url = img_path if img_path.startswith("http") else CDN + img_path
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        downloaded += 1
        time.sleep(0.1)
    print(f"Portraits: {downloaded} downloaded, {skipped} already present")

    download_item_icons()

    params = library.load_params()
    lib = library.rebuild(params.hash_size)
    print(f"Library rebuilt: {len(lib)} entries at hash_size="
          f"{params.hash_size} -> {library.LIBRARY_FILE}")
    print("Next: `python -m draft_assist.proving.tune` to pick the "
          "recognition operating point against these portraits.")


def download_item_icons() -> None:
    """Item art for the draft screen's item row.

    Named by a slug of the DISPLAY name, so `rules/items.yaml` needs no
    internal keys and the loader needs no lookup table. Failures here are
    reported and skipped: an item without a picture falls back to its name,
    and losing the whole portrait build over one 404 would be absurd.
    """
    ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    items = fetch_items()
    downloaded = skipped = failed = 0
    for name, img_path in sorted(items.items()):
        dest = ITEMS_DIR / f"{slug(name)}.png"
        if dest.exists():
            skipped += 1
            continue
        url = img_path if img_path.startswith("http") else CDN + img_path
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            downloaded += 1
        except requests.RequestException as exc:
            print(f"  item '{name}': {exc}")
            failed += 1
        time.sleep(0.05)
    print(f"Item icons: {downloaded} downloaded, {skipped} already present"
          + (f", {failed} failed" if failed else ""))


if __name__ == "__main__":
    main()

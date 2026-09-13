"""Say which items in the rules have no picture, and WHY.

An item with no icon draws its name instead, which is a normal fallback
and looks exactly the same whatever went wrong — a download that 404'd, a
rule naming an item OpenDota does not list, a name that matches two icons
and is therefore refused, or a file on disk that will not decode. "Eul's
Scepter isn't showing the image" cannot be answered from the picture, so
this answers it from the disk.

Reads only. Fixing a missing file is Settings > Downloads > Item icons, which
skips what is already there and so retries exactly the ones that failed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draft_assist.config import ITEMS_DIR, RULES_FILE, item_slug  # noqa: E402


def rule_items() -> list[str]:
    """Every item named in the rules, in the order they first appear."""
    import yaml
    with open(RULES_FILE, encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    rules = loaded.get("rules", loaded if isinstance(loaded, list) else [])
    seen: list[str] = []
    for rule in rules:
        name = (rule or {}).get("item")
        if name and name not in seen:
            seen.append(name)
    return seen


def main() -> None:
    print(f"Icons live in {ITEMS_DIR}")
    if not ITEMS_DIR.is_dir():
        raise SystemExit("The folder does not exist — the download has never "
                         "run. Settings > Downloads > Item icons.")
    slugs = sorted(p.stem for p in ITEMS_DIR.glob("*.png"))
    print(f"{len(slugs)} icons on disk\n")

    from PyQt6.QtGui import QGuiApplication, QPixmap
    app = QGuiApplication.instance() or QGuiApplication([])   # noqa: F841

    missing = 0
    for name in rule_items():
        key = item_slug(name)
        matches = [s for s in slugs if s == key or s.startswith(key)]
        if not matches:
            near = [s for s in slugs if key.split("_")[0] in s][:4]
            print(f"NO FILE     {name}  (looked for {key}*)"
                  + (f"  near: {', '.join(near)}" if near else ""))
            missing += 1
        elif len(matches) > 1 and key not in matches:
            print(f"AMBIGUOUS   {name}  matches {', '.join(matches)}")
            missing += 1
        else:
            chosen = key if key in matches else matches[0]
            if QPixmap(str(ITEMS_DIR / f"{chosen}.png")).isNull():
                print(f"WILL NOT LOAD {name}  ->  {chosen}.png "
                      f"({(ITEMS_DIR / f'{chosen}.png').stat().st_size} bytes)")
                missing += 1
    print(f"\n{missing} of the rules' items have no usable picture."
          if missing else "\nEvery item named in the rules has a picture.")


if __name__ == "__main__":
    main()

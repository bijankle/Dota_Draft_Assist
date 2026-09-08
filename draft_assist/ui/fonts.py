"""Fonts the app loads from disk at startup.

Qt will only use a family it knows about, and a .ttf sitting in a folder
is not installed — so anything supplied rather than system-installed has
to be registered with `QFontDatabase` before the stylesheet asks for it by
name. That is all this does.

**These ARE committed, and they are OPEN.** Alegreya is under the SIL
Open Font License 1.1 — the licence is in the font's own metadata and
`OFL.txt` sits beside it — which permits redistribution outright rather
than on anybody's say-so. That is the bar: a file only goes in here if its
licence says yes on its own. Everything else fetched from elsewhere — the
hero portraits, the item icons, a supplied `app.ico` — stays out of the
repository because it is Valve's or Blizzard's artwork.

Committed or not, a MISSING font is still normal rather than an error: the
stylesheet names a fallback behind each family, so a checkout without the
files opens a readable app. Nothing here raises.
"""

from pathlib import Path

from ..config import ASSETS_DIR

FONTS_DIR = ASSETS_DIR / "fonts"
# What the stylesheet asks for by name. Registering the files is what
# makes these resolvable; without them the stylesheet falls through to the
# next family in its list.
TITLE_FAMILY = "Alegreya Black"       # the app's own name in the title bar
BODY_FAMILY = "Alegreya"              # everything else


def load_bundled(directory: Path | None = None) -> list[str]:
    """Register every font file in `assets/fonts/`. Returns the families.

    Called once, before the stylesheet is applied — a family registered
    afterwards is not picked up by rules already resolved.
    """
    from PyQt6.QtGui import QFontDatabase

    directory = directory if directory is not None else FONTS_DIR
    families: list[str] = []
    if not directory.is_dir():
        return families
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in (".ttf", ".otf"):
            continue
        handle = QFontDatabase.addApplicationFont(str(path))
        if handle != -1:
            families.extend(QFontDatabase.applicationFontFamilies(handle))
    return families

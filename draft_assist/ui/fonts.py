"""Fonts the app loads from disk at startup.

Qt will only use a family it knows about, and a .ttf sitting in a folder
is not installed — so anything supplied rather than system-installed has
to be registered with `QFontDatabase` before the stylesheet asks for it by
name. That is all this does.

**Nothing here is committed.** `assets/fonts/` is gitignored, the same
rule the portraits, the item icons and a supplied app icon follow: a font
file is somebody else's work and whether it may be redistributed is not
ours to assume. The app therefore treats a missing font exactly the way it
treats a missing portrait — normal, not an error — and the stylesheet
names a fallback after it.
"""

from pathlib import Path

from ..config import ASSETS_DIR

FONTS_DIR = ASSETS_DIR / "fonts"
# What the stylesheet asks for by name. Registering the files is what
# makes these resolvable; without them the stylesheet falls through to the
# next family in its list.
TITLE_FAMILY = "LifeCraft"            # the app's own name in the title bar
BODY_FAMILY = "ITC Novarese Std"      # everything else


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

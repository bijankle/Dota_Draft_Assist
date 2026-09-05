"""Hero portraits for the draft tiles, from the recognition library.

The app already downloads every hero's portrait so the vision pipeline can
match against them (`assets/portraits/base/<hero_id>_<name>.png`), so the UI
costs nothing to draw the same art — and a tile that looks like the pick bar
is read faster than a row of names, which is the whole point of the change.

A missing file is normal, not an error: the portraits are downloaded by a
menu action and a fresh install has none. Callers get None and draw a plain
tile.
"""

import re
from pathlib import Path

from PyQt6.QtGui import QPixmap

from ..config import PORTRAITS_DIR

BASE_DIR = PORTRAITS_DIR / "base"

_paths: dict[int, Path] | None = None
_cache: dict[int, QPixmap | None] = {}


def _index() -> dict[int, Path]:
    """hero id -> portrait file, read from disk once.

    Reads the module's BASE_DIR at call time rather than binding it as a
    default, so pointing the app at another folder is a one-line change
    that actually takes effect.
    """
    global _paths
    if _paths is None:
        found: dict[int, Path] = {}
        base_dir = BASE_DIR
        if base_dir.is_dir():
            for path in sorted(base_dir.glob("*.png")) + \
                    sorted(base_dir.glob("*.jpg")):
                m = re.match(r"(\d+)_", path.name)
                if m:
                    found.setdefault(int(m.group(1)), path)
        _paths = found
    return _paths


def portrait(hero_id: int | None) -> QPixmap | None:
    """The hero's portrait, or None when it has not been downloaded."""
    if hero_id is None:
        return None
    if hero_id not in _cache:
        path = _index().get(hero_id)
        pixmap = QPixmap(str(path)) if path is not None else None
        _cache[hero_id] = (pixmap if pixmap is not None and not pixmap.isNull()
                           else None)
    return _cache[hero_id]


def forget() -> None:
    """Drop the cache — after a portrait download, or in tests."""
    global _paths
    _paths = None
    _cache.clear()

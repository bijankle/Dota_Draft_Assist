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

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

from ..config import PORTRAITS_DIR

BASE_DIR = PORTRAITS_DIR / "base"

_paths: dict[int, Path] | None = None
_cache: dict[int, QPixmap | None] = {}
# Scaled copies, keyed by (hero, width, height). Rescaling a 256x144 image
# with a smooth transform inside paintEvent is the classic Qt performance
# mistake: ten tiles and twenty matrix headers repainting on every tick is
# thirty rescales a frame, for pictures that never change.
_scaled: dict[tuple[int, int, int], QPixmap] = {}


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


def scaled(hero_id: int | None, width: int, height: int) -> QPixmap | None:
    """The portrait, fitted inside width x height, cached at that size.

    Aspect ratio is kept, so the result is usually smaller than the box in
    one direction; callers centre it.
    """
    art = portrait(hero_id)
    if art is None or width < 1 or height < 1:
        return None
    key = (int(hero_id), int(width), int(height))
    hit = _scaled.get(key)
    if hit is None:
        hit = art.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
        _scaled[key] = hit
    return hit


def filling(hero_id: int | None, width: int, height: int) -> QPixmap | None:
    """The portrait scaled to COVER width x height, cropped to centre.

    `scaled` fits inside the box and leaves bars; that is right for a
    header, where the whole picture is the point. Behind a grid cell the
    picture is a backdrop for a number and a letterboxed portrait reads as
    a mistake, so this one fills the cell and loses the edges instead.
    """
    art = portrait(hero_id)
    if art is None or width < 1 or height < 1:
        return None
    key = ("fill", int(hero_id), int(width), int(height))
    hit = _scaled.get(key)
    if hit is None:
        grown = art.scaled(width, height,
                           Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                           Qt.TransformationMode.SmoothTransformation)
        hit = grown.copy((grown.width() - width) // 2,
                         (grown.height() - height) // 2, width, height)
        _scaled[key] = hit
    return hit


def forget() -> None:
    """Drop the caches — after a portrait download, or in tests."""
    global _paths
    _paths = None
    _cache.clear()
    _scaled.clear()

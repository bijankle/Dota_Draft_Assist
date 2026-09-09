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
# Whether the artwork is on disk at all. Only True is remembered — see
# `any_downloaded`.
_have: bool = False


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


def any_downloaded() -> bool:
    """Has this machine got the artwork at all?

    A FRESH INSTALL HAS NONE, and that is the state the first-run banner
    exists for: the pictures are not in the repository (they are Valve's)
    and are fetched to the user's own disk, so somebody handed a copy of
    this app opens it to a grid of empty plates until they run the
    download.

    IT DELIBERATELY DOES NOT BUILD `_index`. That index caches ABSENCE —
    it remembers finding nothing just as firmly as it remembers finding
    something — and this question is asked from the banner, which the
    live loop refreshes. Answering it through the index would therefore
    cache "there are no portraits" on the first tick after startup, which
    is before any download can have run, and nothing but `forget` would
    ever revisit it. A single cheap look at the directory instead, with
    only the TRUE answer remembered: once the artwork is on disk it does
    not leave, whereas "not yet" has to stay askable or the banner would
    never clear.
    """
    global _have
    if not _have:
        _have = BASE_DIR.is_dir() and any(BASE_DIR.iterdir())
    return _have


def forget() -> None:
    """Drop the caches — after a portrait download, or in tests."""
    global _paths, _have
    _paths = None
    _have = False
    _cache.clear()
    _scaled.clear()

"""Item icons for the draft screen, downloaded alongside the hero portraits.

Same deal as `ui/portraits.py`: the file is looked up by a slug of the
item's display name, so `rules/items.yaml` can go on saying "Black King
Bar" the way a person writes it rather than carrying an internal key to
suit the loader.

A missing icon is NORMAL rather than an error — a fresh install has none
until the download has run, and a rule can name an item OpenDota does not
list. Callers get None and draw the name instead.
"""

import re
from pathlib import Path

from PyQt6.QtGui import QPixmap

from ..config import ASSETS_DIR

ITEMS_DIR = ASSETS_DIR / "items"

_cache: dict[str, QPixmap | None] = {}


def slug(name: str) -> str:
    """'Black King Bar' -> 'black_king_bar'."""
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def icon(item_name: str) -> QPixmap | None:
    key = slug(item_name)
    if key not in _cache:
        found = None
        for suffix in (".png", ".jpg"):
            path = ITEMS_DIR / f"{key}{suffix}"
            if path.exists():
                pixmap = QPixmap(str(path))
                if not pixmap.isNull():
                    found = pixmap
                break
        _cache[key] = found
    return _cache[key]


def forget() -> None:
    """Drop the cache — after a download, or in tests."""
    _cache.clear()

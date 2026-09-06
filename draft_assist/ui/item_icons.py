"""Item icons for the draft screen, downloaded alongside the hero portraits.

Same deal as `ui/portraits.py`: the file is looked up by a slug of the
item's display name, so `rules/items.yaml` can go on saying "Black King
Bar" the way a person writes it rather than carrying an internal key to
suit the loader.

A missing icon is NORMAL rather than an error — a fresh install has none
until the download has run, and a rule can name an item OpenDota does not
list. Callers get None and draw the name instead.
"""

from PyQt6.QtGui import QPixmap

from ..config import ITEMS_DIR, item_slug as slug

_cache: dict[str, QPixmap | None] = {}
_available: list[str] | None = None


def _slugs() -> list[str]:
    """Every icon on disk, by slug, read once."""
    global _available
    if _available is None:
        _available = sorted(p.stem for p in ITEMS_DIR.glob("*.png")) \
            if ITEMS_DIR.is_dir() else []
    return _available


def _resolve(name: str) -> str | None:
    """Rule name -> icon slug, exactly or by unique prefix.

    The rules say "Eul's Scepter"; the item's published display name is
    "Eul's Scepter of Divinity". Rather than make the rules file carry the
    long form — it is written by a person, for a person — a rule name that
    is a unique PREFIX of exactly one downloaded icon resolves to it. Two
    matches is ambiguous and resolves to nothing, because guessing between
    two items is worse than showing the name.
    """
    key = slug(name)
    slugs = _slugs()
    if key in slugs:
        return key
    prefixed = [s for s in slugs if s.startswith(key)]
    return prefixed[0] if len(prefixed) == 1 else None


def any_downloaded() -> bool:
    """True when the icon pack has been fetched at all.

    One missing icon is normal; NONE at all means the download has not run,
    and the strip should say so rather than looking permanently broken.
    """
    return ITEMS_DIR.is_dir() and any(ITEMS_DIR.glob("*.png"))


def icon(item_name: str) -> QPixmap | None:
    key = slug(item_name)
    if key not in _cache:
        found = None
        resolved = _resolve(item_name)
        if resolved is not None:
            pixmap = QPixmap(str(ITEMS_DIR / f"{resolved}.png"))
            found = pixmap if not pixmap.isNull() else None
        _cache[key] = found
    return _cache[key]


def forget() -> None:
    """Drop the caches — after a download, or in tests."""
    global _available
    _available = None
    _cache.clear()
    from .item_row import forget_scaled
    forget_scaled()

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
    # A RECIPE IS NOT A CANDIDATE. Valve publishes the scroll that builds
    # an item as an item of its own - "Eul's Scepter Recipe" beside
    # "Eul's Scepter of Divinity" - so a rule saying "Eul's Scepter" is a
    # prefix of TWO and was refused as ambiguous, which is this
    # resolver working exactly as designed and still drawing no icon.
    #
    # It is not ambiguous in any sense that matters: nothing advises you
    # to buy a recipe, so the two were never both answers to the
    # question. Dropping them is also general - most items have a recipe,
    # so any future rule named by its short form would have hit this.
    #
    # Measured against the whole file: Eul's was the ONLY one of the 24
    # items the rules name that could not resolve, and this resolves it.
    real = [s for s in prefixed if "recipe" not in s]
    if len(real) == 1:
        return real[0]
    return prefixed[0] if len(prefixed) == 1 else None


def why_missing(name: str) -> str:
    """Which of the four causes it is, for an item drawing its name.

    A MISSING ICON HAS FOUR CAUSES AND ONE APPEARANCE — the download
    404'd, the rules name an item OpenDota does not list, the name
    matches two icons and is refused rather than guessed at, or the file
    will not decode — and the picture cannot say which. That is what
    `tools/check_item_icons.py` was written for, and it has no menu item
    any more, so the answer goes where somebody looking at the blank tile
    already is: its tooltip.
    """
    key = slug(name)
    slugs = _slugs()
    if not slugs:
        return "No item icons downloaded yet — Settings > Downloads."
    matches = [s for s in slugs if s.startswith(key)]
    if not matches:
        return ("No icon was downloaded under this name: either the "
                "download failed for it, or the rules call it something "
                "OpenDota does not. Settings > Downloads > Item icons "
                "retries exactly the missing ones.")
    if len(matches) > 1:
        return (f"This name matches {len(matches)} icons "
                f"({', '.join(matches[:3])}) and is refused rather than "
                "guessed at — drawing the wrong item is worse.")
    return f"The file will not decode: {matches[0]}.png"


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

"""Small persisted UI preferences (overlay position, collapsed state).

Deliberately separate from calibration and from the data cache: these are
per-machine conveniences, gitignored, and losing the file costs nothing but
a re-drag of the overlay.
"""

import json
from pathlib import Path

from ..config import REPO_ROOT

SETTINGS_FILE = REPO_ROOT / "ui_settings.json"

# The ceiling on both "how many to show" settings. Twenty suggested picks
# is already more than a draft screen can be read against; past that the
# strip is a list and the point of a strip is that it is not one.
MAX_SHOWN = 20
# The keys that ceiling applies to, clamped on the way IN as well as out —
# a hand-edited file asking for two hundred tiles must not be honoured.
COUNTS = ("suggested_picks", "suggested_items")

DEFAULTS = {
    "overlay_x": 40,
    "overlay_y": 40,
    "overlay_expanded": True,
    "overlay_rows": 6,
    # Start a recording by itself when Dota reaches the draft. On by
    # default: the session you most want is the one you were not
    # expecting, and remembering to press Record before queueing is
    # exactly the thing that gets forgotten.
    "auto_record": True,
    # Both sources on by default: they answer different
    # questions and the app wants both. Turning one off is a
    # debugging step, never a mode.
    "use_gsi": True,
    "use_vision": True,
    # How see-through the window is, remembered between runs. It HAS to be
    # listed here: `save` writes only the keys DEFAULTS names, so a
    # preference the app set but this dict did not know about was written
    # by the slider, kept in memory, and dropped on the way to disk.
    "overlay_opacity": 0.7,
    # How many tiles each strip shows AT MOST. A cap is not a quota: the
    # item strip stops at whatever clears the severity floor, so raising
    # this to 20 does not produce 20 items, it only stops truncating the
    # ones that were already worth showing.
    "suggested_picks": 8,
    "suggested_items": 5,
}


def clamp_count(value, fallback: int) -> int:
    """A count between 1 and MAX_SHOWN, or the fallback if it is not one."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(1, min(MAX_SHOWN, number))


def load(path: Path | None = None) -> dict:
    """Path is resolved at call time, never bound as a default, so the
    destination can be repointed (tests do this)."""
    path = path or SETTINGS_FILE
    settings = dict(DEFAULTS)
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return settings
        if isinstance(stored, dict):
            # Only known keys, so a stale file can never inject surprises.
            settings.update({k: v for k, v in stored.items() if k in DEFAULTS})
    for key in COUNTS:
        settings[key] = clamp_count(settings.get(key), DEFAULTS[key])
    return settings


def save(settings: dict, path: Path | None = None) -> None:
    path = path or SETTINGS_FILE
    settings = dict(settings)
    for key in COUNTS:
        settings[key] = clamp_count(settings.get(key), DEFAULTS[key])
    try:
        path.write_text(
            json.dumps({k: settings.get(k, v) for k, v in DEFAULTS.items()},
                       indent=2),
            encoding="utf-8")
    except OSError:
        pass          # a preference failing to save must never break the app

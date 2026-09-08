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

# The default fortnight, and the ceiling the settings box offers. A year
# is "stop asking" without being 0, which is off outright.
DATA_REMINDER_DAYS = 14
MAX_REMINDER_DAYS = 365

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
    # How old the statistics have to get before the app says anything at
    # all about it: ONE dialog when the app opens, and nothing on screen
    # for the fortnight before that. The age used to be a banner at the
    # top, a pill on the tab row and a segment of the status line — three
    # copies of a number worth acting on about twice a month. Zero turns
    # the prompt off.
    "data_reminder_days": DATA_REMINDER_DAYS,
    # Off by default. It is the user's own app on the user's own machine,
    # and something that sits above the draft the whole time it is running
    # has to be asked for rather than assumed.
    "ads_enabled": False,
    # THE WINDOW IS LOCKED AT ITS SIZE, at the user's request, and it is
    # unlocked from View > Resize window (lock). A draft is read at a
    # glance with the cursor moving fast near the window's edges, and a
    # window that resizes when you meant to click a pick has cost the
    # pick. The size it is locked AT is remembered too, or unlocking,
    # resizing and locking again would be undone by the next restart.
    "window_locked": True,
    "window_w": 1240,
    "window_h": 820,
}


def clamp_count(value, fallback: int) -> int:
    """A count between 1 and MAX_SHOWN, or the fallback if it is not one."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(1, min(MAX_SHOWN, number))


def clamp_days(value, fallback: int) -> int:
    """Whole days between 0 (never ask) and MAX_REMINDER_DAYS."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(0, min(MAX_REMINDER_DAYS, number))


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
    settings["data_reminder_days"] = clamp_days(
        settings.get("data_reminder_days"), DATA_REMINDER_DAYS)
    return settings


def save(settings: dict, path: Path | None = None) -> None:
    path = path or SETTINGS_FILE
    settings = dict(settings)
    for key in COUNTS:
        settings[key] = clamp_count(settings.get(key), DEFAULTS[key])
    settings["data_reminder_days"] = clamp_days(
        settings.get("data_reminder_days"), DATA_REMINDER_DAYS)
    try:
        path.write_text(
            json.dumps({k: settings.get(k, v) for k, v in DEFAULTS.items()},
                       indent=2),
            encoding="utf-8")
    except OSError:
        pass          # a preference failing to save must never break the app

"""Small persisted UI preferences (overlay position, collapsed state).

Deliberately separate from calibration and from the data cache: these are
per-machine conveniences, gitignored, and losing the file costs nothing but
a re-drag of the overlay.
"""

import json
from pathlib import Path

from ..config import REPO_ROOT

SETTINGS_FILE = REPO_ROOT / "ui_settings.json"

DEFAULTS = {
    "overlay_enabled": False,
    "overlay_x": 40,
    "overlay_y": 40,
    "overlay_expanded": True,
    "overlay_rows": 6,
    # Start a recording by itself when Dota reaches the draft. On by
    # default: the session you most want is the one you were not
    # expecting, and remembering to press Record before queueing is
    # exactly the thing that gets forgotten.
    "auto_record": True,
}


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
    return settings


def save(settings: dict, path: Path | None = None) -> None:
    path = path or SETTINGS_FILE
    try:
        path.write_text(
            json.dumps({k: settings.get(k, v) for k, v in DEFAULTS.items()},
                       indent=2),
            encoding="utf-8")
    except OSError:
        pass          # a preference failing to save must never break the app

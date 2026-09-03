"""Paths and runtime configuration. The Stratz key is read from .env at
runtime, never hardcoded."""

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_CACHE = REPO_ROOT / "data_cache"
RAW_DUMP_DIR = DATA_CACHE / "raw"
CAPTURES_DIR = REPO_ROOT / "captures"
DEBUG_OUT = REPO_ROOT / "debug_out"
ASSETS_DIR = REPO_ROOT / "assets"
PORTRAITS_DIR = ASSETS_DIR / "portraits"
RULES_FILE = REPO_ROOT / "rules" / "items.yaml"
LAYOUT_FILE = REPO_ROOT / "draft_assist" / "vision" / "layout_default.json"
# Local calibration nudges (gitignored); overrides the default layout.
CALIBRATION_FILE = REPO_ROOT / "calibration_local.json"

# Which rank brackets the statistics are drawn from.
#
# This is a DATA-PULL setting, not a display one: the baselines and the
# interaction matrices are built for the chosen brackets, so changing it
# means rebuilding the dataset. The choice is stored in preferences.json
# (gitignored) and read at call time, so the app and the pull subprocess
# always agree.
#
# The default follows the original reasoning: aim one bracket above where
# you play, so the advice reflects the games you are trying to win rather
# than the ones you already do. Two adjacent brackets are combined for
# sample size.
ALL_BRACKETS = ("HERALD", "GUARDIAN", "CRUSADER", "ARCHON",
                "LEGEND", "ANCIENT", "DIVINE", "IMMORTAL")
DEFAULT_TARGET_BRACKETS = ("ANCIENT", "DIVINE")
PREFS_FILE = REPO_ROOT / "preferences.json"


def target_brackets() -> tuple[str, ...]:
    """The brackets statistics are pulled for, resolved at call time."""
    import json
    try:
        stored = json.loads(PREFS_FILE.read_text(encoding="utf-8"))
        chosen = stored.get("target_brackets")
    except (OSError, json.JSONDecodeError, AttributeError):
        return DEFAULT_TARGET_BRACKETS
    if not isinstance(chosen, list):
        return DEFAULT_TARGET_BRACKETS
    # Keep canonical rank order regardless of what order they were picked
    # in, and drop anything unrecognised rather than failing the pull.
    valid = tuple(b for b in ALL_BRACKETS if b in chosen)
    return valid or DEFAULT_TARGET_BRACKETS


def save_target_brackets(brackets) -> None:
    import json
    ordered = [b for b in ALL_BRACKETS if b in set(brackets)]
    if not ordered:
        raise ValueError("at least one bracket must be selected")
    PREFS_FILE.write_text(
        json.dumps({"target_brackets": ordered}, indent=2), encoding="utf-8")


# Backwards-compatible alias; prefer target_brackets() so a changed
# preference takes effect without a restart.
TARGET_BRACKETS = DEFAULT_TARGET_BRACKETS

# Cached data older than this is considered stale and triggers a warning in
# the UI (the pull itself is a manual/daily action; the live loop never
# makes network calls).
CACHE_MAX_AGE_HOURS = 36


def stratz_api_key() -> str:
    load_dotenv(REPO_ROOT / ".env")
    key = os.environ.get("STRATZ_API_KEY", "").strip()
    if not key or key == "your-stratz-api-key-here":
        raise RuntimeError(
            "STRATZ_API_KEY not set. Copy .env.example to .env and paste "
            "your key from stratz.com (the .env file is gitignored)."
        )
    return key

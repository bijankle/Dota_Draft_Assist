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

# Target bracket: user is Legend-Ancient, stats come from one bracket above —
# Ancient and Divine combined (summed wins / summed picks). See CLAUDE.md.
TARGET_BRACKETS = ("ANCIENT", "DIVINE")

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

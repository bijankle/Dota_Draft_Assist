"""Which accounts this machine has looked at, and when.

LOCAL ONLY, and that is the point of the file rather than an aside: it is
gitignored, exactly like `ui_settings.json` and the Stratz key, so sending
someone a copy of this app sends them none of your match history and none
of your account numbers. Open it on their machine and the list is empty
until they add their own; add one and it is there the next time they open
the app.

What is kept is deliberately thin — the account id, the name it resolved
to, when it was last run and the headline of that run — so the top of the
tab can say "last run on the 3rd, 412 matches, 51.2%" without either
re-running or storing a copy of somebody's match history on disk. The
workbook is where a run is kept; this is a bookmark.
"""

import json
from pathlib import Path

from ..config import REPO_ROOT

# Beside the other per-machine files, and in `.gitignore` with them.
STORE_FILE = REPO_ROOT / "history_accounts.json"
MAX_REMEMBERED = 12


def _path(path: Path | None = None) -> Path:
    """Resolved at CALL time, never as a default argument.

    A default is evaluated once at import, so a test that repointed the
    constant would still write into the repository — which has already
    happened once in this codebase, with the calibration file.
    """
    return path or STORE_FILE


def load(path: Path | None = None) -> list:
    try:
        with open(_path(path), encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return []
    if not isinstance(raw, list):
        return []
    return [row for row in raw
            if isinstance(row, dict) and isinstance(row.get("account_id"), int)]


def save(rows: list, path: Path | None = None) -> None:
    try:
        with open(_path(path), "w", encoding="utf-8") as handle:
            json.dump(rows[:MAX_REMEMBERED], handle, indent=2)
    except OSError:
        pass            # a bookmark that cannot be written is not a fault


def remember(account_id: int, name: str = "", *, when: str = "",
             matches: int = 0, wins: int = 0, options: dict | None = None,
             path: Path | None = None) -> list:
    """Put this account at the top of the list, keeping what it knew.

    Merged rather than replaced: running an account without a name (an id
    typed straight in) must not wipe the name a search found earlier, and
    opening the tab must not blank the last run just by selecting one.
    """
    rows = [row for row in load(path) if row["account_id"] != account_id]
    kept = next((row for row in load(path)
                 if row["account_id"] == account_id), {})
    entry = {"account_id": account_id,
             "name": name or kept.get("name", ""),
             "last_run": when or kept.get("last_run", ""),
             "matches": matches or kept.get("matches", 0),
             "wins": wins or kept.get("wins", 0),
             "options": options or kept.get("options", {})}
    rows.insert(0, entry)
    save(rows, path)
    return rows


def forget(account_id: int, path: Path | None = None) -> list:
    rows = [row for row in load(path) if row["account_id"] != account_id]
    save(rows, path)
    return rows


def label(row: dict) -> str:
    """How a remembered account reads in the dropdown."""
    name = (row.get("name") or "").strip()
    return f"{name} · {row['account_id']}" if name else str(row["account_id"])

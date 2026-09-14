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
    """How a remembered account reads in the dropdown.

    THE NUMBER LEADS AND THE NAME IS IN BRACKETS AFTER IT, at the user's
    request: the friend ID is what the field takes and what this file is
    keyed on, so it is the identity — but nobody remembers which nine
    digit number was theirs a fortnight later, and everybody recognises
    the name beside it. An account whose name could not be resolved reads
    as its number alone rather than as an empty pair of brackets.
    """
    name = (row.get("name") or "").strip()
    return f"{row['account_id']} ({name})" if name else str(row["account_id"])


# ---- what a fresh install starts on -------------------------------------
#
# THE ACCOUNT THIS TAB OPENS ON BEFORE ANYBODY HAS LOOKED ONE UP, at the
# user's request: "i think it would be cool to have topson steam ID be the
# one that gets used for the app by default", and then, on what "by
# default" means: "by default i mean only when its being setup. If the
# user searches for their account to analyse it should be remembered and
# appear when the app is closed and reopened."
#
# So it is a STARTING VALUE, not a setting and not a remembered account.
# It is never written into `history_accounts.json` — that file is the list
# of accounts THIS MACHINE has actually looked at, and an entry nobody ran
# would read as a run that happened. The moment a real account is measured
# it is remembered, it is what `_load_accounts` adopts on the next start,
# and this number is never seen again on that machine.
#
# WHY A REAL ACCOUNT IS RIGHT HERE AND WRONG IN THE FIXTURES. The test
# fixtures use a MADE-UP id (see `test_the_example_account_is_not_a_real_
# one`) because there they stand in for the player themselves — payloads,
# names, a match history — and pinning a stranger's identity to that data
# would be inventing a record about them. This is the opposite job: the
# tab needs an account with a real public match history behind it so the
# Run button has something to show, and a number that cannot exist would
# come back empty and read as the app being broken. A professional
# player's account id is public and carries no personal data of anybody's.
EXAMPLE_ACCOUNT = 94054712
EXAMPLE_NAME = "Topson"


def starting_account(path: Path | None = None) -> int | None:
    """The id to open the box on, or None once this machine has its own."""
    return None if load(path) else EXAMPLE_ACCOUNT

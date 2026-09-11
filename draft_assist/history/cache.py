"""The last run for each account, kept on disk so opening the tab is free.

**THE HISTORY TAB USED TO COST A FETCH EVERY TIME YOU LOOKED AT IT.** The
run is a few hundred matches over a free API, so seeing last week's answer
again meant waiting for it to be measured again — and the tab opened blank
until you did. At the user's request the whole run is now kept, and it is
re-fetched only when they ask: a new account ID, or Update on one already
there.

**WHAT IS STORED IS THE RAW MATCHES, NOT THE FINDINGS.** The blocks are
recomputed from the matches on the way back in (`rebuild`), which costs
milliseconds and buys two things. The workbook's raw sheet still has
something to draw from, so Export works with no network at all. And the
analysis can never be stale in the dangerous way — change a floor or a
sigma in `analyse.py` and every cached run reflects it immediately,
instead of showing numbers computed by a version of the code that is no
longer in the app.

This is a REVERSAL of the rule beside it in `store.py`, which keeps a
bookmark precisely so that no copy of anybody's match history sits on
disk. The privacy property that mattered survives it: this folder is
gitignored exactly like `history_accounts.json` and `.env`, so sending
somebody a copy of this app still sends them none of it. What changed is
only how much of your own run your own machine keeps for you.
"""

import json
from dataclasses import asdict, fields
from datetime import datetime
from pathlib import Path

from ..config import REPO_ROOT
from .report import Options, Report
from .shape import Match

# Beside the other per-machine files, and in `.gitignore` with them.
CACHE_DIR = REPO_ROOT / "history_cache"
# One run per account, and the accounts themselves are capped at
# `store.MAX_REMEMBERED` — so this is bounded by that rather than growing
# for ever. Pruning happens on every save.
KEEP = 12


def cache_dir() -> Path:
    """Resolved at CALL time, never bound as a default argument — the rule
    this codebase learned from the calibration file, where a module-level
    default let a test write into the real repository."""
    return CACHE_DIR


# ITEM IDS ARE NOT NAMES, AND THE REBUILD HAS NO NETWORK. The item block
# keys its buckets by OpenDota's numeric item id and turns them into words
# with a map fetched from `/constants/items`. `rebuild` recomputes every
# block on the way back in and had no map to give it, so a CACHED run —
# which is what the tab shows whenever you open an account without
# re-running it — printed "Item 1", "Item 63", "Item 116" down the whole
# block. The names were only ever right on the run that fetched them.
# So the map is written beside the runs and read back with them. It is
# tiny, it changes about twice a year, and it is the one part of a run
# that is not about the player at all.
NAMES_FILE = "items.json"
# AND THE MAP IS BUNDLED, so it never depends on a fetch at all.
# Writing it beside the runs fixed the rebuild, and left a hole the user
# walked straight into: the file only exists after a run has written one,
# so an install that updated without re-measuring went on printing ids
# until they pressed Update, and it "fixed itself" with nothing having
# been done differently. Worse, the fetch it depends on fails SILENTLY —
# `opendota.item_names` answers {} on any ApiError, `save_item_names({})`
# writes nothing, and the block prints numbers with nothing on screen
# saying why. That is the item icons' "four causes and one appearance"
# again, and the answer is the same: do not make a name depend on the
# network. 500 items, twelve kilobytes, changed about twice a year, and
# it is factual data rather than anybody's artwork — the same bar
# `rules/items.yaml` already clears by naming items in this repository.
BUNDLED_NAMES = Path(__file__).with_name("item_names.json")
_bundled: dict | None = None


def _path(account_id: int, where: Path | None = None) -> Path:
    return (where or cache_dir()) / f"{int(account_id)}.json"


def _match_to_dict(match: Match) -> dict:
    raw = asdict(match)
    # The one field that is not already JSON: keep it as an ISO string and
    # let `_match_from_dict` put it back, rather than recomputing it from
    # `start` — the two could disagree about the timezone.
    raw["when"] = match.when.isoformat()
    return raw


_FIELDS = {f.name for f in fields(Match)}


def _match_from_dict(raw: dict) -> Match | None:
    """One match, or None if the row is not one.

    A row this cannot read is DROPPED rather than raising: the file is
    written by an older version of the app as often as by this one, and a
    cache that cannot be read must degrade to "no cache" rather than
    taking the tab down with it.
    """
    if not isinstance(raw, dict):
        return None
    kept = {k: v for k, v in raw.items() if k in _FIELDS}
    try:
        kept["when"] = datetime.fromisoformat(str(kept.get("when")))
        return Match(**kept)
    except (TypeError, ValueError):
        return None


def save(report: Report, where: Path | None = None) -> bool:
    """Keep this run. Returns whether it landed.

    Never raises: a cache that cannot be written is a slower tab, not a
    failed run, and the run has already finished by the time this is
    called.
    """
    account_id = report.options.account_id
    if not account_id:
        return False
    folder = where or cache_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        payload = {
            "account_id": account_id,
            "name": report.name or "",
            "how": report.how or "",
            "ran_at": report.ran_at.isoformat(),
            "options": report.options.as_dict(),
            "dropped": report.dropped or {},
            "sessions": report.sessions,
            "returned": report.returned,
            "matches": [_match_to_dict(m) for m in report.matches],
        }
        _path(account_id, folder).write_text(
            json.dumps(payload), encoding="utf-8")
    except (OSError, TypeError, ValueError):
        return False
    _prune(folder)
    return True


def run_files(folder: Path) -> list:
    """The cached RUNS in this folder, and nothing else.

    A run is named for the account it holds (`<account id>.json`), and it
    is not the only thing living here: `NAMES_FILE` is the item id -> name
    map, written beside the runs so a rebuild can name items with no
    network. Globbing `*.json` sweeps that up too, which went wrong in
    both directions — `_prune` counted it towards `KEEP` and could DELETE
    it once there were that many accounts, and a reader that assumed
    every file here was a run raised `KeyError: 'matches'` on it.

    Losing the map is not fatal, because `BUNDLED_NAMES` is underneath
    it — but it is the "Item 63" bug from a fourth cause, and a prune
    that deletes a file it does not own is wrong whether or not
    something else happens to catch it.
    """
    if not folder.is_dir():
        return []
    return [path for path in folder.glob("*.json") if path.stem.isdigit()]


def _prune(folder: Path) -> None:
    """Keep the newest `KEEP` runs and drop the rest."""
    try:
        files = sorted(run_files(folder),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for stale in files[KEEP:]:
            stale.unlink()
    except OSError:
        pass


def save_item_names(names: dict, where: Path | None = None) -> bool:
    """Keep the id -> name map for every later rebuild. Never fatal: a run
    that cannot write it still names its own items."""
    if not names:
        return False
    folder = where or cache_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / NAMES_FILE).write_text(
            json.dumps({str(k): v for k, v in names.items()}),
            encoding="utf-8")
        return True
    except OSError:
        return False


def _read_names(path: Path) -> dict:
    """One id -> name file. Keys come back as INTS, because that is what
    the buckets are keyed by and a map keyed by strings would miss every
    one of them silently — the same "Item 63" from a different cause."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key, value in raw.items():
        try:
            out[int(key)] = str(value)
        except (TypeError, ValueError):
            continue
    return out


def bundled_item_names() -> dict:
    """The map that ships with the app. Read once — it is a file inside
    the package, so no test repoints it and nothing invalidates it."""
    global _bundled
    if _bundled is None:
        _bundled = _read_names(BUNDLED_NAMES)
    return dict(_bundled)


def item_names(where: Path | None = None) -> dict:
    """Every id -> name this machine can offer, best last.

    THE BUNDLED MAP IS THE FLOOR and a run's own fetch is the ceiling: a
    fresh install with no run, a cold cache and a failed fetch all still
    name their items, and an item added since this file was cut is still
    picked up the next time the list is fetched.
    """
    names = bundled_item_names()
    names.update(_read_names((where or cache_dir()) / NAMES_FILE))
    return names


def load(account_id: int, picked: dict | None = None,
         where: Path | None = None) -> Report | None:
    """The last run for this account, with its blocks rebuilt, or None.

    `picked` is which analyses the tab currently has ticked; the blocks
    are computed for THOSE rather than for whatever was ticked when the
    run happened, so turning one on shows it without re-fetching.
    """
    try:
        raw = json.loads(_path(account_id, where).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    matches = [m for m in (_match_from_dict(row)
                           for row in raw.get("matches") or [])
               if m is not None]
    if not matches:
        return None
    options = Options.from_dict(raw.get("options") or {}, int(account_id))
    if picked:
        options.picked = dict(picked)
    try:
        ran_at = datetime.fromisoformat(str(raw.get("ran_at")))
    except (TypeError, ValueError):
        ran_at = datetime.now()
    return rebuild(options, matches, raw, ran_at)


def rebuild(options: Options, matches: list, raw: dict,
            ran_at: datetime) -> Report:
    """Recompute the findings from the matches. See the module docstring:
    the analysis is never stored, so it can never be a version behind the
    code drawing it."""
    from . import analyse
    baseline = (sum(1 for m in matches if m.win) / len(matches)
                if matches else 0.0)
    # The remembered map, not {}: see NAMES_FILE. With no map the item
    # block prints raw ids, and this is the path every cached run takes.
    blocks = analyse.build_blocks(matches, baseline, options.picked,
                                  item_names())
    return Report(options=options, how=str(raw.get("how") or ""),
                  name=str(raw.get("name") or ""), matches=matches,
                  blocks=blocks, dropped=dict(raw.get("dropped") or {}),
                  sessions=int(raw.get("sessions") or 0),
                  returned=int(raw.get("returned") or 0), ran_at=ran_at)


def forget(account_id: int, where: Path | None = None) -> None:
    try:
        _path(account_id, where).unlink()
    except OSError:
        pass

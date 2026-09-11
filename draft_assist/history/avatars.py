"""The Steam profile picture for an account, kept on the user's own disk.

WHY IT IS CACHED AT ALL: the row that draws it is on the Draft tab, which
is repainted constantly and must never make a network call. The picture is
therefore fetched exactly once - during a RUN, which is the one moment
this feature is already allowed on the network - and read off disk for
ever after.

WHERE: inside `history_cache/`, which is gitignored, so a copy of this app
carries nobody's face. Same rule as the portraits and the match history
itself. The folder is a SUBDIRECTORY, so `cache.run_files` (which globs
`*.json` at the top level) cannot see it and the prune cannot touch it.

THE URL IS KEPT BESIDE THE PICTURE, in a sidecar, so a changed avatar is
noticed and re-fetched while an unchanged one costs nothing. Keeping it in
the accounts store instead would put one fact in two files; the folder is
the whole state this way.

NOTHING HERE RAISES. A missing, undownloadable or corrupt avatar draws the
fallback initial, which is a normal state rather than a fault - exactly
how a missing hero portrait is treated.
"""

from pathlib import Path

from .cache import cache_dir


def folder(where: Path | None = None) -> Path:
    """Resolved at CALL time, never bound as a default argument - the rule
    this codebase learned from the calibration file."""
    return (where or cache_dir()) / "avatars"


def path_for(account_id: int, where: Path | None = None) -> Path:
    return folder(where) / f"{int(account_id)}.img"


def _sidecar(account_id: int, where: Path | None = None) -> Path:
    return folder(where) / f"{int(account_id)}.url"


def stored(account_id: int, where: Path | None = None) -> Path | None:
    """The picture already on disk, or None. Reads only - safe anywhere,
    including the live loop, because it touches no network."""
    try:
        path = path_for(account_id, where)
        return path if path.is_file() and path.stat().st_size else None
    except OSError:
        return None


def known_url(account_id: int, where: Path | None = None) -> str:
    try:
        return _sidecar(account_id, where).read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return ""


def save(account_id: int, data: bytes, url: str = "",
         where: Path | None = None) -> Path | None:
    """File the bytes under this account. None when it could not be done."""
    if not data:
        return None
    try:
        place = folder(where)
        place.mkdir(parents=True, exist_ok=True)
        path = path_for(account_id, where)
        path.write_bytes(data)
        _sidecar(account_id, where).write_text(url or "", encoding="utf-8")
        return path
    except OSError:
        return None


def ensure(account_id: int, url: str, *, fetch=None,
           where: Path | None = None) -> Path | None:
    """The picture for this account, downloading it only if it has to.

    `fetch` is injected so the tests never reach the network and so the
    one place that DOES is `opendota.avatar_bytes`, named by its caller
    rather than imported here - this module is about the disk.
    """
    if not account_id:
        return None
    have = stored(account_id, where)
    if have is not None and known_url(account_id, where) == (url or ""):
        return have                      # unchanged, so nothing to do
    if not url:
        return have                      # no url: keep whatever is there
    if fetch is None:
        from .opendota import avatar_bytes as fetch
    saved = save(account_id, fetch(url), url, where)
    return saved if saved is not None else have

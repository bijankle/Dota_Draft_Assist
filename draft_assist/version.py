"""What version this is, and which build of it is running.

**A VERSION NUMBER AND A BUILD ARE TWO DIFFERENT ANSWERS**, which is why
both are here. The version is what a person says out loud and what they
quote when something is wrong; the build is what actually identifies the
code, and it is the one that settles "have you got the fix yet".

The build is READ FROM WHEREVER THIS COPY CAME FROM, because the two
kinds of install know different things. A clone knows its commit from
git. A copy unzipped from GitHub has no git at all, and its commit is in
`installed_version.json` — written by the updater, which is the only
thing that ever put code in that folder. A first unzip has neither, and
that is not a fault: it says so and gives the version alone.

Nothing here may raise. It is read by the About box and by the diagnostic
paste, and neither is worth an exception — a missing build is a line that
reads "build unknown", never a dialog that will not open.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# THE ONE PLACE THE NUMBER IS SPELLED. Raise it here and the About box,
# the diagnostic paste and anything else that reports a version move
# together — two spellings of a version is the sort of disagreement
# nobody notices until somebody is reading a bug report.
VERSION = "1.0.0"

ROOT = Path(__file__).resolve().parent.parent


def _from_git() -> tuple[str, str] | None:
    """(short sha, ISO date) for a clone, or None for anything else."""
    if not (ROOT / ".git").exists():
        return None
    try:
        # NO CONSOLE: this runs on a windowless app, so a child that
        # wants one is handed a fresh black box. See `console.no_window`.
        from . import console
        out = subprocess.run(
            ["git", "-C", str(ROOT), "log", "-1", "--format=%h %cI"],
            capture_output=True, text=True, timeout=5, check=False,
            **console.no_window())
    except (OSError, subprocess.SubprocessError):
        return None
    parts = out.stdout.strip().split()
    return (parts[0], parts[1]) if out.returncode == 0 and len(parts) == 2 \
        else None


def _from_install_record() -> tuple[str, str] | None:
    """(short sha, ISO date) for a copy the updater wrote."""
    record = ROOT / "installed_version.json"
    try:
        data = json.loads(record.read_text(encoding="utf-8"))
        sha = str(data["sha"])[:7]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    when = datetime.fromtimestamp(record.stat().st_mtime,
                                  tz=timezone.utc).isoformat()
    return (sha, when)


def build() -> str:
    """The commit and date behind this copy, in words, or "unknown"."""
    found = _from_git() or _from_install_record()
    if found is None:
        return "unknown"
    sha, when = found
    try:
        day = datetime.fromisoformat(when).strftime("%d %B %Y").lstrip("0")
    except ValueError:
        return sha
    return f"{sha} · {day}"


def described() -> str:
    """One line: "Version 1.0.0 (build abc1234 - 10 September 2026)"."""
    return f"Version {VERSION} (build {build()})"


# How long to wait on GitHub before giving up. SHORT on purpose: this
# runs while somebody is opening the app, and "we could not ask" has to
# cost a few seconds rather than half a minute. An unanswered check is
# not a fault and never blocks anything.
CHECK_TIMEOUT = 6


def installed_sha() -> str:
    """The commit this copy was installed at, or "" if it cannot be had.

    Written by the ZIP updater, and — since this went in —
    STAMPED INTO THE SHAREABLE ZIP by `tools/make_release.py`. Before
    that a fresh unzip had no record at all, so it could not tell
    "already current" from "months behind" and every press of Update
    downloaded the branch whether or not anything had changed.
    """
    try:
        from .config import INSTALL_RECORD
        with open(ROOT / INSTALL_RECORD, encoding="utf-8") as handle:
            record = json.load(handle)
        return str(record.get("sha") or "")[:40] if isinstance(
            record, dict) else ""
    except Exception:           # noqa: BLE001 - see the module note
        return ""


def is_a_clone() -> bool:
    """True for a git checkout, which must NEVER be nagged to update.

    A clone follows whatever branch it is actually tracking — that is
    the whole reason `choose_target` prefers the upstream — so comparing
    it against `main` would put an update banner over the author's own
    window every time they worked on a branch. The check below is for a
    copy somebody unzipped, which has no git and no other way to know it
    has gone stale.
    """
    return (ROOT / ".git").exists()


def newer_release(timeout: int = CHECK_TIMEOUT) -> str:
    """The head commit of the release branch when it is NEWER than this
    copy, else "" — which also covers every way of not knowing.

    "" IS THE ANSWER TO FOUR DIFFERENT QUESTIONS and deliberately so:
    this is a clone, there is no network, GitHub rate-limited us, or we
    are already current. None of them is a fault and none of them should
    put anything on screen, so they collapse. The one case that returns
    a string is the one case with something to offer.

    Nothing here raises, for the reason the rest of this module does not:
    it is called while the app is opening, and a copy that cannot reach
    GitHub must still start.
    """
    if is_a_clone():
        return ""
    have = installed_sha()
    if not have:
        # A copy with no stamp at all: older than this change, or unzipped
        # from a GitHub archive by hand. It cannot be compared, so it is
        # not claimed to be behind — `zip_update` still downloads when
        # asked, which is where "unknown means fetch" belongs.
        return ""
    try:
        import requests
        from .config import GITHUB_OWNER, GITHUB_REPO, RELEASE_BRANCH
        response = requests.get(
            f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
            f"/commits/{RELEASE_BRANCH}",
            timeout=timeout,
            headers={"Accept": "application/vnd.github+json"})
        if not response.ok:
            return ""
        latest = str(response.json().get("sha") or "")[:40]
    except Exception:           # noqa: BLE001 - see the module note
        return ""
    return latest if latest and latest != have else ""

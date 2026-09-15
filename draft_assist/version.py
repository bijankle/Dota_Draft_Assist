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

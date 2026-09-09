"""Pull the latest code — for THIS repository, and no other.

THERE ARE TWO KINDS OF INSTALL AND THE BUTTON MUST WORK ON BOTH.

A CLONE has a `.git` directory, and git is the right tool for it: it is
the only thing that brings new code down while keeping edits the user has
made to their own files, and it knows exactly what it has. That is the
path this file started as, and it is unchanged.

A DOWNLOADED COPY has no `.git` at all — which is what GitHub's "Download
ZIP" button leaves you with, and what almost everybody who is handed this
app will have, because installing git is where most people stop. It used
to be REFUSED with instructions to install git and clone; that is a fine
answer for one person who wrote the app and a useless one for a stranger
who just wants the new version. So it now updates by downloading the
release branch's ZIP and writing the files out.

**WHAT MAKES THE ZIP PATH SAFE IS THAT THE ZIP IS THE MANIFEST.** A
GitHub archive contains exactly the files the repository tracks, so
everything gitignored — the Stratz key in `.env`, `ui_settings.json`,
`preferences.json`, `calibration_local.json`, `history_accounts.json`,
the statistics in `data_cache/`, every downloaded portrait and item icon,
the recordings — is not in it and therefore cannot be written over. The
user's key and settings survive every update by CONSTRUCTION rather than
by a list somebody has to remember to keep up to date. `NEVER_WRITE` is
belt and braces on top of that, for the day somebody commits a `.env` by
accident.

Files DELETED in a release are handled by remembering what was written
last time (`installed_version.json`): anything this tool wrote which is
no longer in the archive is removed. A stale module left on disk is not
inert — it is importable — so this matters.

**IT ONLY EVER UPDATES THIS REPOSITORY.** The owner and repository are
constants here and the git path checks `origin` against the app's own
name before fetching. The match history analyser was folded in from
another repository and nothing may reach back to it.

**THE RELEASE BRANCH IS `main`, and that is the whole point of it.**
Development happens on branches; `main` is what a stranger's copy
follows, so half-finished work never reaches anybody. A clone that is
sitting on a development branch keeps following that branch — the ladder
below resolves what a checkout is actually tracking rather than forcing
everyone onto one answer.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draft_assist.config import REPO_ROOT  # noqa: E402

OWNER = "bijankle"
REPO = "Dota_Draft_Assist"
# What a downloaded copy follows. Development happens elsewhere and is
# merged here when it is fit to hand to somebody.
RELEASE_BRANCH = "main"

# The app's own repository, lower-cased for comparison. A fork or a rename
# is a legitimate reason for this to fail; the message names what it found
# so that is obvious rather than mysterious.
THIS_REPO = REPO.lower()

INSTALL_NAME = "installed_version.json"


def install_file() -> Path:
    """What the ZIP path wrote last time, so a file dropped from a release
    can be dropped from the install too. Gitignored: it describes THIS
    machine and nobody else's.

    RESOLVED AT CALL TIME, never as a module constant — the same rule
    `load_layout` and `ui_settings.load` follow. A constant is evaluated
    once at import, so a test that repoints `REPO_ROOT` would still read
    and write the real repository's file, which has already happened once
    in this codebase with the calibration file.
    """
    return REPO_ROOT / INSTALL_NAME


# Never written by the ZIP path whatever an archive contains. The archive
# should never carry these, and if one ever does it must not land on top
# of somebody's API key.
NEVER_WRITE = {".env", INSTALL_NAME, "calibration_local.json",
               "ui_settings.json", "preferences.json",
               "history_accounts.json"}


class Refused(Exception):
    """The update cannot honestly be done. The message says why."""


NO_NETWORK = (
    "Could not reach GitHub, so there is nothing to update from. Check "
    "this machine is online and that nothing is blocking the connection, "
    "then try again. Nothing has been changed.")


def git(*args, check=True) -> str:
    try:
        result = subprocess.run(["git", "-C", str(REPO_ROOT), *args],
                                capture_output=True, text=True)
    except FileNotFoundError:
        # On the git path this cannot happen (the path is only taken when
        # a .git directory exists, which means git put it there) — but a
        # folder copied WITH its .git and no git installed is exactly that
        # state, so it still has to answer in a sentence.
        raise Refused(
            "This folder is a git clone, but git is not installed on this "
            "machine so it cannot be updated. Install Git for Windows from "
            "https://git-scm.com/download/win, or delete the .git folder "
            "and Update will download the new version instead.")
    if check and result.returncode != 0:
        raise Refused((result.stderr or result.stdout).strip()
                      or f"git {' '.join(args)} failed")
    return (result.stdout or "").strip()


def check_remote(url: str) -> None:
    """Refuse an origin that is not this app.

    The match history analyser came from a separate repository and is now
    wholly inside this one. Updating must never reach back to it, and the
    cheapest way to be sure is to look at where origin points.
    """
    if not url:
        raise Refused(
            "This checkout has no 'origin' remote, so there is nowhere to "
            "update from. It was probably copied rather than cloned; clone "
            "it from GitHub instead and your settings will carry over.")
    if THIS_REPO not in url.lower():
        raise Refused(
            f"'origin' points at {url}, which is not this app. Update only "
            "ever pulls Dota Draft Assist — nothing here updates from any "
            "other repository.")


def choose_target(branch: str, upstream: str, remote_branches, head: str):
    """What to pull, and why. Returns (ref, reason) or (None, why not).

    Pure, so the ladder can be tested without a git repository to hand.
    `remote_branches` are short names as `origin/x` gives them: "main",
    "claude/thing". `head` is what `origin/HEAD` resolves to, or "".
    """
    branches = [b for b in remote_branches if b]
    if upstream:
        return upstream, f"tracking {upstream}"
    if branch and branch in branches:
        return f"origin/{branch}", f"the remote's own {branch}"
    if RELEASE_BRANCH in branches:
        return (f"origin/{RELEASE_BRANCH}",
                f"the release branch, {RELEASE_BRANCH}")
    if head and head in branches:
        return f"origin/{head}", f"the remote's default branch, {head}"
    if len(branches) == 1:
        return (f"origin/{branches[0]}",
                f"the remote's only branch, {branches[0]}")
    if not branches:
        return None, "the remote has no branches to pull from"
    return None, ("the remote has several branches and none of them matches "
                  f"'{branch}', so which one to pull is not this tool's "
                  "guess to make. Run: git pull --rebase origin <branch>")


# ---------------------------------------------------------------- git ----

def git_update() -> None:
    """A clone: let git do it, because git is better at this than we are."""
    url = git("remote", "get-url", "origin", check=False)
    check_remote(url)
    print(f"origin:     {url}")

    branch = git("rev-parse", "--abbrev-ref", "HEAD", check=False)
    if branch == "HEAD":
        raise Refused(
            "This checkout is on a detached HEAD rather than a branch, so "
            "there is nothing to update. Run: git checkout <branch>")
    print(f"branch:     {branch}")

    print("\nFetching…")
    print(git("fetch", "--prune", "origin", check=False) or "  (up to date)")

    upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name",
                   "@{upstream}", check=False)
    remote_branches = [line.strip().removeprefix("origin/")
                       for line in git("for-each-ref",
                                       "--format=%(refname:short)",
                                       "refs/remotes/origin", check=False
                                       ).splitlines()
                       if line.strip() and "->" not in line]
    head = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD",
               check=False).removeprefix("origin/")

    target, reason = choose_target(branch, upstream, remote_branches, head)
    if target is None:
        raise Refused(f"Nothing to pull: {reason}.")
    print(f"Pulling from {target} — {reason}.\n")

    remote_branch = target.removeprefix("origin/")
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "pull", "--rebase", "--autostash",
         "origin", remote_branch],
        text=True)
    if result.returncode != 0:
        raise Refused(
            "The pull did not finish. Your own edits are safe — nothing was "
            "discarded. If it stopped in a rebase, `git rebase --abort` puts "
            "the checkout back exactly as it was.")

    # SET THE UPSTREAM, so the next update is an ordinary pull rather than
    # this whole ladder again — and so `git status` starts saying how far
    # ahead or behind the checkout is.
    if not upstream:
        git("branch", f"--set-upstream-to=origin/{remote_branch}", branch,
            check=False)
        print(f"\nTracking set: {branch} follows origin/{remote_branch}.")
    print("\nUpdated.")


# ---------------------------------------------------------------- zip ----

def _requests():
    try:
        import requests
    except ImportError:                                 # pragma: no cover
        raise Refused(
            "The `requests` package is missing from this Python "
            "environment, so the new version cannot be downloaded. Run: "
            "pip install -r requirements.txt")
    return requests


def head_sha(branch: str = RELEASE_BRANCH) -> str:
    """The newest commit on the release branch, or "" if it cannot be had.

    Only ever used to say "you already have this" and to label what was
    installed. A rate limit or an outage here must not stop an update: an
    unknown answer means carry on and download, which is the SAFE way to
    be wrong. Refusing to update because a version check failed would be
    the check breaking the thing it exists to help.
    """
    requests = _requests()
    try:
        response = requests.get(
            f"https://api.github.com/repos/{OWNER}/{REPO}/commits/{branch}",
            timeout=20, headers={"Accept": "application/vnd.github+json"})
        if not response.ok:
            return ""
        return str(response.json().get("sha") or "")[:40]
    except Exception:
        return ""


def load_installed() -> dict:
    try:
        with open(install_file(), encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def download(branch: str, into: Path) -> Path:
    """The branch as a zip, on disk. Whole file first, then unpack.

    Downloaded COMPLETELY before anything is written into the install, so
    a connection that drops halfway leaves the app exactly as it was
    rather than half replaced.
    """
    requests = _requests()
    url = (f"https://github.com/{OWNER}/{REPO}/archive/refs/heads/"
           f"{branch}.zip")
    print(f"Downloading {url}")
    target = into / "release.zip"
    try:
        with requests.get(url, timeout=120, stream=True) as response:
            if response.status_code == 404:
                raise Refused(
                    f"GitHub has no branch called '{branch}' in {OWNER}/"
                    f"{REPO}, so there is no release to download.")
            if not response.ok:
                raise Refused(
                    f"GitHub answered HTTP {response.status_code} for the "
                    "download. That is their end, not yours — try again "
                    "shortly.")
            with open(target, "wb") as handle:
                for chunk in response.iter_content(chunk_size=65536):
                    handle.write(chunk)
    except Refused:
        raise
    except Exception:
        raise Refused(NO_NETWORK)
    print(f"  {target.stat().st_size / 1e6:.1f} MB")
    return target


def unpack(archive: Path, into: Path) -> Path:
    """Extract, and return the single folder GitHub wraps everything in."""
    with zipfile.ZipFile(archive) as zf:
        names = [n for n in zf.namelist() if not n.startswith("/")]
        if not names:
            raise Refused("The downloaded archive was empty.")
        # A path that climbs out of the extraction folder is how a zip
        # overwrites files it was never meant to reach. Ours never will;
        # checking costs four lines and the alternative is trusting a
        # download with write access to the whole disk.
        for name in names:
            if ".." in Path(name).parts or Path(name).is_absolute():
                raise Refused(
                    f"The archive contains an unsafe path ({name}) and was "
                    "not applied. Nothing has been changed.")
        zf.extractall(into)
    roots = {Path(n).parts[0] for n in names}
    if len(roots) != 1:
        raise Refused("The archive did not have the shape GitHub's "
                      "archives have, so it was not applied.")
    return into / roots.pop()


def apply_tree(source: Path, previous: list) -> tuple:
    """Write every file in the archive into the install. Returns (written,
    removed).

    Only paths the archive carries are written, which is what keeps the
    user's key, settings and downloads out of it: they are gitignored, so
    they are not in the archive, so they are not touched.
    """
    written = []
    for path in sorted(source.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(source).as_posix()
        if relative in NEVER_WRITE:
            print(f"  skipped {relative} (yours, never replaced)")
            continue
        destination = REPO_ROOT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        written.append(relative)

    # Anything WE wrote last time that this release no longer carries.
    # Never anything else: a file the user put here is theirs.
    removed = []
    for relative in previous:
        if relative in written or relative in NEVER_WRITE:
            continue
        stale = REPO_ROOT / relative
        try:
            if stale.is_file():
                stale.unlink()
                removed.append(relative)
        except OSError:
            pass                    # a file we cannot remove is not a fault
    return written, removed


def zip_update(branch: str = RELEASE_BRANCH) -> None:
    """A downloaded copy: fetch the release branch and write it out."""
    print(f"Channel:    {branch} (downloaded copy, no git needed)")
    installed = load_installed()
    latest = head_sha(branch)
    have = str(installed.get("sha") or "")
    if have:
        print(f"installed:  {have[:7]}")
    if latest:
        print(f"latest:     {latest[:7]}")
    if latest and have and latest == have:
        # NOT an error, and it must not look like one: "you already have
        # this" is a successful outcome of pressing Update.
        print(f"\nAlready up to date ({branch} @ {latest[:7]}).")
        return

    with tempfile.TemporaryDirectory(prefix="dda-update-") as temporary:
        workspace = Path(temporary)
        archive = download(branch, workspace)
        source = unpack(archive, workspace / "unpacked")
        print("\nApplying…")
        written, removed = apply_tree(source, installed.get("files") or [])

    try:
        with open(install_file(), "w", encoding="utf-8") as handle:
            json.dump({"branch": branch, "sha": latest, "files": written},
                      handle, indent=1)
    except OSError:
        # The update itself succeeded; only the bookkeeping failed. Saying
        # so beats failing a completed update.
        print("  (could not record the version — the update still applied)")

    print(f"  {len(written)} files written"
          + (f", {len(removed)} removed" if removed else ""))
    print(f"\nUpdated to {branch}"
          + (f" @ {latest[:7]}." if latest else "."))
    print("Your settings, your Stratz key and everything you have "
          "downloaded were left alone.")


def main() -> None:
    print(f"Repository: {REPO_ROOT}")
    if (REPO_ROOT / ".git").exists():
        print("Install:    git clone")
        git_update()
    else:
        zip_update()


if __name__ == "__main__":
    try:
        main()
    except Refused as refused:
        print(f"\n{refused}")
        raise SystemExit(1)

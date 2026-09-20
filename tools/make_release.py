"""Build the zip that carries the app AND every package it runs on.

    python tools/stock_wheels.py --windows     fill wheels/ first
    python tools/make_release.py               build the zip

WHY THIS EXISTS, in the owner's words: "can you package all of the
requirements within the app itself? the app requirements num py open cv
etc they can jsut be kept static forever... so the user never needs to
preinstall them".

WHAT A STRANGER GETS. One zip. They unzip it, double-click
`Dota Draft Assist.bat`, and the launcher installs every package out of
the folder it just unzipped - no pypi.org, no pip upgrade, no Visual
C++ error, and no connection needed for any of it. That is the whole
point: the step that turned a real user around was the packages, not
the app.

WHY THE WHEELS ARE NOT IN GIT, which is the same question asked the
other way. `tools/update_app.py` updates a downloaded copy by fetching
the branch's ZIP, and that archive carries every TRACKED file - so a
committed `wheels/` makes every press of Update a 190 MB download
instead of about 2 MB, for ever, against this app's own rule that the
update is the code and nothing else. Git also keeps every version of
every file permanently, so each refresh would add another 190 MB to
every clone.

So the two are separated by WHAT THEY ARE FOR. The repository is how an
existing copy UPDATES, and stays small. This zip is how a new copy is
INSTALLED, and carries everything. Nobody downloads the packages twice
either way: the first install is the same bytes whether they come from
PyPI or from inside this zip - what changes is that here they arrive in
one step that cannot half-fail.

THE BUNDLE IS NOT PINNED TO ONE PYTHON. `stock_wheels --windows`
fetches for every version in its `PY_VERSIONS`, and most of what this
app needs is `py3-none-any` or abi3 anyway, so covering three costs
about 40 MB rather than three times the whole set.
"""

import argparse
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from draft_assist import config, console                      # noqa: E402
from draft_assist.version import VERSION                      # noqa: E402
from tools import stock_wheels                                # noqa: E402

# Nothing under these ever goes in, whatever git says. The manifest is
# git's tracked list, which already excludes the key and the settings -
# this is belt and braces for the day somebody commits one by accident,
# the same list `update_app.NEVER_WRITE` keeps for the same reason.
NEVER_SHIP = (".env", "ui_settings.json", "preferences.json",
              "history_accounts.json", "calibration_local.json")


def from_git() -> list[str]:
    """The files git tracks, or [] when there is no git and no clone."""
    try:
        result = subprocess.run(["git", "-C", str(ROOT), "ls-files"],
                                capture_output=True, text=True,
                                **console.no_window())
    except OSError:
        return []                            # git is not installed
    if result.returncode:
        return []                            # not a clone
    return [line for line in result.stdout.splitlines() if line.strip()]


def from_install() -> list[str]:
    """What the ZIP updater last wrote, out of `installed_version.json`.

    THE SAME MANIFEST BY A DIFFERENT ROUTE. `update_app` records every
    file it installed so it can delete the ones that go away, and those
    files ARE the repository's tracked list - it built them from the
    branch archive, which carries exactly that. So a copy that was
    unzipped rather than cloned can still say what belongs in a
    release, with no git and no network.
    """
    try:
        import json
        data = json.loads(
            (ROOT / "installed_version.json").read_text(encoding="utf-8"))
    except Exception:
        return []
    files = data.get("files")
    return [str(name) for name in files] if isinstance(files, list) else []


def tracked() -> list[str]:
    """The files that belong in a release.

    TWO ROUTES, because there are two kinds of install and the owner
    may be on either. A CLONE asks git. A copy UNZIPPED from GitHub has
    no `.git` at all and may have no git installed - and telling
    somebody to install git to build a zip whose whole purpose is that
    nobody has to install anything is the joke this tool exists to
    avoid. It reads what the updater wrote instead.
    """
    names = from_git() or from_install()
    if not names:
        raise SystemExit(
            "Cannot tell which files belong in a release.\n\n"
            "This folder is neither a git clone nor a copy that has "
            "been updated at least once (there is no "
            "installed_version.json). Press Help > Update application "
            "first, then try again.")
    return names


def wanted(name: str) -> bool:
    return Path(name).name not in NEVER_SHIP


def built_from() -> str:
    """The commit this zip is being cut at, or "" if it cannot be had.

    A clone knows it from git. A copy that was itself unzipped and then
    updated knows it from the record the updater wrote. Neither is fatal:
    an unstamped zip behaves exactly as every zip did before this, which
    is to say it cannot tell whether it is current.
    """
    try:
        result = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                capture_output=True, text=True,
                                **console.no_window())
        if not result.returncode:
            return result.stdout.strip()[:40]
    except OSError:
        pass
    try:
        data = json.loads(
            (ROOT / config.INSTALL_RECORD).read_text(encoding="utf-8"))
        return str(data.get("sha") or "")[:40]
    except Exception:           # noqa: BLE001 - a stamp, not the release
        return ""


def stamp(files: list[str]) -> str:
    """The `installed_version.json` a fresh unzip should start life with.

    **A ZIP THAT DOES NOT KNOW WHICH BUILD IT IS CANNOT BE TOLD IT IS
    OUT OF DATE**, and that is what sent a real user round the houses:
    they unzipped a shareable copy, the core of the app did not work,
    and the fix was to press Help > Update application - which nothing
    on screen had any way of suggesting, because the app could not tell
    a current copy from one cut months ago. Stamping it closes that:
    the app compares this sha against the release branch and can say so.

    It carries the FILE LIST as well as the sha, which is the same shape
    `update_app` writes, so the first update from a shareable zip can
    also remove files that went away rather than leaving them importable.
    """
    return json.dumps({"branch": config.RELEASE_BRANCH,
                       "sha": built_from(),
                       "files": sorted(files)}, indent=1)


def build(out: Path, wheels: bool = True) -> tuple[int, float]:
    """Write the zip. Returns (files, megabytes)."""
    files = [name for name in tracked() if wanted(name)]
    extras: list[Path] = []
    if wheels:
        extras = stock_wheels.stocked()
        if not extras:
            print("NOTHING IN " + stock_wheels.WHEEL_DIR + "/ - this zip "
                  "will carry the app and no packages.")
            print("Run: python tools/stock_wheels.py --windows")
    out.parent.mkdir(parents=True, exist_ok=True)
    total = len(files) + len(extras)
    done = 0
    # The wheels are already compressed, so re-compressing them costs
    # minutes and saves nothing; the source is text and is worth it.
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in files:
            path = ROOT / name
            if not path.is_file():
                continue                  # a submodule, or a stale index
            zf.write(path, name)
            done += 1
            if done % 50 == 0:
                console.progress(done / (total + 1), "packing the app")
        for path in extras:
            zf.write(path, f"{stock_wheels.WHEEL_DIR}/{path.name}",
                     compress_type=zipfile.ZIP_STORED)
            done += 1
            console.progress(done / (total + 1), "packing the packages")
        # LAST, and never from `files`: it is gitignored, so it is not in
        # the tracked list and cannot be, and it is written here rather
        # than copied from this machine's own record - which describes
        # this install and nobody else's.
        zf.writestr(config.INSTALL_RECORD, stamp(files))
    console.progress(1.0, "done")
    return done, out.stat().st_size / 1e6


def main(argv: list[str] | None = None) -> int:
    console.plain_output()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="",
                        help="where to write the zip")
    parser.add_argument("--no-wheels", action="store_true",
                        help="build the app alone, as GitHub's own "
                             "Download ZIP does")
    args = parser.parse_args(argv)

    name = f"Dota Draft Assist {VERSION}.zip"
    out = Path(args.out) if args.out else ROOT / "dist" / name
    print(stock_wheels.describe())
    print(f"\nBuilding {out}\n")
    count, size = build(out, wheels=not args.no_wheels)
    print()
    print(f"{count} file(s), {size:.0f} MB -> {out}")
    if args.no_wheels:
        print("\nNo packages in this one: setup will download them.")
    else:
        print("\nUnzip this anywhere and double-click the .bat. Every")
        print("package installs out of the folder, with no connection.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

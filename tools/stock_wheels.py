"""Keep the app's Python packages in the app's own folder.

    python tools/stock_wheels.py            refresh the cache
    python tools/stock_wheels.py --check    say what is there, write nothing

WHY THIS EXISTS. A first run downloaded about 180 MB of packages from
pypi.org before the app could open, and every repair of a broken `.venv`
downloaded them again. That is the slowest part of setting this app up
and the part most likely to fail: no internet, a network blocking
pypi.org, or an old pip that cannot read today's package files.

So the downloaded WHEELS are kept in `wheels/` beside the app, and the
launcher installs from there first. What that buys, in order of how
often it matters:

  * A REPAIRED `.venv` costs nothing and needs no connection at all.
    Rebuilding the environment is currently the app's own advice when
    anything goes wrong with it.
  * COPYING THE WHOLE FOLDER to another PC, or zipping it for somebody
    else, carries the packages with it. That is the only way a stranger
    gets this app working with no download, and it needs no build
    pipeline - it is a folder copy.
  * A SECOND install on the same machine is instant.

WHAT THIS IS NOT. The wheels are NOT committed to the repository, and
they must not be. `tools/update_app.py` updates a downloaded copy by
fetching the branch's ZIP, so anything tracked is downloaded again on
EVERY update - and the owner's own standing rule for that button is
that it is the code and nothing else, because minutes of network behind
a progress box reads as a frozen application. Measured from PyPI, the
wheels for ONE Python version are 181 MB against the app's own ~2 MB,
and git keeps every version of every file for ever, so each refresh
would add another 181 MB to every clone. `wheels/` is gitignored for
the same reason `data_cache/` and the downloaded artwork are.
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from draft_assist import console                         # noqa: E402

# Where the wheels live. Beside the app, gitignored, and named in the
# launcher - three places that have to agree, so it is spelled here and
# the test reads this name out of this file.
WHEEL_DIR = "wheels"

# What to stock. `pip` itself is in the list deliberately: an old pip is
# the commonest way a first run fails, and upgrading it was a download of
# its own. Cached, that upgrade is offline too.
REQUIREMENTS = ("requirements.txt", "requirements-windows.txt")
ALSO = ("pip", "setuptools", "wheel")

# THE PYTHON VERSIONS A BUNDLE COVERS. Most of what this app installs is
# `py3-none-any` or abi3 - PyQt6 is cp310-abi3, opencv is cp37-abi3, Qt
# itself is pure - so ONE file serves every version. The exceptions are
# numpy and pywin32, which are built per version, and covering three
# costs about 40 MB rather than three times 187.
#
# Named here rather than guessed from the host, because a bundle built
# on one machine has to install on somebody else's.
# EVERY VERSION SOMEBODY CAN REASONABLY INSTALL, because the one it
# misses is the one that fails. `py -3` fetches the newest Python on
# the machine, so a bundle that stops at 3.13 sends a fresh install
# on 3.14 straight to "from versions: none" - which is what happened.
# Cheap to widen: almost everything here is py3-none-any or abi3, so
# a version adds only its own numpy and pywin32, about 25 MB.
PY_VERSIONS = ("311", "312", "313", "314")
PLATFORM = "win_amd64"


def wheel_dir() -> Path:
    """Resolved at CALL time, never as a default argument - a default is
    evaluated once at import, which is how a test that repointed a path
    still wrote into the real repository."""
    return ROOT / WHEEL_DIR


def requirement_files() -> list[Path]:
    """The requirement files that exist. `requirements-windows.txt` is
    real on every platform, but a Linux box cannot resolve what is in
    it, so a caller may end up with only the first."""
    return [ROOT / name for name in REQUIREMENTS if (ROOT / name).exists()]


def stocked() -> list[Path]:
    folder = wheel_dir()
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir()
                  if p.suffix in (".whl", ".gz", ".zip"))


def describe() -> str:
    """One line for the diagnostic paste and for --check."""
    files = stocked()
    if not files:
        return f"{WHEEL_DIR}/: empty - setup will download from pypi.org"
    size = sum(p.stat().st_size for p in files) / 1e6
    return (f"{WHEEL_DIR}/: {len(files)} package file(s), {size:.0f} MB - "
            "setup installs from here without a download")


def windows_download(into: Path) -> int:
    """Fetch the Windows wheels for every version in `PY_VERSIONS`.

    FROM ANY MACHINE. `pip download --only-binary=:all: --platform
    win_amd64 --python-version 312` resolves against PyPI's metadata
    rather than against the interpreter running it, so a bundle for
    Windows can be built on Linux - which is the only way this project
    can build one at all.

    `--only-binary=:all:` is REQUIRED rather than tidy: pip refuses to
    cross-compile a source distribution, and without it a package with
    no wheel for that combination fails the whole call instead of being
    reported.
    """
    into.mkdir(parents=True, exist_ok=True)
    files = requirement_files()
    jobs = [(f"{path.name} for Python 3.{version[1:]}",
             ["--python-version", version, "--platform", PLATFORM,
              "--only-binary=:all:", "-r", str(path)])
            for version in PY_VERSIONS for path in files]
    # pip itself is pure Python, so one fetch covers every version.
    jobs.append(("pip and its helpers", ["--only-binary=:all:", *ALSO]))
    return run_jobs(jobs, into)


def download(into: Path, extra: list[str] | None = None) -> int:
    """Fetch every package this app needs into `into`. Returns the exit
    code of the last failing step, or 0.

    ONE `pip download` PER FILE rather than one call with every `-r`,
    because a failure then names WHICH set could not be resolved -
    `requirements-windows.txt` cannot resolve at all off Windows, and
    that is a normal answer rather than a fault.
    """
    into.mkdir(parents=True, exist_ok=True)
    jobs: list[tuple[str, list[str]]] = []
    for path in requirement_files():
        jobs.append((path.name, ["-r", str(path)]))
    if extra is None:
        extra = list(ALSO)
    if extra:
        jobs.append(("pip and its helpers", list(extra)))
    return run_jobs(jobs, into)


def run_jobs(jobs: list[tuple[str, list[str]]], into: Path) -> int:
    """Run each `pip download` in turn, reporting as it goes."""
    into.mkdir(parents=True, exist_ok=True)
    worst = 0
    for number, (what, args) in enumerate(jobs, start=1):
        console.progress(number / (len(jobs) + 1), f"fetching {what}")
        print(f"  {what} ...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "download", *args,
             "--dest", str(into)],
            **console.no_window())
        if result.returncode:
            # NOT FATAL, and said so. Off Windows the second file cannot
            # resolve; on Windows a single package may 404. Either way
            # what DID come down is still worth keeping, and the caller
            # decides what a partial cache is worth.
            print(f"  could not fetch {what} (exit {result.returncode})")
            worst = result.returncode
    console.progress(1.0, "done")
    return worst


def main(argv: list[str] | None = None) -> int:
    console.plain_output()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="report what is cached and write nothing")
    parser.add_argument("--windows", action="store_true",
                        help="fetch the Windows wheels for every Python "
                             "version a bundle covers, from any machine")
    args = parser.parse_args(argv)

    folder = wheel_dir()
    print(describe())
    if args.check:
        return 0

    print(f"\nStocking {folder} - about 190 MB the first time, and only")
    print("what has changed after that.\n")
    if args.windows:
        print("Windows wheels for Python "
              + ", ".join("3." + v[1:] for v in PY_VERSIONS) + ".\n")
        code = windows_download(folder)
    else:
        code = download(folder)
    print()
    print(describe())
    if code:
        print("\nSome packages could not be fetched (the lines above say")
        print("which). What did come down is kept and will still be used.")
    else:
        print("\nSetup on this machine, and on any copy of this folder,")
        print("now installs without downloading anything.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Fetch the artwork the app needs to be worth looking at.

Hero portraits, item icons and the community's alternative portraits, to
THIS MACHINE'S disk. None of it is in the repository and none of it ever
will be: it is Valve's artwork, and a repository anybody can clone is not
a place to redistribute somebody else's pictures from. Downloading it to
your own disk at runtime is a different thing entirely, and it is what
every install has always done.

So this is how a copy handed to somebody else ends up looking like the
app rather than like a grid of empty plates: the update runs it, and the
first-run banner offers it. The pictures are ESSENTIAL to the experience
— a row of faces is read at a glance where a row of names is read as a
list — so getting them must not be a step anybody has to know about.

**IT NEVER FAILS THE THING THAT CALLED IT.** It runs as the last step of
Update, after the code is already in place, so a slow CDN or a blocked
connection must not turn a successful code update into a failed one. Each
part says what happened and the script exits 0 regardless; Setup ▸
Download re-runs whichever half went wrong, and both skip what is already
on disk, so a retry costs only the files that are actually missing.

NEEDS NO API KEY. Portraits and icons come from OpenDota's public
constants and Valve's CDN, which is what makes this safe to run
automatically for somebody who has not signed up for anything — the
statistics, which DO need a Stratz key, are a separate job.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def run(name: str, call) -> bool:
    """One part, loudly, and never fatally."""
    print(f"\n=== {name} ===")
    try:
        call()
        return True
    except KeyboardInterrupt:
        raise
    except BaseException as failure:                # noqa: BLE001 - see above
        print(f"  {name} did not finish: "
              f"{failure.__class__.__name__}: {failure}")
        print("  Nothing else is affected. Setup ▸ Download runs this "
              "again, and it skips whatever is already on disk.")
        return False


def portraits_and_icons() -> None:
    from tools import build_library
    build_library.main()


def alternative_portraits() -> None:
    """Persona, arcana and custom-set pictures, so a team-mate wearing one
    stops reading as UNKNOWN.

    Kept apart from the portraits above because it is the half that has
    never been run against the live site — the network policy where it was
    written blocks it — so it is the half most likely to come back with
    nothing, and it must not take the base portraits down with it.
    """
    from tools import fetch_custom_portraits
    saved = sys.argv[:]
    try:
        sys.argv = ["fetch_custom_portraits.py"]
        fetch_custom_portraits.main()
    finally:
        sys.argv = saved


def main() -> None:
    print("Fetching the artwork this app draws with.")
    print("To this machine's disk only — none of it is in the repository.")
    done = [run("Hero portraits and item icons", portraits_and_icons),
            run("Alternative hero portraits", alternative_portraits)]
    if all(done):
        print("\nArtwork is up to date.")
    else:
        print("\nSome artwork could not be fetched — see above. The app "
              "works without it: a missing picture draws the name instead.")


if __name__ == "__main__":
    main()

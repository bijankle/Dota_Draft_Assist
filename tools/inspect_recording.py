"""Say what a recording of Dota's game data actually contained.

Reads the payloads archived by Game > Record game data and prints which
components the game sent and whether the enemy line-up was ever among them.
It only reads files, so it runs happily while the app is open and listening
-- unlike the live probe, which needs the port.

    python tools/inspect_recording.py [--from data_cache/gsi]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draft_assist.config import DATA_CACHE, RECORDINGS_DIR  # noqa: E402
from draft_assist.data import store  # noqa: E402
from draft_assist.gsi import summary as gsi_summary  # noqa: E402


def _newest_recording() -> Path | None:
    """The newest session's payloads, or the pre-sessions archive.

    A session folder keeps its payloads in gsi/; data_cache/gsi is where
    recordings landed before Record became one button, and is still worth
    reading rather than orphaning.
    """
    from draft_assist import record

    for folder in record.sessions(RECORDINGS_DIR):
        if (folder / "gsi").is_dir():
            return folder / "gsi"
    legacy = DATA_CACHE / "gsi"
    return legacy if legacy.is_dir() else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="source", type=Path, default=None,
                        help="a recording folder (default: the newest)")
    parser.add_argument("--match", default="", metavar="ID",
                        help="only payloads from this match id (a folder "
                             "often holds several games)")
    args = parser.parse_args()

    if args.source is None:
        args.source = _newest_recording()
    if args.source is None or not args.source.is_dir():
        raise SystemExit(
            f"No recordings found under {RECORDINGS_DIR}.\n\n"
            "Press Record in the app before a game and Stop after the "
            "draft, then run this again.")

    dataset = store.load_or_empty()
    if dataset.is_empty:
        print("NOTE: no hero data downloaded yet, so hero names will be "
              "blank.\n")
    print(f"Examining {args.source}\n")
    report = gsi_summary.from_directory(args.source, dataset,
                                        match=args.match)
    print(gsi_summary.format_report(report, args.source))


if __name__ == "__main__":
    main()

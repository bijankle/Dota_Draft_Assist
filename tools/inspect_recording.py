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

from draft_assist.config import DATA_CACHE  # noqa: E402
from draft_assist.data import store  # noqa: E402
from draft_assist.gsi import summary as gsi_summary  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="source", type=Path,
                        default=DATA_CACHE / "gsi")
    args = parser.parse_args()

    if not args.source.is_dir():
        raise SystemExit(
            f"No recordings at {args.source}.\n\n"
            "Tick Game > Record game data, sit through a draft, then run "
            "this again.")

    dataset = store.load_or_empty()
    if dataset.is_empty:
        print("NOTE: no hero data downloaded yet, so hero names will be "
              "blank.\n")
    print(f"Examining {args.source}\n")
    report = gsi_summary.from_directory(args.source, dataset)
    print(gsi_summary.format_report(report, args.source))


if __name__ == "__main__":
    main()

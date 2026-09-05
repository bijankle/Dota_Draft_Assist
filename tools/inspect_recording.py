"""Print a recording session's report.

The same document the app shows under Debug > Recordings: what the app
concluded tick by tick, why it declined when it declined, how the screen's
reading scored against the game's own line-ups, and what the raw payloads
contained. One report, because Record starts both sources at once.

It only reads files, so it runs happily while the app is open and
listening -- unlike the live probe, which needs the port.

    python tools/inspect_recording.py [--from recordings/<session>]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draft_assist import record  # noqa: E402
from draft_assist.config import RECORDINGS_DIR  # noqa: E402
from draft_assist.data import store  # noqa: E402


def _newest_recording() -> Path | None:
    from draft_assist import record

    folders = record.sessions(RECORDINGS_DIR)
    return folders[0] if folders else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="source", type=Path, default=None,
                        help="a recording folder (default: the newest)")
    args = parser.parse_args()

    folder = args.source or _newest_recording()
    if folder is None or not folder.is_dir():
        raise SystemExit(
            f"No recordings found under {RECORDINGS_DIR}.\n\n"
            "Press Record in the app before a game and Stop after the "
            "draft, then run this again.")

    # A bare gsi/ folder is what recordings looked like before Record
    # became one button; read its parent so the report is the whole session.
    if folder.name == "gsi" and (folder.parent / "state.jsonl").exists():
        folder = folder.parent

    dataset = store.load_or_empty()
    if dataset.is_empty:
        print("NOTE: no hero data downloaded yet, so hero names will be "
              "blank.\n")
    print(record.format_session_report(folder, dataset))


if __name__ == "__main__":
    main()

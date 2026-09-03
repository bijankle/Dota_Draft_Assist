"""Daily data pull CLI: OpenDota + Stratz -> data_cache/dataset.npz.

Needs network and STRATZ_API_KEY in .env. Run roughly once a day; everything
downstream (scoring, UI) reads only the cache.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draft_assist.data.build import build_dataset  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-bracket-check", action="store_true",
                        help="skip the OpenDota-vs-Stratz tier verification "
                             "(only if you are certain the mapping is right)")
    parser.add_argument("--brackets", nargs="+", metavar="BRACKET",
                        help="rank brackets to build statistics for "
                             "(default: whatever is set in the app)")
    args = parser.parse_args()
    build_dataset(skip_bracket_check=args.skip_bracket_check,
                  brackets=args.brackets)


if __name__ == "__main__":
    main()

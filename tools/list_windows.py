"""List the visible window titles this machine is showing, so the capture
source can be chosen or diagnosed without launching the app.

The Dota client's window is titled exactly "Dota 2". Anything else that
merely mentions Dota (a browser tab, a guide, a video) is a different
program and will produce meaningless recognition if captured.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draft_assist.capture.window import (DOTA_TITLE, client_size,  # noqa: E402
                                         list_window_titles)


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("This tool only works on Windows.")
    titles = list_window_titles()
    if not titles:
        raise SystemExit("No visible windows found (unexpected).")

    print(f"{len(titles)} visible windows:\n")
    for t in titles:
        mark = "  <-- the Dota client" if t == DOTA_TITLE else ""
        print(f"  {t!r}{mark}")

    print()
    if DOTA_TITLE in titles:
        size = client_size(DOTA_TITLE)
        print(f"Dota client found; client area measures "
              f"{size[0]}x{size[1]} pixels." if size else
              "Dota client found, but its size could not be read.")
        print("The app will bind to it automatically.")
    else:
        lookalikes = [t for t in titles if "dota" in t.lower()]
        print("No window titled exactly 'Dota 2' — the app cannot bind "
              "automatically.")
        if lookalikes:
            print("These mention Dota but are NOT the client:")
            for t in lookalikes:
                print(f"  {t!r}")
        print("Start Dota in borderless windowed mode, or pick a source in "
              "the app's Debug tab.")


if __name__ == "__main__":
    main()

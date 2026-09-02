"""Step-1 risk probe: does Dota keep producing frames while fully occluded?

Binds the Dota 2 window with Windows Graphics Capture (via the
`windows-capture` package), which reads the window's own swap-chain buffer
independently of what is drawn in front of it, and saves a frame to
captures/probe/ every SAVE_INTERVAL seconds.

Run it, then cover the Dota window completely with any other window and
unfocus Dota. Watch the console: each saved frame is compared with the
previous one and reported CHANGED or STATIC, and a stall warning fires if
Windows stops delivering frames at all. Menu idle animations mean a live,
occluded Dota should keep reporting CHANGED.

Nothing gets built on top of capture until this probe passes.

Usage (Windows, Dota 2 running in borderless windowed mode):
    python tools/probe_capture.py [--minutes 5] [--window "Exact Title"]
"""

import argparse
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draft_assist.capture.window import (DOTA_TITLE,  # noqa: E402
                                         list_window_titles)

try:
    from windows_capture import WindowsCapture
except ImportError:
    sys.exit(
        "The 'windows-capture' package is required (Windows only):\n"
        "    pip install -r requirements-windows.txt"
    )

OUT_DIR = Path(__file__).resolve().parent.parent / "captures" / "probe"
SAVE_INTERVAL = 2.0  # seconds between saved frames
STALL_WARN = 5.0  # warn if no frame arrived for this long
# Mean absolute pixel difference above which two frames count as changed.
# Menu idle animations move few pixels, so the bar is deliberately low.
CHANGE_THRESHOLD = 0.15


def find_dota_title(override: str | None = None) -> str:
    """The Dota client's window, or an explicit override.

    Strict by design: an earlier version bound "the only window with dota in
    its title", which cheerfully captured a browser playing a Dota video and
    made the probe look like it worked. Use --window to capture something
    else deliberately.
    """
    titles = list_window_titles()
    if override:
        if override not in titles:
            sys.exit(f"No visible window titled {override!r}. Visible:\n"
                     + "\n".join(f"  {t!r}" for t in titles))
        return override
    if DOTA_TITLE in titles:
        return DOTA_TITLE
    lookalikes = [t for t in titles if "dota" in t.lower()]
    message = [
        f"No window titled exactly {DOTA_TITLE!r} — is Dota running in "
        "borderless windowed mode?",
    ]
    if lookalikes:
        message.append("These mention Dota but are NOT the client:")
        message += [f"  {t!r}" for t in lookalikes]
        message.append("Capture one deliberately with: "
                       "python tools/probe_capture.py --window \"<title>\"")
    message.append("All visible windows:")
    message += [f"  {t!r}" for t in titles]
    sys.exit("\n".join(message))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=float, default=5.0,
                        help="how long to run before exiting (default 5)")
    parser.add_argument("--window", metavar="TITLE",
                        help="capture this exact window title instead of "
                             "the Dota client")
    args = parser.parse_args()

    title = find_dota_title(args.window)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Capturing window '{title}' -> {OUT_DIR}")
    print("Now cover the Dota window with another window and unfocus it.")
    print("Expect: saved frames keep showing Dota and keep reporting CHANGED.\n")

    state = {
        "last_frame": None,        # newest frame from the capture thread (BGRA)
        "last_arrival": time.monotonic(),
        "frames_arrived": 0,
    }
    lock = threading.Lock()

    capture = WindowsCapture(cursor_capture=False, draw_border=False,
                             window_name=title)

    @capture.event
    def on_frame_arrived(frame, capture_control):  # noqa: ANN001
        with lock:
            state["last_frame"] = frame.frame_buffer.copy()
            state["last_arrival"] = time.monotonic()
            state["frames_arrived"] += 1

    @capture.event
    def on_closed():
        print("Capture session closed by Windows (window closed?).")

    control = capture.start_free_threaded()

    prev_saved: np.ndarray | None = None
    saved = 0
    deadline = time.monotonic() + args.minutes * 60
    try:
        while time.monotonic() < deadline:
            time.sleep(SAVE_INTERVAL)
            now = time.monotonic()
            with lock:
                frame = state["last_frame"]
                age = now - state["last_arrival"]
                arrived = state["frames_arrived"]

            if frame is None:
                print("Waiting for first frame...")
                continue
            if age > STALL_WARN:
                print(f"WARNING: no new frame for {age:.1f}s "
                      f"({arrived} total) — Windows may have stopped "
                      "delivering frames for the occluded window.")

            saved += 1
            bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            path = OUT_DIR / f"frame_{saved:04d}.png"
            cv2.imwrite(str(path), bgr)

            verdict = "first frame"
            if prev_saved is not None:
                if prev_saved.shape == bgr.shape:
                    diff = float(np.mean(
                        np.abs(bgr.astype(np.int16) - prev_saved.astype(np.int16))))
                    verdict = (f"CHANGED (diff {diff:.2f})"
                               if diff > CHANGE_THRESHOLD
                               else f"STATIC (diff {diff:.2f})")
                else:
                    verdict = f"resized to {bgr.shape[1]}x{bgr.shape[0]}"
            prev_saved = bgr
            print(f"{path.name}  {bgr.shape[1]}x{bgr.shape[0]}  "
                  f"{arrived} frames arrived  {verdict}")
    except KeyboardInterrupt:
        pass
    finally:
        control.stop()

    print(f"\nDone: {saved} frames in {OUT_DIR}")
    print("PASS if frames saved while Dota was covered show Dota (not the "
          "covering window) and mostly report CHANGED.")
    print("FAIL if they freeze (STATIC + stall warnings) or show the wrong "
          "window — then we fall back to leaving the team panels visible.")


if __name__ == "__main__":
    main()

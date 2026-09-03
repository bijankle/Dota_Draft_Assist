"""Grab a single frame of the Dota window on demand.

The live capture session is for the screen-reading fallback. This is
different and much smaller: one frame, when the user presses the snapshot
key, so a real draft screen can be saved and inspected even while the app is
running on game data. That is how the overlay's slot positions get anchored
without anyone guessing.

Windows-only; returns None everywhere else so callers can degrade politely.
"""

import sys
import threading
import time

import numpy as np


def capture_once(title: str, timeout: float = 3.0) -> np.ndarray | None:
    """Newest frame of `title` as BGR, or None if capture is unavailable."""
    if sys.platform != "win32":
        return None
    try:
        from windows_capture import WindowsCapture
    except ImportError:
        return None

    holder: dict = {"frame": None}
    arrived = threading.Event()

    capture = WindowsCapture(cursor_capture=False, draw_border=False,
                             window_name=title)

    @capture.event
    def on_frame_arrived(frame, capture_control):  # noqa: ANN001
        if holder["frame"] is None:
            holder["frame"] = frame.frame_buffer.copy()
            arrived.set()

    @capture.event
    def on_closed():
        arrived.set()

    control = capture.start_free_threaded()
    try:
        arrived.wait(timeout)
    finally:
        control.stop()

    frame = holder["frame"]
    if frame is None:
        return None
    if frame.ndim == 3 and frame.shape[2] == 4:
        frame = frame[:, :, :3]
    return np.ascontiguousarray(frame)

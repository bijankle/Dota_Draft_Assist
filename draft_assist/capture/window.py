"""Windows-only helpers around the Dota window handle (ctypes, no pywin32
needed at import time on other platforms). READ-ONLY: this module measures
and enumerates windows; nothing anywhere sends input to the game or touches
its process (see CLAUDE.md).
"""

import sys

# The Dota 2 client's window title is exactly this. Anything else with
# "dota" in the title is some other program (a browser tab, a guide, a
# video) and must never be captured by accident.
DOTA_TITLE = "Dota 2"


def list_window_titles() -> list[str]:
    """Visible top-level window titles, in z-order as EnumWindows reports."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    titles: list[str] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if buf.value.strip():
                    titles.append(buf.value)
        return True

    user32.EnumWindows(enum_proc, 0)
    # De-duplicate while preserving order; identical titles cannot be told
    # apart by name anyway.
    seen, out = set(), []
    for t in titles:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def find_dota_window_title() -> str | None:
    """The Dota client's window, or None.

    Deliberately EXACT: an earlier version fell back to 'the only visible
    window with dota in its title', which happily bound a browser playing a
    Dota video and fed the recogniser garbage pixels. A near miss here is
    worse than no match, because the failure looks like broken recognition
    rather than a wrong capture source.
    """
    return DOTA_TITLE if DOTA_TITLE in list_window_titles() else None


def dota_like_titles() -> list[str]:
    """Other windows mentioning Dota — offered as suggestions in the UI's
    capture-source picker, never bound automatically."""
    return [t for t in list_window_titles()
            if "dota" in t.lower() and t != DOTA_TITLE]


def client_size(title: str) -> tuple[int, int] | None:
    """Client-area size of the window with this title, from its handle —
    dimensions are always measured, never assumed from a resolution."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return None
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    return rect.right - rect.left, rect.bottom - rect.top


def window_rect(title: str) -> tuple[int, int, int, int] | None:
    """Client area of the window, in SCREEN coordinates: (x, y, w, h).

    This is what an overlay anchors itself to. It is read straight from the
    window handle — no capture, no calibration, nothing asked of the user —
    which is why an edge-anchored overlay needs no setup at all.

    Returns physical pixels. Callers on a scaled display must divide by the
    screen's device pixel ratio before handing the numbers to Qt.
    """
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return None
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    origin = wintypes.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        return None
    return (origin.x, origin.y,
            rect.right - rect.left, rect.bottom - rect.top)


def is_foreground(title: str) -> bool:
    """True when this window is the one the user is looking at, so an
    overlay can hide itself the moment you alt-tab away from the game."""
    if sys.platform != "win32":
        return False
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, title)
    return bool(hwnd) and user32.GetForegroundWindow() == hwnd

"""Windows-only helpers around the Dota window handle (ctypes, no pywin32
needed at import time on other platforms). READ-ONLY: this module measures
the window; nothing anywhere sends input to it or touches the process (see
CLAUDE.md).
"""

import sys


def find_dota_window_title() -> str | None:
    """Exact 'Dota 2' title, or the single Dota-like candidate, else None."""
    if sys.platform != "win32":
        return None
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
                titles.append(buf.value)
        return True

    user32.EnumWindows(enum_proc, 0)
    if "Dota 2" in titles:
        return "Dota 2"
    candidates = [t for t in titles if "dota" in t.lower()]
    return candidates[0] if len(candidates) == 1 else None


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

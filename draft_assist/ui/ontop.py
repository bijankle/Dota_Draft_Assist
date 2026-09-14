"""Keep a window in front, or stop keeping it in front.

**IT IS NOT `setWindowFlags`, AND THAT IS THE WHOLE POINT OF THIS FILE.**
Qt's way to change always-on-top is to add or remove
`WindowStaysOnTopHint` — and on Windows, changing a window's flags
DESTROYS AND RECREATES THE NATIVE HANDLE. This app has already been bitten
by exactly that once: `setWindowIcon` ran before `setWindowFlags`, the icon
was pushed at an HWND that no longer existed, and the taskbar button fell
back to pythonw.exe (see `appicon.push_native_icon`). Doing it on a BUTTON
would repeat that fault every time the button was pressed, and it would
take the window's Win32 icon, its AppUserModelID relaunch properties and
its taskbar button's identity with it each time.

Windows has a call that does only the one thing: `SetWindowPos` with
`HWND_TOPMOST` or `HWND_NOTOPMOST`. It moves the window in the Z order and
touches nothing else — same handle, same icon, same identity, no flicker.

Everywhere else (which in practice means the test machines, since the app
is Windows-only) it falls back to Qt's flag and then puts the window back
on screen, because `setWindowFlags` hides it.

Never fatal. A window that will not come to the front is a nuisance; an
app that will not start because it could not reorder itself is worse.
"""

from __future__ import annotations

import sys

# What `apply` last did, for the diagnostic paste. It reads identically
# whether the call worked or was never made unless it says which.
note = "not attempted"

# SetWindowPos' first two arguments and the flags that make it a Z-order
# change and nothing else.
_TOPMOST = -1
_NOTOPMOST = -2
_NOMOVE = 0x0002
_NOSIZE = 0x0001
_NOACTIVATE = 0x0010


def _windows(hwnd: int, on: bool) -> bool:
    import ctypes
    user32 = ctypes.windll.user32          # noqa: F821 - Windows only
    # `restype` is NOT optional: the default is a 32-bit int, and the
    # same omission truncated a 64-bit HICON elsewhere in this app.
    user32.SetWindowPos.restype = ctypes.c_bool
    user32.SetWindowPos.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_uint]
    return bool(user32.SetWindowPos(
        ctypes.c_void_p(hwnd),
        ctypes.c_void_p(_TOPMOST if on else _NOTOPMOST),
        0, 0, 0, 0, _NOMOVE | _NOSIZE | _NOACTIVATE))


def apply(window, on: bool) -> bool:
    """Put `window` on top, or let it fall behind. True if it took."""
    global note
    on = bool(on)
    if sys.platform == "win32":
        try:
            hwnd = int(window.winId())
        except Exception:
            hwnd = 0
        if not hwnd:
            note = "no window handle yet"
            return False
        try:
            if _windows(hwnd, on):
                note = f"SetWindowPos {'topmost' if on else 'not topmost'}"
                return True
            note = "SetWindowPos refused"
        except Exception as exc:            # noqa: BLE001 - never fatal
            note = f"SetWindowPos failed: {exc}"
        return False

    # NOT WINDOWS. Qt's flag is the only route, and it hides the window on
    # the way through — so it has to be shown again, and only if it was
    # on screen to begin with. Showing a window nobody had opened would
    # be this function deciding something it was not asked about.
    from PyQt6.QtCore import Qt

    try:
        was_visible = window.isVisible()
        window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on)
        if was_visible:
            window.show()
        note = f"window flag {'set' if on else 'cleared'}"
        return True
    except Exception as exc:                # noqa: BLE001 - never fatal
        note = f"window flag failed: {exc}"
        return False

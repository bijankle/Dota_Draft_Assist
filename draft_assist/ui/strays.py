"""Catch every window this process puts on screen, and say what it was.

**THIS EXISTS BECAUSE THE FAULT CANNOT BE SEEN FROM THE MACHINE THE CODE
IS WRITTEN ON.** Reported as "still get these small windows flashign up
on the screen frequently jsut on boot - they have the app logo top left
and are small blank windowwws flickering on / off", and then, which is
the part that names it: "the blue is my desktiop background",
"treansulscent when transitioning into materialsiing thje window". So it
is a window with the DESKTOP showing through it and a thin frame round
it — something mid-materialisation, not a stray widget with a grey
client area.

Two rounds were spent reasoning at it and the second one was wrong. What
IS established, by measurement rather than argument, is that the Qt side
is clean: across a full boot the only top-level Show in the whole
application is `MainWindow`'s, and `allWidgets()` afterwards holds
exactly one parentless widget (`test_ui_smoke.
test_the_app_owns_exactly_one_window_and_nothing_else`). That rules out
this project's own favourite trap and rules out nothing else — a window
belonging to a LIBRARY, or Qt's own native handle being destroyed and
recreated, is invisible to every check of that kind.

So this asks WINDOWS, which is the only thing that knows. `EnumWindows`
filtered to our own process id, sampled fast enough to catch a flash,
for the first seconds after the app opens. It records what the eye
cannot: the window CLASS (which names whoever created it — Qt, a capture
library, a console host), whether it has a native CAPTION (which is what
draws an icon top-left), whether it is LAYERED (translucent), its size
and where it was. A window that has come and gone is still in the
report.

**SAMPLED, NOT HOOKED.** A CBT hook would catch every creation exactly
and is a system-wide hook installed from a running app, which is a far
bigger thing to get wrong than missing a frame. At `PERIOD` a window has
to survive about a twentieth of a second to be seen, and the report says
how many samples it was in — one sample is "gone before we looked
again", which is itself the measurement.

**AND IT STOPS.** `WATCH_FOR` seconds of boot and then the timer is
dropped: the complaint is about boot, and a sampler running all evening
over a window read at a glance during a draft is the sort of cost this
app measures its refresh loop to avoid.

Never fatal, and nothing at all off Windows.
"""

from __future__ import annotations

import sys
import time

# How often to look, and for how long after the app opens. 40ms catches
# anything on screen for a tenth of a second; 45s covers a slow first
# start with the statistics being read off disk.
PERIOD = 0.04
WATCH_FOR = 45.0

# Win32 bits worth naming in the report. CAPTION is what draws the app's
# icon in a corner; LAYERED is what lets the desktop show through.
_WS_CAPTION = 0x00C00000
_WS_VISIBLE = 0x10000000
_WS_EX_LAYERED = 0x00080000
_WS_EX_TOOLWINDOW = 0x00000080
_GWL_STYLE = -16
_GWL_EXSTYLE = -20


class Seen:
    """One window, and everything measured about it while it existed."""

    def __init__(self, hwnd: int, at: float):
        self.hwnd = hwnd
        self.first = at
        self.last = at
        self.samples = 1
        self.cls = ""
        self.title = ""
        self.rect = (0, 0, 0, 0)
        self.style = 0
        self.exstyle = 0

    @property
    def size(self) -> tuple[int, int]:
        left, top, right, bottom = self.rect
        return right - left, bottom - top

    def line(self, start: float, ours: int) -> str:
        width, height = self.size
        marks = []
        if self.hwnd == ours:
            marks.append("THE APP'S OWN WINDOW")
        if self.style & _WS_CAPTION == _WS_CAPTION:
            marks.append("native caption (draws an icon)")
        if self.exstyle & _WS_EX_LAYERED:
            marks.append("layered (see-through)")
        if self.exstyle & _WS_EX_TOOLWINDOW:
            marks.append("tool window")
        return (f"{self.cls!r} {self.title!r} {width}x{height} "
                f"at ({self.rect[0]},{self.rect[1]}) "
                f"{self.first - start:.2f}s..{self.last - start:.2f}s "
                f"({self.samples} sample{'' if self.samples == 1 else 's'})"
                + (" - " + ", ".join(marks) if marks else ""))


class Watcher:
    """Samples this process's visible top-level windows for a while."""

    def __init__(self):
        self.started = time.monotonic()
        self.seen: dict[int, Seen] = {}
        self.samples = 0
        self.note = "not attempted"

    # -- the one Windows call ------------------------------------------
    def _visible_windows(self) -> list[int]:
        """Every VISIBLE top-level window owned by this process."""
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32       # noqa: F821 - Windows only
        kernel32 = ctypes.windll.kernel32   # noqa: F821 - Windows only
        # `restype` is not optional anywhere in this app's ctypes: the
        # default is a 32-bit int, which truncates a 64-bit handle.
        user32.IsWindowVisible.restype = ctypes.c_bool
        user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
        mine = kernel32.GetCurrentProcessId()
        found: list[int] = []

        proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p,
                                   ctypes.c_void_p)

        def each(hwnd, _lparam):            # noqa: ANN001
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == mine and user32.IsWindowVisible(hwnd):
                found.append(int(hwnd))
            return True

        user32.EnumWindows(proto(each), None)
        return found

    def _describe(self, entry: Seen) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32       # noqa: F821 - Windows only
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(ctypes.c_void_p(entry.hwnd), buf, 256)
        entry.cls = buf.value
        user32.GetWindowTextW(ctypes.c_void_p(entry.hwnd), buf, 256)
        entry.title = buf.value
        rect = wintypes.RECT()
        user32.GetWindowRect(ctypes.c_void_p(entry.hwnd), ctypes.byref(rect))
        entry.rect = (rect.left, rect.top, rect.right, rect.bottom)
        # GetWindowLongPtrW does not exist on 32-bit Python, where the
        # 32-bit call is the right one anyway.
        longptr = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        longptr.restype = ctypes.c_ssize_t
        longptr.argtypes = [ctypes.c_void_p, ctypes.c_int]
        entry.style = int(longptr(ctypes.c_void_p(entry.hwnd), _GWL_STYLE))
        entry.exstyle = int(longptr(ctypes.c_void_p(entry.hwnd),
                                    _GWL_EXSTYLE))

    # -- the loop ------------------------------------------------------
    def sample(self) -> None:
        """One look. Never raises — this is a diagnostic, not a feature."""
        if sys.platform != "win32":
            self.note = "not Windows"
            return
        try:
            windows = self._visible_windows()
        except Exception as exc:            # noqa: BLE001 - see above
            self.note = f"{type(exc).__name__}: {exc}"
            return
        now = time.monotonic()
        self.samples += 1
        self.note = f"{self.samples} samples"
        for hwnd in windows:
            entry = self.seen.get(hwnd)
            if entry is None:
                entry = self.seen[hwnd] = Seen(hwnd, now)
            else:
                entry.last = now
                entry.samples += 1
            try:
                self._describe(entry)
            except Exception:               # noqa: BLE001 - see above
                pass

    def expired(self) -> bool:
        return time.monotonic() - self.started >= WATCH_FOR

    def report(self, ours: int = 0) -> str:
        """What appeared, oldest first. Every window, including ours."""
        if not self.seen:
            return self.note
        lines = [f"{self.note}, {WATCH_FOR:.0f}s from start"]
        for entry in sorted(self.seen.values(), key=lambda s: s.first):
            lines.append("  " + entry.line(self.started, ours))
        return "\n".join(lines)

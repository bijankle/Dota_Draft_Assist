"""The application's icon, and the one place that decides what it is.

Three sources, in order, and none of them is a file this repository ships:

1. `assets/app.ico` or `app.png`, if the user put one there. Their own
   file on their own machine, whatever they like.
2. Bloodseeker's portrait, which the app has ALREADY downloaded into
   `assets/portraits/base/` for the recogniser. The user asked for that
   icon; it is Valve's artwork, so it is not committed here — but it is
   already sitting on their disk, fetched by a step they ran themselves,
   and pointing the window at a file that exists is not redistribution.
3. A drawn fallback, so a fresh install is never iconless.

Drawn rather than shipped as a binary: a few lines of painting keep the
repository free of image blobs nobody can diff, and the fallback only has
to read as "this app" at 16 pixels.

The TASKBAR is a separate problem on Windows. A Python process is grouped
under python.exe and shows its icon no matter what the window says, unless
the process declares an explicit AppUserModelID first — hence `claim_taskbar_identity`.
"""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPixmap

from ..config import ASSETS_DIR
from . import theme

# Anything here wins over everything below, in this order.
CANDIDATES = ("app.ico", "app.png")
# Bloodseeker. The user asked for this one by name; the recogniser has
# already downloaded it, so nothing new is fetched and nothing is shipped.
FALLBACK_HERO = 4
# Windows groups by this string rather than by executable, so setting it
# is what stops the taskbar showing Python's icon.
APP_ID = "DotaDraftAssist.App"

_icon: QIcon | None = None


def _drawn(size: int = 256) -> QPixmap:
    """A dark shield with a draft-blue chevron. Deliberately plain."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    body = QRectF(size * 0.06, size * 0.06, size * 0.88, size * 0.88)
    grad = QLinearGradient(body.topLeft(), body.bottomRight())
    grad.setColorAt(0.0, QColor(theme.BG_INPUT))
    grad.setColorAt(1.0, QColor(theme.BG_DEEP))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(grad)
    painter.drawRoundedRect(body, size * 0.18, size * 0.18)
    font = QFont()
    font.setPointSizeF(size * 0.58)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(theme.ACCENT))
    painter.drawText(body, int(Qt.AlignmentFlag.AlignCenter), "D")
    painter.end()
    return pixmap


def icon() -> QIcon:
    """The app icon, read once."""
    global _icon
    if _icon is None:
        _icon = _supplied() or _hero_portrait() or QIcon(_drawn())
    return _icon


def _supplied() -> QIcon | None:
    for name in CANDIDATES:
        path = ASSETS_DIR / name
        if path.exists():
            candidate = QIcon(str(path))
            if not candidate.isNull():
                return candidate
    return None


def _hero_portrait() -> QIcon | None:
    """Bloodseeker, out of the portraits the recogniser downloaded."""
    from .portraits import portrait
    art = portrait(FALLBACK_HERO)
    return QIcon(art) if art is not None else None


def claim_taskbar_identity() -> None:
    """Tell Windows this is its own application, not python.exe.

    Without it the taskbar groups the window under Python and shows
    Python's icon whatever `setWindowIcon` says. Must run before the first
    window appears. A no-op everywhere else, and never fatal: an icon is
    not worth failing to start over.
    """
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass


def pixmap(size: int) -> QPixmap:
    art = icon().pixmap(size, size)
    return art if not art.isNull() else _drawn(size)


def forget() -> None:
    """Drop the cache — after the user drops a file in, or in tests."""
    global _icon
    _icon = None


def source() -> str:
    """Where the icon came from — for the About box and for tests."""
    if _supplied() is not None:
        return "assets"
    if _hero_portrait() is not None:
        return "portrait"
    return "drawn"

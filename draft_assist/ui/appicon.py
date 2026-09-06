"""The application's icon, and the one place that decides what it is.

The user asked for Warcraft III: The Frozen Throne's icon. That is
Blizzard's artwork and this project will not download or ship it — so the
app loads whatever `assets/app.ico` (or .png) the user puts there, which is
their own file on their own machine, and falls back to a drawn one so the
window is never iconless.

Drawn rather than shipped as a binary: a few lines of painting keep the
repository free of image blobs nobody can diff, and the fallback only has
to read as "this app" at 16 pixels.
"""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPixmap

from ..config import ASSETS_DIR
from . import theme

# Anything here wins over the drawn fallback, in this order.
CANDIDATES = ("app.ico", "app.png")

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
    font.setPointSizeF(size * 0.46)
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
        for name in CANDIDATES:
            path = ASSETS_DIR / name
            if path.exists():
                candidate = QIcon(str(path))
                if not candidate.isNull():
                    _icon = candidate
                    break
        else:
            _icon = QIcon(_drawn())
    return _icon


def pixmap(size: int) -> QPixmap:
    art = icon().pixmap(size, size)
    return art if not art.isNull() else _drawn(size)


def forget() -> None:
    """Drop the cache — after the user drops a file in, or in tests."""
    global _icon
    _icon = None


def is_custom() -> bool:
    """True when the user supplied their own file rather than the drawn one."""
    return any((ASSETS_DIR / name).exists() for name in CANDIDATES)

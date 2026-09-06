"""The application's icon, and the one place that decides what it is.

Three sources, in order, and none of them is a file this repository ships:

1. `assets/app.ico` (or .png/.jpg), if the user put one there — by hand or
   through Setup ▸ Choose app icon…, which copies their file into place.
   Their own artwork on their own machine, whatever they like.
2. Bloodseeker's portrait, which the app has ALREADY downloaded into
   `assets/portraits/base/` for the recogniser. Valve's artwork, so it is
   not committed here — but it is already on their disk, fetched by a step
   they ran themselves, and pointing a window at a file that exists is not
   redistribution.
3. A drawn fallback, so a fresh install is never iconless.

Every pixmap this module hands out is SQUARE and letterboxed, never
cropped. Source 2 is a 256x144 head shot — Dota's own crop — so filling a
square box with it slices the top and bottom off the hero's head, which is
exactly what it looked like. Fitting it inside a transparent square keeps
the whole picture and lets a square icon (source 1, normally) fill the box
edge to edge.

The TASKBAR is a separate problem on Windows. A Python process is grouped
under python.exe and shows its icon no matter what the window says, unless
the process declares an explicit AppUserModelID before its first window —
hence `claim_taskbar_identity`. Windows also asks the icon for specific
sizes (16 for the title, 32 and 48 for the taskbar, 256 for Alt-Tab), so a
QIcon carrying one pixmap gets scaled by the shell into something blurry:
the icon is built at every size the shell asks for.
"""

import shutil
import struct
from pathlib import Path

from PyQt6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPixmap

from ..config import ASSETS_DIR
from . import theme

# Anything here wins over everything below, in this order.
CANDIDATES = ("app.ico", "app.png", "app.jpg", "app.jpeg", "app.bmp")
# The sizes Windows actually asks a taskbar icon for.
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
# What goes into a .ico for a shortcut. Fewer than SIZES: the file is read
# by Explorer, which picks the nearest and scales.
ICO_SIZES = (16, 32, 48, 64, 128, 256)
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


def _square(art: QPixmap, size: int) -> QPixmap:
    """`art` fitted inside a transparent square of `size`, never cropped."""
    canvas = QPixmap(size, size)
    canvas.fill(QColor(0, 0, 0, 0))
    if art.isNull() or size < 1:
        return canvas
    fitted = art.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
    painter = QPainter(canvas)
    painter.drawPixmap((size - fitted.width()) // 2,
                       (size - fitted.height()) // 2, fitted)
    painter.end()
    return canvas


def icon() -> QIcon:
    """The app icon, built once."""
    global _icon
    if _icon is None:
        _icon = _build()
    return _icon


def _build() -> QIcon:
    path = supplied_path()
    if path is not None:
        # A real .ico already carries every size the shell wants, and
        # whatever the user supplied is meant to be used as it is.
        candidate = QIcon(str(path))
        if not candidate.isNull():
            return candidate
    art = _hero_pixmap() or _drawn(256)
    built = QIcon()
    for size in SIZES:
        built.addPixmap(_square(art, size))
    return built


def supplied_path() -> Path | None:
    """The user's own icon file, if there is one."""
    for name in CANDIDATES:
        path = ASSETS_DIR / name
        if path.exists():
            return path
    return None


def install(path) -> Path:
    """Copy the user's chosen file in as the app icon.

    Raises ValueError if Qt cannot read it as an image, because a silent
    no-op here looks exactly like the bug this is meant to fix. Any icon
    already installed is removed first: two candidates would leave the
    order in CANDIDATES deciding, which is not what the user just chose.
    """
    src = Path(path)
    art = QPixmap(str(src))
    if art.isNull():
        raise ValueError(f"{src.name} is not an image Qt can read")
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    for name in CANDIDATES:
        (ASSETS_DIR / name).unlink(missing_ok=True)
    if src.suffix.lower() == ".ico":
        dest = ASSETS_DIR / "app.ico"
        shutil.copyfile(src, dest)
    else:
        # Normalised to PNG so the rest of the app has one thing to find,
        # and so a format Qt can read but not re-read from a copy cannot
        # exist.
        dest = ASSETS_DIR / "app.png"
        art.save(str(dest), "PNG")
    forget()
    return dest


def _hero_pixmap() -> QPixmap | None:
    """Bloodseeker, out of the portraits the recogniser downloaded."""
    from .portraits import portrait
    return portrait(FALLBACK_HERO)


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
    """A square pixmap of exactly `size`, whatever the source's shape."""
    art = icon().pixmap(size, size)
    if art.isNull():
        art = _drawn(size)
    if art.width() == size and art.height() == size:
        return art
    return _square(art, size)


def write_ico(path) -> Path:
    """Write a multi-size .ico from whatever the icon currently is.

    A Windows SHORTCUT's icon must be an .ico (or an exe/dll): point
    `IconLocation` at a .png and the shortcut draws blank, which is exactly
    what a pinned taskbar button with no picture looks like. And the pin is
    where this matters most, because Windows sources a pinned button's icon
    from the Start-menu shortcut whose AppUserModelID matches the running
    window — so if that shortcut has no usable icon, neither does the pin.

    PNG-compressed entries, which every Windows since Vista reads, so this
    is a header and the pixmaps we already have rather than a BMP encoder.
    """
    path = Path(path)
    frames = []
    for size in ICO_SIZES:
        # QBuffer() with no argument owns its byte array. Handing it a
        # temporary QByteArray instead lets Python free the array while Qt
        # is still writing into it, which crashes the process.
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        written = pixmap(size).save(buffer, "PNG")
        data = bytes(buffer.data())
        buffer.close()
        if written:
            frames.append((size, data))
    if not frames:
        raise ValueError("no icon pixmaps could be encoded")

    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = len(header) + 16 * len(frames)
    entries, blobs = b"", b""
    for size, data in frames:
        # 0 means 256 in the one-byte width and height fields.
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0,
                               1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + entries + blobs)
    return path


def forget() -> None:
    """Drop the cache — after the user drops a file in, or in tests."""
    global _icon
    _icon = None


def source() -> str:
    """Where the icon came from — for the About box and for tests."""
    if supplied_path() is not None:
        return "assets"
    if _hero_pixmap() is not None:
        return "portrait"
    return "drawn"

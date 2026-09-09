"""The application's icon, and the one place that decides what it is.

Four sources, in order:

1. `assets/app.ico` (or .png/.jpg), if the user put one there — by hand or
   through Setup ▸ Choose app icon…, which copies their file into place.
   Their own artwork on their own machine, whatever they like. Gitignored,
   so an update never overwrites it.
1b. `assets/app-default.png` (or .ico) — the icon this repository SHIPS,
   if one has been committed. A DIFFERENT NAME from the above on purpose:
   Setup ▸ Choose app icon… writes `app.ico`, so sharing the name would
   make every update stamp on the user's own pick. Whatever goes here has
   to be the project's to distribute.
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

from PyQt6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt
from PyQt6.QtGui import (QColor, QIcon, QLinearGradient, QPainter,
                         QPen, QPixmap, QPolygonF)

from ..config import ASSETS_DIR, REPO_ROOT
from . import theme

# Anything here wins over everything below, in this order. THESE ARE THE
# USER'S OWN and are gitignored, so an update can never land on top of a
# choice somebody made on their own machine.
CANDIDATES = ("app.ico", "app.png", "app.jpg", "app.jpeg", "app.bmp")
# The icon this repository SHIPS, if one has been committed. Deliberately
# a different name from CANDIDATES rather than the same file: Setup ▸
# Choose app icon… writes `app.ico`, and if the shipped default used that
# name too, every update would overwrite the user's pick with it. Two
# names, two owners, and the user's wins.
DEFAULT_CANDIDATES = ("app-default.ico", "app-default.png")
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
# What the taskbar and the jump list call it. Without it the
# window's jump list is headed "Python".
APP_NAME = "Dota Draft Assist"

_icon: QIcon | None = None
# What the last attempt at the taskbar identity did. A pin that
# still shows Python's icon has to be diagnosable from a paste,
# and a silent False says nothing about which half failed.
identity_note = "not attempted"


def _drawn(size: int = 256) -> QPixmap:
    """The icon this repository SHIPS, painted rather than committed.

    It has to be original. The icons asked for — Warcraft's Frozen Throne,
    then Bloodseeker — are Blizzard's and Valve's artwork, and putting
    either in the repository is redistributing it the moment anyone else
    clones this. So the shipped mark is drawn: two blades meeting across a
    diagonal, which is a draft in one shape — your side and theirs, and the
    line between them.

    Painted, not a committed .png, for two reasons that have both bitten
    already: no image blob nobody can diff, and it renders at whatever size
    the shell asks for instead of being upscaled from one. `assets/app.ico`
    still overrides it, so the user keeps whatever they like locally
    without it reaching anybody else.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    body = QRectF(size * 0.04, size * 0.04, size * 0.92, size * 0.92)
    plate = QLinearGradient(body.topLeft(), body.bottomRight())
    plate.setColorAt(0.0, QColor("#3b4252"))
    plate.setColorAt(1.0, QColor(theme.BG_DEEP))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(plate)
    painter.drawRoundedRect(body, size * 0.22, size * 0.22)

    # Two wedges facing each other across a diagonal gap: allies and
    # enemies, and the matchup between them. One shape, so it survives
    # being drawn sixteen pixels wide.
    gap = size * 0.055
    mine = QPolygonF([QPointF(size * 0.20, size * 0.74),
                      QPointF(size * 0.50 - gap, size * 0.20),
                      QPointF(size * 0.50 - gap, size * 0.74)])
    theirs = QPolygonF([QPointF(size * 0.80, size * 0.26),
                        QPointF(size * 0.50 + gap, size * 0.80),
                        QPointF(size * 0.50 + gap, size * 0.26)])
    painter.setBrush(QColor(theme.ACCENT))
    painter.drawPolygon(mine)
    painter.setBrush(QColor(theme.BAD))
    painter.drawPolygon(theirs)

    painter.setPen(QPen(QColor(0, 0, 0, 90), max(1.0, size * 0.012)))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(body, size * 0.22, size * 0.22)
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


def is_ico(path) -> bool:
    """Is this REALLY an .ico, or just something named one?

    Qt sniffs an image's content and ignores its extension, so a PNG
    renamed to .ico loads perfectly and the title bar looks right. The
    WINDOWS SHELL does not: it needs a genuine ICO container for a
    taskbar button, a pin and a shortcut, and given anything else it
    quietly draws something else. That combination — title bar correct,
    taskbar wrong — is exactly what a renamed PNG produces, and nothing
    anywhere said so.

    The header is six bytes: a zero, a 1 for "icon", and how many images
    are inside.
    """
    try:
        head = Path(path).open("rb").read(6)
    except OSError:
        return False
    if len(head) < 6:
        return False
    reserved = int.from_bytes(head[0:2], "little")
    kind = int.from_bytes(head[2:4], "little")
    count = int.from_bytes(head[4:6], "little")
    return reserved == 0 and kind == 1 and count > 0


def _from_file(path: Path) -> QIcon | None:
    """An icon built from a file somebody supplied, or None if unreadable.

    A REAL .ico ALREADY CARRIES EVERY SIZE the shell asks for, drawn or
    hinted for each, so it is used exactly as it is.

    ANYTHING ELSE IS ONE IMAGE — a 1024x1024 PNG is the normal case — and
    handing the shell a QIcon with a single pixmap in it is precisely how
    a taskbar button comes out blurry: Windows asks for 16, 32, 48 and
    256, finds only the one, and scales it itself at whatever quality it
    feels like. So a raster file is downsampled HERE, once per size in
    `SIZES`, with a smooth transform. Same treatment the drawn and
    portrait sources already got; this branch was skipping it.
    """
    # The CONTENT, not the extension: a real .ico carries every size, and
    # something merely named .ico carries one image that Qt would then
    # hand out at 1024 for a 16px request.
    if is_ico(path):
        supplied = QIcon(str(path))
        return supplied if not supplied.isNull() else None
    art = QPixmap(str(path))
    if art.isNull():
        return None
    built = QIcon()
    for size in SIZES:
        built.addPixmap(_square(art, size))
    return built


def _build() -> QIcon:
    for path in (supplied_path(), default_path()):
        if path is not None:
            candidate = _from_file(path)
            if candidate is not None:
                return candidate
    art = _hero_pixmap() or _drawn(256)
    built = QIcon()
    for size in SIZES:
        built.addPixmap(_square(art, size))
    return built


def default_path() -> Path | None:
    """The icon this repository ships, if one has been committed.

    Unlike everything around it this file IS in the repository, so it
    reaches every install and a fresh download opens with the app's real
    icon rather than the drawn fallback. Whatever goes here has to be the
    project's to distribute — the same bar the bundled fonts had to clear,
    and the one Valve's and Blizzard's artwork does not.
    """
    for name in DEFAULT_CANDIDATES:
        path = ASSETS_DIR / name
        if path.exists():
            return path
    return None


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


# {9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3} — the AppUserModel property set.
# The names are in pscon, but not in every pywin32, so the keys are built
# from the GUID and the property id and pscon is only a preference.
_AUM_FMTID = "{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}"
_AUM_PIDS = {"RelaunchCommand": 2, "RelaunchIconResource": 3,
             "RelaunchDisplayNameResource": 4, "ID": 5}


def launch_python() -> str:
    """pythonw from the app's own venv, so relaunching opens no console.

    The venv the launcher builds is the one with PyQt6 in it; whatever
    interpreter is running right now might not be, if it was started some
    other way.
    """
    import sys
    for candidate in (REPO_ROOT / ".venv/Scripts/pythonw.exe",
                      Path(sys.executable).with_name("pythonw.exe"),
                      Path(sys.executable)):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def relaunch_command() -> str:
    """The command line that starts this app from any working directory.

    `-m draft_assist.ui.app` is what the .bat runs and it needs the
    repository as the working directory. A pin has none, so this points at
    `draft_assist/__main__.py`, which puts the root on `sys.path` itself.
    """
    target = REPO_ROOT / "draft_assist" / "__main__.py"
    return f'"{launch_python()}" "{target}"'


def shell_ico() -> Path | None:
    """A real .ico for Windows to draw the pin and the shortcut from.

    The shell will not take a .png here — it draws blank — so a supplied
    .ico is used as it is and anything else is rendered into one next to
    it. Never fatal: no icon is worse than the right icon and better than
    not starting.
    """
    # Only a file that really IS an ICO goes to the shell. One that is
    # not gets rendered into a proper one below, which is what makes a
    # renamed PNG work in the taskbar instead of silently not.
    for candidate in (ASSETS_DIR / "app.ico", ASSETS_DIR / "app-default.ico"):
        if candidate.exists() and is_ico(candidate):
            return candidate
    try:
        return write_ico(ASSETS_DIR / "app-generated.ico")
    except Exception:                   # noqa: BLE001 - see the docstring
        return None


def _property_key(name: str, pscon, pythoncom):
    """`pscon.PKEY_AppUserModel_<name>` if this pywin32 has it, else built."""
    key = getattr(pscon, f"PKEY_AppUserModel_{name}", None)
    if key is not None:
        return key
    return (pythoncom.MakeIID(_AUM_FMTID), _AUM_PIDS[name])


def claim_window_identity(hwnd: int) -> bool:
    """Put the app's identity and relaunch details ON THE WINDOW.

    `claim_taskbar_identity` is only half the story. Pinning a RUNNING
    window does not pin the window: Windows pins an app identity and then
    has to work out what to launch and what to draw for it. Given only an
    AppUserModelID it goes looking for a Start-menu shortcut carrying the
    same string, and with none it falls back to the executable — which is
    pythonw.exe, so the pinned button turns into the Python icon labelled
    "Python", which is exactly what it did.

    A window can answer that question itself. `PKEY_AppUserModel_Relaunch*`
    on the window's own property store tell the shell what to run, what to
    draw and what to call it, and the pin is built from those with no
    shortcut anywhere in it. They must be set before the window is shown,
    because the taskbar reads them when it creates the button.

    Returns whether it was written, and is never fatal: an icon is not
    worth failing to start over.
    """
    global identity_note
    import sys
    # The handle first: a window with no native handle yet is a caller
    # mistake on any platform, and reading "not Windows" for it would
    # point at the wrong half.
    if not hwnd:
        identity_note = "no window handle"
        return False
    if sys.platform != "win32":
        identity_note = "not Windows"
        return False
    try:
        import pythoncom
        from win32com.propsys import propsys, pscon
    except ImportError:
        identity_note = "pywin32 is not installed"
        return False
    try:
        store = propsys.SHGetPropertyStoreForWindow(
            int(hwnd), propsys.IID_IPropertyStore)
        values = {"ID": APP_ID,
                  "RelaunchCommand": relaunch_command(),
                  "RelaunchDisplayNameResource": APP_NAME}
        icon_file = shell_ico()
        if icon_file is not None:
            # ",0" is the resource index, and it is not optional: without
            # one the shell reads the string as a resource reference it
            # cannot parse and draws nothing.
            values["RelaunchIconResource"] = f"{icon_file},0"
        for name, value in values.items():
            # PROPVARIANTType takes ONE argument. Handing it an explicit
            # variant type killed the interpreter outright with
            # STATUS_STACK_BUFFER_OVERRUN, which no `except` can catch.
            store.SetValue(_property_key(name, pscon, pythoncom),
                           propsys.PROPVARIANTType(value))
        store.Commit()
        identity_note = f"set on hwnd {int(hwnd)}: {values['RelaunchCommand']}"
        return True
    except Exception as exc:            # noqa: BLE001 - see the docstring
        identity_note = f"{type(exc).__name__}: {exc}"
        return False


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
    if default_path() is not None:
        return "default"
    if _hero_pixmap() is not None:
        return "portrait"
    return "drawn"

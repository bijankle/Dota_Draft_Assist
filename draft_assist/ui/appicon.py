"""The application's icon, and the one place that decides what it is.

Four sources, in order:

1. `assets/app.ico` (or .png/.jpg), if the user put one there — by hand or
   through Settings ▸ Appearance ▸ Choose app icon…, which copies their file into place.
   Their own artwork on their own machine, whatever they like. Gitignored,
   so an update never overwrites it.
1b. `assets/app-default.png` (or .ico) — the icon this repository SHIPS,
   if one has been committed. A DIFFERENT NAME from the above on purpose:
   Settings ▸ Appearance ▸ Choose app icon… writes `app.ico`, so sharing the name would
   make every update stamp on the user's own pick. Whatever goes here has
   to be the project's to distribute. With BOTH names present the bigger
   picture wins rather than the first extension — see `_best`.
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
from PyQt6.QtGui import (QColor, QIcon, QImage, QImageReader,
                         QLinearGradient, QPainter, QPen, QPixmap,
                         QPolygonF)

from ..config import ASSETS_DIR, REPO_ROOT
from . import theme

# Anything here wins over everything below, in this order. THESE ARE THE
# USER'S OWN and are gitignored, so an update can never land on top of a
# choice somebody made on their own machine.
CANDIDATES = ("app.ico", "app.png", "app.jpg", "app.jpeg", "app.bmp")
# The icon this repository SHIPS, if one has been committed. Deliberately
# a different name from CANDIDATES rather than the same file: Settings ▸
# Appearance ▸ Choose app icon… writes `app.ico`, and if the shipped default used that
# name too, every update would overwrite the user's pick with it. Two
# names, two owners, and the user's wins.
DEFAULT_CANDIDATES = ("app-default.ico", "app-default.png")
# NEITHER LIST IS TRIED IN ORDER. The order breaks a TIE and nothing more
# — see `_best`, which ranks whichever files are present by how big a
# picture each one actually holds.
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


def gui_ready() -> bool:
    """Is there a QGuiApplication yet?

    **TOUCHING A QPixmap BEFORE ONE EXISTS KILLS THE PROCESS**, and not
    with an exception: Qt prints "QPixmap: Must construct a
    QGuiApplication before a QPixmap" and aborts, so no `except` anywhere
    can save it and there is no traceback to read. From outside it is
    simply "the app does not open at all".

    That is not hypothetical — `ensure_start_menu_shortcut` was called
    from `main()` before the QApplication was built, and it reaches a
    QPixmap through `shell_ico` -> `write_ico` -> `pixmap`. Every entry
    point in this module that can end up painting therefore asks this
    first and refuses politely, so the worst a caller can do is get no
    icon rather than no application.
    """
    from PyQt6.QtGui import QGuiApplication
    return QGuiApplication.instance() is not None


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
        if not gui_ready():
            raise RuntimeError(
                "no QGuiApplication yet — building the icon here would "
                "abort the process rather than raise")
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


# The smallest LARGEST image an .ico must carry to be handed over whole.
# One 32x32 inside is enough for a title bar and not for a taskbar button,
# which asks for 40, 48 and 256 depending on the display's scaling.
PASS_THROUGH_MIN = 128


def ico_sizes(path) -> set:
    """Every image size inside an .ico, or an empty set.

    A real .ico is a DIRECTORY of images and may hold as few as one. The
    header alone says it is an icon; only the directory says whether it
    covers the sizes the shell will ask for.
    """
    import struct
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return set()
    if len(raw) < 6:
        return set()
    reserved, kind, count = struct.unpack("<HHH", raw[:6])
    if reserved or kind != 1 or count < 1 or len(raw) < 6 + 16 * count:
        return set()
    found = set()
    for index in range(count):
        # A zero in the one-byte width field means 256.
        width = raw[6 + index * 16] or 256
        found.add(width)
    return found


def covers_the_shell(path) -> bool:
    """Does this .ico carry a big enough image to hand over untouched?"""
    return is_ico(path) and max(ico_sizes(path), default=0) >= PASS_THROUGH_MIN


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
    # The CONTENT, not the extension, and the CONTENTS, not just the
    # header: an .ico holding a single 32x32 satisfies `is_ico` and still
    # leaves the shell nothing to draw a taskbar button from.
    if covers_the_shell(path):
        supplied = QIcon(str(path))
        return supplied if not supplied.isNull() else None
    art = QPixmap(str(path))
    if art.isNull():
        # A thin .ico still loads through QIcon, so fall back to its
        # biggest image and rebuild the range around it. Upscaling a 32
        # to 256 is not pretty, but a button drawn from something beats
        # one drawn from nothing.
        thin = QIcon(str(path))
        biggest = max(thin.availableSizes(), key=lambda s: s.width(),
                      default=None)
        if biggest is None:
            return None
        art = thin.pixmap(biggest)
    if art.isNull():
        return None
    built = QIcon()
    for size in SIZES:
        built.addPixmap(_square(art, size))
    return built


def _build() -> QIcon:
    for path in _readable_candidates():
        candidate = _from_file(path)
        if candidate is not None:
            return candidate
    art = _hero_pixmap() or _drawn(256)
    built = QIcon()
    for size in SIZES:
        built.addPixmap(_square(art, size))
    return built


def biggest_image(path) -> int:
    """The largest picture this file actually holds, or 0 if none.

    An .ico is a DIRECTORY of images, so its answer is its biggest entry;
    anything else is one image, and its header says how big it is without
    decoding a megabyte of pixels to find out. Zero doubles as the
    readability test: a file Qt cannot make sense of has nothing to offer
    and must not be chosen over one that does.
    """
    if is_ico(path):
        return max(ico_sizes(path), default=0)
    size = QImageReader(str(path)).size()
    if not size.isValid():
        return 0
    return max(size.width(), size.height())


def _best(names) -> Path | None:
    """Whichever of these files has the most to draw with.

    **ORDERING BY EXTENSION IS WHAT BROKE THIS, and it broke it in the one
    way that looks like nothing changed.** `app-default.ico` was checked
    before `app-default.png`, so an .ico holding a single 32x32 sitting
    beside a 1024x1024 PNG won on the strength of its filename and the PNG
    was never opened — leaving the taskbar exactly as wrong as it had been
    before the PNG was added, which is precisely what "I added the full
    size png and it still is not working" was. Nothing on screen could say
    so: the title bar draws fine from a 32, and the file that was being
    ignored was sitting right there in the folder.

    So the question is not which name comes first, it is which file has
    the most to draw with — `biggest_image`. A real .ico wins a TIE,
    because it can be handed to the shell untouched; the list order breaks
    the tie after that. Two files no longer produce a worse icon than
    either of them alone, which is the property that was missing.
    """
    ranked = []
    for order, name in enumerate(names):
        path = ASSETS_DIR / name
        if path.exists():
            ranked.append((biggest_image(path), is_ico(path), -order, path))
    if not ranked:
        return None
    return max(ranked)[3]


def default_path() -> Path | None:
    """The icon this repository ships, if one has been committed.

    Unlike everything around it this file IS in the repository, so it
    reaches every install and a fresh download opens with the app's real
    icon rather than the drawn fallback. Whatever goes here has to be the
    project's to distribute — the same bar the bundled fonts had to clear,
    and the one Valve's and Blizzard's artwork does not.
    """
    return _best(DEFAULT_CANDIDATES)


def supplied_path() -> Path | None:
    """The user's own icon file, if there is one."""
    return _best(CANDIDATES)


def _readable_candidates() -> list:
    """The supplied file and the shipped one, best first, skipping any
    that hold no picture at all."""
    return [path for path in (supplied_path(), default_path())
            if path is not None and biggest_image(path) > 0]


def chosen_path() -> Path | None:
    """The file the app's icon is actually built from, if any.

    ONE answer, asked by `_build` and by `shell_ico` alike. They used to
    decide separately — `shell_ico` had its own hard-coded pair of
    filenames — and two lists that can disagree is how the window and the
    pin end up drawing two different pictures, which is a worse fault than
    either of them being wrong.
    """
    found = _readable_candidates()
    return found[0] if found else None


def describe() -> str:
    """One line saying where the icon came from and what is in it.

    "Title bar right, taskbar wrong" has now had THREE separate causes: a
    PNG renamed to .ico, a genuine .ico holding one 32x32, and a big PNG
    passed over because a small .ico sorted ahead of it. None of the three
    is visible in the picture and all three are obvious in one line, so
    the line goes in Debug ▸ Copy everything with the rest of what a
    report needs.
    """
    path = chosen_path()
    if path is None:
        return f"{source()} — no icon file in {ASSETS_DIR}"
    if is_ico(path):
        holds = f"ico holding {sorted(ico_sizes(path))}"
    else:
        holds = f"{biggest_image(path)}px image"
    passed = "handed to the shell as it is" if covers_the_shell(path) \
        else "rebuilt at every size"
    return f"{source()}: {path.name} — {holds}, {passed}"


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
    # Only a file that really IS an ICO goes to the shell, and only the
    # one the app's own icon was built from — asking `chosen_path` rather
    # than a second list of filenames is what stops the window and the pin
    # drawing two different pictures. Anything else is rendered into a
    # proper .ico below, which is what makes a PNG work in the taskbar
    # instead of silently not.
    if not gui_ready():
        return None
    candidate = chosen_path()
    if candidate is not None and covers_the_shell(candidate):
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


# The Win32 icon a window is asked for, and the two sizes the shell asks
# it for. WM_SETICON is how a window TELLS Windows what it looks like;
# everything else in this module is about files the shell reads later.
_WM_SETICON = 0x0080
_WM_GETICON = 0x007F
_ICON_SMALL, _ICON_BIG = 0, 1
_SM_CXICON, _SM_CYICON = 11, 12
_SM_CXSMICON, _SM_CYSMICON = 49, 50
_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x0010
# The handles must OUTLIVE the call. Windows does not copy them, and a
# destroyed HICON leaves the taskbar drawing whatever it likes.
_handles: list = []

# What `push_native_icon` last did. In the paste beside `identity_note`,
# because between them they say which of the two mechanisms is at fault.
window_icon_note = "not attempted"


def push_native_icon(hwnd: int) -> bool:
    """Set the window's OWN Win32 icon, which is what the taskbar draws.

    **THE LIVE TASKBAR BUTTON IS NOT DRAWN FROM `RelaunchIconResource`.**
    That property, and the AppUserModelID beside it, are what a PIN and a
    jump list are built from. A button for a window that is running comes
    from the window itself — `WM_GETICON`, falling back to the window
    class, falling back to the executable. Everything this module did
    before was about files the shell reads later, and the live button was
    never addressed at all except through Qt's `setWindowIcon`.

    Which this app then undermined. `setWindowIcon` ran BEFORE
    `setWindowFlags(FramelessWindowHint | ...)`, and changing a window's
    flags on Windows DESTROYS AND RECREATES the native handle — so the
    icon was pushed at an HWND that no longer exists, and the button fell
    back to pythonw.exe. It is the same shape as every other fault in this
    module: our own title bar draws from `appicon.pixmap` and was always
    right, while the thing the SHELL reads had nothing in it.

    So the icon is set here, explicitly, from the .ico this module
    already renders — at the two sizes Windows asks for by name rather
    than at guessed ones, because a display at 150% scaling asks for
    different numbers. Never fatal: an icon is not worth failing to start
    over.
    """
    global window_icon_note
    import sys
    if not hwnd:
        window_icon_note = "no window handle"
        return False
    if sys.platform != "win32":
        window_icon_note = "not Windows"
        return False
    icon_file = shell_ico()
    if icon_file is None:
        window_icon_note = "no .ico to load"
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        # RESTYPES ARE NOT OPTIONAL HERE. ctypes defaults a return to
        # `int`, which is 32 bits — so a 64-bit HICON comes back
        # TRUNCATED, and the truncated value is a handle to nothing. The
        # call then succeeds, sets garbage, and reports success.
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR,
                                      wintypes.UINT, ctypes.c_int,
                                      ctypes.c_int, wintypes.UINT]
        user32.SendMessageW.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                        ctypes.c_void_p, ctypes.c_void_p]

        def load(cx: int, cy: int):
            return user32.LoadImageW(
                None, str(icon_file), _IMAGE_ICON,
                user32.GetSystemMetrics(cx), user32.GetSystemMetrics(cy),
                _LR_LOADFROMFILE)

        big = load(_SM_CXICON, _SM_CYICON)
        small = load(_SM_CXSMICON, _SM_CYSMICON)
        if not big and not small:
            window_icon_note = f"LoadImage found nothing in {icon_file.name}"
            return False
        window = wintypes.HWND(int(hwnd))
        for which, handle in ((_ICON_BIG, big), (_ICON_SMALL, small)):
            if handle:
                _handles.append(handle)
                user32.SendMessageW(window, _WM_SETICON,
                                    ctypes.c_void_p(which),
                                    ctypes.c_void_p(handle))
        # READ IT BACK. "I sent the message" is not the same claim as
        # "the window has an icon", and this module has already shipped
        # four fixes whose diagnostics could not tell those apart.
        got_big = user32.SendMessageW(window, _WM_GETICON,
                                      ctypes.c_void_p(_ICON_BIG), None)
        got_small = user32.SendMessageW(window, _WM_GETICON,
                                        ctypes.c_void_p(_ICON_SMALL), None)
        window_icon_note = (f"{icon_file.name} -> hwnd {int(hwnd)}; "
                            f"reads back big={got_big or 0} "
                            f"small={got_small or 0}")
        return bool(got_big or got_small)
    except Exception as exc:            # noqa: BLE001 - see the docstring
        window_icon_note = f"{type(exc).__name__}: {exc}"
        return False


SHORTCUT_NAME = "Dota Draft Assist"
# What `ensure_start_menu_shortcut` last did, for the paste.
shortcut_note = "not attempted"
_shortcut_done = False


def start_menu_link() -> Path:
    """Where the app's own Start-menu shortcut goes."""
    return (Path.home() / "AppData/Roaming/Microsoft/Windows"
            / "Start Menu/Programs" / f"{SHORTCUT_NAME}.lnk")


def write_shortcut(path=None) -> Path:
    """Write the .lnk, with the AppUserModelID and the icon on it.

    The ONE implementation, shared with `tools/make_shortcut.py` — the
    menu item and the automatic call must not be able to produce two
    different shortcuts. Raises on failure; the callers decide whether
    that is worth saying anything about.
    """
    import pythoncom
    from win32com.propsys import propsys, pscon
    from win32com.shell import shell

    link_path = Path(path) if path is not None else start_menu_link()
    link_path.parent.mkdir(parents=True, exist_ok=True)
    link = pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER,
        shell.IID_IShellLink)
    link.SetPath(launch_python())
    # The same target the window's relaunch command uses, so a pin made
    # from the shortcut and one made from the running window start the app
    # identically.
    link.SetArguments(f'"{REPO_ROOT / "draft_assist" / "__main__.py"}"')
    link.SetWorkingDirectory(str(REPO_ROOT))
    link.SetDescription("Read the Dota 2 draft and suggest picks and items")
    icon = shell_ico()
    if icon is not None:
        link.SetIconLocation(str(icon), 0)
    # Stamped BEFORE the file is written, and survivable: this call has
    # already taken the process down once (an explicit variant type killed
    # the interpreter with STATUS_STACK_BUFFER_OVERRUN, which no `except`
    # can catch), and a shortcut without the identity is still a shortcut.
    try:
        store = link.QueryInterface(propsys.IID_IPropertyStore)
        store.SetValue(pscon.PKEY_AppUserModel_ID,
                       propsys.PROPVARIANTType(APP_ID))
        store.Commit()
    except Exception:                   # noqa: BLE001 - see above
        pass
    link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(link_path), 0)
    announce_shortcut(link_path)
    return link_path


# SHChangeNotify, and the two events that mean "there is a new item here".
_SHCNE_CREATE = 0x00000002
_SHCNE_UPDATEDIR = 0x00001000
_SHCNF_PATHW = 0x0005


def announce_shortcut(link_path) -> None:
    """Tell the shell the Start menu changed, NOW.

    **WRITING THE FILE IS NOT ENOUGH ON THE RUN THAT WRITES IT.** The
    shell resolves an AppUserModelID against its own index of Start-menu
    shortcuts, and a .lnk that has just appeared is not in that index
    yet — so the taskbar button, created moments later when the window is
    shown, still finds nothing and draws blank. By the NEXT launch the
    index has caught up and the icon is correct, which is exactly the
    shape the user reported: wrong on a fresh unzip, right after an
    update restarts the app.

    `SHChangeNotify` is the documented way to say "notice this now"
    rather than waiting for the shell to get round to it. Both the file
    and its folder are announced, because the two are indexed
    separately. Never fatal: an un-announced shortcut is still a
    shortcut, and it will be picked up on the next start regardless.
    """
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        shell32 = ctypes.windll.shell32
        shell32.SHChangeNotify.restype = None
        shell32.SHChangeNotify.argtypes = [wintypes.LONG, wintypes.UINT,
                                           ctypes.c_void_p, ctypes.c_void_p]
        here = ctypes.c_wchar_p(str(link_path))
        folder = ctypes.c_wchar_p(str(Path(link_path).parent))
        shell32.SHChangeNotify(_SHCNE_CREATE, _SHCNF_PATHW,
                               ctypes.cast(here, ctypes.c_void_p), None)
        shell32.SHChangeNotify(_SHCNE_UPDATEDIR, _SHCNF_PATHW,
                               ctypes.cast(folder, ctypes.c_void_p), None)
    except Exception:                   # noqa: BLE001 - see the docstring
        pass


def ensure_start_menu_shortcut() -> bool:
    """Make sure the shortcut the AppUserModelID resolves to exists.

    **THIS IS WHAT AN EXPLICIT AppUserModelID OBLIGES THE APP TO PROVIDE,
    and not providing it is worse than never having set one.** Declaring
    an ID tells Windows to stop treating the process as pythonw.exe and
    to treat it as its own application — after which the shell resolves
    that application's name and icon through the Start-menu shortcut
    carrying the same string. With no such shortcut there is nothing to
    resolve to, which is why the button drew as a BLANK PAGE rather than
    as Python's logo: it had already stopped being Python and had not yet
    become anything.

    Evidence, from a real install, that this is the remaining half:
    `window_icon_note` reported both HICON handles set on the window, so
    the window itself was not the problem, and the button was still
    wrong.

    It is AUTOMATIC at the user's request — "it should be all auto
    anyway" — rather than the menu item it used to be, which is a step
    nobody who has just unzipped this app would know to take. It writes
    ONE file inside the user's own Start menu and nothing else.

    Rewritten on every start rather than only when missing, because the
    thing it points at moves: this app is normally run from a folder
    somebody unzipped, and downloading a newer ZIP produces a SECOND
    folder beside the first. A shortcut left pointing at the old one is
    worse than none, and re-writing it costs a few milliseconds against
    a fault that is invisible until somebody clicks it.

    Never fatal, once per process, and silent — a Start-menu entry is not
    something to interrupt a first run about.
    """
    global shortcut_note, _shortcut_done
    import sys
    if _shortcut_done:
        return True
    if sys.platform != "win32":
        shortcut_note = "not Windows"
        return False
    if not gui_ready():
        # Not merely a bad idea: it reaches a QPixmap, which ABORTS the
        # process when there is no QGuiApplication. Called too early once
        # already, and the app simply stopped opening.
        shortcut_note = "called before the QApplication existed"
        return False
    try:
        written = write_shortcut()
    except ImportError:
        shortcut_note = "pywin32 is not installed"
        return False
    except Exception as exc:            # noqa: BLE001 - see the docstring
        shortcut_note = f"{type(exc).__name__}: {exc}"
        return False
    _shortcut_done = True
    shortcut_note = f"{written} -> {APP_ID}"
    return True


def _identity_summary(hwnd: int, command: str, icon_file) -> str:
    """What `claim_window_identity` reports it did.

    NAMING THE ICON is the whole reason this is separate. `shell_ico`
    returning None — the .ico could not be written — used to leave the
    note reading exactly as it does on success, so a report saying "set
    on hwnd ..." was consistent both with the shell having been handed a
    picture and with it having been handed none. That is the one question
    the note exists to answer, and it was the one it could not.
    """
    drew = (f"icon {icon_file}" if icon_file is not None
            else "NO ICON FILE — shell_ico() could not write one")
    return f"set on hwnd {hwnd}: {command} | {drew}"


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
        identity_note = _identity_summary(
            int(hwnd), values["RelaunchCommand"], icon_file)
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


# Below this size an entry is written as a DIB rather than as a PNG. See
# `write_ico`: PNG entries inside an .ico are only reliably read at 256,
# and 256 is the one size the shell does NOT ask for when it draws a
# taskbar button.
PNG_ENTRY_MIN = 256


def _dib_entry(size: int) -> bytes | None:
    """One icon image in the ORIGINAL format: a BITMAPINFOHEADER, the
    pixels bottom-up as BGRA, and an AND mask.

    Written by hand because Qt has no "encode me a DIB" call, and it is
    twenty lines: a 40-byte header whose HEIGHT IS DOUBLED (the format
    counts the colour bitmap and the mask as one image), the rows in
    reverse because a DIB is bottom-up, and a mask of zeroes since a
    32-bit entry carries its own alpha and Windows uses that.
    """
    art = pixmap(size).toImage().convertToFormat(
        QImage.Format.Format_ARGB32)
    if art.isNull() or art.width() != size or art.height() != size:
        return None
    stride = art.bytesPerLine()
    raw = bytes(art.constBits().asstring(stride * size))
    # Format_ARGB32 is B, G, R, A per pixel on a little-endian machine,
    # which is exactly a 32-bit DIB's byte order. Bottom row first.
    rows = [raw[y * stride:y * stride + size * 4] for y in range(size)]
    pixels = b"".join(reversed(rows))
    mask_stride = ((size + 31) // 32) * 4
    mask = b"\x00" * (mask_stride * size)
    head = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
                       len(pixels) + len(mask), 0, 0, 0, 0)
    return head + pixels + mask


def write_ico(path) -> Path:
    """Write a multi-size .ico from whatever the icon currently is.

    A Windows SHORTCUT's icon must be an .ico (or an exe/dll): point
    `IconLocation` at a .png and the shortcut draws blank, which is exactly
    what a pinned taskbar button with no picture looks like. And the pin is
    where this matters most, because Windows sources a pinned button's icon
    from the Start-menu shortcut whose AppUserModelID matches the running
    window — so if that shortcut has no usable icon, neither does the pin.

    **THE ENTRIES BELOW 256 ARE DIBs, NOT PNGs, AND THAT IS THE WHOLE
    POINT OF THIS FUNCTION.** Every entry used to be PNG-compressed on the
    strength of "every Windows since Vista reads PNG icons". What Vista
    added was PNG at **256**, for the extra-large view; the shell's older
    icon paths — the ones that draw a TASKBAR BUTTON, a pin and a
    shortcut, at 16, 32 and 48 — go through code that expects the original
    DIB layout and quietly draw nothing when handed a PNG at those sizes.
    Which is the signature this app has now produced three times over:
    the window's own icon perfect, because Qt reads anything, and the
    shell's copy blank or generic, because it does not.

    So 256 stays PNG — it is huge as a DIB and it is the one size the
    format documents as PNG — and everything the taskbar actually asks
    for is written the way an icon has been written since 1985.
    """
    if not gui_ready():
        raise RuntimeError(
            "no QGuiApplication yet — rendering an .ico here would abort "
            "the process rather than raise")
    path = Path(path)
    frames = []
    for size in ICO_SIZES:
        if size >= PNG_ENTRY_MIN:
            # QBuffer() with no argument owns its byte array. Handing it a
            # temporary QByteArray instead lets Python free the array
            # while Qt is still writing into it, which crashes the
            # process.
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            written = buffer if pixmap(size).save(buffer, "PNG") else None
            data = bytes(buffer.data())
            buffer.close()
            if written is None:
                continue
        else:
            data = _dib_entry(size)
            if data is None:
                continue
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

"""Put a Start-menu shortcut for the app on this machine.

A .bat file cannot be pinned to Start in any useful way — Windows pins the
shell, not the thing it launches, and the icon is the console's. A .lnk can
be pinned, carries its own icon, and starts without a console window, so
that is what this makes.

Windows only, and it changes nothing outside the user's own Start menu.
Run it once: `python tools/make_shortcut.py`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draft_assist.config import ASSETS_DIR, REPO_ROOT  # noqa: E402

NAME = "Dota Draft Assist"


def python_for_launch() -> str:
    """pythonw from the app's own venv, so no console window appears.

    The venv the launcher builds is the one that has PyQt6 in it; the
    interpreter running this script might not be, if it was started some
    other way.
    """
    for candidate in (REPO_ROOT / ".venv/Scripts/pythonw.exe",
                      Path(sys.executable).with_name("pythonw.exe"),
                      Path(sys.executable)):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def icon_path() -> str | None:
    for name in ("app.ico", "app.png"):
        candidate = ASSETS_DIR / name
        if candidate.exists():
            return str(candidate)
    return None


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Windows only — there is no Start menu to pin to.")
    try:
        import pythoncom          # noqa: F401  (pywin32 brings both)
        from win32com.client import Dispatch
    except ImportError:
        raise SystemExit(
            "Needs pywin32: pip install -r requirements-windows.txt")

    start_menu = (Path.home() / "AppData/Roaming/Microsoft/Windows"
                  / "Start Menu/Programs")
    start_menu.mkdir(parents=True, exist_ok=True)
    link_path = start_menu / f"{NAME}.lnk"

    shell = Dispatch("WScript.Shell")
    link = shell.CreateShortCut(str(link_path))
    link.Targetpath = python_for_launch()
    link.Arguments = "-m draft_assist.ui.app"
    link.WorkingDirectory = str(REPO_ROOT)
    link.Description = "Read the Dota 2 draft and suggest picks and items"
    icon = icon_path()
    if icon:
        link.IconLocation = icon
    link.save()

    print(f"Created {link_path}")
    if not icon:
        print("No assets/app.ico — the shortcut uses Python's icon. Drop an "
              ".ico in assets/ and run this again to change it.")
    print("It is now in the Start menu; right-click it there to pin it.")


if __name__ == "__main__":
    main()

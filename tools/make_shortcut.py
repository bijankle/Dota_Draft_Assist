"""Put a Start-menu shortcut for the app on this machine.

A .bat file cannot be pinned to Start in any useful way — Windows pins the
shell, not the thing it launches, and the icon is the console's. A .lnk can
be pinned, carries its own icon, and starts without a console window, so
that is what this makes.

**The shortcut also carries the app's AppUserModelID, and that is the part
that makes PINNING THE RUNNING WINDOW work.** Right-clicking a running
window's taskbar button and choosing Pin does not pin the window: Windows
pins the app identity, then goes looking for a Start-menu shortcut whose
`System.AppUserModel.ID` matches, and takes the pinned button's icon,
name and launch command from THAT. With no matching shortcut it falls back
to the executable — pythonw.exe — and shows Python's icon, which is
exactly what a pin of this app looked like. WScript.Shell cannot write
that property, so the shortcut is built through IShellLink and
IPropertyStore directly.

The icon must be a real .ico. Point `IconLocation` at a .png and the
shortcut draws blank, so one is generated from whatever icon the app is
currently using when the user has not supplied their own .ico.

Windows only, and it changes nothing outside the user's own Start menu.
Run it once: `python tools/make_shortcut.py`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draft_assist.config import ASSETS_DIR, REPO_ROOT  # noqa: E402
# Must match what the app declares before its first window: the pin is
# matched to this shortcut by that string and nothing else.
from draft_assist.ui.appicon import APP_ID  # noqa: E402

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
    """A real .ico, generated from the app's own icon if need be.

    A shortcut cannot use a .png — it draws blank — so a supplied .ico is
    used as it is and anything else is rendered into one.
    """
    supplied = ASSETS_DIR / "app.ico"
    if supplied.exists():
        return str(supplied)
    try:
        from PyQt6.QtWidgets import QApplication
        from draft_assist.ui import appicon
        QApplication.instance() or QApplication([])
        return str(appicon.write_ico(ASSETS_DIR / "app-generated.ico"))
    except Exception as exc:            # an icon is never worth failing over
        print(f"Could not build an .ico ({exc}); the shortcut will use "
              "Python's icon.")
        return None


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Windows only — there is no Start menu to pin to.")
    try:
        import pythoncom
        from win32com.propsys import propsys, pscon
        from win32com.shell import shell
    except ImportError:
        raise SystemExit(
            "Needs pywin32: pip install -r requirements-windows.txt")

    start_menu = (Path.home() / "AppData/Roaming/Microsoft/Windows"
                  / "Start Menu/Programs")
    start_menu.mkdir(parents=True, exist_ok=True)
    link_path = start_menu / f"{NAME}.lnk"

    link = pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER,
        shell.IID_IShellLink)
    link.SetPath(python_for_launch())
    link.SetArguments("-m draft_assist.ui.app")
    link.SetWorkingDirectory(str(REPO_ROOT))
    link.SetDescription("Read the Dota 2 draft and suggest picks and items")
    icon = icon_path()
    if icon:
        link.SetIconLocation(icon, 0)

    # The whole reason for building the link this way: WScript.Shell has no
    # way to write a property-store value, and this one property is what
    # ties a pinned taskbar button to this shortcut's icon.
    store = link.QueryInterface(propsys.IID_IPropertyStore)
    store.SetValue(pscon.PKEY_AppUserModel_ID,
                   propsys.PROPVARIANTType(APP_ID, pythoncom.VT_LPWSTR))
    store.Commit()

    link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(link_path), 0)

    print(f"Created {link_path}")
    print(f"AppUserModelID: {APP_ID}")
    if not icon:
        print("No icon — the shortcut uses Python's. Put an .ico in assets/ "
              "(or use Setup > Choose app icon) and run this again.")
    print("It is now in the Start menu; right-click it there to pin it.")
    print("Already pinned the RUNNING WINDOW? Unpin it and pin it again — "
          "Windows caches the old identity, and the pin only finds this "
          "shortcut's icon on a fresh pin.")


if __name__ == "__main__":
    main()

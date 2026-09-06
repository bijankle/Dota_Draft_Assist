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


def stamp_identity(link, propsys, pscon) -> bool:
    """Write System.AppUserModel.ID onto the link, if it can be done.

    This is the property Windows matches a pinned taskbar button against,
    so it is the difference between the pin showing our icon and showing
    python.exe's. It is also the call that crashed the interpreter outright
    when handed an explicit variant type, so it is kept to the form that
    works and its failure is survivable.
    """
    try:
        store = link.QueryInterface(propsys.IID_IPropertyStore)
        store.SetValue(pscon.PKEY_AppUserModel_ID,
                       propsys.PROPVARIANTType(APP_ID))
        store.Commit()
        return True
    except Exception as exc:            # noqa: BLE001 - see the docstring
        print(f"Could not write the AppUserModelID: {exc}")
        return False


def open_containing_folder(path: Path) -> None:
    """Show the shortcut, because pinning it is now the user's move.

    Nothing can pin to the taskbar on the user's behalf: Windows removed
    the verb. Putting the file in front of them is the most the app can
    do, and it beats describing a path.
    """
    import subprocess
    try:
        subprocess.run(["explorer", "/select,", str(path)], check=False)
    except OSError:
        pass


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

    # The identity is stamped BEFORE the file is written, and the whole
    # attempt is wrapped, because it has already taken the process down
    # once: passing PROPVARIANTType an explicit VT killed the interpreter
    # with STATUS_STACK_BUFFER_OVERRUN (exit 3221226505), which no `except`
    # can catch. The one-argument form is the one that works. A shortcut
    # without the identity is still a usable shortcut, so failing here must
    # not cost the shortcut.
    stamped = stamp_identity(link, propsys, pscon)
    link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(link_path), 0)

    print(f"Created {link_path}")
    if stamped:
        print(f"AppUserModelID: {APP_ID}")
    else:
        print("The AppUserModelID could not be written, so a pin made from "
              "the running window will still show Python's icon. Pin THIS "
              "shortcut instead and the icon is correct.")
    if not icon:
        print("No icon — the shortcut uses Python's. Put an .ico in assets/ "
              "(or use Setup > Choose app icon) and run this again.")
    print("")
    print("TO PIN IT TO THE TASKBAR: Windows does not allow a program to "
          "pin itself — that verb was removed — so drag the shortcut onto "
          "the taskbar, or right-click it and choose Pin to taskbar "
          "(Windows 11 hides that under 'Show more options').")
    print("Already pinned the RUNNING WINDOW? Unpin it and pin it again — "
          "Windows caches the old identity, and the pin only picks this "
          "shortcut up on a fresh pin.")
    open_containing_folder(link_path)


if __name__ == "__main__":
    main()

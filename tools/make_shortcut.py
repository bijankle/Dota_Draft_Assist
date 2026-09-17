"""Put a Start-menu shortcut for the app on this machine.

A .bat file cannot be pinned to Start in any useful way — Windows pins the
shell, not the thing it launches, and the icon is the console's. A .lnk can
be pinned, carries its own icon, and starts without a console window, so
that is what this makes.

**The shortcut also carries the app's AppUserModelID**, which is how
Windows matches a pin to it. Right-clicking a running window's taskbar
button and choosing Pin does not pin the window: Windows pins an app
identity and then has to decide what to launch and what to draw for it.
Left to itself it falls back to the executable — pythonw.exe — and shows
Python's icon, which is what a pin of this app looked like. WScript.Shell
cannot write that property, so the shortcut is built through IShellLink
and IPropertyStore directly.

That is now the SECOND answer to the pin, not the first: the window sets
its own relaunch command and icon (`appicon.claim_window_identity`), so
pinning the running window works with no shortcut involved. This is still
worth having for the Start menu, and as the fallback if those properties
cannot be written.

The icon must be a real .ico. Point `IconLocation` at a .png and the
shortcut draws blank, so one is generated from whatever icon the app is
currently using when the user has not supplied their own .ico.

Windows only, and it changes nothing outside the user's own Start menu.
Run it once: `python tools/make_shortcut.py`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Must match what the app declares before its first window: the pin is
# matched to this shortcut by that string and nothing else.
from draft_assist.ui import appicon  # noqa: E402
from draft_assist.ui.appicon import APP_ID  # noqa: E402



def icon_path() -> str | None:
    """A real .ico, generated from the app's own icon if need be.

    A shortcut cannot use a .png — it draws blank — so a supplied .ico is
    used as it is and anything else is rendered into one.
    """
    try:
        from PyQt6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        found = appicon.shell_ico()
    except Exception as exc:            # an icon is never worth failing over
        print(f"Could not build an .ico ({exc}); the shortcut will use "
              "Python's icon.")
        return None
    return str(found) if found else None


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
    # ONE implementation, in `appicon`, shared with the automatic call the
    # app makes at every startup. Two copies of this could write two
    # different shortcuts for one AppUserModelID, which is precisely the
    # kind of disagreement that made the taskbar icon take five attempts.
    icon = icon_path()
    try:
        link_path = appicon.write_shortcut()
    except ImportError:
        raise SystemExit(
            "Needs pywin32: pip install -r requirements-windows.txt")

    print(f"Created {link_path}")
    print(f"AppUserModelID: {APP_ID}")
    print("The app now writes this automatically on every start, so you "
          "should not need to run it by hand.")
    if not icon:
        print("No icon — the shortcut uses Python's. Put an .ico in assets/ "
              "(or use Settings > Appearance > Choose app icon) and "
              "run this again.")
    print("")
    print("TO PIN IT TO THE TASKBAR: Windows does not allow a program to "
          "pin itself — that verb was removed — so drag the shortcut onto "
          "the taskbar, or right-click it and choose Pin to taskbar "
          "(Windows 11 hides that under 'Show more options').")
    print("")
    print("You may not need this at all any more: the window now carries "
          "its own relaunch command and icon, so pinning the RUNNING "
          "window should work on its own. Either way a pin keeps whatever "
          "identity it was made with — unpin it, restart the app, and pin "
          "it again.")
    open_containing_folder(link_path)


if __name__ == "__main__":
    main()

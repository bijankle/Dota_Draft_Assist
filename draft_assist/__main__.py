"""Path-independent entry point: `python -m draft_assist`, or run this file.

The app is normally started by `Dota Draft Assist.bat`, which runs
`-m draft_assist.ui.app` from the repository root. That needs the root to
be the working directory, and a WINDOWS PIN HAS NO WORKING DIRECTORY: the
relaunch command a pinned taskbar button stores is a bare command line the
shell runs from wherever it likes. Pointing that command at a file inside
the package would put the package's own folder on `sys.path` instead of
the root, and `import draft_assist` would fail with the app apparently
just not starting.

So this file puts the root on `sys.path` itself and then imports by name.
It is the target of `appicon.relaunch_command`, and one small module beats
a second .bat.
"""

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from draft_assist.ui.app import main  # noqa: E402

if __name__ == "__main__":
    main()

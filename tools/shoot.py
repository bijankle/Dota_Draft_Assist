"""Photograph the app's screens, headlessly, with mock data in them.

WHY THIS EXISTS. Three times in one evening something shipped that read
perfectly in the source and was wrong on screen: an account row that was
two lines instead of one, two labels printing with no gap between them,
and a gold shield that was computed nowhere and so never appeared. Every
test passed through all three. This app's oldest lesson is that a layout
is checked by looking at it, and until now looking at it meant being at
the Windows machine with Dota open.

It renders the REAL widgets - the same classes the app builds, under the
app's own stylesheet - so a picture here cannot drift from the product
the way a mockup would. What it cannot show is anything that needs
Windows or a running game: capture, GSI, the crop boxes. Those are still
only visible on the machine.

    python tools/shoot.py                 every screen
    python tools/shoot.py history draft   just these
    python tools/shoot.py --list          what can be shot
    python tools/shoot.py --out somewhere

NOTHING REAL IS TOUCHED. The settings file, the remembered accounts,
their cached runs and the recordings folder all live in the repository
root, so this points every one of them at a temporary directory first -
the same redirection `tests/conftest.py` does, and for the same reason.
A probe written in a hurry wrote `shield_pct: 90` into a real settings
file during this tool's own design, which is the bug that argued for
doing it properly here.
"""

import argparse
import os
import random
import sys
import tempfile
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# BEFORE Qt is imported, never after. Touching a QPixmap without a usable
# platform plugin does not raise - Qt prints a line and ABORTS the
# process, so there is no traceback and no exception to catch.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication          # noqa: E402
from PyQt6.QtGui import QPixmap                   # noqa: E402

from draft_assist import console                  # noqa: E402

SHOT_DIR = ROOT / "debug_out" / "shots"


def sandbox() -> None:
    """Point every file the app writes at a temporary directory."""
    from draft_assist.history import cache, store
    from draft_assist.ui import app as app_mod
    from draft_assist.ui import settings as ui_settings

    where = Path(tempfile.mkdtemp(prefix="dda-shots-"))
    ui_settings.SETTINGS_FILE = where / "ui_settings.json"
    store.STORE_FILE = where / "accounts.json"
    cache.CACHE_DIR = where / "history_cache"
    app_mod.RECORDINGS_DIR = where / "recordings"


#: THE QApplication HAS TO BE KEPT ALIVE BY SOMETHING. PyQt owns the C++
#: object through the Python one, so an application created and not
#: assigned is collected the moment the function returns - and the next
#: widget then dies with "Must construct a QApplication before a QWidget"
#: and ABORTS the process, pointing at the widget rather than at the
#: missing reference. Cost an hour the first time.
APP = None


def application() -> QApplication:
    global APP
    APP = QApplication.instance() or QApplication([])
    from draft_assist.ui import theme
    sheet = getattr(theme, "STYLESHEET", None)
    APP.setStyleSheet(sheet if isinstance(sheet, str) else theme.stylesheet())
    return APP


# ------------------------------------------------------- mock data ----

HEROES = [
    (1, "Anti-Mage"), (8, "Juggernaut"), (11, "Shadow Fiend"),
    (14, "Pudge"), (19, "Tiny"), (22, "Zeus"), (25, "Lina"),
    (26, "Lion"), (35, "Sniper"), (41, "Faceless Void"),
    (44, "Phantom Assassin"), (52, "Leshrac"), (74, "Invoker"),
    (86, "Rubick"), (5, "Crystal Maiden"), (2, "Axe"),
    (98, "Timbersaw"), (6, "Drow Ranger"), (84, "Ogre Magi"),
    (63, "Weaver"),
]


def mock_matches(count: int = 620, seed: int = 7) -> list:
    """A season's worth of games, varied enough that every block fills.

    The point is a picture with REAL SHAPE in it - a hero list long
    enough to need its cut, sessions long enough to tilt, contribution
    figures far enough apart to draw a bar. A handful of identical
    matches renders a page of empty tables and proves nothing.
    """
    from draft_assist.history.shape import Match

    rng = random.Random(seed)
    out = []
    when = datetime.now() - timedelta(days=360)
    for index in range(count):
        hero_id, hero = HEROES[rng.randrange(len(HEROES))]
        # A hero's own strength, so the hero block has something to rank.
        edge = ((hero_id * 37) % 100) / 100.0 - 0.5
        when += timedelta(hours=rng.choice([1, 1, 2, 5, 14, 26, 30]))
        minutes = rng.randint(22, 58)
        win = rng.random() < 0.5 + edge * 0.35
        scale = 1.0 + edge
        out.append(Match(
            match_id=7_000_000_000 + index,
            start=int(when.timestamp()),
            when=when,
            duration=minutes * 60,
            slot=rng.choice([0, 1, 2, 128, 129]),
            radiant=rng.random() < 0.5,
            win=win,
            hero_id=hero_id,
            hero=hero,
            kills=max(0, int(rng.gauss(7 * scale, 3))),
            deaths=max(0, int(rng.gauss(7 / max(scale, 0.4), 2))),
            assists=max(0, int(rng.gauss(12, 5))),
            gold_per_min=int(rng.gauss(430 * scale, 70)),
            xp_per_min=int(rng.gauss(520 * scale, 80)),
            last_hits=int(rng.gauss(minutes * 5 * scale, 40)),
            denies=max(0, int(rng.gauss(11 * scale, 5))),
            level=rng.randint(16, 30),
            hero_damage=int(rng.gauss(minutes * 620 * scale, 4000)),
            tower_damage=int(rng.gauss(minutes * 110 * scale, 1500)),
            party_size=rng.choice([None, 1, 1, 2, 3, 5]),
            lobby_type=7,
            game_mode=22,
        ))
    return out


def mock_report():
    """A finished `Report`, built by the REAL analysis.

    Not a hand-made object with plausible fields: `build_blocks` is what
    the app runs, so a screen shot here exercises the same floors, the
    same sigmas and the same ordering the product does.
    """
    from draft_assist.history import analyse
    from draft_assist.history.cache import bundled_item_names
    from draft_assist.history.report import Options, Report
    from draft_assist.ui.demo import demo_dataset

    matches = mock_matches()
    from draft_assist.history import shape
    shaped = shape.sessionise(matches) if hasattr(shape, "sessionise") else None
    if shaped is None:                     # the name differs by version
        for index, match in enumerate(matches):
            match.session, match.position = index // 4, index % 4
            match.previous = "" if match.position == 0 else (
                "win" if matches[index - 1].win else "loss")

    baseline = sum(1 for m in matches if m.win) / len(matches)
    picked = {ident: True for ident, *_ in analyse.ANALYSES}
    blocks = analyse.build_blocks(matches, baseline, picked,
                                  bundled_item_names(), ds=demo_dataset())
    return Report(
        options=Options(account_id=86680300, window="12m", cap=5000,
                        picked=picked),
        how="", name="Bijson", matches=matches, blocks=blocks,
        dropped={}, sessions=len(matches) // 4, returned=len(matches),
        ran_at=datetime(2026, 9, 12, 0, 11))


# ---------------------------------------------------------- screens ----

def a_window(drafted: bool = True):
    from draft_assist.config import RULES_FILE
    from draft_assist.model import items as items_mod
    from draft_assist.ui.app import MainWindow
    from draft_assist.ui.demo import demo_dataset
    from draft_assist.ui.providers import DemoProvider

    ds = demo_dataset()
    provider = DemoProvider(ds)
    if drafted:
        provider.draft.started -= 45      # a full 5v5 on the board
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, provider, rules, meta)
    win.timer.stop()
    win.resize(1240, 1040)
    win.show()
    for _ in range(8):
        win.refresh()
        QApplication.instance().processEvents()
    return win


def a_history_tab(width: int = 1400, height: int = 1000):
    """The History tab, CURRENT, with a full report drawn on it.

    Making it the current tab is not cosmetic. A QTabWidget HIDES the
    pages that are not on screen, and a hidden widget is never laid out -
    so every card came back at Qt's default 640x480 with its bar column
    and half its rows cut off. Same trap the tests hit from the other
    side, where `isVisibleTo` answers "is this the open tab" rather than
    "did the app hide this".
    """
    win = a_window(drafted=False)
    win.resize(width, height)
    for index in range(win.tabs.count()):
        if win.tabs.tabText(index) == "History":
            win.tabs.setCurrentIndex(index)
            break
    settle(win)
    tab = win.history_tab
    report = mock_report()
    tab.report = report
    tab.render(report)
    settle(win)
    return win, tab


def settle(widget) -> None:
    """Qt defers layout, so measuring or drawing straight after a resize
    reads the old geometry - every widget at x=0, in the case that taught
    this. Run it, twice, with the event loop turned over in between."""
    app = QApplication.instance()
    for _ in range(3):
        if widget.layout() is not None:
            widget.layout().activate()
        app.processEvents()


def shoot_window():
    win = a_window()
    return win, win.size()


def shoot_draft():
    win = a_window()
    return win.draft_widget if hasattr(win, "draft_widget") else win, None


def shoot_history():
    """THE WHOLE PAGE, not the viewport. The report is thirteen cards
    long and lives in a scroll area, so rendering the tab itself would
    photograph one screenful and call it the report."""
    win, tab = a_history_tab()
    page = tab.page
    settle(win)
    tall = max(page.sizeHint().height(), page.height())
    page.resize(tab.scroll.viewport().width(), tall)
    if page.layout() is not None:
        page.layout().activate()
    return page, None


def shoot_account():
    win, tab = a_history_tab()
    row = tab.last_run
    row.resize(760, 52)
    settle(row)
    return row, None


def shoot_settings():
    win = a_window(drafted=False)
    win._open_settings("General")
    settle(win.settings_window)
    return win.settings_window, None


def shoot_section(ident: str):
    """One card of the report, by its own id — so the list of shots is
    `analyse.ANALYSES` and cannot go stale as sections are added."""
    win, tab = a_history_tab()
    card = tab._anchors.get(ident)
    if card is None:
        raise SystemExit(
            f"'{ident}' drew no card. It is either switched off or it had "
            "nothing to measure in the mock data.")
    settle(win)
    return card, None


def screens() -> dict:
    from draft_assist.history import analyse
    shots = {
        "window": ("The whole app window, drafted", shoot_window),
        "draft": ("The Draft tab", shoot_draft),
        "history": ("The History tab, full report", shoot_history),
        "account": ("The account row", shoot_account),
        "settings": ("The settings window", shoot_settings),
    }
    for ident, name, *_ in analyse.ANALYSES:
        shots[ident] = (f"History section: {name}",
                        partial(shoot_section, ident))
    # The two summary cards carry their own anchors rather than a block
    # id, since they summarise every section rather than being one.
    shots["winrate"] = ("History: the Win rate summary",
                        partial(shoot_section, "winning"))
    shots["impact"] = ("History: the Impact summary",
                       partial(shoot_section, "contrib"))
    shots["filter"] = ("History: the Filter card",
                       partial(shoot_section, "sample"))
    return shots


# ------------------------------------------------------------ driver ----

def take(name: str, maker, into: Path) -> Path:
    widget, size = maker()
    settle(widget)
    box = size or widget.size()
    picture = QPixmap(box)
    widget.render(picture)
    into.mkdir(parents=True, exist_ok=True)
    path = into / f"{name}.png"
    picture.save(str(path))
    return path


def main() -> None:
    console.plain_output()
    shots = None
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("names", nargs="*", help="which screens (default: all)")
    parser.add_argument("--out", default=str(SHOT_DIR))
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    # THE QApplication FIRST, before anything imports the ui package.
    # Constructing a QWidget without one does not raise - Qt prints a
    # line and ABORTS, so there is nothing to catch and no traceback.
    application()
    sandbox()
    shots = screens()

    if args.list:
        for name, (what, _) in shots.items():
            print(f"  {name:<12} {what}")
        return

    wanted = args.names or list(shots)
    unknown = [n for n in wanted if n not in shots]
    if unknown:
        raise SystemExit(f"No such screen: {', '.join(unknown)}. "
                         "Run with --list to see them.")

    into = Path(args.out)
    for name in wanted:
        what, maker = shots[name]
        try:
            path = take(name, maker, into)
            print(f"  {name:<12} {path.relative_to(ROOT)}")
        except SystemExit as refused:
            print(f"  {name:<12} skipped - {refused}")
        except Exception as bad:              # noqa: BLE001
            # One screen failing must never cost the rest: the point of a
            # contact sheet is what it DOES show.
            print(f"  {name:<12} FAILED - {type(bad).__name__}: {bad}")
    print(f"\n{len(wanted)} screen(s) -> {into}")


if __name__ == "__main__":
    main()

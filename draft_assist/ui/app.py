"""The application window: an ordinary draggable, resizable desktop window.

An optional companion overlay (View > Draft overlay) puts a small draggable
badge on top of Dota that expands into the recommendations; the main window
stays a normal window, because the drill-downs need to be clicked. Neither
touches the game — see overlay.py.

Every maintenance action (update the app, pull statistics, tune recognition,
probe capture, choose a capture source) is a menu item that runs in a
progress dialog, so there is exactly one thing to launch and no console
windows. The window opens even with no data downloaded yet and explains what
to do.

Draft state comes from Dota's own Game State Integration feed by default —
the game reports itself through a Valve-supported channel, so there is no
pixel interpretation and no per-frame compute. Screen capture is retained
behind --vision as a fallback for anything GSI does not report, and any slot
can always be filled in by hand.

Run modes (everything but live capture works with no game and no Windows):
    python -m draft_assist.ui.app              # game data (GSI)
    python -m draft_assist.ui.app --manual     # hand-entered draft
    python -m draft_assist.ui.app --vision     # screen capture fallback
    python -m draft_assist.ui.app --demo       # scripted fake draft
    python -m draft_assist.ui.app --replay DIR # saved frames from disk
"""

import argparse
import os
import platform
import random
import subprocess
import sys
import time
from pathlib import Path

from PyQt6.QtCore import (PYQT_VERSION_STR, QEvent, QPoint, QRect, QSize,
                          QT_VERSION_STR, Qt, QTimer)
from PyQt6.QtGui import (QAction, QColor, QImage, QKeySequence,
                         QPainter, QPen, QPixmap)
from PyQt6.QtWidgets import (QApplication, QCheckBox,
                             QDialog, QFrame, QGridLayout,
                             QHBoxLayout, QLabel,
                             QFileDialog,
                             QMainWindow, QMenuBar, QMessageBox,
                             QPlainTextEdit,
                             QDoubleSpinBox, QListWidget,
                             QPushButton,
                             QScrollArea, QSizePolicy, QSlider,
                             QStatusBar, QTabWidget,
                             QVBoxLayout, QWidget)

from ..gsi.state import DRAFTING_STATES
from ..config import (CALIBRATION_FILE, DEBUG_OUT, RECORDINGS_DIR,
                       REPO_ROOT, RULES_FILE, pair_source,
                       save_pair_source, save_target_brackets,
                       target_brackets)
from ..data import store
from ..data.store import Dataset
from ..timing import LOOP
from ..vision import harvest
from ..model import items as items_mod
from ..model import roles as roles_mod
from ..model import scoring
from . import settings as ui_settings
from ..capture.window import DOTA_TITLE
from .. import record as record_mod
from . import theme
from . import accountrow, menusearch, ontop, rolebar
from . import chrome
from . import ornate
from . import reasons
from . import tilekit
from .bracket_dialog import BracketDialog
from . import appicon
from .chrome import Dropdown, ResizeGrip, TitleBar, card
from . import hero_picker
from .hero_picker import HeroPickerDialog
from . import item_icons
from . import portraits
from .framebox import FrameView
from .item_row import ItemRow
from .flowlayout import fits_in_one_row
from .suggest_row import SuggestRow
from .manual import ManualDraft
from .tables import MatrixTable, minimum_grid_width
from .task_dialog import TaskDialog
from . import teams
from .history_tab import HistoryTab
from .teams import TeamPanel, minimum_panel_width
from .tasks import TASKS

# Loose mapping from queued position to OpenDota hero role tags, used ONLY
# for the visual highlight (the list itself is never filtered by role).
ROLE_LABELS = [("(no role)", None), ("Carry (1)", "carry"), ("Mid (2)", "mid"),
               ("Offlane (3)", "offlane"), ("Soft support (4)", "soft_support"),
               ("Hard support (5)", "hard_support")]
# The slot menu says "Pos 1"; the scoring layer says "carry". One mapping,
# in one place, so the two cannot drift apart.
ROLE_BY_LABEL = {"Pos 1": "carry", "Pos 2": "mid", "Pos 3": "offlane",
                 "Pos 4": "soft_support", "Pos 5": "hard_support"}


class MarkLabel(QWidget):
    """A heart or a shield, drawn at label size beside its count box.

    THE MARK IS ITS OWN LABEL. Two count boxes on one heading row need
    telling apart, and the thing they set is a picture - so the picture
    is the word. It also cannot go stale the way "Hearts:" would if the
    mark ever changed shape or colour, since it is the same painter the
    tiles use.
    """

    SIDE = 22

    def __init__(self, shield: bool, parent=None):
        # ONE MARK PER LABEL. It used to take None for "both", drawn as
        # a heart and a shield with a painted rule between them, which
        # was the single merged count box's label. The heading carries a
        # LEGEND now - one row per mark, each naming what it means - so
        # there is nothing left for a both-marks label to sit beside,
        # and "hand" went with the hand.
        super().__init__(parent)
        self._shield = shield
        self.setFixedSize(self.SIDE, self.SIDE)
        self.setToolTip(
            "Gold shield: hardest to counter of the suggestions"
            if shield else "Pink heart: your best of the suggestions")

    def _mark(self, painter, box, shield) -> None:
        # The painters inset their mark inside the box they are handed,
        # so it is grown by the inset to come out at label size.
        grown = box.adjusted(-tilekit.STAR_INSET, -tilekit.STAR_INSET,
                             tilekit.STAR_INSET, tilekit.STAR_INSET)
        if shield:
            tilekit.paint_shield(painter, grown)
        else:
            tilekit.paint_heart(painter, grown)

    def paintEvent(self, event) -> None:   # noqa: N802 - Qt naming
        self._mark(QPainter(self), self.rect(), self._shield)


def open_folder(path: Path) -> None:
    """Show a folder in the system file manager."""
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - opening a local folder for the user
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def set_log(widget, text: str) -> None:
    """Replace a read-only log's text without stealing the user's selection.

    `setPlainText` replaces the whole document, which drops the selection
    AND the scroll position. Four times a second that makes the log
    impossible to select and copy, which is the one thing a log is for —
    the selection vanished the instant it was made and looked like a Qt
    bug rather than our own refresh.
    """
    if widget.toPlainText() == text:
        return
    if widget.textCursor().hasSelection():
        return                          # mid-drag: leave it alone
    bar = widget.verticalScrollBar()
    at = bar.value()
    widget.setPlainText(text)
    bar.setValue(min(at, bar.maximum()))


def set_label(widget, text: str) -> None:
    """Same rule for a selectable QLabel."""
    if widget.text() == text or widget.selectedText():
        return
    widget.setText(text)


def _scrolling(page: QWidget) -> QScrollArea:
    """Wrap a long page so its height stops dictating the WINDOW's.

    A QTabWidget's minimum is the LARGEST of its pages, so the Debug tab —
    a full-resolution picture, a log, a timing table and a row of
    calibration controls, 1200px of minimum between them — set the floor
    for the whole window even while the Draft tab was the one on screen.
    The window could not be made shorter than the tab nobody was looking
    at. Inside a scroll area a page asks for nothing, and the floor becomes
    the tab you are actually using.
    """
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setWidget(page)
    return area


# How big a tile in the two advice strips is, against a pick. The ten
# picks are the subject of the screen; the suggestions and the items are
# advice about them, and at the same size the three rows read as equals.
# EVERY PORTRAIT IN THE APP IS ONE BOX, and the pick tile is that box.
# The strips were briefly 70% of a pick, so that the ten picks read as the
# subject and the advice under them as advice — and at the user's request
# that is reversed: a portrait is a portrait wherever it is drawn, and the
# eye should not have to re-scale between three rows of them. One number,
# so going back to a smaller strip is one number.
STRIP_OF_PICK = 1.0

# The two states where the pick bar IS on screen, without their prefix.
_DRAFT_STATE_NAMES = frozenset(
    st.replace("DOTA_GAMERULES_STATE_", "") for st in DRAFTING_STATES)


class MainWindow(QMainWindow):
    # IS DOTA'S CONFIG FILE THERE, cached, because the banner asks on
    # every tick and `find_dota_dir` is a registry read plus a walk of
    # every Steam library. The banner that asks is the one a fresh
    # install sits under for a whole session, so this would be four
    # filesystem walks a second at exactly the wrong moment — the same
    # trap the gate's signature and the hidden debug view were both
    # found in. `GSI_CONFIG_TTL` is generous because the answer only
    # changes when something in this app changes it, and both of those
    # paths clear the cache outright.
    GSI_CONFIG_TTL = 10.0
    _gsi_config_seen: bool | None = None
    _gsi_config_asked: float = 0.0

    def __init__(self, ds: Dataset, provider, rules, rules_meta,
                 manual: ManualDraft | None = None):
        super().__init__()
        self.ds, self.provider = ds, provider
        self._open_tasks = []
        self.recorder = record_mod.Recorder(RECORDINGS_DIR)
        self.sessions: list = []
        # Set when the user stops a session by hand during a draft,
        # so auto does not immediately start another one.
        self._auto_blocked = False
        # Per-match hand corrections to the reading, cleared when the match
        # changes: which heroes were moved across, and the order the user
        # dragged each bank into.
        self.slot_order: dict[str, list[int]] = {"ally": [], "enemy": []}
        # Position 1-5 per slot, assigned by hand. Vision reads the
        # ranked-role icons, but not until the crop geometry is right,
        # so nothing sets these automatically yet.
        self.slot_roles = {"ally": [None] * 5,
                           "enemy": [None] * 5}
        # Your own hero and whether it is locked, set from the tile's menu
        # rather than a dropdown. A hero id, not a slot: the slot it stands
        # in can change under it.
        self.my_hero_id: int | None = None
        self.my_hero_locked = False
        # Set to a task key by the Update button; cleared when that task ends.
        self._restart_after_task = ""
        self._swap_match = ""
        # hero id -> "ally"/"enemy", for one hero put on the wrong
        # side. Cleared with the swap when the match changes.
        self.side_overrides: dict[int, str] = {}
        from ..vision import layout as layout_mod
        session = getattr(provider, "session", None)
        self.layout_spec = (getattr(session, "layout", None)
                            or layout_mod.load_layout())
        self.rules, self.rules_meta = rules, rules_meta
        self.manual = manual if manual is not None else getattr(
            provider, "manual", None) or ManualDraft()
        self.snapshot = None
        self.last_draft_key = None
        # The board Clear all was pressed on, blanked until something on it
        # changes (see `_is_cleared`). None means nothing is being blanked.
        self._cleared = None
        # Until when the status line belongs to something the user did
        # rather than to the state (see `_say`).
        self._quiet_until = 0.0
        # THE ONE SELECTION, and everything on the Draft tab answers to
        # it: (where, hero id), where `where` is "ally", "enemy" or
        # "suggest". Clicking it again clears it; it survives a refresh
        # but not the hero going off screen.
        #
        # ONE, because there is only one question at a time. A hero can
        # be clicked on a pick tile, on a suggestion, or on either grid's
        # axis, and a second selection living beside the first would put
        # two sets of numbers on the board with nothing saying which is
        # which — so a new click REPLACES the old one wherever it came
        # from, and the gold ring is the single answer to "measured
        # against what".
        self.focus: tuple[str, int] | None = None
        # Which heroes the History tab's current run says you are good
        # on, or None for "no run loaded" — see `_history_run_changed`.
        self.stars = None
        # {hero id: why} for the gold shield. From the DATASET rather
        # than from any run, so it is filled before the History tab has
        # ever been opened.
        self.shields: dict = {}
        # Why the shields are what they are, for Settings to print under
        # the bar that sets them. Never empty after the first recompute.
        self.shields_note: str = ""
        # Heroes whose alternative portrait has been learned this session,
        # so a draft's worth of frames writes one file rather than hundreds.
        self._learned: set[int] = set()
        self.scored: list[scoring.ScoredHero] = []
        self._last_advice: list = []
        self._reason_popup = None
        self.settings = ui_settings.load()
        self.setWindowTitle("Dota Draft Assist")
        self.setWindowIcon(appicon.icon())
        # Frameless: Windows' own title bar is a white strip above a dark
        # app and reads as a different program bolted on top. The cost is
        # that the drag and the resize corner have to be put back by hand,
        # which `ui/chrome.py` does.
        #
        # ALWAYS-ON-TOP IS STILL SET HERE, and it is still the default —
        # but it is no longer the only state. The pin in the title bar
        # turns it off and on, and it does NOT come back through
        # `setWindowFlags`: changing a window's flags on Windows destroys
        # and recreates the native handle, which would throw away the
        # window's Win32 icon and its taskbar identity on every press.
        # See `ui/ontop.py`.
        flags = Qt.WindowType.FramelessWindowHint
        if self.settings.get("always_on_top", True):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        # The narrowest honest width. Two things are competing for it —
        # five matrix columns wide enough to print "+12.34", and five pick
        # tiles wide enough to still show a portrait — so the floor is
        # whichever of them needs more, doubled for the two halves.
        self._floor_w = 2 * max(minimum_grid_width(),
                                minimum_panel_width()) + 44
        self.setMinimumWidth(self._floor_w)
        # Set before the first resize, since `resizeEvent` writes it.
        self._normal_box = None
        # CLAMPED TO THE SCREEN ON THE WAY IN. The saved height is now
        # written correctly (see `closeEvent`), but a settings file an
        # earlier build wrote still carries whatever went wrong then — so
        # a copy that has already got into this state opens fixed rather
        # than staying broken until somebody edits the file by hand.
        area = chrome.work_area(self)
        height = int(self.settings.get("window_h", 820) or 820)
        if area is not None:
            height = min(height, area.height())
        self.resize(int(self.settings.get("window_w", 1240) or 1240), height)
        self._restore_position()
        self._build_menus()
        self._build()
        self._refresh_sources()
        self._sync_source_controls()
        self._update_first_run_banner()
        self.setWindowOpacity(
            float(self.settings.get("overlay_opacity", 0.7)))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(300)
        # AFTER `_build`, because a fixed size has to be at least what the
        # layout can honestly draw and there is no layout to ask before
        # that. The action's own tick is set here rather than when it was
        # created, for the same reason.
        # SIGNALS BLOCKED: setting the tick to match the file is not the
        # user ticking it, and letting it through announced "Window size
        # locked" in the status bar on every start — which then held the
        # line for five seconds against everything the app had to say
        # about the game.
        # The saved sizes, applied BEFORE the first layout so the tiles
        # are built at the size the user chose rather than jumping to it.
        teams.set_scale(float(self.settings.get("portrait_scale", 1.0)))
        tilekit.set_scale(float(self.settings.get("number_scale", 1.0)))
        for panel in self.team_panels.values():
            panel.rescale()
        # FREELY RESIZABLE, floored at what the layout can actually draw.
        # There is no lock any more; the size is remembered on close
        # (`closeEvent`) and applied above, which is what the lock was
        # really for.
        self.setMinimumSize(self._floor_w, 0)
        # AFTER THE TABS EXIST, which is the whole reason it is repeated
        # here. `_add_section_menu` builds the tick boxes with the
        # toolbar, long before the Draft tab is laid out, so the blocks
        # it wants to hide are not attributes yet and the first call
        # silently hid nothing — the matrices drew on a fresh install
        # with their own tick box unticked beside them.
        self._apply_sections()
        # AND THE PALETTE, for the same reason and one step further on:
        # a settings file saying greyscale must arrive at a grey window
        # on the FIRST paint, not after somebody opens the View menu.
        # Idempotent, so running it here and on every settings change
        # costs nothing when it is already right. NOT rebuilding the
        # views: see `_apply_greyscale`.
        self._apply_greyscale(rebuild=False)
        # Before the window is shown, because the taskbar reads a window's
        # relaunch properties when it creates the button — and a pin of the
        # running window is built from those, not from the window icon.
        appicon.claim_window_identity(int(self.winId()))
        # The pin shows what the flags above were built from. Set without
        # announcing it: restoring the file is not the user pressing it.
        self.title_bar.set_pinned(
            bool(self.settings.get("always_on_top", True)))
        # AFTER `setWindowFlags`, and that is the whole point of it being
        # here rather than beside the `setWindowIcon` further up.
        # Changing a window's flags on Windows DESTROYS AND RECREATES the
        # native handle, so an icon pushed before that went to an HWND
        # that no longer exists — and the taskbar, which draws a running
        # window's button from the window's OWN Win32 icon rather than
        # from any of the relaunch properties above, fell back to
        # pythonw.exe. Our title bar draws from `appicon.pixmap` and so
        # looked right throughout, which is what made this invisible.
        self.setWindowIcon(appicon.icon())
        appicon.push_native_icon(int(self.winId()))

    # ---- menus ---------------------------------------------------------
    def _act(self, menu, text, slot, shortcut=None, tip=""):
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        if tip:
            action.setStatusTip(tip)
        menu.addAction(action)
        return action

    def _build_menus(self) -> None:
        """File | View | Help, and nothing else on the bar.

        It was Setup | Game | View | Help, and most of what those two held
        is done ONCE — install the game config, fetch the artwork, pick
        your ranks — sitting permanently across the top of a window read
        at a glance during a draft. At the user's request everything out
        of Setup and Game is a tab in Settings (`settings_window`), the
        Debug tab with them, and what is left up here is the three
        headings a person opens on purpose.

        FOUR ITEMS WENT ENTIRELY rather than moving, also at the user's
        request, because each asked for something the app now does for
        itself or says elsewhere: "Make a pinnable shortcut…" (written
        automatically at every start — see `appicon.
        ensure_start_menu_shortcut`), "Run first-time setup…" (the wizard
        opens itself when it is needed and the banner is the way back),
        "Check item icons…" (the strip already draws the name and the
        download reports what failed) and "Game data status…" (Diagnose
        answers the same question by naming the ONE broken link rather
        than printing the whole checklist).
        """
        # NOT self.menuBar(): QMainWindow puts that above the central
        # widget, which would leave a menu strip sitting on top of our own
        # title bar. It goes inside the bar instead, the way Steam does it.
        bar = chrome.RuledMenuBar()
        self.menu_bar = bar

        file_menu = bar.addMenu("&File")
        self._act(file_menu, "S&ettings…", self._open_settings, "Ctrl+,",
                  "Everything the app reads, downloads and diagnoses")
        # CALIBRATE PICK BOXES IS GONE, at the user's request — "i dont
        # see the point in having the portrait box vision box feature at
        # all... my plan now is to have the automatic detection work so
        # the user never needs to draw out these vision boxes". It does:
        # at strategy time the game names the ten heroes on screen and
        # `autocal` measures the geometry off them, which is where every
        # calibration this app has ever shipped actually came from. What
        # went with the drag is the RULE that protected it — a
        # measurement now replaces the last measurement, because there is
        # no hand-set answer left for it to overwrite.
        # UPDATE IS IN HELP AND ONLY IN HELP, at the user's request. It
        # was on BOTH menus, wired to the same `_update_app` - one action
        # in two places, which is two things to keep in step for no gain.
        # Help is where it belongs: it is pressed about once a patch, and
        # it sits beside About, which answers "which version have I got".
        # NO QUIT, at the user's request: the window's own close button is
        # where everybody closes a window, and a menu item for it is a
        # line of menu that has never been read.

        view_menu = bar.addMenu("&View")
        # Transparency and Sizes are inserted later (see
        # `_add_transparency_menu` / `_add_sizes_menu`), once the sliders
        # they hold exist — the toolbar is built after the menu bar and
        # the sliders belong to it. Those two are the whole menu now.
        #
        # THREE ITEMS WERE REMOVED FROM HERE at the user's request:
        # **Resize window (lock)** — the window is freely resizable and
        # its size is remembered between runs, which is what the lock was
        # buying at the price of a menu item and a mode. The protection
        # it gave against a stray drag near the edge mid-draft goes with
        # it; that was the trade.
        # **Reset window position** — a rescue for a window dragged
        # off-screen, which is a thing that has not happened.
        # **Reload data and library** — the app reloads on its own after
        # every download and relaunches itself after an update, so the
        # only time this was reachable was when nothing needed it.
        # `reload_backend` itself STAYS: the download tasks call it, and
        # that is the path that actually needs a reload.
        self.view_menu = view_menu

        # Force recognition is a real control, but it belongs beside the
        # picture it affects (Debug ▸ Live) rather than in the menu bar.
        self.force_action = QAction("&Force recognition", self)
        self.force_action.setCheckable(True)
        self.force_action.setShortcut(QKeySequence("Ctrl+F"))
        self.force_action.toggled.connect(self._set_forced)
        self.addAction(self.force_action)

        help_menu = bar.addMenu("&Help")
        # THE SEARCH IS THE MENU, not an item in it. It was "Search…",
        # which opened a modal window with a box in it - "I don't like all
        # the dead space of having a separate window to search on". Now
        # the box sits at the top of this dropdown and the first key
        # pressed lands in it, the way the Windows key behaves. Attached
        # at the END of building this menu, since it keeps the menu's own
        # items to put back when the box is empty.
        # EVERY EXPLANATION IN THE APP ENDS UP HERE. The screens carry one
        # line each now, so this is where "how does it actually work" is
        # answered — see `ui/manual.py`.
        self._act(help_menu, "&User manual", self._open_manual, "F1",
                  "How every part of the app works")
        self._act(help_menu, "Update &application…", self._update_app)
        help_menu.addSeparator()
        # DEBUGGING LIVES UNDER HELP, at the user's request. It is still a
        # tab of the settings window - that window owns the live view and
        # handing a live widget between two parents is the parentless-
        # QWidget trap this app has hit three times - but nobody looks for
        # "debug" under Settings, and this opens it directly on that tab.
        self._act(help_menu, "&Debug view…",
                  lambda: self._open_settings("Debug"))
        # RECOGNITION CHECKS IS GONE, submenu and all four items, at the
        # user's request: "all of those were used to refine the software
        # - once its done i dont nteed them". They were instruments, and
        # they did their job — the hero check graded a recording against
        # the game's own line-up, the threshold fixer wrote what that
        # measured, and the two resolution tools settled where the pick
        # bar sits and killed the letterboxed model. What they measured
        # is IN the app now: `DraftLayout`'s fractions, `hud_box`, and
        # `autocal` measuring the rest off a real frame. A permanent menu
        # of development apparatus is a menu nobody in a draft wants.
        # The scripts are still in `tools/` and still under test, so the
        # next measurement is a console away rather than gone.
        help_menu.addSeparator()
        self._act(help_menu, "&About", self._about)
        # AFTER the items above, so `MenuSearch` reads the real list.
        self.menu_search = menusearch.MenuSearch(
            help_menu, self._all_commands, self)
        self.help_menu = help_menu
        # Ctrl+K drops the same menu rather than opening anything of its
        # own: a shortcut that led somewhere else would be a second way to
        # search that behaved like a different feature.
        search_key = QAction("Search", self)
        search_key.setShortcut("Ctrl+K")
        search_key.triggered.connect(
            lambda: self.menu_search.popup_under(bar))
        self.addAction(search_key)

    # ---- what the app can be asked to do -------------------------------
    def _command_groups(self) -> list:
        """The Settings tabs, as (title, intro, commands).

        ONE list, used twice: it builds the tabs and it is what Help ▸
        Search searches. Two lists would be one of them going stale, and
        the one that would go stale is the search — the half nobody
        notices is wrong until they cannot find something.
        """
        from .commands import Command

        def act(label, detail, words, run):
            return Command(label=label, detail=detail, words=tuple(words),
                           run=run)

        downloads = [
            # FIRST, because it is the one a fresh install needs and the
            # only one that needs no account anywhere.
            act("All artwork…",
                "Every hero portrait and item icon — no API key needed.",
                ("pictures", "portraits", "images", "icons", "artwork"),
                lambda: self.run_task("fetch_assets")),
            act("Statistics and portraits…",
                "The hero numbers and Valve's base portrait for each. This "
                "is the one that takes a few minutes.",
                ("data", "numbers", "stats", "update"),
                lambda: self.run_task("update_data")),
            act("Alternative portraits…",
                "Persona, arcana and custom-set pictures, so a set "
                "portrait stops reading as UNKNOWN.",
                ("arcana", "persona", "variants", "pictures"),
                lambda: self.run_task("fetch_custom_portraits")),
            act("Item icons…",
                "Just the item pictures, with the reason if it fails.",
                ("items", "pictures", "icons"),
                lambda: self.run_task("fetch_item_icons")),
            act("Statistics bracket…",
                "Which ranks the statistics are drawn from. Changing it "
                "means re-pulling: the matrices are built for the ranks "
                "you choose.",
                ("rank", "ranks", "mmr", "legend", "ancient", "divine"),
                self._choose_brackets),
        ]
        game = [
            act("Set up game data (GSI)…",
                "Install Dota's Game State Integration config, which is "
                "how the app knows a draft has started.",
                ("gsi", "install", "config", "dota"),
                self._install_gsi),
            act("Diagnose game data…",
                "Check every requirement and name the one that is "
                "failing. Start here when the app sees nothing.",
                ("gsi", "broken", "problem", "nothing", "silent"),
                self._diagnose_gsi),
            act("Clear manual draft",
                "Empty every hand-entered slot.",
                ("reset", "empty", "manual"),
                self._clear_manual),
        ]
        appearance = [
            act("Choose app icon…",
                "Use your own .ico or .png for the window and the taskbar.",
                ("icon", "logo", "taskbar", "picture"),
                self._choose_app_icon),
        ]
        # Everything under Advanced diagnoses the APP rather than the
        # draft. It is occasionally necessary and it is not what a menu
        # bar is for, which is why it was a submenu before and is a tab
        # now.
        advanced = [
            act("List capture sources…",
                "Every window the capture layer can see.",
                ("windows", "capture", "screen"),
                lambda: self.run_task("list_windows")),
            act("Save debug snapshot",
                "Write the current frame, crops and matches to disk.",
                ("frame", "screenshot", "snapshot"),
                self._save_snapshot),
            act("Edit item rules",
                "The hand-authored file behind the item strip.",
                ("items", "rules", "yaml", "build"),
                self._edit_rules),
            act("Reload item rules",
                "Re-read that file without restarting.",
                ("items", "rules"),
                self._reload_rules),
            act("Open data folder",
                "Where the downloaded statistics live.",
                ("folder", "cache", "files"),
                lambda: open_folder(REPO_ROOT / "data_cache")),
            act("Open debug folder",
                "Where snapshots and recordings are written.",
                ("folder", "files", "recordings"),
                lambda: open_folder(DEBUG_OUT)),
        ]
        return [
            ("Downloads",
             "Each of these skips what is already on disk.", downloads),
            ("Game data", "How the app hears from Dota itself.", game),
            ("Appearance", "", appearance),
            ("Advanced",
             "Diagnosing the app rather than the draft.", advanced),
        ]

    def _all_commands(self) -> list:
        """Everything searchable: the Settings tabs, plus the handful of
        things that stayed on the menu bar. A search that only knew about
        Settings would answer "where is Transparency" with nothing."""
        from .commands import Command
        found = []
        for title, _intro, commands in self._command_groups():
            where = f"Settings ▸ {title}"
            for command in commands:
                found.append(Command(label=command.label, where=where,
                                     detail=command.detail,
                                     words=command.words, run=command.run))
        found += [
            Command("Settings…", "File",
                    "Everything the app reads, downloads and diagnoses.",
                    ("preferences", "options", "config"),
                    self._open_settings),
            # HELP, not File. The search TELLS you where a thing lives,
            # so a stale menu name here sends somebody to a menu that no
            # longer holds it - worse than not finding it, because they
            # stop looking.
            Command("Update application…", "Help",
                    "Pull the latest code, then reopen the app.",
                    ("upgrade", "version", "new"), self._update_app),
            Command("Transparency", "View",
                    "How see-through the window is, on a slider.",
                    ("opacity", "seethrough", "faded"),
                    lambda: self._show_view_menu()),
            Command("Sizes", "View",
                    "How big the portraits and the numbers are.",
                    ("scale", "bigger", "smaller", "zoom", "font"),
                    lambda: self._show_view_menu()),
            Command("Debug", "Settings",
                    "What the app is reading right now, and what past "
                    "sessions recorded.",
                    ("log", "live", "recordings", "frame", "timings"),
                    lambda: self._open_settings("Debug")),
            Command("Measure the crop boxes", "Settings ▸ Debug",
                    "Read the pick bar's geometry off a frame the game has "
                    "named the heroes in. It happens by itself; this is "
                    "how to ask for it now.",
                    ("calibrate", "boxes", "crop", "portraits", "picks",
                     "recognition", "setup", "align", "measure"),
                    self._measure_from_banner),
            Command("User manual", "Help",
                    "How every part of the app works, in one place.",
                    ("manual", "help", "guide", "docs", "instructions",
                     "how", "explain"), self._open_manual),
            Command("About", "Help", "Which version this is.",
                    ("version", "build", "licence"), self._about),
        ]
        return found

    def _show_view_menu(self) -> None:
        """Drop the View menu open under the bar.

        Transparency and Sizes are SLIDERS inside that menu — there is no
        dialog to open and no single value to set — so the honest thing a
        search result can do for them is put the menu on screen with them
        in it, rather than pretending to apply something.
        """
        for action in self.menu_bar.actions():
            if action.text().replace("&", "") == "View":
                self.menu_bar.setActiveAction(action)
                return

    # ---- widgets -----------------------------------------------------
    def _build(self) -> None:
        # Built here, added to the shell below the title bar rather than
        # through addToolBar — same reason as the menu bar.
        # THE TOOLBAR IS GONE. It held five controls: the record dot and
        # Auto went to the Run menu, and Clear all / Detect all / Demo
        # went to the board bar between the two headings — both at the
        # user's request. What was left was an empty QToolBar adding a
        # rule to the strip with nothing after it, which drew as two
        # dividers side by side. Dead UI is not inert here: it goes
        # stale and then gets read as documentation.
        # Recording is one button because it is one action. It used to be a
        # menu tick for payloads, a separate probe for frames and Ctrl+S for
        # snapshots, in three folders — so the evidence for any one game was
        # scattered and usually incomplete.
        # The round red dot everyone already knows, rather than 110px of
        # "● Record" / "■ Stop": the symbol needs no words, and this row
        # has to stay readable at the narrowest the window goes.
        # RECORDING MOVED TO ITS OWN MENU, at the user's request: "move
        # the auto + tickbox + record button into a new menu header
        # called run". Both are built here, where the toolbar is, and
        # handed to `_add_run_menu` — they are the same two widgets, in
        # a menu instead of on the row.
        self.record_button = chrome.RecordButton()
        self.record_button.clicked.connect(self._toggle_recording)

        # A TICK, not a filled square: a coloured box says something is
        # different about this control, not that it is switched on.
        self.auto_record_check = chrome.TickBox("Auto")
        self.auto_record_check.setToolTip(
            "Start recording by itself when Dota reaches the draft, and "
            "stop a minute after it ends")
        self.auto_record_check.setChecked(
            bool(self.settings.get("auto_record", True)))
        self.auto_record_check.toggled.connect(self._set_auto_record)

        # Wipe the board, then fill it again in one press. Correcting a
        # bad reading pick by pick is five right-clicks and a picker each;
        # when the whole board is wrong, starting over is one gesture and
        # re-reading is another.
        # THEY LOOK LIKE BUTTONS NOW, at the user's request — first
        # "make the button red so they look like buttons", then "id like
        # to make all buttons have a gold border (the same as the app
        # border)". They need no property of their own for that: the
        # base `QPushButton` rule carries the gold, so being a button IS
        # the styling. An `outline` property briefly sat here and went
        # when the gold made it redundant.
        # They also briefly moved off this row to sit between the Radiant
        # and Dire headings, and came straight back when the profile went
        # to the title bar and freed this end of it.
        self.clear_all_button = QPushButton("Clear all")
        self.clear_all_button.setToolTip(
            "Empty every hand-entered slot on both teams, and forget any "
            "side or order corrections made this match")
        self.clear_all_button.clicked.connect(self._clear_all)

        self.detect_all_button = QPushButton("Detect all")
        self.detect_all_button.setToolTip(
            "Read the ten portraits off the Dota window now, whatever the "
            "gate thinks — and forget what was read before, so a stale "
            "answer cannot win the vote against the new frame")
        self.detect_all_button.clicked.connect(self._detect_all)

        self.demo_button = QPushButton("Demo")
        self.demo_button.setToolTip(
            "Fill the board with a random 5v5, to see what the app does "
            "with one. Hand entry, so Clear all empties it again.")
        self.demo_button.clicked.connect(self._demo_draft)


        self.recording_label = QLabel("")
        self.recording_label.setProperty("dim", True)
        self.recording_label.setVisible(False)

        # Recordings and the report have a whole tab of their own
        # (Debug ▸ Recordings). Buttons for them up here were the same
        # thing said twice, in the row that has to stay readable at the
        # narrowest the window goes.
        self.open_recordings_button = QPushButton("Recordings")
        self.open_recordings_button.clicked.connect(
            lambda: open_folder(RECORDINGS_DIR))

        # Update is in Help, not up here. It is pressed once a patch, and
        # the row it was in has to stay readable at the narrowest the
        # window goes. It still closes and reopens the app by itself.
        self.report_button = QPushButton("Report")
        self.report_button.clicked.connect(self._show_latest_report)

        self.force_check = QCheckBox("Force recognition")
        self.force_check.toggled.connect(self._set_forced)
        # No expanding spacer: on the tab strip the toolbar is sized to
        # its contents, and a spacer there would push the controls off the
        # right edge of the window.
        # TRANSPARENCY IS IN THE VIEW MENU, not on this row. It is set
        # once and then left alone for the evening, and a row read at a
        # glance mid-draft should hold the things pressed mid-draft.
        self._add_run_menu()
        self._add_transparency_menu()
        self._add_sizes_menu()
        # LAST, so the four tick boxes sit under the two sliders.
        # `_add_transparency_menu` moves ITSELF to the top of the menu
        # when anything is already there, so adding these first would
        # have left Sizes stranded below them.
        self._add_section_menu()

        # There is no capture pill: it said the same sentence as the status
        # bar in less room, one line higher up. Keeping it around invisible
        # is how it became a window of its own.
        # THERE IS NO DATA-AGE PILL, and no data-age banner or status
        # segment either. "data 20h" was three copies of a number that is
        # only ever worth acting on once a fortnight, sitting on screen for
        # the other fourteen days; the prompt is now a dialog at startup
        # (`_prompt_if_data_is_old`) and nothing at all in between.

        # BandedTabs, not QTabWidget: the tab row has to be one dark band
        # edge to edge, and the gap between the tabs and the toolbar is
        # painted by the tab widget itself where no stylesheet reaches.
        tabs = chrome.BandedTabs()
        self.tabs = tabs

        shell = chrome.FramedShell()
        shell_lay = QVBoxLayout(shell)
        # Inset by the frame's width so the border has somewhere to be
        # drawn that is not on top of the content — a border painted over
        # the app eats the resize corner and the first pixels of the tabs.
        shell_lay.setContentsMargins(ornate.WIDTH, ornate.WIDTH,
                                     ornate.WIDTH, ornate.WIDTH)
        shell_lay.setSpacing(0)
        self.title_bar = TitleBar("Dota Draft Assist")
        self.title_bar.add_menu_bar(self.menu_bar)
        self.title_bar.minimise.connect(self.showMinimized)
        self.title_bar.maximise.connect(self._toggle_maximised)
        self.title_bar.close_clicked.connect(self.close)
        self.title_bar.pinned.connect(self._set_pinned)
        shell_lay.addWidget(self.title_bar)
        # THE PROFILE LIVES IN THE TITLE BAR, left of the pin, and
        # CLICKING IT DROPS THE DETAIL. The shape is Steam's and only
        # the shape, at the user's request: "purrely the ideao of having
        # profile just left of the pin icon ... and when its clicked the
        # callout drops down ... do nto copy a bunch of crap fro msteam
        # i was just usign that as an example".
        #
        # This is the THIRD place it has been in as many messages — a row
        # of its own at the top of the Draft tab, then beside the tabs,
        # then the far right of the strip — and the title bar is the one
        # that costs no layout at all. It is about YOU rather than about
        # the draft or the tabs, and it is now beside the other things
        # that are about the window itself.
        #
        # ONE implementation of the detail: the callout holds the same
        # `AccountRow` the Draft tab used to, so "who is this and when
        # was it measured" is spelled once. The button carries the name
        # alone, because that is what fits between the menus and the pin.
        self.account_row = accountrow.AccountRow()
        self.account_row.clicked.connect(self._show_history_tab)
        self.profile_button = accountrow.ProfileButton()
        self.profile_button.clicked.connect(self._show_profile)
        self.title_bar.add_widget(self.profile_button)
        self._build_profile_menu()

        # BACK ON THE TAB ROW, at the user's request one message after
        # they left it: "on second thought it makes more senxse to have
        # the clear / detect / demo o nthe same row as the draft /
        # history now that i have moved profiel to the top bar next to
        # the pin". Moving the profile into the title bar is what freed
        # this end of the row, and these three are the controls pressed
        # mid-draft, so the row that is always on screen is where they
        # belong. They keep the OUTLINED red from their trip to the
        # board bar — "make the button red so they look like buttons".
        for button in (self.clear_all_button, self.detect_all_button,
                       self.demo_button):
            tabs.add_rule()
            tabs.add_tools(button)

        shell_lay.addWidget(tabs.strip)
        shell_lay.addWidget(tabs, 1)
        # A frameless window has no resize border, so the corner is put
        # back explicitly. Bottom-right only: one grip is enough to size a
        # window and four would be four things to mis-hit.
        self._shell_lay = shell_lay
        self.setCentralWidget(shell)

        # ----- Draft tab: the two teams, and the grids under them.
        # The whole tab answers one question — what does this ten-hero
        # board look like — so nothing else lives on it. Your five sit on
        # the left and theirs on the right because that is where they are
        # on the pick bar, and the matrices sit directly underneath the
        # side they describe: counters under the two teams they compare,
        # synergy under your own.
        draft_widget = QWidget()
        outer = QVBoxLayout(draft_widget)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        self.banner = QFrame()
        self.banner.setProperty("banner", True)
        blay = QHBoxLayout(self.banner)
        blay.setContentsMargins(12, 10, 12, 10)
        self.banner_label = QLabel()
        self.banner_label.setWordWrap(True)
        blay.addWidget(self.banner_label, 1)
        self.banner_button = QPushButton("Download now")
        self.banner_button.setProperty("accent", True)
        # The banner says several different things, so the button cannot be
        # wired to one of them: it runs whatever the current message is
        # about.
        self._banner_action = lambda: self.run_task("update_data")
        self.banner_button.clicked.connect(lambda: self._banner_action())
        blay.addWidget(self.banner_button)
        outer.addWidget(self.banner)

        # LEFT IS ALWAYS RADIANT, which is how the pick bar the user is
        # looking at is arranged, so the panels are re-ordered rather than
        # re-labelled when the player turns out to be Dire (see
        # `_order_panels`). The dict keys stay ally/enemy — everything else
        # in the app reasons in those terms — and only the PANELS' seating
        # changes: the two grid cards below them are pinned, synergies
        # left and counters right, whichever side the user is on.
        # THE AD SLOT IS GONE, at the user's request — "remove the ad
        # stuff all together". It was the SPACE a banner would take, on a
        # timer, above the two team panels, so that living with one for an
        # evening could be tried before committing to it. It was tried and
        # switched off, and the honest reading of its own note is that the
        # decision was already made: the ad networks worth using serve
        # into WEB PAGES, there is no supported path for a PyQt window,
        # and this app has no page to serve into. A switch nobody will
        # turn on is a widget, a setting, a stylesheet rule and a painted
        # creative to keep working for ever.
        # WHOSE HISTORY THE NUMBERS ARE FOR, at the user's request, in the
        # slot the ad used to have to itself - and the ad now defaults
        # OFF, so on an ordinary install this row IS the top of the
        # content. It follows `report_changed` like the stars do, so
        # looking somebody else up re-draws it, and it makes no request of
        # its own: the picture was fetched during the run.

        self.teams_row = teams_row = QHBoxLayout()
        teams_row.setSpacing(10)
        self._panel_order = ["ally", "enemy"]
        self.team_panels = {}
        self.team_buttons = {}
        self.team_captions = {}
        for side, caption in (("ally", "Your team"), ("enemy", "Enemy team")):
            panel = TeamPanel(side, caption)
            self.team_panels[side] = panel
            self.team_buttons[side] = panel.buttons
            self.team_captions[side] = panel.caption
            for index, b in enumerate(panel.slots):
                b.setToolTip("Click to set this pick; click a filled slot "
                             "and every other hero shows what it is worth "
                             "beside or against it. Right-click to change "
                             "it, clear it, or give it a role.")
                b.clicked.connect(self._on_slot_clicked)
                b.setContextMenuPolicy(
                    Qt.ContextMenuPolicy.CustomContextMenu)
                b.customContextMenuRequested.connect(
                    lambda pos, side=side, i=index:
                        self._slot_menu(side, i, pos))
                b.dropped_on.connect(self._on_slot_dropped)
        # ONE tile size for the whole app: the panel computes it from the
        # width it was given, and the strips below follow it.
        self.team_panels["ally"].tile_resized.connect(self._resize_strips)

        # WHAT THE TWO LINE-UPS ARE MADE OF, between the board and the
        # advice about it, at the user's request. It reads in the same
        # direction as everything else on this tab: the ten picks are the
        # subject, this says what they add up to, and the suggestions
        # below answer what to do about it. Valve's own 0-to-3 role
        # ratings, normalised by how many picks each side has made so a
        # 3v5 board is still a comparison (`model/roles.py`).
        #
        # ONE CARD PER SIDE HOLDING BOTH, at the user's request: "i dont
        # like that the padding is not joined between the pills and the
        # 5 / 5 portaits sectrions... they belong in the same section..
        # obviously dire and radiant would stay seperate pads though."
        # This is the last step of an argument that started with "see the
        # padding on the background that allows you to know that 5 heroes
        # at the pick menu are radiant? that padding should encapsulate
        # the roles". It did not, quite: the roles sat in a SECOND card
        # under the first, so a side read as two stacked sections rather
        # than one. Now the padding genuinely encapsulates both, and the
        # only division the tab draws is the one that means something —
        # Radiant from Dire.
        # AND NO HEADING ON THE ROLES: "you don't need to state roles,
        # it's obvious from the content."
        self.role_bar = rolebar.RoleCards()
        self.side_cards = {}
        for side in ("ally", "enemy"):
            side_card, slay = card()
            slay.setSpacing(6)
            slay.addWidget(self.team_panels[side])
            slay.addWidget(self.role_bar.bars[side])
            self.side_cards[side] = side_card
            teams_row.addWidget(side_card, 1)
        outer.addLayout(teams_row)
        # VIEW HIDES THE TWO BARS THEMSELVES now that there is no block
        # of their own to hide. `_apply_sections` takes a sequence for
        # exactly this: a section can be two widgets in two cards. There
        # is no row left to leave an empty double gap behind, which is
        # what the wrapper widget was for.
        self.roles_block = [self.role_bar.bars[side]
                            for side in ("ally", "enemy")]

        # The board is the top of the screen and everything under it is
        # advice about the board: first which hero to take, then what to
        # build against what is already there.
        self.count_boxes = {}
        # THE COUNT RIDES ON THE HEADING, and the legend sits below it.
        # "you dont need suggested picks and pick suggestions - please
        # rearrange": the card was headed "Suggested picks" and its first
        # body row read "Pick suggestions = 20", which is the same two
        # words twice with a number after one of them. So the number
        # joins the heading it was paraphrasing and that row goes.
        #
        # This is a PARTIAL reversal of "i think it would look better if
        # 'suggested picks' header was above all the text - shift the
        # rest down so it's all level 1 row lower than the header", and
        # only partial on purpose. What that asked for was the TEXT off
        # the heading line, and the legend — the two mark rows and the
        # role filter — stays exactly where that put it. A corner is
        # sized to itself, so a count box is the one thing that can ride
        # there; the filter REFLOWS and still must have the card's full
        # width in the body, or it cannot tell how many columns it has
        # room for.
        #
        # It also puts this card back in step with Suggested items,
        # which has had its count on the heading throughout.
        # "TOP PICKS", and the heading is INSIDE the grid rather than on
        # the card's own heading line. At the user's request: "instead of
        # suggested picks, use the header 'top picks' and make the
        # required adjustments in the rows below so that the input boxes
        # align edges... shift the heart and shield stuff to the right as
        # required and then evenly space everything to its right".
        #
        # A card corner is sized to ITSELF and sits a fixed gap after the
        # title, so the count box landed wherever the words "Suggested
        # picks" happened to end — nowhere near the two below it. Putting
        # the heading in the same QGridLayout as the legend puts all
        # three boxes in one COLUMN, which aligns them by construction
        # rather than by a measurement somebody has to keep right.
        self.suggested_box = self._count_box("suggested_picks")
        picks_card, playy = card()
        playy.addWidget(self._picks_controls())
        self.suggest_row = SuggestRow()
        self.suggest_row.clicked_hero.connect(
            self._on_suggestion_clicked)
        playy.addWidget(self.suggest_row)
        self.picks_card = picks_card
        outer.addWidget(picks_card)

        items_card, ilay = card(
            "Suggested items", self._count_box("suggested_items"))
        self.item_row = ItemRow()
        self.item_row.asked_why.connect(self._why_this_item)
        ilay.addWidget(self.item_row)
        self.items_card = items_card
        outer.addWidget(items_card)

        # ----- the grids, each under the team whose heroes head it.
        # Synergy is ally-by-ally, so it belongs under your five on the
        # LEFT; counters are read against their five, so its columns belong
        # under theirs on the RIGHT. A column then reads straight down from
        # the tile it is about, which is why the headers are those same
        # portraits rather than the names a second time.
        self.grids_row = grids = QHBoxLayout()
        grids.setSpacing(10)
        with_card, withlay = card("Synergies")
        self.synergy_matrix = MatrixTable()
        # No caption: the heading says which grid this is and the headers
        # say what the axes are.
        self.synergy_matrix.set_compact(True, short_names=False)
        self.synergy_matrix.set_icon_headers(True)
        # No Sigma row or column — each tile already carries that hero's
        # total in its corner, and the same figure twice is once too many.
        self.synergy_matrix.set_margins(False)
        withlay.addWidget(self.synergy_matrix)
        grids.addWidget(with_card, 1)
        vs_card, vslay = card("Counters")
        self.matchup_matrix = MatrixTable()
        # BOTH GRIDS FEED THE ONE SELECTION. Clicking an axis face is the
        # same gesture as clicking a pick or a suggestion, so it goes to
        # the same handler and lands in the same `self.focus`; the grids
        # are told what to draw rather than deciding it, which is what
        # keeps one hero lit across all four surfaces.
        self.synergy_matrix.hero_clicked.connect(self._on_grid_hero_clicked)
        self.matchup_matrix.hero_clicked.connect(self._on_grid_hero_clicked)
        self.matchup_matrix.set_compact(True, short_names=False)
        self.matchup_matrix.set_icon_headers(True)
        self.matchup_matrix.set_margins(False)
        vslay.addWidget(self.matchup_matrix)
        grids.addWidget(vs_card, 1)
        # SYNERGIES LEFT, COUNTERS RIGHT, ALWAYS — they are never
        # re-seated. See `_order_panels`.
        self.synergy_card, self.matchup_card = with_card, vs_card
        grids.setContentsMargins(0, 0, 0, 0)
        self.grids_block = QWidget()
        self.grids_block.setProperty("bare", True)
        self.grids_block.setLayout(grids)
        outer.addWidget(self.grids_block)
        # The stretch goes at the BOTTOM, not into the grids. Giving it to
        # them left half the window blank and, worse, meant the window had
        # no shorter size to offer — a stretching widget never asks for
        # less. Now every card is its own height and the slack is slack.
        outer.addStretch(1)

        # IN A SCROLL AREA, which the Debug tab has needed for a while
        # and this one now does too. A QTabWidget's minimum is its TALLEST
        # page, and the Draft tab has grown: ten picks, the roles card,
        # two wrapping advice strips and two grids. The strips also began
        # declaring the height their wrap actually needs (`suggest_row`,
        # `item_row`) — without that they were silently cropped — and a
        # widget's honest minimum is the WINDOW's minimum, which took the
        # floor to 894px. That is a window a 1366x768 laptop cannot open.
        # Inside a scroll area the page asks for nothing, so the floor is
        # back and nothing is ever cut off: at any ordinary size there is
        # nothing to scroll, and on a short screen the tab scrolls instead
        # of hiding its last row of tiles.
        tabs.addTab(_scrolling(draft_widget), "Draft")

        # ----- History tab: one account's match history, measured.
        # It used to be the ranked list of every hero NOT in this game,
        # with a breakdown and a counters list beside it. That answered
        # "what should I pick", which the Draft tab answers in the one
        # place it belongs — under the picks, where Suggested picks is that
        # same list cut to its head. This tab now answers the other
        # question, which the app was never asking: across a few hundred of
        # your own games, what actually goes with winning. See
        # `ui/history_tab.py`; nothing in the live loop touches it.
        analysis = HistoryTab(say=self._say, settings=self.settings)
        self.history_tab = analysis
        # THE ONE PLACE THE TWO TABS MEET. The suggestion strip ranks by
        # draft fit, which knows nothing about you; the History tab knows
        # a great deal about you and nothing about the board. A star says
        # "and this is a hero you play a lot and win on", on the tile the
        # fit is already on. It follows whichever run is LOADED there, at
        # the user's request, rather than being pinned to one account.
        analysis.report_changed.connect(self._history_run_changed)
        # AND THE RUN IT ALREADY HAS. `HistoryTab.__init__` loads the
        # cached run and assigns `report`, which emits - EIGHT LINES
        # ABOVE this connect, into nothing at all. So on a fresh start the
        # account row sat at "No account measured yet" until the user
        # re-ran or changed account, with last night's analysis sitting on
        # disk the whole time. A signal announces CHANGES; the state it
        # already holds has to be read once, here.
        self._history_run_changed(analysis.report)
        # AND THE SHIELDS, for the same reason one line up and a worse
        # one: `_recompute_shields` was called from `reload_backend` and
        # NOWHERE ELSE, so on an ordinary start it never ran at all and
        # `self.shields` stayed the empty dict it is built with - for the
        # whole session, on every tile, for ever. The mark could only
        # appear after a statistics download, which is not something
        # anybody does to make a mark show up. "The shield is not working
        # at all" was exactly right.
        #
        # It needs no history and no account, only the matrix, so unlike
        # the stars it can be worked out the moment the dataset is in
        # hand.
        self._recompute_shields()
        tabs.addTab(analysis, "History")

        # ----- Debug tab: the picture answers what a log never will
        dbg = QWidget()
        dlay = QVBoxLayout(dbg)
        dlay.setContentsMargins(12, 12, 12, 12)
        dlay.setSpacing(10)

        src_card, slay = card("Capture source")
        src_row = QHBoxLayout()
        self.source_combo = Dropdown()
        self.source_combo.setMinimumWidth(300)
        src_row.addWidget(self.source_combo, 1)
        self.refresh_sources_button = QPushButton("Refresh")
        self.refresh_sources_button.clicked.connect(self._refresh_sources)
        src_row.addWidget(self.refresh_sources_button)
        self.bind_button = QPushButton("Capture this window")
        self.bind_button.setProperty("accent", True)
        self.bind_button.clicked.connect(self._bind_source)
        src_row.addWidget(self.bind_button)
        slay.addLayout(src_row)
        # It belongs beside the picture it affects. It was CREATED and then
        # added to nothing, and a parentless QWidget becomes a top-level
        # WINDOW the moment anything shows it — which is what the second
        # "Dota Draft Assist" window holding one checkbox was.
        slay.addWidget(self.force_check)
        if not hasattr(self.provider, "available_sources"):
            self.source_combo.addItem(
                "(screen capture only — the current source is game data)")
        dlay.addWidget(src_card)

        # What the app concluded about the draft, and the one control that
        # corrects it. This was a card of its own on the DRAFT tab, where
        # it repeated what the tiles and the status bar already say: an
        # unresolved slot draws as "+", the source is in the status bar,
        # and sides are now fixed by dragging a tile rather than by reading
        # a sentence about them.
        state_card, elay = card("What the app is reading")
        self.unknown_label = QLabel("")
        self.unknown_label.setProperty("dim", True)
        # Selectable, because the whole point of this card is that its text
        # gets pasted to somebody. A QLabel is not selectable by default.
        self.unknown_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        elay.addWidget(self.unknown_label)
        self.manual_hint = QLabel("")
        self.manual_hint.setWordWrap(True)
        self.manual_hint.setProperty("dim", True)
        self.manual_hint.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        elay.addWidget(self.manual_hint)
        # Only meaningful when the source is pixels: the two banks are then
        # just screen positions. Game data reports player.team_name, so
        # asking would be asking about something already known.
        side_row = QHBoxLayout()
        self.side_label = QLabel("My team:")
        side_row.addWidget(self.side_label)
        self.side_combo = Dropdown()
        self.side_combo.addItems(["left bank", "right bank"])
        self.side_combo.currentIndexChanged.connect(self._force_redraw)
        side_row.addWidget(self.side_combo)
        side_row.addStretch(1)
        elay.addLayout(side_row)
        dlay.addWidget(state_card)

        self.debug_image = FrameView("No frame captured yet.")
        self.debug_image.setMinimumHeight(320)
        self.debug_image.setProperty("card", True)
        dlay.addWidget(self.debug_image, 3)

        log_card, loglay = card("Recognition log")
        log_row = QHBoxLayout()
        log_row.addStretch(1)
        self.copy_log_button = QPushButton("Copy everything")
        self.copy_log_button.setProperty("accent", True)
        self.copy_log_button.setToolTip(
            "Copy the status line, what the app is reading, this log and "
            "the loop timings — everything needed to diagnose a bad draft "
            "or a slow one, in one paste")
        self.copy_log_button.clicked.connect(self._copy_debug_log)
        log_row.addWidget(self.copy_log_button)
        loglay.addLayout(log_row)
        self.debug_text = QPlainTextEdit()
        self.debug_text.setReadOnly(True)
        self.debug_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        loglay.addWidget(self.debug_text, 1)
        dlay.addWidget(log_card, 1)

        # Where the refresh loop's time actually goes. Always measured;
        # only drawn when this tab is open.
        timing_card, tlay = card("Loop timings · milliseconds")
        self.timing_text = QPlainTextEdit()
        self.timing_text.setReadOnly(True)
        self.timing_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.timing_text.setMinimumHeight(160)
        self.timing_text.setMaximumHeight(220)
        font = self.timing_text.font()
        font.setFamily("Consolas")
        font.setStyleHint(font.StyleHint.Monospace)
        self.timing_text.setFont(font)
        tlay.addWidget(self.timing_text)
        dlay.addWidget(timing_card)

        # Calibration lives beside the picture because it is only usable
        # with the picture: the boxes move as the numbers change, so being
        # off is corrected by eye in seconds rather than by editing JSON
        # and restarting.
        cal_card, callay = card("Crop boxes")
        cal_note = QLabel(
            "Measured from the game, not drawn by hand — and measured "
            "again by itself whenever the boxes stop finding the "
            "portraits. These are what it last measured, as fractions of "
            "Dota's 16:9 HUD area; nudging one is a last resort.")
        cal_note.setWordWrap(True)
        cal_note.setProperty("dim", True)
        callay.addWidget(cal_note)
        grid = QHBoxLayout()
        self.cal_spins = {}
        for field, label, step in (
                ("radiant_x", "left bank x", 0.001),
                ("dire_x", "right bank x", 0.001),
                ("y", "top y", 0.001),
                ("slot_w", "width", 0.001),
                ("slot_h", "height", 0.001),
                ("pitch", "spacing", 0.001)):
            column = QVBoxLayout()
            caption = QLabel(label)
            caption.setProperty("dim", True)
            column.addWidget(caption)
            spin = QDoubleSpinBox()
            spin.setDecimals(4)
            spin.setRange(0.0, 1.0)
            spin.setSingleStep(step)
            spin.setValue(getattr(self.layout_spec, field))
            spin.valueChanged.connect(
                lambda value, name=field: self._set_calibration(name, value))
            column.addWidget(spin)
            self.cal_spins[field] = spin
            grid.addLayout(column)
        callay.addLayout(grid)
        cal_buttons = QHBoxLayout()
        self.measure_button = QPushButton("Measure from this game")
        self.measure_button.setProperty("accent", True)
        self.measure_button.setToolTip(
            "At strategy time the game has named all ten heroes and the app "
            "has a frame of them — so the boxes can be measured instead of "
            "nudged. Takes about a minute.")
        self.measure_button.clicked.connect(self._measure_calibration)
        cal_buttons.addWidget(self.measure_button)
        save_cal = QPushButton("Save")
        save_cal.setProperty("accent", True)
        save_cal.clicked.connect(self._save_calibration)
        cal_buttons.addWidget(save_cal)
        reset_cal = QPushButton("Reset to defaults")
        reset_cal.clicked.connect(self._reset_calibration)
        cal_buttons.addWidget(reset_cal)
        self.cal_label = QLabel("")
        self.cal_label.setProperty("dim", True)
        cal_buttons.addWidget(self.cal_label, 1)
        callay.addLayout(cal_buttons)
        dlay.addWidget(cal_card)

        snap_row = QHBoxLayout()
        self.snapshot_button = QPushButton(
            "Save debug snapshot (frame + crops + matches)")
        self.snapshot_button.clicked.connect(self._save_snapshot)
        snap_row.addWidget(self.snapshot_button)
        open_debug = QPushButton("Open debug folder")
        open_debug.clicked.connect(lambda: open_folder(DEBUG_OUT))
        snap_row.addWidget(open_debug)
        self.snapshot_label = QLabel("")
        self.snapshot_label.setProperty("dim", True)
        snap_row.addWidget(self.snapshot_label, 1)
        dlay.addLayout(snap_row)

        # The Debug tab is two jobs: what the app is looking at RIGHT NOW,
        # and what a past session recorded. They want different screens.
        debug_tabs = QTabWidget()
        self.debug_tabs = debug_tabs
        debug_tabs.addTab(_scrolling(dbg), "Live")
        debug_tabs.addTab(_scrolling(self._build_sessions_tab()),
                          "Recordings")
        # NOT a tab of the main window any more, at the user's request: it
        # is handed to the settings window as its Debug tab the first time
        # that is opened (`_open_settings`). It keeps THIS window as its
        # parent until then, because a parentless QWidget in this app is a
        # second window in the taskbar — a bug that has already happened
        # three times — and `_update_debug` goes on asking whether it is
        # VISIBLE, which it is not while it is parked here unshown.
        debug_tabs.setParent(self)
        debug_tabs.hide()

        # Our own, INSIDE the shell, rather than QMainWindow's: the
        # ornate frame is drawn round the shell, and a status bar hung off
        # the window sits outside it — a border round everything except
        # the bottom strip is a border that has been forgotten about.
        self.status = QStatusBar()
        self.status.setSizeGripEnabled(False)
        # The grip goes INSIDE the status bar, at its right end. It used to
        # have a row of its own below, which left a strip of window under
        # the status message with nothing in it — the message should end
        # where the window does. Sharing the bar means the grip sits on the
        # message's own background, which is what a resize corner does in
        # every other application.
        self.resize_grip = ResizeGrip(self.status)
        self.status.addPermanentWidget(self.resize_grip)
        self._shell_lay.addWidget(self.status)

        # ALL FOUR CORNERS, at the user's request: "I want to be able to
        # resize from any corner of the window... so that if I can only
        # see / access the top right corner and not the bottom right, I
        # can shrink it and then drag it up".
        #
        # CORNERS AND NOT SIDES, which is the second half of that request
        # and a correction to the first attempt: a live top edge and a
        # draggable title bar cannot share the same pixels, so a resize
        # strip along the top of the bar took away the gesture the bar
        # exists for — "now I can't drag to move the app window". The
        # sides went with it; the complaint was about reaching a CORNER
        # of a window grown off the screen, and four corners answer it.
        #
        # The grip above stays, because it is the only handle that can be
        # SEEN — three diagonal dots saying the window is resizable — and
        # because it accepts its own presses it goes on serving the corner
        # it is in. What it could not do is rescue a window whose bottom
        # right is off the screen, which is the whole complaint.
        #
        # FOUR WATCHERS, and the list is not arbitrary: the window catches
        # everything that IGNORES a press and propagates up to it, which
        # is most of the border, and the other three are the widgets on
        # the border that ACCEPT their own presses and would otherwise
        # swallow them silently.
        self.resize_border = chrome.ResizeBorder(self)
        for edge_widget in (self, self.centralWidget(),
                            self.title_bar, self.status):
            self.resize_border.watch(edge_widget)

    def _build_sessions_tab(self) -> QWidget:
        """Past recordings, each one discrete, with its report ready to
        copy. Every Record press makes its own folder, so a session is a
        single game and never a pool of several."""
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        left = QVBoxLayout()
        left.addWidget(QLabel("Sessions (newest first)"))
        self.session_list = QListWidget()
        self.session_list.setMinimumWidth(220)
        self.session_list.currentRowChanged.connect(self._show_session)
        left.addWidget(self.session_list, 1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh_sessions)
        left.addWidget(refresh)
        layout.addLayout(left)

        right = QVBoxLayout()
        self.session_report = QPlainTextEdit()
        self.session_report.setReadOnly(True)
        self.session_report.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.NoWrap)
        right.addWidget(self.session_report, 1)
        buttons = QHBoxLayout()
        self.copy_report_button = QPushButton("Copy report")
        self.copy_report_button.setProperty("accent", True)
        self.copy_report_button.clicked.connect(self._copy_session_report)
        buttons.addWidget(self.copy_report_button)
        replay = QPushButton("Replay this session")
        replay.setToolTip(
            "Send this session's payloads back through the app exactly as "
            "Dota sent them — the highest-fidelity test there is")
        replay.clicked.connect(self._replay_session)
        buttons.addWidget(replay)
        # The two that came off the toolbar. They belong beside the
        # recordings they are about, not in the row above the draft.
        buttons.addWidget(self.report_button)
        self.report_button.setToolTip(
            "The newest session's report, whatever is selected here")
        buttons.addWidget(self.open_recordings_button)
        self.open_recordings_button.setToolTip(
            "Open the recordings folder")
        buttons.addWidget(self.recording_label)
        open_session = QPushButton("Open this folder")
        open_session.clicked.connect(self._open_session_folder)
        buttons.addWidget(open_session)
        buttons.addStretch(1)
        right.addLayout(buttons)
        layout.addLayout(right, 1)

        self._refresh_sessions()
        return page

    def _show_latest_report(self) -> None:
        """Jump to the newest session's report. One button, one document —
        the screen's reading and the game's payloads were never two
        separate questions."""
        self._refresh_sessions()
        # Debug is a tab of the SETTINGS window now, so the way to it is
        # to open that on Debug rather than to index into the main tabs —
        # where index 1 is the History tab and used to be this.
        self._open_settings("Debug")
        self.debug_tabs.setCurrentIndex(1)
        if not self.sessions:
            self._say(
                "No recordings yet — press Record before a game", 8000)

    def _refresh_sessions(self) -> None:
        self.sessions = record_mod.sessions(RECORDINGS_DIR)
        self.session_list.clear()
        for folder in self.sessions:
            self.session_list.addItem(folder.name)
        if self.sessions:
            self.session_list.setCurrentRow(0)
        else:
            self.session_report.setPlainText(
                "No recordings yet. Press Record before a game and Stop "
                "after the draft.")

    def _show_session(self, row: int) -> None:
        if not (0 <= row < len(self.sessions)):
            return
        folder = self.sessions[row]
        # Re-derive rather than trusting report.txt: a session stopped by a
        # crash never got one written.
        try:
            self.session_report.setPlainText(
                record_mod.format_session_report(folder, self.ds))
        except OSError as exc:
            self.session_report.setPlainText(f"Could not read {folder}:\n{exc}")

    def _current_session(self):
        row = self.session_list.currentRow()
        return self.sessions[row] if 0 <= row < len(self.sessions) else None

    def _copy_session_report(self) -> None:
        text = self.session_report.toPlainText()
        if not text:
            return
        QApplication.clipboard().setText(text)
        self._say("Report copied to the clipboard", 5000)

    def _replay_session(self) -> None:
        """Replay the selected recording. It lives here rather than in a
        menu because it is one more thing you do WITH a recording, and the
        recording is what you already have selected."""
        folder = self._current_session()
        if folder is None or not (folder / "gsi").is_dir():
            self._say(
                "Select a recording with game data first", 6000)
            return
        self.run_task("replay_gsi", str(folder / "gsi"))

    def _open_session_folder(self) -> None:
        folder = self._current_session()
        open_folder(folder if folder is not None else RECORDINGS_DIR)

    # ---- maintenance tasks --------------------------------------------
    def run_task(self, key: str, argument: str = "") -> None:
        task = TASKS[key]
        if argument:
            task = task.with_argument(argument)
        dialog = TaskDialog(task, self)
        # A task that is going to relaunch the app closes its own dialog
        # when it works. Nobody wants to press Close on a progress box and
        # then watch the app they just updated restart anyway.
        restarting = getattr(self, "_restart_after_task", "") == task.key
        dialog.close_on_success = restarting
        if task.modeless:
            # A feeding task drives the main window, so it must not sit on
            # top of it modally: the point of simulating a draft is to click
            # the heroes it produces and read the breakdown.
            dialog.finished.connect(
                lambda _r, d=dialog: self._task_finished(d))
            self._open_tasks.append(dialog)
            dialog.start()
            dialog.show()
            return
        dialog.start()
        dialog.exec()
        # THE SAME ENDING FOR BOTH PATHS. `_task_finished` was wired only
        # to the modeless one, so a modal task's restart request was
        # recorded and then never acted on — which is why Update pulled the
        # new version and left the old one running, waiting to be closed
        # and reopened by hand.
        self._task_finished(dialog)

    def _task_finished(self, dialog) -> None:
        if dialog in self._open_tasks:
            self._open_tasks.remove(dialog)
        if dialog.succeeded and dialog.task.reload_after:
            self.reload_backend()
        # Only the Update commands ask for a restart, and only a pull that
        # actually worked earns one — relaunching after a failure would
        # hide the error the dialog is showing.
        if getattr(self, "_restart_after_task", "") == dialog.task.key:
            self._restart_after_task = ""
            if dialog.succeeded:
                self._relaunch()

    def reload_backend(self) -> None:
        """Re-read dataset and portrait library from disk, and rebuild the
        capture session around them, so a data update takes effect without
        restarting the app."""
        self.ds = store.load_or_empty()
        # The shield reads the matrix, so a reloaded dataset is a new
        # answer and this is the one place that can notice.
        self._recompute_shields()
        # The icon can come out of the portrait library, so a download that
        # has just landed may have supplied one.
        appicon.forget()
        # Both picture caches index their folder ONCE and remember it was
        # empty. A download that happens while the app is running would
        # therefore never appear — which is exactly what "I ran the update
        # and the item icons are still blank" looks like from outside.
        portraits.forget()
        item_icons.forget()
        self._apply_app_icon()
        session = getattr(self.provider, "session", None)
        if session is not None:
            try:
                from ..vision import library as library_mod
                params = library_mod.load_params()
                session.params = params
                session.lib = library_mod.load(expected_hash_size=params.hash_size)
            except FileNotFoundError:
                pass  # no portraits yet; the banner explains what to do
        self.last_draft_key = None
        self._update_first_run_banner()
        self._refresh_views()
        self._say(
            "Reloaded: "
            + (f"{len(self.ds.hero_ids)} heroes" if not self.ds.is_empty
               else "no data downloaded yet"), 5000)

    def _choose_brackets(self) -> None:
        """Pick the rank brackets statistics come from, then offer the
        re-pull the change requires."""
        current = target_brackets()
        dialog = BracketDialog(current, parent=self)
        if dialog.exec() != BracketDialog.DialogCode.Accepted:
            return
        if dialog.selected == current:
            return
        try:
            save_target_brackets(dialog.selected)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Statistics bracket",
                                f"Could not save the choice:\n\n{exc}")
            return
        self._update_first_run_banner()
        chosen = " + ".join(b.title() for b in dialog.selected)
        answer = QMessageBox.question(
            self, "Statistics bracket",
            f"Statistics will now be pulled for {chosen}.\n\n"
            "The cached data was built for the previous bracket, so it has "
            "to be rebuilt. Update now?")
        if answer == QMessageBox.StandardButton.Yes:
            self.run_task("update_data")

    def _bracket_mismatch(self) -> tuple[str, str] | None:
        """(cached, wanted) when the dataset on disk was built for different
        brackets than are currently selected — the numbers would otherwise
        silently disagree with the label."""
        if self.ds.is_empty:
            return None
        cached = tuple(self.ds.meta.get("target_brackets", ()))
        wanted = target_brackets()
        if cached and tuple(cached) != wanted:
            return ("+".join(cached), "+".join(wanted))
        return None

    def _show_banner(self, message: str, button: str, action) -> None:
        set_label(self.banner_label, message)
        if self.banner_button.text() != button:
            self.banner_button.setText(button)
        self._banner_action = action
        self.banner.setVisible(True)

    def _update_everything(self) -> None:
        """Statistics AND artwork, which is what every banner button that
        says "update" should mean. One task, so there is one thing to
        watch and one thing that can fail."""
        self.run_task("update_data")

    def _run_setup(self) -> None:
        """The first-run wizard, on demand.

        The banner's button is the only way back to it now: the menu
        here, so there is one way to do this rather than a wizard that can
        only ever be seen once.
        """
        from .setup_wizard import SetupWizard, STEPS
        wizard = SetupWizard(self)
        wizard.exec()
        # WHAT IS LEFT UNDONE IS REMEMBERED PER STEP, not as one "did
        # they finish" flag. Each step writes its own answer as you leave
        # it, so closing the window on the third page keeps the first two
        # and puts only the rest on the banner. Skip this step and
        # closing the window come to the same thing here, which is the
        # honest reading of both.
        self.settings["setup_pending"] = list(wizard.pending)
        ui_settings.save(self.settings)
        # The GSI config is the app's own half of the last step and has
        # nothing in it to decide, so it is written rather than asked
        # about — but only once that step has actually been reached.
        self._ensure_gsi_config()
        done = {step.ident for step in STEPS} - set(wizard.pending)
        if {"key", "ranks"} & done:
            # The statistics are built FOR the ranks, so either answer
            # changing means the download is what happens next.
            self._update_everything()
        if wizard.account_id is not None:
            self._measure_history(wizard.account_id)
        self._update_first_run_banner()

    def _measure_history(self, account_id: int) -> None:
        """Run the History tab once, on the account setup just collected.

        "its nice to have the steam code asked for and then to run the
        default analysis so that everything is setup as a starting
        point". The options are `ui_settings.history_options`' own
        defaults — ranked only, no turbo, six months, 5000 matches —
        which is already exactly what was asked for, so nothing here
        overrides them and the tab and this agree by construction.

        NEVER FATAL: it is a network call at the end of setup, and a
        first run that cannot reach OpenDota must still leave a set-up
        app rather than an error.
        """
        tab = getattr(self, "history_tab", None)
        if tab is None:
            return
        try:
            tab.account_box.setText(str(account_id))
            tab.start()
        except Exception:               # noqa: BLE001 - never worth a crash
            pass

    def _ensure_gsi_config(self) -> str:
        """Write Dota's GSI config unless the user skipped setup.

        THIS IS THE HALF THAT NEEDS NO HUMAN. Game data has exactly two
        requirements: this file in the Dota install, and
        `-gamestateintegration` in Steam's launch options. The second is
        the user's and cannot be automated at all -- it lives in Steam's
        own localconfig.vdf, which Steam rewrites from memory on exit.
        The first is a mkdir and a write with nothing whatever to decide,
        and it was a menu item somebody had to find, named by a banner,
        for no reason anybody could state: "why is it not just auto run
        at setup with all the other crap like portraits".

        IDEMPOTENT, so it can run at every start: `gsi_install.ensure`
        reuses the token already on disk, which means an unchanged config
        renders identical text and nothing is written. Minting a fresh
        token here would make the app reject the payloads of a Dota that
        is already running, which looks exactly like no payloads at all.

        Returns a short note for the status line, or "" when there was
        nothing to do. NEVER RAISES: a Dota install that cannot be found
        or written to is a thing to say on the banner, not a reason for
        the app to fail to open.
        """
        if "gsi" in (self.settings.get("setup_pending") or []):
            return ""
        from ..gsi import install as gsi_install

        server = getattr(self.provider, "server", None)
        port = getattr(server, "port", gsi_install.DEFAULT_PORT)
        try:
            result = gsi_install.ensure(port=port)
        except gsi_install.DotaNotFound:
            return ""
        except OSError:
            return ""
        # THE TOKEN HAS TO REACH THE LISTENER IN THE SAME BREATH. The
        # server was built with whatever token was on disk at startup,
        # which on a fresh install was none -- so a config written now
        # and a listener still expecting nothing would reject every
        # payload Dota sent, and a rejected payload is indistinguishable
        # from a silent game.
        if server is not None:
            server.token = result.token
        self._forget_gsi_config()
        return "Game data config installed" if result.created else ""

    def _launch_option_help(self) -> None:
        """The one step that is the user's, spelled out and pasteable.

        It is a procedure rather than a sentence at the user's request --
        "there should be instruction at setup for the user to add the
        -gamestateintegration in their steam... step by step". The steps
        themselves live in `gsi_install.LAUNCH_STEPS` so this dialog, the
        wizard's third card and the manual cannot drift apart.
        """
        from ..gsi import install as gsi_install

        steps = "\n".join(
            f"{n}.  {step}"
            for n, step in enumerate(gsi_install.LAUNCH_STEPS, 1))
        # IT REOPENS AFTER A COPY. Every button on a QMessageBox closes
        # it, so pressing Copy took the seven steps off the screen at the
        # exact moment somebody was about to follow them -- and this
        # dialog IS the steps. Showing it again is a flash; losing them
        # is the whole feature.
        copied = False
        while True:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Information)
            box.setWindowTitle("One step in Steam")
            box.setText("Dota needs one launch option before it will send "
                        "anything.")
            box.setInformativeText(
                steps + ("\n\nCopied, and Steam should be opening Dota's "
                         "properties. Paste it into the Launch Options box."
                         if copied else ""))
            copy = box.addButton(gsi_install.COPY_AND_OPEN,
                                 QMessageBox.ButtonRole.ActionRole)
            by_hand = box.addButton("or do it by hand",
                                    QMessageBox.ButtonRole.ActionRole)
            box.addButton(QMessageBox.StandardButton.Close)
            box.exec()
            if box.clickedButton() is by_hand:
                self._gsi_by_hand()
                continue
            if box.clickedButton() is not copy:
                return
            self._copy_and_open_steam()
            copied = True

    def _copy_and_open_steam(self) -> None:
        """Put the launch option on the clipboard and open the dialog it
        goes in. ONE ACTION, not two: the clipboard is loaded by the time
        the box you paste into is in front of you.

        `steam://gameproperties/570` was confirmed on the user's own
        machine, with Steam running and with Steam closed, BEFORE this
        was built on it — Steam ignores a verb it does not know without
        saying so, so an unverified one is a button that looks like it
        worked and did nothing. The message is the same either way for
        the same reason: the handler reporting success is not evidence
        the window opened, and the seven steps are still on screen.
        """
        from ..gsi import install as gsi_install

        QApplication.clipboard().setText(gsi_install.LAUNCH_OPTION)
        gsi_install.open_properties()
        self._say(f"Copied {gsi_install.LAUNCH_OPTION} — paste it into "
                  "Steam's Launch Options box, then restart Dota.", 8000)

    def _gsi_by_hand(self) -> None:
        """What the button does, for when it did not do it.

        A CALLOUT rather than three more numbered lines: the fallback is
        not the path, and printing it inline is what made the first thing
        to do the fourth thing on the page.
        """
        from ..gsi import install as gsi_install

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Opening it by hand")
        box.setText("What the button does for you:")
        box.setInformativeText(
            "\n".join(f"{n}.  {line}" for n, line
                       in enumerate(gsi_install.BY_HAND, 1))
            + "\n\nThen carry on from step 2. "
            + f"{gsi_install.LAUNCH_OPTION} is on your clipboard.")
        box.exec()

    def _gsi_config_installed(self) -> bool:
        """Is Dota's config file there? Cached — see `GSI_CONFIG_TTL`."""
        now = time.monotonic()
        if (self._gsi_config_seen is not None
                and now - self._gsi_config_asked < self.GSI_CONFIG_TTL):
            return self._gsi_config_seen
        from ..gsi import install as gsi_install
        try:
            path = (gsi_install.config_dir(gsi_install.find_dota_dir())
                    / gsi_install.CONFIG_NAME)
            answer = path.exists()
        except (gsi_install.DotaNotFound, OSError):
            answer = False
        self._gsi_config_seen = answer
        self._gsi_config_asked = now
        return answer

    def _forget_gsi_config(self) -> None:
        """Ask again next time. Called by everything that WRITES the
        config, since a cache that outlives the thing it describes is how
        a banner goes on reporting a fault that was just fixed."""
        self._gsi_config_seen = None

    def _install_gsi_from_banner(self) -> None:
        """The banner's button DOES the install rather than naming a menu.

        Pressing it is the agreement that Skip withheld, so it clears
        `setup_skipped` as well -- otherwise the config would be written
        once here and then never kept up to date.
        """
        pending = [k for k in (self.settings.get("setup_pending") or [])
                   if k != "gsi"]
        self.settings["setup_pending"] = pending
        ui_settings.save(self.settings)
        note = self._ensure_gsi_config()
        if note:
            self._say(note + " — now add the launch option in Steam.", 8000)
            self._launch_option_help()
        elif self._gsi_config_installed():
            # Already there, so the missing half is the one in Steam.
            self._launch_option_help()
        else:
            self._install_gsi()          # say WHY it could not be written
        self._update_first_run_banner()

    def offer_setup(self) -> None:
        """Show the wizard on a fresh install, once, after the window is up.

        AFTER `show()`: it is modal, and a modal dialog raised over a
        window that has not appeared yet is a dialog with nothing behind
        it. Skippable, so nobody offline or merely curious meets a wall —
        the banner is the way back and this asks again next start.
        """
        from .setup_wizard import needed
        if needed():
            self._run_setup()
            return
        # AND AN INSTALL THAT IS ALREADY PAST THE WIZARD STILL GETS THE
        # CONFIG. `needed()` asks about the KEY alone, so every existing
        # install -- including the one this app was written on -- skips
        # the wizard entirely and would never have had the file written
        # for it. This is the line that makes "GSI setup happens at
        # startup" true for them rather than only for a fresh unzip. It
        # writes nothing when the config is already right.
        note = self._ensure_gsi_config()
        if note:
            self._say(note, 6000)
        self._update_first_run_banner()

    def _stale_days(self) -> float:
        """How many days past the reminder the statistics are, or 0.

        THIS IS A BANNER NOW, not the startup dialog it used to be — at
        the user's request, and it is a REPLACEMENT rather than an
        addition. The age was once a banner, a pill on the tab row AND a
        segment of the status line, which is three copies of a number
        worth acting on twice a month; it was cut back to one dialog for
        that reason. A dialog you dismiss on the way to a draft is one you
        dismiss forever, though, and the thing it was asking about goes on
        being true. So it is one strip at the top, with the days on it and
        a button that fixes it — still exactly one place, still nothing at
        all until it matters.
        """
        days = ui_settings.clamp_days(
            self.settings.get("data_reminder_days"),
            ui_settings.DATA_REMINDER_DAYS)
        if not days or self.ds.is_empty:
            return 0.0
        try:
            age = self.ds.age_hours() / 24.0
        except Exception:
            return 0.0
        return age if age >= days else 0.0

    def _update_first_run_banner(self, snap=None) -> None:
        """The one strip at the top that says what is wrong RIGHT NOW.

        The game feed being dead is first, ahead of anything about the
        statistics, because it is the fault that costs a whole draft — and
        it used to be one segment of a pipe-separated status line at the
        bottom of the window, between the capture mode and how old the data
        is. "Where is the warning line" is a fair question about that.

        Only a fault the user can fix puts it up: Dota simply not being
        open is silence too, and a banner that is up all evening is one
        nobody reads on the night it matters.
        """
        if snap is not None and getattr(snap, "gsi_setup_broken", False):
            # THE BUTTON DOES THE HALF THAT IS OURS, which it used to
            # describe instead: "check game data should not jsut give an
            # error and instruct you to download game data... instead it
            # should just facilitate the installation directly". So the
            # strip asks which half is missing and offers that -- the
            # config file, which nobody has anything to decide about, or
            # the Steam launch option, which is the user's and gets the
            # procedure rather than its name.
            if not self._gsi_config_installed():
                self._show_banner(
                    "<b>Dota is not sending game data.</b> Its config "
                    "file has not been written yet.",
                    "Install it", self._install_gsi_from_banner)
                return
            self._show_banner(
                "<b>Dota is not sending game data.</b> Add "
                "-gamestateintegration to Dota's launch options in Steam, "
                "then restart Dota.",
                "Show me how", self._launch_option_help)
            return
        # THE CROP BOXES, second only to the feed, because between them
        # they are the two ways the app goes blind for a whole draft. This
        # is not a guess about recognition being unlucky: the game named
        # the ten heroes on screen and the calibrated boxes matched none of
        # them (`Snapshot.crop_boxes_wrong`). It was reported in the
        # recording's notes and nowhere else, so a real draft was read two
        # slots out of ten for eighty seconds with nothing on screen
        # saying why.
        #
        # AND THE BUTTON IS THE AUTOMATIC ROUTE, at the user's request —
        # "I thought the latest system is all automatic???". It is, and
        # this strip was the one place that did not say so: it sent them
        # to drag two rectangles over the client by hand, which is the
        # fallback for when measuring fails rather than the first thing to
        # try. The app can measure the boxes off this very frame, because
        # what raised the banner is exactly what measuring needs — a
        # picture of the bar with all ten heroes named by the game.
        if snap is not None and getattr(snap, "crop_boxes_wrong", False):
            self._show_banner(
                "<b>The app cannot find the pick portraits on your "
                "screen.</b> Picks will be read late or not at all until "
                "the crop boxes are measured.",
                "Measure the boxes", self._measure_from_banner)
            return
        # STEPS THE USER SKIPPED, named. "allow users to click 'skip
        # this step' and then there is a banner at the main menu for
        # outstanding steps" — so a skip is a decision to come back to
        # it rather than a decision to go without, and this strip is
        # what makes that true. It sits under the two faults that cost a
        # draft outright and above everything about the statistics,
        # because it is the one rung that names something the user
        # themselves put off.
        # The GSI step is left OFF this list even when it is pending:
        # its own rung above says the feed is silent, which is a
        # measurement rather than a memory of a button press, and two
        # strips about one thing is one of them going stale.
        outstanding = [k for k in (self.settings.get("setup_pending") or [])
                       if k != "gsi"]
        if outstanding:
            from .setup_wizard import STEPS
            names = [step.title.lower() for step in STEPS
                     if step.ident in outstanding]
            many = len(names) != 1
            self._show_banner(
                f"<b>Setup {'has' if many else 'has'} "
                f"{len(names)} step{'s' if many else ''} left.</b> "
                + ", ".join(names).capitalize() + ".",
                "Finish setup", self._run_setup)
            return
        # ARTWORK BEFORE STATISTICS, because it is the half that always
        # works. A fresh install has neither, and the statistics need a
        # free Stratz key the user has to go and get — so leading with
        # that leaves somebody staring at a grid of empty plates while
        # they sign up for something. The pictures need no account at all.
        if not portraits.any_downloaded():
            self._show_banner(
                "<b>No hero pictures yet.</b> They download to this "
                "machine and need no account.",
                "Get the artwork", lambda: self.run_task("fetch_assets"))
            return
        if self.ds.is_empty:
            self._show_banner(
                "<b>No statistics downloaded yet.</b> Every number in "
                "the app comes from these.",
                "Set up now", self._run_setup)
            return

        # THE BRACKET CHANGED. Checked before the age, because the numbers
        # on screen are the WRONG RANK rather than merely old — and the
        # user changes this in a dialog and comes straight back here, so
        # this strip is where they find out it needs a rebuild.
        mismatch = self._bracket_mismatch()
        if mismatch:
            cached, wanted = mismatch
            self._show_banner(
                f"<b>Rank bracket changed to {wanted}.</b> The numbers "
                f"below are still {cached}.",
                "Update now", self._update_everything)
            return

        # HOW OLD, and only past the reminder. Under it there is nothing
        # to say and the strip stays away entirely.
        stale = self._stale_days()
        if stale:
            self._show_banner(
                f"<b>Statistics were updated {stale:.0f} days ago.</b> "
                "They stop tracking the current patch.",
                "Update now", self._update_everything)
            return

        # SOME of the artwork, which is a different question from none of
        # it. `any_downloaded` goes true on the first download and stays
        # true, so a hero added in a patch has no picture and nothing
        # anywhere says so. Updating the app used to fetch the artwork as
        # its last step; at the user's request Update is now the code and
        # nothing else — seconds rather than minutes — so this strip is
        # what notices instead.
        # It is the LAST rung on purpose. A wrong rank bracket and stale
        # statistics are the ADVICE being wrong; a missing portrait is one
        # tile drawing blank, which is the least of the five. And it must
        # come after the "no statistics" rung either way: `missing_for`
        # reads an index that caches absence, and an empty dataset has no
        # hero list to compare against.
        absent = portraits.missing_for(self.ds.hero_ids)
        if absent:
            many = len(absent) != 1
            self._show_banner(
                f"<b>{len(absent)} hero picture{'s are' if many else ' is'} "
                "missing.</b> Usually a hero added in a patch.",
                "Get the artwork", lambda: self.run_task("fetch_assets"))
            return
        # THERE IS NO "THE PICK BOXES ARE NOT SET UP" RUNG ANY MORE. It
        # was the last one, and it asked for the one thing this app no
        # longer wants anybody to do by hand. With no calibration file
        # the boxes are `DraftLayout()`'s measured 16:9 fractions put
        # through `hud_box`, which is right at every resolution the sweep
        # could predict — and where it is not, the first strategy time of
        # the first match measures the real geometry and saves it. An
        # absent calibration file is therefore not a fault to report; a
        # measurement that could not be made is, and that is the crop-box
        # rung above.
        self.banner.setVisible(False)

    def _edit_rules(self) -> None:
        if sys.platform == "win32":
            os.startfile(RULES_FILE)  # noqa: S606
        else:
            subprocess.Popen(["xdg-open", str(RULES_FILE)])

    def _reload_rules(self) -> None:
        try:
            self.rules, self.rules_meta = items_mod.load_rules(RULES_FILE)
        except Exception as exc:
            QMessageBox.warning(self, "Item rules",
                                f"Could not load rules/items.yaml:\n\n{exc}")
            return
        self._refresh_views()
        self._say(f"Loaded {len(self.rules)} item rules", 5000)

    def _open_manual(self, section: str | bool = "") -> None:
        """The manual, built once and kept.

        `section` takes a bool as well as a name because QAction.triggered
        hands its slot a `checked` flag — a menu item wired straight to a
        method that takes an argument is a trap this app has fallen into
        before.

        Built once for the reason the settings window is: a second copy
        of a window is a second entry in the taskbar and a second thing
        to keep in step, and this one is opened and closed all day.
        """
        from .handbook import ManualWindow

        if getattr(self, "manual_window", None) is None:
            self.manual_window = ManualWindow(self)
        if section and isinstance(section, str):
            self.manual_window.show_section(section)
        else:
            self.manual_window.show()
            self.manual_window.raise_()
            self.manual_window.activateWindow()

    def _about(self) -> None:
        """WHAT THIS IS, not what it does.

        It used to be three paragraphs describing the product — what it
        reads, where the numbers come from, what it will not touch — all
        of which is the first page of the manual now. An About box
        answers "which one have I got, and who is it by", because that
        is the question somebody has when they open one.
        """
        from .. import version
        from . import appicon

        box = QMessageBox(self)
        box.setWindowTitle("About Dota Draft Assist")
        box.setIconPixmap(appicon.pixmap(64))
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(
            "<b style='font-size: 15px'>Dota Draft Assist</b><br>"
            f"Version {version.VERSION}<br>"
            f"<span style='color: {theme.TEXT_DIM}'>Build "
            f"{version.build()}</span>")
        box.setInformativeText(
            f"Python {platform.python_version()} · PyQt "
            f"{PYQT_VERSION_STR} · Qt {QT_VERSION_STR}<br>"
            f"{platform.system()} {platform.release()}<br><br>"
            "Personal-use software. Dota 2 is a trademark of Valve "
            "Corporation, which does not endorse this and has nothing to "
            "do with it.<br><br>"
            "Help ▸ User manual explains how it all works.")
        manual = box.addButton("User manual",
                               QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() is manual:
            self._open_manual()

    # ---- the window IS the overlay --------------------------------------
    def _set_see_through(self, opacity: float) -> None:
        """Opacity is the whole reason this can sit over a game at all."""
        self.settings["overlay_opacity"] = float(opacity)
        ui_settings.save(self.settings)
        self.setWindowOpacity(opacity)

    # ---- game data (GSI) ----------------------------------------------
    def _install_gsi(self) -> None:
        """Write the GSI config into the Dota install and say what is left
        to do — the launch option is the step everyone forgets."""
        from ..gsi import install as gsi_install

        port = getattr(getattr(self.provider, "server", None), "port",
                       gsi_install.DEFAULT_PORT)
        try:
            result = gsi_install.install(port=port)
        except gsi_install.DotaNotFound as exc:
            QMessageBox.warning(self, "Set up game data", str(exc))
            return
        except OSError as exc:
            QMessageBox.warning(
                self, "Set up game data",
                f"Could not write the config file:\n\n{exc}\n\n"
                "If Dota is installed somewhere protected, run the app once "
                "as administrator, or copy the config in by hand.")
            return

        server = getattr(self.provider, "server", None)
        if server is not None:
            server.token = result.token
        self._forget_gsi_config()

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Set up game data")
        box.setText("Game State Integration is installed."
                    if result.created else
                    "Game State Integration was already installed.")
        # THE SAME SEVEN STEPS THE WIZARD AND THE BANNER SHOW. This box
        # used to carry its own three-line abbreviation of them, which is
        # one more place for the procedure to go stale -- and the shorter
        # telling was missing the two things people actually get wrong:
        # that an existing launch option must be kept, and that Steam has
        # no OK button.
        box.setInformativeText(
            "One more step, and it is yours -- no program can set it for "
            "you:\n\n"
            + "\n".join(f"{n}.  {step}" for n, step
                        in enumerate(gsi_install.LAUNCH_STEPS, 1)))
        box.setDetailedText(
            f"Config written to:\n{result.config_path}\n\n"
            f"Dota install:\n{result.dota_dir}\n\n"
            f"Listening on 127.0.0.1:{result.port}\n\n"
            "GSI is Valve's own feature: Dota sends this data because the "
            "config asks it to. Nothing is injected into the game and no "
            "memory is read.")
        # This box appears at the exact moment somebody would go and do
        # the Steam step, so it offers to take them there.
        steam = box.addButton(gsi_install.COPY_AND_OPEN,
                              QMessageBox.ButtonRole.ActionRole)
        box.exec()
        if box.clickedButton() is steam:
            self._copy_and_open_steam()

    def _diagnose_gsi(self) -> None:
        """Test each GSI requirement separately.

        Every broken link produces the same symptom — silence — so guessing
        is expensive. This names the failing step instead."""
        from ..gsi import diagnose

        server = getattr(self.provider, "server", None)
        if server is not None:
            # Let the diagnostic see a failed bind, which otherwise looks
            # identical to Dota simply not sending anything.
            server._bind_error = getattr(self.provider, "bind_error", "")
        checks = diagnose.run_checks(server=server)
        report = diagnose.format_report(checks)
        failing = [c for c in checks if c.ok is False]

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning if failing
                    else QMessageBox.Icon.Information)
        box.setWindowTitle("Diagnose game data")
        box.setDetailedText(report)

        def render() -> None:
            """Re-run while the dialog is open. A point-in-time result goes
            stale the moment a draft starts, and a stale 'no payloads' next
            to a working overlay is worse than no diagnostic at all."""
            live = diagnose.run_checks(server=server)
            bad = [c for c in live if c.ok is False]
            box.setText(diagnose.headline(live))
            box.setInformativeText(
                (bad[0].fix or bad[0].detail) if bad else
                "Dota only sends game data while you are in a match — "
                "including the draft. The main menu sends nothing.")
            box.setDetailedText(diagnose.format_report(live))

        render()
        ticker = QTimer(box)
        ticker.timeout.connect(render)
        ticker.start(1000)
        box.exec()
        ticker.stop()

    def _swap_provider(self, provider) -> None:
        try:
            self.provider.stop()
        except Exception:
            pass
        self.provider = provider
        self.last_draft_key = None
        message = provider.start()
        self._say(message, 8000)
        self._refresh_sources()
        self._sync_source_controls()

    def _sync_source_controls(self) -> None:
        """Only show capture controls when pixels are actually the source;
        under game data there is no gate to force and no window to bind."""
        is_capture = hasattr(self.provider, "session")
        for widget in (self.force_check,):
            widget.setVisible(is_capture)
        self.force_action.setEnabled(is_capture)
        for widget in (self.source_combo, self.refresh_sources_button,
                       self.bind_button):
            widget.setEnabled(is_capture
                              and hasattr(self.provider, "available_sources"))

    def _clear_manual(self) -> None:
        self.manual.clear()
        self.last_draft_key = None
        self._say("Cleared hand-entered draft slots", 5000)

    # WHAT THE DRAFT TAB MAY BE CUT DOWN TO, at the user's request: "i
    # want to be able to tick on/off all the subheaders, except for the
    # top 5 / 5 portraits - as that is the main part of the app". Each
    # entry is a setting, the words on the tick box, and the attribute
    # holding the whole block — heading and all, since "if the user
    # unticks them the headers should hide away".
    #
    # THE TEN PICKS ARE NOT ON THIS LIST and must not be added to it.
    # Everything here is ADVICE ABOUT the board; the board itself is
    # what the app is, and a tick box that empties the window is not a
    # setting anybody wants to find by accident.
    #
    # IN THE VIEW MENU rather than Settings ▸ Appearance, also at the
    # user's request — "maybe its best to go in the view dropdown menu
    # and have a tick box on it". It is the same argument the mark
    # counts were moved on: a control you work by looking at the result
    # belongs beside the result, not two menus away.
    SECTIONS = (
        ("show_roles", "Team roles", "roles_block"),
        ("show_suggestions", "Top picks", "picks_card"),
        ("show_items", "Suggested items", "items_card"),
        ("show_matrices", "Synergies and counters", "grids_block"),
    )

    def _add_section_menu(self) -> None:
        """A tick box per block of the Draft tab."""
        self.view_menu.addSeparator()
        self.section_actions = {}
        for key, label, _attr in self.SECTIONS:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(bool(self.settings.get(key, True)))
            act.toggled.connect(
                lambda on, k=key: self._set_section(k, on))
            self.view_menu.addAction(act)
            self.section_actions[key] = act
        self._apply_sections()

        # GREYSCALE, on its own below the blocks, because it is not one
        # of them: those four say what is ON the Draft tab, this says how
        # the whole app looks. Its own separator keeps the two questions
        # apart in a menu that is read at a glance.
        self.view_menu.addSeparator()
        self.greyscale_action = QAction("Greyscale", self)
        self.greyscale_action.setCheckable(True)
        self.greyscale_action.setChecked(bool(self.settings.get("greyscale")))
        self.greyscale_action.toggled.connect(self._set_greyscale)
        self.view_menu.addAction(self.greyscale_action)

    def _set_greyscale(self, on: bool) -> None:
        if bool(self.settings.get("greyscale")) == bool(on):
            return
        self.settings["greyscale"] = bool(on)
        ui_settings.save(self.settings)
        self._apply_greyscale()

    def _apply_greyscale(self, rebuild: bool = True) -> None:
        """Swap the palette and the artwork together, then redraw.

        `rebuild=False` FROM `__init__`, and it is not an optimisation.
        `_refresh_views` runs the whole draw — the strips, the relations
        and both grids — and from inside the constructor it reaches
        `tables.set_focus` on grids that are built but not yet laid out.
        That SEGFAULTS: Qt aborts rather than raising, so there is no
        traceback into our own code, and it only shows up in about one
        run in fifteen because it depends on what the layout has got
        round to. Caught by running the suite thirty times, not by a
        test. Nothing is lost by skipping it there — the first paint is
        about to draw everything anyway.

        BOTH HALVES OR NEITHER. The stylesheet covers every widget Qt
        draws, and the hero portraits and item icons are pixmaps painted
        by us — greying only the first leaves full-colour faces on a grey
        screen, which is most of the window still in colour.

        IDEMPOTENT, and called from `_apply_settings` as well as from the
        menu, so a hand-edited settings file and a click arrive at the
        same place.

        The caches are dropped rather than converted in place: a portrait
        is greyed once as it is loaded, so the way to change the answer
        is to make it be loaded again. That also picks up the scaled
        copies, which are keyed by size and know nothing about colour.
        """
        from . import item_icons, item_row as item_row_mod

        want = bool(self.settings.get("greyscale"))
        theme.set_greyscale(want)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(theme.STYLESHEET)
        portraits.forget()
        item_row_mod.forget_scaled()
        for forget in (getattr(item_icons, "forget", None),
                       getattr(item_icons, "forget_scaled", None)):
            if callable(forget):
                forget()
        if getattr(self, "greyscale_action", None) is not None:
            # Setting a control to what the file already says is not the
            # user pressing it, and unblocked it would write the settings
            # file on every start.
            self.greyscale_action.blockSignals(True)
            self.greyscale_action.setChecked(want)
            self.greyscale_action.blockSignals(False)
        if rebuild and getattr(self, "suggest_row", None) is not None:
            self._refresh_views()
        self.update()

    def _set_section(self, key: str, shown: bool) -> None:
        """Remember a tick and redraw. Written through `ui_settings.save`
        like every other preference — `DEFAULTS` is the write filter, so
        each of these four has an entry there or it would be kept for the
        session and dropped on the way to disk."""
        if bool(self.settings.get(key)) == bool(shown):
            return
        self.settings[key] = bool(shown)
        ui_settings.save(self.settings)
        self._apply_sections()

    def _apply_sections(self) -> None:
        """Show or hide each block, and keep the ticks in step with it.

        IDEMPOTENT, and called from `_apply_settings` as well as from the
        menu: a settings file edited by hand, or a window built before
        the menu existed, must arrive at the same place as a click.
        `blockSignals` while a tick is corrected, since setting a control
        to what the file already says is not the user pressing it — and
        unblocked it would write the settings file on every start, which
        is the fault `TitleBar.set_pinned` carries the same guard for.
        """
        for key, _label, attr in self.SECTIONS:
            shown = bool(self.settings.get(key, True))
            block = getattr(self, attr, None)
            # A SECTION MAY BE SEVERAL WIDGETS. The roles are one block
            # to the reader and two widgets in two cards, one per side,
            # since the picks and the pills for a side share a card now.
            for widget in (block if isinstance(block, (list, tuple))
                           else [block] if block is not None else []):
                widget.setVisible(shown)
            act = getattr(self, "section_actions", {}).get(key)
            if act is not None and act.isChecked() != shown:
                act.blockSignals(True)
                act.setChecked(shown)
                act.blockSignals(False)

    def _show_profile(self) -> None:
        """Drop the account detail under the button that was clicked.

        A QMenu because that is what a drop-down IS on every platform —
        it closes on a click outside, it is positioned against the
        widget rather than the screen, and it takes the app's own
        stylesheet. The row inside it is the same `AccountRow` the Draft
        tab used to carry, so there is one implementation of the detail
        and it cannot drift from the button's name.

        BUILT ONCE AND KEPT, which is not an optimisation. A
        QWidgetAction owns its widget, so a menu built per click would
        destroy the row on the way out — and `show_report` would then be
        writing into a destroyed C++ object behind a live Python
        wrapper, which is the fault `history_tab.fill()` carries its own
        note about. Handing the row back with `setParent(None)` instead
        is worse again: a parentless QWidget is a WINDOW the moment
        anything shows it, and this app has opened a stray second
        "Dota Draft Assist" that way three times.
        """
        # Under the button, so the callout hangs off the thing that
        # opened it rather than appearing at the cursor.
        self._profile_menu.exec(self.profile_button.mapToGlobal(
            self.profile_button.rect().bottomLeft()))

    def _build_profile_menu(self) -> None:
        """Built at construction, not on the first click.

        Lazily was the obvious way and it is wrong here: until the menu
        exists the row has NO PARENT, and a parentless QWidget is a
        WINDOW the moment anything shows it — which is how this app has
        opened a stray second "Dota Draft Assist" three times, and why
        `test_no_widget_is_left_without_a_parent` walks these attributes.
        """
        from PyQt6.QtWidgets import QMenu, QWidgetAction

        menu = QMenu(self)
        action = QWidgetAction(menu)
        self.account_row.setParent(menu)
        action.setDefaultWidget(self.account_row)
        menu.addAction(action)
        menu.addSeparator()
        menu.addAction("Open the History tab").triggered.connect(
            self._show_history_tab)
        self._profile_menu = menu

    def _add_run_menu(self) -> None:
        """Run: the two recording controls, in a menu of their own.

        At the user's request — "move the auto + tickbox + record button
        into a new menu header called run". They were the first two
        things on the tab row, and the row is read mid-draft: Clear all
        and Detect all are pressed while a draft is going wrong, where
        recording is set once an evening and left.

        THEY ARE THE SAME TWO WIDGETS, in a `QWidgetAction` — the route
        Transparency and Sizes already take. A checkable menu item would
        have been more menu-like and would have cost the round red dot,
        which is the one thing on screen that says at a glance whether a
        session is running; and `RecordButton` would have become dead
        code, which this app deletes rather than leaves to be read as
        documentation later.

        INSERTED BEFORE View rather than appended, so the bar reads
        File | Run | View | Help — what the app IS doing, then how it
        looks, then help.
        """
        from PyQt6.QtWidgets import QMenu, QWidgetAction

        menu = QMenu("&Run", self)
        self.menu_bar.insertMenu(self.view_menu.menuAction(), menu)
        self.run_menu = menu
        for widget, label, tip in (
                (self.record_button, "Record this draft",
                 "Start or stop a recording now"),
                (self.auto_record_check, "Record every draft",
                 "Start by itself when Dota reaches the draft")):
            row = QWidget(menu)
            row.setProperty("bare", True)
            lay = QHBoxLayout(row)
            lay.setContentsMargins(14, 6, 14, 6)
            lay.setSpacing(10)
            # THE WIDGET KEEPS ITS PARENT WHEN IT MOVES. A parentless
            # QWidget is a WINDOW the moment anything shows it, and these
            # two have just been taken off a layout.
            widget.setParent(row)
            lay.addWidget(widget)
            name = QLabel(label, row)
            lay.addWidget(name, 1)
            row.setToolTip(tip)
            action = QWidgetAction(menu)
            action.setDefaultWidget(row)
            menu.addAction(action)

    def _add_transparency_menu(self) -> None:
        """View ▸ Transparency: the same slider, in a menu.

        A submenu of fixed percentages would have been more menu-like and
        worse: this is a value tuned by eye against a running game, a few
        percent at a time, so it stays a slider. A `QWidgetAction` is how a
        real widget goes in a menu, and the menu stays open while the
        handle is dragged, which is the whole point.
        """
        from PyQt6.QtWidgets import QWidgetAction

        menu = self.view_menu.addMenu("&Transparency")
        row = QWidget(menu)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(14, 6, 14, 6)
        lay.setSpacing(10)
        # Parented from the start: a parentless QWidget is a WINDOW the
        # moment anything shows it, and this one is built long before the
        # menu is ever opened.
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal, row)
        self.opacity_slider.setFixedWidth(140)
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.setToolTip(
            "How much of Dota shows through this window")
        self.opacity_slider.setValue(
            int(float(self.settings.get("overlay_opacity", 0.7)) * 100))
        self.opacity_readout = QLabel("", row)
        self.opacity_readout.setMinimumWidth(46)
        self.opacity_slider.valueChanged.connect(self._on_opacity_moved)
        lay.addWidget(self.opacity_slider)
        lay.addWidget(self.opacity_readout)
        holder = QWidgetAction(menu)
        holder.setDefaultWidget(row)
        menu.addAction(holder)
        self.transparency_menu = menu
        self._show_opacity(self.opacity_slider.value())
        # At the TOP of View: it is the one thing in there anybody opens
        # the menu for.
        first = self.view_menu.actions()[0]
        if first is not menu.menuAction():
            self.view_menu.removeAction(menu.menuAction())
            self.view_menu.insertMenu(first, menu)
            self.view_menu.insertSeparator(first)

    def _add_sizes_menu(self) -> None:
        """View ▸ Sizes: how big the pictures and the numbers are.

        Two sliders in one submenu because they are one question asked
        twice, and sliders rather than a list of percentages for the same
        reason Transparency is one — this is tuned by eye against the
        window, a few percent at a time, and the menu stays open while the
        handle moves.

        They set the BASE, not the behaviour: a portrait still grows and
        shrinks with the window between its own floor and this cap, so
        "size dynamically, but from a base I choose" is exactly what the
        controls do.
        """
        from PyQt6.QtWidgets import QWidgetAction

        menu = self.view_menu.addMenu("&Sizes")
        self.size_sliders = {}
        for key, label, apply in (
                ("portrait_scale", "Portraits", self._set_portrait_scale),
                ("number_scale", "Numbers", self._set_number_scale)):
            row = QWidget(menu)
            lay = QHBoxLayout(row)
            lay.setContentsMargins(14, 6, 14, 6)
            lay.setSpacing(10)
            name = QLabel(label, row)
            name.setMinimumWidth(78)
            slider = QSlider(Qt.Orientation.Horizontal, row)
            slider.setFixedWidth(140)
            # 25 to 175, CENTRED ON 100 — see `teams.SCALE_MIN`. The
            # two ends are the module's own clamps rather than numbers
            # repeated here, or a slider could offer a value the code
            # behind it silently refuses.
            slider.setRange(round(teams.SCALE_MIN * 100),
                            round(teams.SCALE_MAX * 100))
            slider.setValue(int(float(self.settings.get(key, 1.0)) * 100))
            readout = QLabel("", row)
            readout.setMinimumWidth(46)
            slider.valueChanged.connect(
                lambda value, k=key, r=readout, f=apply: (
                    r.setText(f"{value}%"), f(value / 100.0)))
            readout.setText(f"{slider.value()}%")
            lay.addWidget(name)
            lay.addWidget(slider)
            lay.addWidget(readout)
            holder = QWidgetAction(menu)
            holder.setDefaultWidget(row)
            menu.addAction(holder)
            self.size_sliders[key] = slider
        self.sizes_menu = menu

    def _set_portrait_scale(self, factor: float) -> None:
        """Every portrait in the app, from the pick tiles outwards.

        Only the PANELS are told: they decide the box for the whole app,
        and the strips and the grids follow the signal they raise — which
        is the same path a window drag takes, so there is one way for a
        tile to change size rather than two.
        """
        teams.set_scale(factor)
        self.settings["portrait_scale"] = teams.SCALE
        for panel in self.team_panels.values():
            panel.rescale()
        ui_settings.save(self.settings)

    def _set_number_scale(self, factor: float) -> None:
        """Every signed number in the app, in one multiplier.

        A REPAINT, not a rebuild: nothing about the layout changes when a
        number gets bigger — it is drawn over a tile that is already the
        right size — and rebuilding the strips on every step of a slider
        drag would be scoring the whole draft a hundred times to change a
        font size.
        """
        tilekit.set_scale(factor)
        self.settings["number_scale"] = tilekit.SCALE
        self.update()
        # The grids paint through a delegate into a viewport of their own,
        # which the window's repaint does not reach.
        for grid in (self.synergy_matrix, self.matchup_matrix):
            grid.table.viewport().update()
            grid.table.horizontalHeader().viewport().update()
        ui_settings.save(self.settings)

    def _on_opacity_moved(self, value: int) -> None:
        self._show_opacity(value)
        self._set_see_through(value / 100.0)

    def _show_opacity(self, value: int) -> None:
        self.opacity_readout.setText(f"{value}%")

    def _capture_session(self):
        """The live capture session, whichever provider is wrapping it."""
        vision = getattr(self.provider, "vision", self.provider)
        return getattr(vision, "session", None)

    def _clear_all(self) -> None:
        """Back to an empty board in one press.

        Everything the user has told the app about THIS match goes: the
        hand-entered slots, the side corrections, the dragged order, which
        hero is theirs. Correcting a bad reading one pick at a time is five
        right-clicks and a picker each, and when the whole board is wrong
        that is the long way round to a clean slate.
        """
        self.manual.clear()
        self.side_overrides.clear()
        self.slot_order = {"ally": [], "enemy": []}
        self.my_hero_id = None
        self.my_hero_locked = False
        self.focus = None
        session = self._capture_session()
        if session is not None:
            # Otherwise the screen's own last reading survives the wipe and
            # the board fills straight back in.
            session.detect_now()
        # And the GAME's reading survives it too — precedence is game >
        # hand entry, so on a live match wiping the manual slots changed
        # nothing at all on screen. Remember the board being cleared and
        # blank it until there is something different to show.
        self._cleared = (self._board_key(self.snapshot)
                         if self.snapshot is not None else None)
        self.last_draft_key = None
        self._say(
            "Board cleared — it fills again when the draft changes, or "
            "press Detect all", 8000)
        self.refresh()

    def _demo_draft(self) -> None:
        """Ten random heroes on the board, in one press.

        It goes in through HAND ENTRY rather than through a fake game feed:
        the two "Simulate a draft" menu items each started a subprocess
        posting invented payloads at the real GSI listener and left it
        running, which is a second moving part to answer "show me what a
        full board looks like". This writes the manual slots, so Clear all
        empties it again and nothing outlives the press.
        """
        pool = [h for h in self.ds.hero_ids if h not in self._taken_heroes()]
        if len(pool) < 10:
            self._say("Not enough heroes for a demo draft — is the data "
                      "downloaded?", 8000)
            return
        picked = random.sample(pool, 10)
        for index, hero in enumerate(picked[:5]):
            self.manual.set_slot("ally", index, hero)
        for index, hero in enumerate(picked[5:]):
            self.manual.set_slot("enemy", index, hero)
        self.my_hero_id = picked[0]
        self.last_draft_key = None
        self.refresh()
        self._say("Demo draft — Clear all empties it", 6000)

    def _detect_all(self) -> None:
        """Read all ten portraits off the Dota window, now.

        A ONE-SHOT rather than the Force recognition switch: "re-read the
        board" is something you press once. It forgets the previous
        reading first, because the reason for pressing it is that the
        board on screen and the board in the app disagree — and the
        stabiliser would otherwise let the old answer outvote the new
        frame for another few ticks.
        """
        # FIRST, whatever happens next: asking to see the board again
        # cancels the blanking Clear all put on it. The two buttons are a
        # pair and this is the way out of the first, so it must not depend
        # on there being a capture session to read from — otherwise a
        # cleared board in game-data-only mode has no way back.
        self._cleared = None
        session = self._capture_session()
        if session is None:
            self.last_draft_key = None
            self._say(
                "Nothing to read from — screen capture is off (Settings ▸ "
                "Read the draft from the Dota window)", 8000)
            self.refresh()
            return
        session.detect_now()
        self.last_draft_key = None
        self._say(
            f"Re-reading the draft from {self._capture_target()}", 5000)
        self.refresh()

    def _gsi_server(self):
        """The live listener, whichever provider is wrapping it."""
        provider = self.provider
        server = getattr(provider, "server", None)
        if server is None:
            server = getattr(getattr(provider, "gsi", None), "server", None)
        return server

    def _set_auto_record(self, on: bool) -> None:
        self.settings["auto_record"] = bool(on)
        ui_settings.save(self.settings)
        self._auto_blocked = False
        self._update_record_button()

    def _toggle_recording(self) -> None:
        if self.recorder.active:
            # Stopping by hand mid-draft must mean stopping, not stopping
            # for one tick — otherwise auto would restart it immediately.
            self._auto_blocked = record_mod.is_drafting(
                getattr(self.snapshot, "game_state", ""))
            self._stop_recording("stopped by hand")
        else:
            self._start_recording()

    def _consider_auto_record(self, snap) -> None:
        """Start a session by itself when the game reaches the draft.

        The recording you most want is the one you were not expecting, and
        pressing Record before queueing is exactly the thing that gets
        forgotten. Stopping is already automatic, so this closes the loop:
        the app is either open or it is not.
        """
        drafting = record_mod.is_drafting(getattr(snap, "game_state", ""))
        if not drafting:
            self._auto_blocked = False       # re-arm for the next match
            return
        if self.recorder.active or self._auto_blocked:
            return
        if not self.auto_record_check.isChecked():
            return
        self._start_recording(automatic=True)

    def _start_recording(self, automatic: bool = False) -> None:
        """One button, everything: payloads, frames and the app's reading.

        Each press opens its own folder. Recording never appends to an
        earlier session — pooling two matches made every count in the
        report meaningless, and was what most confused reading the
        evidence.
        """
        try:
            folder = self.recorder.start()
        except OSError as exc:
            QMessageBox.warning(self, "Record",
                                f"Could not start recording:\n\n{exc}")
            return
        server = self._gsi_server()
        if server is not None:
            server.set_archive_dir(self.recorder.gsi_dir)
        self._update_record_button()
        self._say(
            ("Draft detected — recording to " if automatic
             else "Recording to ") + folder.name, 8000)

    def _stop_recording(self, reason: str = "") -> None:
        server = self._gsi_server()
        if server is not None:
            server.set_archive_dir(None)
        frames, states = self.recorder.frames, self.recorder.states
        folder = self.recorder.stop(reason)
        self._update_record_button()
        if folder is None:
            return
        payloads = len(list((folder / "gsi").glob("gsi_*.json")))
        self._refresh_sessions()
        self._say(
            f"Saved {folder.name}: {payloads} payloads, {frames} frames, "
            f"{states} states" + (f" — {reason}" if reason else ""), 15000)

    def _update_record_button(self) -> None:
        recording = self.recorder.active
        self.record_button.set_recording(recording)
        if not recording:
            self.recording_label.setText(
                "auto — waiting for a draft"
                if self.auto_record_check.isChecked() else "")

    def _capture_recording(self, snap, allies, enemies) -> None:
        """Called every tick while recording, and does the whole job on its
        own: the state log, a frame every couple of seconds, and ending the
        session once the draft is over. Nothing here needs a keypress.

        A failed write must never interrupt a draft, so the recorder
        swallows them and reports them in the session's meta.json.
        """
        if not self.recorder.active:
            return
        self.recorder.log_state(
            record_mod.snapshot_record(snap, allies, enemies, self.ds))
        if self.recorder.wants_frame():
            frame = snap.frame
            if frame is None:
                try:
                    frame = self._grab_dota_frame()
                except Exception:
                    frame = None      # Dota closed, or capture unavailable
            self.recorder.save_frame(frame)

        reason = self.recorder.observe(snap.game_state)
        if reason:
            self._stop_recording(reason)
            return

        seconds = int(self.recorder.elapsed)
        payloads = getattr(snap, "frames_arrived", 0)
        countdown = self.recorder.auto_stop_in
        tail = (f"  ·  auto-stop in {countdown:.0f}s" if countdown
                else "  ·  auto-stops after the draft")
        self.recording_label.setText(
            f"REC {seconds // 60}:{seconds % 60:02d}  ·  {payloads} payloads "
            f"·  {self.recorder.frames} frames{tail}")

    # -- quick keyboard entry --------------------------------------------

    def _slot_menu(self, side: str, index: int, pos) -> None:
        """Right-click: change the hero, clear it, or give the slot a role.

        Roles live on the slot rather than on the hero because a slot is
        what a lane is: the same hero in a different game is a different
        position.
        """
        from PyQt6.QtWidgets import QMenu

        button = self.team_buttons[side][index]
        menu = QMenu(self)
        menu.addAction("Change hero…").triggered.connect(
            lambda: self._edit_slot(side, index))
        clear = menu.addAction("Clear slot")
        clear.setEnabled(button.property("hero_id") is not None)
        clear.triggered.connect(lambda: self._clear_slot(side, index))
        move = menu.addAction("Move to the other team")
        move.setToolTip("Exchanges with the hero opposite, keeping 5v5")
        move.setEnabled(button.property("hero_id") is not None)
        move.triggered.connect(lambda: self._move_hero(side, index))

        hero_id = button.property("hero_id")
        menu.addSeparator()
        mine = menu.addAction("This is my pick")
        mine.setCheckable(True)
        mine.setChecked(hero_id is not None and hero_id == self.my_hero_id)
        mine.setEnabled(hero_id is not None and side == "ally")
        mine.setToolTip("Item advice keys off your own hero once it is set")
        mine.triggered.connect(
            lambda checked: self._set_my_hero(hero_id if checked else None))
        locked = menu.addAction("Locked in")
        locked.setCheckable(True)
        locked.setChecked(self.my_hero_locked)
        locked.setEnabled(hero_id is not None and hero_id == self.my_hero_id)
        locked.triggered.connect(self._set_my_hero_locked)

        role_menu = menu.addMenu("Role")
        for label in ("Pos 1", "Pos 2", "Pos 3", "Pos 4", "Pos 5"):
            action = role_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self.slot_roles[side][index] == label)
            action.triggered.connect(
                lambda _checked, name=label:
                    self._set_slot_role(side, index, name))
        role_menu.addSeparator()
        role_menu.addAction("No role").triggered.connect(
            lambda: self._set_slot_role(side, index, None))
        menu.exec(button.mapToGlobal(pos))

    def _set_my_hero(self, hero_id: int | None) -> None:
        self.my_hero_id = hero_id
        if hero_id is None:
            self.my_hero_locked = False
        self._say(
            f"Your pick: {self.ds.name(hero_id)}" if hero_id is not None
            else "Your pick cleared", 5000)
        self._refresh_views()

    def _set_my_hero_locked(self, locked: bool) -> None:
        self.my_hero_locked = bool(locked)
        self._refresh_views()

    def _move_hero(self, side: str, index: int) -> None:
        """Put one hero on the other team.

        Swap teams fixes a whole line-up read the wrong way round; this
        fixes one hero. Both exist because the minimap gives ten heroes
        without reliably saying whose they are, and being able to correct
        the app in a click beats it insisting on a guess.
        """
        other = "enemy" if side == "ally" else "ally"
        hero_id = self.team_buttons[side][index].property("hero_id")
        if hero_id is None:
            return
        # An EXCHANGE, not a one-way move: a 5v5 cannot become 4v6, and if
        # one hero is on the wrong side its opposite number usually is too.
        partner = self.team_buttons[other][index].property("hero_id")
        self.side_overrides[hero_id] = other
        if partner is not None:
            self.side_overrides[partner] = side
        self.last_draft_key = None
        message = f"{self.ds.name(hero_id)} moved to the other team"
        if partner is not None:
            message = (f"{self.ds.name(hero_id)} and "
                       f"{self.ds.name(partner)} exchanged teams")
        self._say(message, 6000)
        self.refresh()

    def _on_slot_dropped(self, from_side: str, from_index: int,
                         to_side: str, to_index: int) -> None:
        """Drag one pick onto another.

        Across teams it EXCHANGES the two, because a 5v5 cannot become 4v6
        and a hero on the wrong side almost always has an opposite number
        in the same boat. Within a team it swaps their two positions, which
        is how the order is put right when the feed's order is not the
        screen's.
        """
        moved = self.team_buttons[from_side][from_index].property("hero_id")
        if moved is None:
            return
        landed = self.team_buttons[to_side][to_index].property("hero_id")
        if from_side == to_side:
            self._swap_positions(from_side, moved, landed)
            return
        self.side_overrides[moved] = to_side
        if landed is not None:
            self.side_overrides[landed] = from_side
        self.last_draft_key = None
        self._say(
            f"{self.ds.name(moved)} and {self.ds.name(landed)} exchanged "
            "teams" if landed is not None
            else f"{self.ds.name(moved)} moved to the other team", 6000)
        self.refresh()

    def _swap_positions(self, side: str, moved: int,
                        landed: int | None) -> None:
        """Two picks change places within their own bank.

        The order matters because it is meant to be the order on Dota's
        pick bar, and the game's feed does not reliably give that. Stored
        as an explicit list for the match rather than as a permutation, so
        a reading that changes underneath it degrades gracefully.
        """
        if landed is None or landed == moved:
            return
        allies, enemies = self._sides(self.snapshot)
        current = list(allies if side == "ally" else enemies)
        if moved not in current or landed not in current:
            return
        i, j = current.index(moved), current.index(landed)
        current[i], current[j] = current[j], current[i]
        self.slot_order[side] = current
        self.last_draft_key = None
        self._say(
            f"{self.ds.name(moved)} and {self.ds.name(landed)} swapped "
            "places", 5000)
        self.refresh()

    def _set_slot_role(self, side: str, index: int, role: str | None) -> None:
        self.slot_roles[side][index] = role
        self.last_draft_key = None
        self.refresh()

    def _clear_slot(self, side: str, index: int) -> None:
        """Remove the hero THIS TILE is showing.

        By the hero, never by the position: `manual.entered` drops the
        empties and `merge` puts the game's picks in front, so the third
        tile on screen is not `manual.allies[2]`. Clearing by index cleared
        a slot that was already empty and the hero stayed on screen.
        """
        hero_id = self.team_buttons[side][index].property("hero_id")
        if hero_id is None:
            return
        if not self.manual.replace(side, hero_id, None):
            # The GAME put it there, so removing it here would not stick —
            # the next payload brings it straight back. Say so rather than
            # doing nothing, which is indistinguishable from being broken.
            self._say(
                f"{self.ds.name(hero_id)} came from the game, not from hand "
                "entry — it cannot be cleared here", 6000)
            return
        self.last_draft_key = None
        self.refresh()

    def _taken_heroes(self) -> set[int]:
        """Every hero already in the draft, either side.

        A hero cannot be in two slots — not on both teams and not twice on
        one — so every entry point filters against this rather than each
        checking its own corner.
        """
        taken = set(self.manual.entered("ally")) | set(
            self.manual.entered("enemy"))
        snap = self.snapshot
        # A BLANKED board does not reserve the heroes it is hiding. After
        # Clear all the picker would otherwise refuse every one of the ten
        # the game is still reporting — which is most of the heroes you
        # would want to type back in.
        if snap is not None and not self._is_cleared(snap):
            taken |= set(snap.left) | set(snap.right)
        return taken

    def _taken_where(self) -> dict[int, str]:
        """The same set, each hero carrying WHICH SIDE already holds it.

        The picker draws this on the row it refuses, because a hero
        silently missing from the list reads as a hero the app does not
        know: "I typed in his name to manually add him and I couldn't
        find [him]", about a hero who was on the board at the time.
        Naming the side is what makes it actionable - that is the tile to
        go and right-click.
        """
        taken = self._taken_heroes()
        mine = set(self.manual.entered("ally"))
        theirs = set(self.manual.entered("enemy"))
        snap = self.snapshot
        if snap is not None and not self._is_cleared(snap):
            mine |= set(snap.left)
            theirs |= set(snap.right)
        where = {}
        for hero_id in taken:
            if hero_id in mine:
                where[hero_id] = "already on your team"
            elif hero_id in theirs:
                where[hero_id] = "already on the enemy team"
            else:
                where[hero_id] = hero_picker.IN_DRAFT
        return where

    def resolve_hero(self, text: str, exclude: set[int] | None = None):
        """Text a user typed under time pressure -> hero id, or None.

        Exact name wins, then a prefix, then a word start, then anything
        containing it — and an ambiguous prefix is NOT resolved, because
        silently entering the wrong hero is worse than entering none.
        """
        needle = " ".join(text.split()).lower()
        if not needle:
            return None
        exclude = exclude or set()
        pool = [(hid, self.ds.name(hid)) for hid in self.ds.hero_ids
                if hid not in exclude]
        for hid, name in pool:
            if name.lower() == needle:
                return hid
        for match in (lambda n: n.startswith(needle),
                      lambda n: any(w.startswith(needle) for w in n.split()),
                      lambda n: needle in n):
            hits = [hid for hid, name in pool if match(name.lower())]
            if len(hits) == 1:
                return hits[0]
            if hits:
                return None          # ambiguous: make the user type more
        return None

    def _edit_slot(self, side: str, index: int) -> None:
        """Fill, change or clear a draft slot by hand."""
        if self.ds.is_empty:
            QMessageBox.information(
                self, "Choose hero",
                "Download the hero data first: Settings ▸ Downloads ▸ Statistics and portraits.")
            return
        taken = self._taken_where()
        # WHAT THE TILE IS SHOWING, not `manual.allies[index]`: the two are
        # different lists (see `_clear_slot`), so editing by index opened
        # the picker on the wrong hero and then wrote the answer into an
        # empty slot — which put the new hero on the board BESIDE the one
        # being changed instead of in place of it.
        current = self.team_buttons[side][index].property("hero_id")
        caption = ("Your team" if side == "ally" else "Enemy team")
        dialog = HeroPickerDialog(self.ds, taken=taken, current=current,
                                  title=f"{caption} — slot {index + 1}",
                                  parent=self)
        if dialog.exec() != HeroPickerDialog.DialogCode.Accepted:
            return
        chosen = None if dialog.cleared else dialog.selected
        if not self.manual.replace(side, current, chosen):
            if current is not None:
                self._say(
                    f"{self.ds.name(current)} came from the game, not from "
                    "hand entry — it cannot be changed here", 6000)
                return
            free = self.manual.first_free(side)
            if free is None:
                self._say(
                    "All five hand-entered slots on that side are full — "
                    "clear one first", 6000)
                return
            self.manual.set_slot(side, free, chosen)
        self.last_draft_key = None
        # The strips and the tiles are redrawn on a PICK change, and a
        # change made by hand is one: without this the new hero waited for
        # the next tick, which reads as the picker not having worked.
        self.refresh()

    # ---- capture source ------------------------------------------------
    def _set_forced(self, on: bool) -> None:
        for widget in (self.force_check, self.force_action):
            widget.blockSignals(True)
            widget.setChecked(on)
            widget.blockSignals(False)
        self.provider.set_forced(on)

    def _cal_note(self, text: str, seconds: int = 12000) -> None:
        """One sentence about the crop boxes, said in both places.

        `cal_label` is dim text beside the Measure button in Debug ▸ Live,
        which is exactly where somebody who pressed that button is looking
        — and nowhere near somebody who pressed the BANNER. The sentence
        is the same either way, so it goes to both rather than the banner
        path measuring for a minute and reporting into a panel two menus
        deep that nobody has open.
        """
        self.cal_label.setText(text)
        self._say(text, seconds)

    def _measure_from_banner(self, *_ignored) -> None:
        """The banner's button: measure the boxes off the frame in hand.

        THE SAME CODE AS THE MEASURE BUTTON, deliberately. What raised
        this strip is precisely what measuring needs — a picture of the
        pick bar with all ten heroes named by the game — so the answer to
        "the app cannot find the portraits" is to go and find them, not
        to hand somebody two rectangles to drag over the client.
        There is no hand-drag to fall back to any more, so when this
        cannot run the note says what stopped it — no picture, not enough
        heroes named yet, no portraits downloaded — every one of which is
        something the user can act on.

        The flag lives on the snapshot that raised the banner, so a
        success has to clear it here. The next tick builds a fresh one and
        would clear it anyway, but a strip that stays up after the thing
        it is about has been fixed reads as the fix not having worked.
        """
        if self._measure_calibration():
            snap = self.snapshot
            if snap is not None:
                snap.crop_boxes_wrong = False
        self._update_first_run_banner(self.snapshot)

    def _measure_calibration(self) -> bool:
        """Measure the crop boxes from a frame whose heroes the game named.

        This is the only way this project can calibrate: the person who
        can see the screen and the person who can change the numbers are
        not the same, so the app has to measure its own geometry.
        """
        snap = self.snapshot
        frame = getattr(snap, "frame", None) if snap else None
        if frame is None:
            # TWO SOURCES, IN ORDER, and the second is not optional. The
            # live Snapshot is free and is already a picture of this
            # frame — but `use_vision` is a tick box and game-data-only
            # mode has no capture session at all, so "you cannot measure
            # the crop boxes unless the crop boxes are already being
            # used" would be a circle. A one-shot grab of the Dota window
            # breaks it.
            try:
                frame = self._grab_dota_frame()
            except Exception:       # noqa: BLE001 — see below
                # Dota closed between the banner appearing and the button
                # being pressed, or capture is unavailable on this
                # machine. That is a refusal with a sentence, never a
                # traceback out of a button.
                frame = None
        heroes = list(getattr(snap, "left", [])) + list(
            getattr(snap, "right", [])) if snap else []
        if frame is None:
            self._cal_note(
                "no frame — is Dota running in borderless windowed mode?")
            return False
        if len(heroes) < 8:
            self._cal_note(
                "the game has not named enough heroes yet — try this during "
                "strategy time, when all ten are known")
            return False

        from ..vision import autocal
        portraits = autocal.base_portraits(heroes)
        if len(portraits) < 8:
            self._cal_note(
                "portraits are not downloaded — run "
                "Settings ▸ Downloads ▸ Statistics and portraits first")
            return False

        self.measure_button.setEnabled(False)
        self._cal_note("measuring… (about a minute)")
        QApplication.processEvents()
        try:
            result = autocal.calibrate(frame, portraits, self.layout_spec)
        except Exception as exc:                 # never take the app down
            self._cal_note(f"measuring failed: {exc}")
            self.measure_button.setEnabled(True)
            return False
        self.measure_button.setEnabled(True)
        if not result.ok:
            self._cal_note(result.note)
            return False
        self.layout_spec = result.layout
        for field, spin in self.cal_spins.items():
            spin.blockSignals(True)
            spin.setValue(getattr(result.layout, field))
            spin.blockSignals(False)
        self._set_calibration("y", result.layout.y)      # push and redraw
        self._save_calibration()
        self._cal_note(f"{result.note} — saved")
        return True

    def _learn_unknown_portrait(self, snap) -> None:
        """Teach the library the one portrait it could not match.

        Personas, arcanas and cosmetic sets change the top-bar picture, and
        the library only holds Valve's one base image per hero — so a hero
        on a set portrait sits at UNKNOWN while the other nine resolve. The
        artwork does not have to be found anywhere: it is on screen, at the
        right size, with the HUD's own badge and border on it, and the game
        names all ten so the label is exact. Nine matched plus the game's
        ten leaves exactly one answer.

        Everything here is a guard, because a mislabelled crop teaches the
        library that one hero looks like another and never expires. When a
        frame does not qualify the answer is "not this frame" — a draft is
        hundreds of frames and one is enough.
        """
        if snap is None or snap.frame is None or snap.read_raw is None:
            return
        if not getattr(snap, "sides_known", False):
            return                    # the game has not named the ten
        ten = list(snap.left) + list(snap.right)
        hero_id, found = harvest.by_elimination(snap.read_raw, ten)
        if hero_id is None or hero_id in self._learned:
            return
        session = getattr(self.provider, "session", None)
        from ..vision.recognize import crop_rect
        crop = crop_rect(snap.frame, found.rect)
        params = getattr(session, "params", None)
        saved = harvest.save_variant(
            hero_id, crop, f"{snap.match_id or 'game'}_{found.rect.team}"
            f"{found.rect.slot}",
            hash_size=getattr(params, "hash_size", 16))
        if saved is None:
            return
        self._learned.add(hero_id)
        self._say(
            f"Learned {self.ds.name(hero_id)}'s portrait from this game — "
            "it will be recognised from the next reload (F5).", 12000)

    def _adopt_measured_layout(self) -> None:
        """Take the geometry a successful screen search already measured.

        The search hunts all ten portraits across the top strip to work out
        whose five are whose, so by the time it answers it knows exactly
        where every box is and how big. Nothing was doing anything with
        that, which is why it kept running: the cheap path needs calibrated
        boxes, the boxes were never calibrated, so every match paid for the
        search again — and on a real 3440x1440 session that was 25 seconds
        of frozen window.

        **AND IT NOW ADOPTS OVER AN EXISTING CALIBRATION**, which
        REVERSES the guard that stood here. That guard was written for a
        real fault — boxes the user had dragged onto the portraits and
        watched land were silently replaced by whatever the next match
        measured, and "a calibration the user set is an ANSWER, a
        measurement is a guess" was the right way to settle it. There is
        no hand-drag any more, at the user's request, so there is no
        answer left for a guess to overwrite: every calibration this app
        holds is a measurement, and a measurement taken from THIS match is
        never worse than one taken from a match on another monitor at
        another resolution. That is the whole of "the automatic detection
        works so the user never needs to draw these boxes" — without it,
        the first measurement a machine ever made would be the last one it
        could ever take by itself.

        A measurement that is not `ok` still changes nothing: `read_lineup`
        refuses anything short of ten portraits in two banks of five, so
        what reaches here has already been checked against the geometry.
        """
        result = getattr(self.provider, "measured_layout", None)
        if result is None:
            return
        self.provider.measured_layout = None
        if not result.ok:
            return
        self.layout_spec = result.layout
        session = getattr(self.provider, "session", None)
        if session is not None:
            session.layout = result.layout
        for field, spin in getattr(self, "cal_spins", {}).items():
            spin.blockSignals(True)
            spin.setValue(getattr(result.layout, field))
            spin.blockSignals(False)
        from ..vision import layout as layout_mod
        try:
            layout_mod.save_calibration(result.layout)
        except OSError as exc:
            self.cal_label.setText(f"measured but could not save: {exc}")
            return
        self.cal_label.setText(f"measured from the game — {result.note}")
        self._say(
            "Crop boxes measured from this game and saved — recognition "
            "should work from here.", 12000)

    # THE DRAG IS GONE, and with it "Use a saved picture…", which
    # existed only to give the drag something to draw on when Dota was
    # not up. At the user's request: "i dont see the point in having the
    # portrait box vision box feature at all... my plan now is to have
    # the automatic detection work so the user never needs to draw out
    # these vision boxes". `autocal` measures the same six numbers off a
    # frame the game has named the heroes in, which is where every
    # calibration this app has ever shipped came from — the drag was the
    # fallback for before that worked.

    def _set_calibration(self, field: str, value: float) -> None:
        """Live: the next frame is cropped with the new numbers, so the
        boxes in the picture move as the spin box turns."""
        setattr(self.layout_spec, field, float(value))
        session = getattr(self.provider, "session", None)
        if session is not None:
            session.layout = self.layout_spec
        self.cal_label.setText("changed — not saved")
        self._force_redraw()

    def _save_calibration(self) -> None:
        from ..vision import layout as layout_mod
        try:
            layout_mod.save_calibration(self.layout_spec)
        except OSError as exc:
            self.cal_label.setText(f"could not save: {exc}")
            return
        self.cal_label.setText(f"saved to {CALIBRATION_FILE.name}")

    def _reset_calibration(self) -> None:
        from ..vision import layout as layout_mod
        self.layout_spec = layout_mod.DraftLayout()
        for field, spin in self.cal_spins.items():
            spin.blockSignals(True)
            spin.setValue(getattr(self.layout_spec, field))
            spin.blockSignals(False)
        self._set_calibration("y", self.layout_spec.y)   # push and redraw
        self.cal_label.setText("reset to defaults — not saved")

    def _relaunch(self) -> None:
        """Start a fresh copy of ourselves and quit.

        Detached on purpose: the new process must outlive this one, and it
        must not inherit a half-torn-down Qt event loop.
        """
        try:
            # `__main__.py` rather than `-m`, so the new process does not
            # depend on inheriting our working directory — the same target
            # the taskbar pin launches.
            subprocess.Popen(
                [sys.executable, str(REPO_ROOT / "draft_assist"
                                     / "__main__.py")],
                cwd=str(REPO_ROOT), close_fds=True)
        except OSError as exc:
            self._say(f"Could not restart: {exc}", 10000)
            return
        QApplication.quit()

    def _update_app(self) -> None:
        """Pull the code, then reopen. Same deal as the data update.

        A pull that leaves the old process running has done half the job:
        the point of the button was never to run git, it was to be on the
        new version without closing and reopening the app by hand.
        """
        self._restart_after_task = "update_app"
        self.run_task("update_app")

    # ---- the app's icon -------------------------------------------------
    def _choose_app_icon(self) -> None:
        """Let the user hand the app the icon they want.

        This repository ships no icon and will not: the ones asked for are
        Blizzard's and Valve's artwork. But an icon file on the user's own
        machine is theirs to point at, and a file picker is the only honest
        answer to "use the one I gave you".
        """
        path, _filter = QFileDialog.getOpenFileName(
            self, "Choose the app icon", str(REPO_ROOT),
            "Icons and images (*.ico *.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        try:
            dest = appicon.install(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "App icon",
                                f"Could not use that file:\n\n{exc}")
            return
        self._apply_app_icon()
        self._say(
            f"App icon set from {Path(path).name} (copied to "
            f"assets/{dest.name}). The taskbar picks it up when the app is "
            "reopened.", 12000)

    def _apply_app_icon(self) -> None:
        """Push the current icon at everything that draws one.

        The window (Alt-Tab), the application (the taskbar), our own
        title bar, and the relaunch icon Windows builds a pin from — which
        is a file on disk rather than a QIcon, and is the one that is easy
        to leave out of step.
        """
        art = appicon.icon()
        self.setWindowIcon(art)
        app = QApplication.instance()
        if app is not None:
            app.setWindowIcon(art)
        if getattr(self, "title_bar", None) is not None:
            self.title_bar.refresh_icon()
        # Five places, not four: the pin draws from the window's own
        # relaunch icon, which is a FILE, so a new icon has to be written
        # out again for it.
        appicon.claim_window_identity(int(self.winId()))
        appicon.push_native_icon(int(self.winId()))

    def _set_pinned(self, on: bool) -> None:
        """The pin was pressed: hold the window in front, or stop.

        **NOT `setWindowFlags`.** Changing a window's flags on Windows
        DESTROYS AND RECREATES the native handle, and this app has
        already paid for that once — the icon was pushed at an HWND that
        no longer existed and the taskbar button fell back to
        pythonw.exe. On a button it would happen on every press, taking
        the window's Win32 icon and its relaunch identity with it each
        time. `ontop.apply` moves the window in the Z order and touches
        nothing else.
        """
        on = bool(on)
        ontop.apply(self, on)
        if self.settings.get("always_on_top") == on:
            return
        self.settings["always_on_top"] = on
        ui_settings.save(self.settings)
        self._say("Window pinned in front" if on else
                  "Window no longer pinned — click another to raise it",
                  4000)

    def _toggle_maximised(self) -> None:
        # It used to refuse while the size was locked, and there is no
        # lock any more — the window is freely resizable and remembers
        # whatever size it is closed at.
        self.showNormal() if self.isMaximized() else self.showMaximized()

    # THE TOOL WINDOW IS GONE WITH THE TOOLS IT RAN. It was Run, a text
    # panel and Copy results — the shape asked for outright — and every
    # one of its four callers was a recognition instrument the user has
    # since said they no longer need. A window with no way to open it is
    # not a feature held in reserve, it is code that cannot be exercised,
    # so `ui/tool_window.py`, `_open_tool`, the progress relay and the
    # screenshot-folder ladder went with them.

    def _open_settings(self, tab: str = "") -> None:
        """Show the settings window, building it the first time.

        BUILT ONCE AND KEPT, because it owns the debug pages: they are a
        live view of what the app is reading, and handing a live widget
        back and forth between two parents is how this app has previously
        ended up with a second window in the taskbar. Modeless, so the
        debug view can be watched while the draft runs, and it applies as
        you go rather than on an OK that a live view has no use for.
        """
        from .settings_window import SettingsWindow

        self.settings.setdefault("pair_source", pair_source())
        fresh = getattr(self, "settings_window", None) is None
        if fresh:
            self.settings_window = SettingsWindow(
                self.settings, self._command_groups(),
                debug=getattr(self, "debug_tabs", None), parent=self)
            self.settings_window.applied.connect(self._apply_settings)
            # A window built just now has missed every recompute that ever
            # happened, so it would open with a blank line under the bar
            # until something changed - which is the same "says nothing"
            # this note exists to end.
            self.settings_window.set_shield_note(self.shields_note)
        self.settings_window.show_tab(tab)

    def _apply_settings(self, values: dict) -> None:
        """Take one edit from the settings window.

        Called on EVERY change rather than once at the end, so it has to
        be cheap and it has to be idempotent — which it is: each branch
        compares against what is already in `self.settings` and does
        nothing when it matches.
        """
        before = dict(self.settings)
        self.settings.update(values)
        if self.settings == before:
            return
        ui_settings.save(self.settings)
        # The strips are redrawn only when a PICK changes, so without this
        # a new "how many to show" would sit in the settings file doing
        # nothing until the next hero was picked — which reads as the
        # setting not working rather than as a refresh that never ran.
        self._refresh_views()

        self.auto_record_check.setChecked(
            bool(self.settings.get("auto_record", True)))
        if (self.settings.get("use_gsi"), self.settings.get("use_vision")) != (
                before.get("use_gsi"), before.get("use_vision")):
            self._apply_sources()
        self._apply_sections()
        self._apply_greyscale()
        marks = ("heart_count", "shield_count")
        if any(self.settings.get(k) != before.get(k) for k in marks):
            # RE-APPLIED, NOT RE-MEASURED, and that is the change: these
            # used to be percentile floors INSIDE the ranking, so moving
            # one meant reading the whole History run again and
            # recomputing every hero's standing in the field. A share of
            # the strip is a cut over a ranking that has not changed, so
            # the marks are simply drawn again.
            #
            # It still has to happen HERE. The strip is redrawn when a
            # PICK changes, so without this the control moved a number in
            # a file and nothing on screen until the next hero was
            # picked - which is indistinguishable from a broken setting,
            # and is the state the shield bar actually shipped in.
            self.suggest_row.set_stars(self.stars, self._heart_count())
            self.suggest_row.set_shields(self.shields, self._shield_count())
            self._refresh_views()
        chosen = self.settings.get("pair_source", pair_source())
        if chosen != pair_source():
            # Written to preferences.json, not just the UI settings: the
            # pull runs in a subprocess and reads it there.
            save_pair_source(chosen)
            self._say(
                f"Statistics source set to {chosen} — run Settings ▸ "
                "Downloads ▸ Statistics and portraits to rebuild the "
                "matrices from it", 12000)

    def _apply_sources(self) -> None:
        """Rebuild the draft source from the settings.

        The two used to be mutually exclusive menu commands, from when they
        were alternatives. They are not — the game feed says WHEN and
        WHOSE, the screen says WHAT — so this composes whichever are on.
        """
        from ..gsi import install as gsi_install
        from ..gsi.server import GsiServer
        from .providers import GsiProvider, HybridProvider, LiveProvider

        use_gsi = bool(self.settings.get("use_gsi", True))
        use_vision = bool(self.settings.get("use_vision", True))
        session = _capture_session() if use_vision else None
        if use_vision and session is None:
            QMessageBox.information(
                self, "Settings",
                "Reading the screen needs the portrait library — "
                "run Settings ▸ Downloads ▸ Statistics and portraits first.")
        vision = LiveProvider(session) if session is not None else None

        if not use_gsi:
            if vision is not None:
                self._swap_provider(vision)
            else:
                from .providers import ManualProvider
                self._swap_provider(ManualProvider(self.manual))
            return

        server = GsiServer(gsi_install.DEFAULT_PORT,
                           token=gsi_install.read_installed_token())
        gsi = GsiProvider(self.ds, server, self.manual)
        self._swap_provider(
            HybridProvider(gsi, vision) if vision is not None else gsi)

    def _refresh_sources(self) -> None:
        if not hasattr(self.provider, "available_sources"):
            return
        current = self.source_combo.currentText()
        self.source_combo.clear()
        self.source_combo.addItems(self.provider.available_sources())
        idx = self.source_combo.findText(current)
        if idx >= 0:
            self.source_combo.setCurrentIndex(idx)

    def _bind_title(self, title: str | None) -> None:
        if not hasattr(self.provider, "rebind"):
            return
        message = self.provider.rebind(title)
        self.snapshot_label.setText(message)
        self._say(message, 8000)
        self.last_draft_key = None
        self._refresh_sources()

    def _bind_source(self) -> None:
        title = self.source_combo.currentText()
        if title:
            self._bind_title(title)

    # ---- polling -----------------------------------------------------
    def refresh(self) -> None:
        """One tick, with every stage timed.

        The timing is always on and costs a `perf_counter` pair per stage.
        When this loop stops being smooth there is otherwise no way to say
        which stage is costing the time — capture, recognition, scoring and
        redraw all happen inside one tick — and guessing has already been
        wrong once: the stutter that looked like scoring was a hidden
        widget being smooth-scaled four times a second.
        """
        started = time.perf_counter()
        with LOOP.stage("poll (capture + recognition)"):
            snap = self.provider.poll()
        self.snapshot = snap
        # The blanking lifts here, ONCE a tick, rather than as a side
        # effect of whoever asks about it first.
        if self._cleared is not None and self._cleared != self._board_key(snap):
            self._cleared = None
        allies, enemies = self._sides(snap)
        draft_key = (tuple(allies), tuple(enemies), snap.unknown)
        if draft_key != self.last_draft_key:
            self.last_draft_key = draft_key
            with LOOP.stage("rebuild (a pick changed)"):
                self._on_draft_changed(allies, enemies, snap.unknown)
        with LOOP.stage("recording"):
            self._consider_auto_record(snap)
            self._capture_recording(snap, allies, enemies)
        self._adopt_measured_layout()
        with LOOP.stage("learn a new portrait"):
            self._learn_unknown_portrait(snap)
        self._update_first_run_banner(snap)
        with LOOP.stage("status + captions"):
            self._update_status(snap)
            self._update_team_captions(snap)
            self._update_manual_hint(snap)
        with LOOP.stage("debug view"):
            self._update_debug(snap)
        LOOP.tick_done((time.perf_counter() - started) * 1000.0)

    def _update_team_captions(self, snap) -> None:
        """Say who the app thinks you are, using what the game reported,
        and hide the side question when it is already answered."""
        known = getattr(snap, "sides_known", False)
        self.side_label.setVisible(not known)
        self.side_combo.setVisible(not known)

        # ALWAYS Radiant and Dire. "Your team" / "Enemy team" was the
        # fallback whenever the game had not said which side was ours, and
        # it named a thing the user can already see — the panel with their
        # own hero in it. The side is what the eye is looking for, and when
        # it is not known yet the sensible assumption is the common one.
        team = (getattr(snap, "my_team", "") or "").lower()
        mine = "Dire" if team == "dire" else "Radiant"
        theirs = "Radiant" if mine == "Dire" else "Dire"
        for side, caption in (("ally", mine), ("enemy", theirs)):
            label = self.team_captions[side]
            set_label(label, caption)
            # PLAIN WHITE. They were Dota's own green and red, and that put
            # the colours that mean "good for you" and "bad for you" on two
            # words that are not a judgement about anything — with the
            # side's own signed total sitting right beside them wearing the
            # same two colours for the opposite reason. Colour is reserved
            # for meaning here, and "which side is this" is not one.
            label.setStyleSheet(f"color: {theme.TEXT_STRONG};")
        # And the grids are outlined in the two teams' own colours —
        # Radiant green, Dire red, Dota's own — so the counters grid says
        # which of its axes is whose and the synergy card says which
        # triangle is whose. Which of ally and enemy gets which changes
        # with the side the player is on, and this is the only place that
        # knows.
        ally_colour = theme.BAD if mine == "Dire" else theme.GOOD
        enemy_colour = theme.GOOD if mine == "Dire" else theme.BAD
        for grid in (self.synergy_matrix, self.matchup_matrix):
            grid.set_team_colours(ally_colour, enemy_colour)
        # The Roles card names its two halves from the same answer, so a
        # heading there can never disagree with the panel above it.
        self.role_bar.set_sides(mine, theirs)
        # The player's five go to the side they actually belong to, rather
        # than always sitting on the left: Radiant is the left bank of
        # Dota's own pick bar, so a panel on the left labelled Dire would
        # be the one arrangement that disagrees with the screen it is being
        # read beside.
        self._order_panels("enemy" if mine == "Dire" else "ally")

    def _order_panels(self, radiant: str) -> None:
        """Seat the Radiant panel on the left. THE GRIDS DO NOT MOVE.

        **THE TWO CARDS ARE NEVER RE-SEATED, and that REVERSES what stood
        here**, at the user's request: "it should never swap because both
        synergies and counters has both radiant and dire on it anyway —
        synergies left, counters right."

        Each grid used to move with "the team whose heroes head it", and
        that reasoning expired when the cards did. Synergy became TWO
        TRIANGLES carrying both line-ups, and counters is your five
        against theirs with a coloured box round each axis — so neither
        card belongs to a side any more, and there is nothing for the
        seating to follow. What it produced instead was a Draft tab whose
        bottom half changed places depending on which team the matchmaker
        put you on: "the counters matrix switched position to the
        synergies matrix... it used to be synergies on the left".

        The PANELS still swap, because that rule is untouched: Radiant is
        the left bank of Dota's own pick bar, and a panel on the left
        labelled Dire is the one arrangement that disagrees with the
        screen it is read beside. Which triangle is whose is also
        untouched — yours is the lower left, in your team's own colour,
        wherever you are playing.
        """
        want = [radiant, "enemy" if radiant == "ally" else "ally"]
        if want == self._panel_order:
            return
        self._panel_order = want
        # THE CARDS MOVE, not the panels inside them: a side's five picks
        # and its role pills are one card now, and seating the panel
        # alone would leave its pills behind under the other team.
        for side in want:
            self.teams_row.removeWidget(self.side_cards[side])
        for side in want:
            self.teams_row.addWidget(self.side_cards[side], 1)
            self.side_cards[side].show()

    def _update_manual_hint(self, snap) -> None:
        """Say plainly which picks the game reported and which need typing —
        the app should never leave the user guessing why a slot is empty."""
        source = getattr(snap, "lineup_source", "")
        # A new match must not inherit the previous match's correction.
        match = getattr(snap, "match_id", "") or ""
        if match != self._swap_match:
            self._swap_match = match
            self.side_overrides.clear()
            self.slot_order = {"ally": [], "enemy": []}
        if not snap.needs_manual:
            if source == "minimap":
                set_label(self.manual_hint, 
                    "Which five are yours is a guess — drag a hero onto the "
                    "other team to fix it.")
            elif source == "minimap+screen":
                set_label(self.manual_hint, 
                    "Ten heroes from the game, sides read off the pick bar.")
            elif source == "screen":
                set_label(self.manual_hint, "Picks read from the Dota window.")
            else:
                set_label(self.manual_hint, "")
            return
        if source == "screen":
            set_label(self.manual_hint, 
                "Reading the picks from the Dota window — type in anything "
                "it has not recognised.")
        elif snap.game_state:
            set_label(self.manual_hint, 
                "The game reports no picks while you are picking, so these "
                "come off the Dota window. Nothing appearing? Check Debug is "
                "bound to Dota, or type them in.")
        else:
            set_label(self.manual_hint, "Click a slot to enter the draft.")

    def _sides(self, snap) -> tuple[list[int], list[int]]:
        """(allies, enemies).

        When the source reports which team is yours, left/right already mean
        ally/enemy and the manual swap must not apply — otherwise the app
        would let the user contradict the game.
        """
        if self._is_cleared(snap):
            # A blanked board is not empty — it holds whatever has been
            # TYPED IN since, and nothing else. Returning ([], []) here
            # made hand entry impossible after Clear all: `merge` puts the
            # game's five first and cuts to five, so a typed hero was
            # dropped on the way in, the board key never changed, the
            # blanking never lifted, and clicking a slot appeared to do
            # nothing at all. While the board is blanked the game's ten
            # are not on it, so the manual slots are the whole answer.
            return (self._apply_order("ally", self.manual.entered("ally")),
                    self._apply_order("enemy", self.manual.entered("enemy")))
        if getattr(snap, "sides_known", False):
            # The minimap gives ten heroes but not, reliably, which five are
            # yours — one real match came out inverted. So corrections are
            # allowed HERE, where the game itself has not settled it.
            allies, enemies = self._apply_side_overrides(
                snap.left, snap.right)
        else:
            mine_right = self.side_combo.currentIndex() == 1
            allies, enemies = ((snap.right, snap.left) if mine_right
                               else (snap.left, snap.right))
        return (self._apply_order("ally", allies),
                self._apply_order("enemy", enemies))

    def _is_cleared(self, snap) -> bool:
        """Is this exactly the board Clear all was pressed on?

        Clear all emptied the hand-entered slots and asked for a fresh
        reading, and on a live match that did NOTHING visible: the picks
        were the game's, precedence is game > hand entry, and the next
        payload put all ten straight back. A button whose whole purpose is
        a clean slate has to produce one.

        So the cleared line-up is REMEMBERED and blanked, and it stops
        being blanked the moment there is something different to show — a
        pick changes, the match changes, or Detect all is pressed (the
        expiry itself is in `refresh`, once a tick). That is a clean slate
        that cannot become a board stuck empty for the rest of the
        evening, which is what suppressing the sources outright would have
        risked.
        """
        return (self._cleared is not None and snap is not None
                and self._cleared == self._board_key(snap))

    @staticmethod
    def _board_key(snap):
        """What the blanking is pinned to: the MATCH, not the line-up.

        It was keyed on the ten heroes, and that made it fragile in both
        directions. `Detect all` and `Clear all` both drop the capture
        session's reading, so recognition comes back a hero at a time over
        the next few ticks — and any of those partial readings is a
        different line-up, which lifted the blanking and put a half-read
        board on screen. A hand-entered hero perturbed it too.

        The match and whether a draft is on are the two things that mean
        "this is a different board now", and neither wobbles: a new match
        gets a new id, and a new draft is exactly when you want the board
        back. Everything else is lifted deliberately, by pressing Detect
        all.
        """
        return (getattr(snap, "match_id", "") or "",
                getattr(snap, "game_state", "") in DRAFTING_STATES)

    def _apply_order(self, side: str, ids: list[int]) -> list[int]:
        """Put the bank into the order the user dragged it into.

        Only heroes still in the reading are honoured, and anything the
        override does not mention keeps its place at the end — so a stale
        order from earlier in the same match degrades to a partial one
        rather than dropping a pick.
        """
        wanted = [h for h in self.slot_order.get(side, []) if h in ids]
        return wanted + [h for h in ids if h not in wanted]

    def _apply_side_overrides(self, allies, enemies):
        """Move individually corrected heroes across, keeping order."""
        if not self.side_overrides:
            return (allies, enemies)
        wanted = self.side_overrides
        mine = [h for h in allies if wanted.get(h, "ally") == "ally"]
        theirs = [h for h in enemies if wanted.get(h, "enemy") == "enemy"]
        mine += [h for h in enemies if wanted.get(h) == "ally"]
        theirs += [h for h in allies if wanted.get(h) == "enemy"]
        return (mine[:5], theirs[:5])

    def _force_redraw(self) -> None:
        self.last_draft_key = None

    def _current_draft(self) -> scoring.DraftState:
        if self.snapshot is None:
            return scoring.DraftState()
        allies, enemies = self._sides(self.snapshot)
        return scoring.DraftState(
            allies=list(allies), enemies=list(enemies),
            unknown_slots=self.snapshot.unknown,
            my_role=self._my_role(),
            my_hero=self._my_hero() if self.my_hero_locked else None)

    def _my_role(self) -> str | None:
        """The role written on the slot your own hero is standing in.

        Roles belong to slots and your hero belongs to you, so the role
        that filters item advice is wherever those two meet — there is no
        separate answer to keep in sync.
        """
        if self.my_hero_id is None:
            return None
        for index, tile in enumerate(self.team_buttons["ally"]):
            if tile.property("hero_id") == self.my_hero_id:
                label = self.slot_roles["ally"][index]
                return ROLE_BY_LABEL.get(label) if label else None
        return None

    def _my_hero(self) -> int | None:
        return self.my_hero_id

    # ---- reactions -----------------------------------------------------
    def _on_draft_changed(self, allies, enemies, unknown) -> None:
        for side, ids in (("ally", allies), ("enemy", enemies)):
            for i, tile in enumerate(self.team_buttons[side]):
                # Empty slots stay enabled: clicking one is how a pick gets
                # entered when the game does not report it.
                hid = ids[i] if i < len(ids) else None
                tile.set_pick(self.ds.name(hid) if hid is not None else None,
                              self.slot_roles[side][i], hid)
        # A hero that left the draft cannot be the one everything else is
        # measured against — but a focused SUGGESTION was never in it, so
        # the same test would clear it on the very next payload. It is
        # kept while it is still on the strip (`_drop_focus_if_off_screen`
        # decides that, since only the strip knows what it is showing),
        # and when the hero is actually PICKED the ring FOLLOWS IT onto
        # the board: you clicked that hero, it is still that hero, and
        # dropping the selection at the moment the pick lands would clear
        # the board exactly when the answer became real.
        if self.focus is not None:
            where, hid = self.focus
            picked = ("ally" if hid in allies else
                      "enemy" if hid in enemies else None)
            if where == "suggest":
                if picked is not None:
                    self.focus = (picked, hid)
            elif picked is None:
                self.focus = None
        set_label(self.unknown_label, 
            f"{unknown} slot(s) unresolved — scoring uses only confident "
            "slots" if unknown else "")

        # Your own hero has to still be in the draft to be your own hero.
        if self.my_hero_id is not None and self.my_hero_id not in allies:
            self.my_hero_id, self.my_hero_locked = None, False

        self._refresh_views()

    def _refresh_views(self) -> None:
        draft = self._current_draft()
        # Still the whole ranked list, even with the table that showed it
        # gone: Suggested picks is its head, "Why this score" reads terms
        # off it, and the item advice is filtered by the same roles.
        self.scored = scoring.score_all(self.ds, draft)
        self.role_bar.show_draft(draft.allies, draft.enemies)
        self._update_matrices(draft)
        # AFTER the grids are filled, not only on a window resize. Their
        # section count is what they can fit a portrait into, and it is
        # not known until they hold something — so a cap taken on a
        # resize alone was taken from an empty grid and then never
        # revisited, and the picks and the grids settled on two different
        # sizes with nothing to reconcile them.
        self._match_grid_portraits()
        self._update_suggestions(draft)
        self._update_items(draft)
        self._update_relations()

    def _update_matrices(self, draft: scoring.DraftState) -> None:
        # NO SENTENCE UNDER AN EMPTY GRID. "Fill in both teams" is read
        # once and skipped forever, and the 5x5 outline already says the
        # grid is waiting for picks. A reason still worth saying — the
        # OpenDota one below — stays.
        self.matchup_matrix.show_matrix(
            scoring.matchup_matrix(self.ds, draft))
        # A dataset built from OpenDota carries no ally-pair counts at all,
        # so the grid would be a wall of +0.00 that looks like "no synergy
        # anywhere" rather than "this source does not publish it".
        if self.ds.meta.get("has_synergy") is False:
            self.synergy_matrix.show_pairs(
                scoring.SynergyGrid(allies=[], enemies=[], cells=[]),
                f"{self.ds.meta.get('pair_source', 'this source')} publishes "
                "no ally-pair data — switch the statistics source to Stratz "
                "in Settings and re-pull.")
        else:
            # BOTH teams, as the two triangles of one square: synergy is
            # symmetric, so your five only ever filled half of it and the
            # other half is exactly the right shape for theirs.
            self.synergy_matrix.show_pairs(
                scoring.team_synergy_grid(self.ds, draft))

    def _on_slot_clicked(self) -> None:
        b = self.sender()
        hid = b.property("hero_id")
        side = b.property("side")
        if hid is None:
            self._edit_slot(side, b.property("slot_index"))
            return
        # Clicking the focused hero again clears the view, so the way out
        # is the same gesture as the way in. The counters list that used to
        # open beside it went with the History tab: what beats this hero
        # is a question about heroes NOT in the game, and the click view
        # answers the one about the ten that are.
        self.focus = None if self.focus == (side, hid) else (side, hid)
        self._update_relations()

    def _on_grid_hero_clicked(self, hero_id: int) -> None:
        """An axis portrait in either matrix, at the user's request.

        The grids name the same ten heroes the board does, so clicking a
        face here asks the same question a pick tile does and gets the
        same answer everywhere — and clicking it again clears it, which is
        the rule the board has always followed.

        The SIDE comes from the draft rather than from the grid. Counters
        heads its rows with your five and its columns with theirs, and
        synergy's two triangles are the other way up; asking the draft
        which team a hero is on is one question with one answer, where
        working it out from which axis was clicked is four.
        """
        draft = self._current_draft()
        side = ("ally" if hero_id in draft.allies else
                "enemy" if hero_id in draft.enemies else None)
        if side is None:
            return
        self.focus = None if self.focus == (side, hero_id) else (side, hero_id)
        self._update_relations()

    def _update_grid_focus(self) -> None:
        """Read both cards against the focused hero, or against none.

        A focused SUGGESTION clears them instead of blanking them. It is
        not on either grid — it is not in the draft — so every cell would
        fail the "is this about that hero" test and both cards would go
        silently, completely empty, which reads as the grids having
        broken rather than as the hero not being in them.
        """
        hero = None
        if self.focus is not None and self.focus[0] != "suggest":
            hero = self.focus[1]
        for grid in (self.synergy_matrix, self.matchup_matrix):
            grid.set_focus(hero)

    def _on_suggestion_clicked(self, hero_id: int) -> None:
        """A candidate becomes the hero everything else is measured against.

        It used to open a box listing the terms behind that tile's own
        number. Those terms ARE these numbers — the synergy with each of
        your five and the matchup against each of theirs — so they now go
        on the ten portraits the question is about, where the eye already
        is, instead of into a popup over the strip.

        The same selection as a pick, so clicking here CLEARS a pick that
        was focused: one hero at a time, whichever strip it came from.
        """
        self.focus = (None if self.focus == ("suggest", hero_id)
                      else ("suggest", hero_id))
        self._update_relations()

    def _update_relations(self) -> None:
        """Write the signed numbers on everything the focus can speak to.

        This is the matrix read one row at a time, which is how the
        question actually arrives mid-draft: not "show me the grid" but
        "what does THIS hero do to everything else".

        THREE SURFACES ANSWER ONE SELECTION — the ten picks, the
        suggestion strip and both grids — because the hero can be clicked
        on any of them and a click that lit up only the strip it came
        from would make the board mean different things depending on
        where the cursor had been.
        """
        for panel in self.team_panels.values():
            panel.clear_deltas()
        self.suggest_row.clear_deltas()
        draft = self._current_draft()
        # The heading totals are ALWAYS the net contributions, whether or
        # not a hero is clicked: a number beside "Radiant" that changed
        # every time a portrait was clicked would be a number you had to
        # stop and re-read before it meant anything.
        self._update_team_totals(draft)
        self._drop_focus_if_off_screen(draft)
        self._update_grid_focus()
        if self.focus is None:
            # Nothing clicked, so every tile says what that pick is worth
            # overall rather than nothing at all — the tile has a line for
            # a number either way, and an empty one wastes it. The
            # suggestions go back to draft fit, which is their own answer.
            net = scoring.net_contributions(self.ds, draft)
            for panel in self.team_panels.values():
                for tile in panel.slots:
                    value = net.get(tile.property("hero_id"))
                    if value is not None:
                        tile.show_delta(value)
            return
        where, hid = self.focus
        # A SUGGESTION IS READ AS A POSSIBLE ALLY. Left to infer it,
        # `relations_to` sees a hero that is not among your five and
        # treats it as one of theirs — which answers how your team fares
        # AGAINST the hero you are thinking of picking, the opposite of
        # the question the strip exists for.
        ally = where != "enemy"
        relations = {
            r.hero_id: r for r in
            scoring.relations_to(self.ds, hid, draft,
                                 side="ally" if ally else "enemy")}
        for panel in self.team_panels.values():
            for tile in panel.slots:
                other = tile.property("hero_id")
                if other is None:
                    continue
                if other == hid and panel.side == where:
                    tile.set_focused(True)
                    continue
                rel = relations.get(other)
                if rel is None:
                    # Nothing to say about this one — the focused hero
                    # itself, or a hero the dataset does not carry.
                    continue
                tile.show_delta(rel.delta, rel.kind)
        self._update_suggestion_relations(hid, ally, where)

    def _update_suggestion_relations(self, hid: int, ally: bool,
                                     where: str) -> None:
        """What each candidate would be worth beside the focused hero.

        Instead of its draft fit, at the user's request: with a pick
        clicked, the whole board is answering one question and a strip
        still ranking by overall fit is the one row on screen answering a
        different one.

        A focused SUGGESTION gets the ring and keeps every other
        candidate on its own fit — "suggestion versus suggestion is too
        hypothetical", and it is: neither hero is on the board, so the
        pair is a guess about two picks nobody has made.
        """
        self.suggest_row.set_focus(hid)
        if where == "suggest":
            return
        values = {
            r.hero_id: (r.delta, r.kind) for r in
            scoring.relations_from(self.ds, hid, ally,
                                   self.suggest_row.hero_ids)}
        self.suggest_row.show_deltas(values, self.ds.name(hid))

    def _drop_focus_if_off_screen(self, draft: scoring.DraftState) -> None:
        """A hero nobody can see cannot be what the numbers are about.

        The strip is cut to a count the user sets and re-ranked on every
        pick, so a focused candidate can fall off the end of it — and
        numbers all over the board measured against a hero with no ring
        on it anywhere is worse than no numbers at all.
        """
        if self.focus is None or self.focus[0] != "suggest":
            return
        if self.focus[1] not in self.suggest_row.hero_ids:
            self.focus = None

    def _update_team_totals(self, draft: scoring.DraftState) -> None:
        """The signed figure beside each side's name.

        The sum of what `net_contributions` says that side's five heroes
        are worth — the same numbers the five tiles carry when nothing is
        clicked, added up. Read from YOUR side either way: on your own
        panel it is what your draft is worth, on theirs it is how well
        their five are handled, so the two are not a scoreline and are not
        offered as one.

        Nothing at all when no hero on that side has resolved. A heading
        reading "+0.0" over five empty slots claims a measurement nobody
        made.
        """
        net = scoring.net_contributions(self.ds, draft)
        for side, panel in self.team_panels.items():
            figures = [net[hid] for hid in
                       (tile.property("hero_id") for tile in panel.slots)
                       if hid is not None and hid in net]
            panel.set_total(sum(figures) if figures else None)

    def _why_this_item(self, item: str) -> None:
        """Item rules ARE written in words, so this one has a real answer."""
        entry = next((a for a in self._last_advice if a.item == item), None)
        if entry is None:
            return
        heading, lines, note = reasons.item_reasons(
            entry.item, entry.triggers, entry.any_stale)
        self._pop_reasons(heading, lines, note, self.item_row)

    def _pop_reasons(self, heading, lines, note, near) -> None:
        popup = reasons.ReasonPopup(heading, lines, note, self)
        self._reason_popup = popup          # kept alive while it is up
        popup.pop_at(near.mapToGlobal(near.rect().bottomLeft()))

    def _count_box(self, key: str):
        """The little number beside a strip's heading.

        It used to be in Settings, two menus away from the strip whose
        length it sets — which is the wrong place for a number you tune by
        looking at the result.
        """
        box = chrome.CountBox(self._how_many(key), 1, ui_settings.MAX_SHOWN)
        box.setToolTip(
            "How many to show. They wrap onto another row rather than "
            "scrolling, and the default is however many fit on one row.\n"
            "For items this is a CAP, not a quota: a quiet draft still "
            "shows two.")
        box.valueChanged.connect(
            lambda value, k=key: self._set_count(k, value))
        self.count_boxes[key] = box
        return box

    def _picks_controls(self) -> QWidget:
        """The legend: which mark means what, and how many get it.

        ALL THREE COUNTS ON THIS CARD, at the user's request: "it makes
        sense to have the number of shields / hearts setting to be right
        next to the quantity dropdown for number of hero suggestions, and
        this should be the same kind of entry field." The strip's own
        count rides on the heading a line above these two, which is near
        enough to satisfy that and near enough to the words "Suggested
        picks" not to have to repeat them.

        Which is the rule this row already followed for the first of
        them - a number you tune by looking at the result belongs beside
        the result, not two menus away in Settings - so the two badge
        counts MOVE here rather than being repeated. Two places to read
        one setting is two places for it to go stale.
        """
        row = QWidget()
        row.setSizePolicy(QSizePolicy.Policy.Expanding,
                          QSizePolicy.Policy.Preferred)
        # TRANSPARENT. A bare QWidget takes the base `QWidget` rule, which
        # is the CONTENT colour - lighter than the card it is sitting on -
        # so this container painted a pale rectangle behind the whole
        # heading: "the suggested picks area has a weird padding
        # background color discrepancy". Exactly the fault the stylesheet
        # already fixes for every QLabel, one widget kind over. The count
        # boxes on top of it were transparent and correctly showing this.
        row.setProperty("bare", True)
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(10)

        # TWO ROWS, AND THEY ARE A LEGEND, at the user's request: "i
        # want a legend added to the title (suggested picks)... so i
        # want 1 row below the header to show the symbols and what they
        # mean", laid out as
        #
        #     Suggested picks   [N]      <- the card's heading
        #     <heart>  = comfort    = N
        #     <shield> = counter    = N
        #
        # It was three, with "Pick suggestions = N" leading — which said
        # the heading's own words back at it. The count moved up to join
        # them.
        #
        # The marks have carried their meaning in a TOOLTIP since they
        # were drawn, which is a poor place for the one thing a reader
        # needs before the mark means anything at all - a pink heart on
        # a portrait is not self-explaining, and nobody hovers a symbol
        # they have not got a question about yet. Naming them on the
        # card costs two rows that were already half empty.
        #
        # THE HAND IS GONE - "Remove the hand symbol its pointless". It
        # was a picture standing in for the words "pick suggestions",
        # and now that the rows carry words anyway it was the one mark
        # on this card explaining nothing that the text beside it did
        # not. `tilekit.paint_hand` went with it rather than being left
        # for somebody to read as documentation later.
        counts = QWidget(row)
        counts.setProperty("bare", True)
        stack = QGridLayout(counts)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setHorizontalSpacing(6)
        stack.setVerticalSpacing(2)

        # ROW 0 IS THE HEADING, spanning the three label columns so its
        # own box lands in column 3 with the other two. It keeps the
        # heading font — this IS the card's heading now, not a second
        # line under one.
        title = QLabel("Top picks", counts)
        title.setProperty("heading", True)
        stack.addWidget(title, 0, 0, 1, 3)
        stack.addWidget(self.suggested_box, 0, 3)

        # TWO COUNTS AGAIN, WHICH REVERSES THE ONE THAT REPLACED THEM.
        # They were merged on the argument that the marks answer the
        # same question - how far down the strip is worth marking - and
        # that holds right up until the rows are LABELLED separately,
        # which is what a legend is. One value behind two lines each
        # showing a number is the fault this app has a rule about: two
        # places to read one setting is two places for it to go stale.
        for line_no, (shield, word, key) in enumerate(
                ((False, "comfort", "heart_count"),
                 (True, "counter", "shield_count")), start=1):
            stack.addWidget(MarkLabel(shield, counts), line_no, 0)
            stack.addWidget(QLabel("=", counts), line_no, 1)
            stack.addWidget(QLabel(word, counts), line_no, 2)
            box = self._badge_box(key)
            stack.addWidget(box, line_no, 3)
            setattr(self, f"{'shield' if shield else 'heart'}_box", box)
        line.addWidget(counts)
        # THE FILTER TAKES THE SPARE WIDTH rather than a trailing
        # stretch taking it. It reflows from the width it is GIVEN, so a
        # layout that hands it only what it asks for is a chicken and an
        # egg: it laid out one column deep, which made it narrow, which
        # kept it one column deep — eight rows tall, for ever. The stretch
        # factor is what lets it see the room it has to fill.
        line.addWidget(self._role_filter(row), 1)
        self._picks_row = row
        return row

    def _role_filter(self, parent) -> QWidget:
        """The eight role floors, beside the strip they cut.

        The widget is `rolebar.RoleFilter` — it lives beside the Roles
        card it is the other half of, and shares that card's reflow so
        neither can weld the Draft tab wide again. This method is what
        connects it to the settings file.
        """
        wanted = ui_settings.clean_roles(self.settings.get("pick_roles"))
        box = rolebar.RoleFilter(wanted, parent)
        box.picked.connect(self._roles_picked)
        self.role_filter = box
        # Kept for every caller that reads the boxes by role.
        self.role_boxes = box.boxes
        return box

    def _roles_picked(self, _value: int = 0) -> None:
        """Remember the figures and re-cut the strip."""
        picked = self._picked_roles()
        if picked == dict(self.settings.get("pick_roles") or {}):
            return
        self.settings["pick_roles"] = picked
        ui_settings.save(self.settings)
        # The strip is only redrawn when a PICK changes, so without this
        # the new filter would sit in the file until the next hero was
        # picked — the same trap the count boxes carry a note about.
        self._refresh_views()

    def _badge_box(self, key: str):
        """The count beside a mark. Nought is none.

        NO CEILING TIED TO THE SUGGESTION COUNT, at the user's request -
        "remove the 5 cap on the heart and shield qty, as now I have the
        filter here". The two boxes sit beside the suggestion count on
        the same row, so the relationship is visible rather than needing
        enforcing, and a ceiling that moved under the cursor as the strip
        re-cut was worse than a number that is simply larger than it can
        be used. The strip still caps what it DRAWS - it cannot mark a
        tile that is not there - so a big number is harmless.
        """
        box = chrome.CountBox(
            ui_settings.clamp_marks(self.settings.get(key, 3), 3),
            0, ui_settings.MAX_SHOWN)
        box.setToolTip(
            "How many of the suggestions carry this mark. The number "
            "inside each one is its rank, so 1 is the best of them.\n"
            "Nought turns the mark off.")
        box.valueChanged.connect(lambda value, k=key: self._set_count(k, value))
        self.count_boxes[key] = box
        return box

    def _set_count(self, key: str, value: int) -> None:
        if self.settings.get(key) == value:
            return
        # THE MARKS MAY BE NOUGHT and the strips may not: a strip showing
        # nothing is a card with a hole in it, where no marks is a
        # perfectly ordinary thing to want.
        clamp = (ui_settings.clamp_marks if key.endswith("_count")
                 else ui_settings.clamp_count)
        self.settings[key] = clamp(value, value)
        ui_settings.save(self.settings)
        self._refresh_views()

    def _match_grid_portraits(self) -> None:
        """Keep the grids' idea of the box in step with the picks'.

        **THE PICKS SET IT NOW, AND THE GRIDS FOLLOW**, which reverses the
        rule this used to enforce. It took the SMALLER of what the two
        cards could draw and brought the picks down to meet it — one number
        for every portrait in the window, at the price that counters, which
        is six sections across where everything else is five, decided the
        size of the ten picks at the top. On a real 5v5 that is what made
        the pick tiles sit small and adrift in the middle of their card
        with a wide margin either side: "they should be scaling to reach
        the end margins".

        So each region fills ITS OWN card and the portrait size follows
        from how many are across it. The picks are five across and fill
        theirs, which sets the app's box; synergy is also five across, so
        it lands on exactly the same number and its grid reaches the same
        left and right edges as the picks above it. Counters is the one
        exception and can only be: with a portrait column down the side it
        is six across, so it fills its card at about five sixths of the
        size. Dropping that column — putting each row's face into its own
        cells the way synergy does — is the single change that would make
        all three equal again, and it has not been made.

        A grid may still only make its own portrait SMALLER than the pick
        (`_portrait_want` against `_portrait_room`), so nothing in the
        window is ever bigger than the tile it is advice about. What is
        left here is keeping the strips and grids in step when the panel
        has resized without a signal reaching them.

        IDEMPOTENT, and that is not a nicety: this runs from
        `resizeEvent`, and telling the strips a size resizes them, which
        lays the window out again, which calls this again. Without the
        guard that is an unbounded loop and Qt ABORTS the process — no
        exception, no traceback. The old rule had the same guard on the
        cap it computed; the guard has to move with the value.
        """
        panels = list(getattr(self, "team_panels", {}).values())
        if not panels:
            return
        tile = panels[0].slots[0] if panels[0].slots else None
        if tile is None or tile.width() <= 0:
            return
        box = (tile.width(), tile.height())
        if box == getattr(self, "_box_applied", None):
            return
        self._box_applied = box
        self._resize_strips(*box)

    def resizeEvent(self, event) -> None:       # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._remember_place()
        self._match_grid_portraits()

    def moveEvent(self, event) -> None:         # noqa: N802 - Qt naming
        super().moveEvent(event)
        self._remember_place()

    def _remember_place(self) -> None:
        """Keep the last geometry the window had as an ORDINARY window.

        `normalGeometry` is Qt's own answer to this and it is only half
        an answer: measured here it gives back the right SIZE while a
        window is maximised and a position of (0, 0) — so relying on it
        would have remembered the size correctly and forgotten the place
        every time the window was closed maximised, which is the exact
        fault the height had before today. Tracking it while it is
        happening cannot be wrong about either, and does not depend on a
        platform behaving the way the documentation reads.
        """
        if not self.isMaximized() and not self.isMinimized():
            self._normal_box = self.geometry()

    def _resize_strips(self, width: int, height: int) -> None:
        """The picks decided how big a tile is; the strips follow.

        One box for every tile in the app, so a suggestion is the size of a
        pick and the blank plates before the game are the size of the tiles
        after it. The item strip takes the HEIGHT and keeps its own width,
        because an 88x64 icon in a 16:9 box is dead space either side of
        every item.
        """
        # The connection is made as soon as the panels exist, which is
        # before the strips do; a widget that is not built yet has no size
        # to be told about.
        picks = getattr(self, "suggest_row", None)
        items = getattr(self, "item_row", None)
        if picks is None or items is None:
            return
        width = max(1, round(width * STRIP_OF_PICK))
        height = max(1, round(height * STRIP_OF_PICK))
        picks.set_tile_size(width, height)
        items.set_tile_size(width, height)
        # And the grids' portraits follow the same box. They had a size of
        # their own (`HEADER_ICON_MAX`), so the same hero was one size at
        # the top of the window and another in the grid under it.
        for grid in (self.synergy_matrix, self.matchup_matrix):
            grid.set_tile_width(width)
        # Bigger tiles means fewer fit on a row, and the default count is
        # "however many fit on one row" — so the strips have to be redrawn
        # or the number stays at whatever the old size allowed.
        if (not self.settings.get("suggested_picks")
                or not self.settings.get("suggested_items")):
            self._refresh_views()

    def _row_capacity(self, key: str) -> int:
        """How many tiles fit across the strip as it is RIGHT NOW."""
        # getattr: the count box is built BEFORE the strip it measures —
        # the heading is what it rides on — so on the first pass there is
        # nothing to measure and the window's own width stands in.
        strip = getattr(
            self, "suggest_row" if key == "suggested_picks" else "item_row",
            None)
        width = strip.width() if strip is not None else 0
        if width <= 1:                      # before the first layout pass
            width = max(0, self.width() - 60)
        # The strip's OWN tile width, not the module constant: the tiles
        # grow with the window now, so a fixed 78 would answer this
        # question for a size the strip stopped being.
        tile = strip.tile_width() if strip is not None else tilekit.STRIP_W
        return fits_in_one_row(width, tile)

    def _how_many(self, key: str) -> int:
        """A strip's cap. A CAP, not a quota, and auto until you set it.

        `0` in the settings means "as many as fit on one row", which is the
        default because it is the number that looks right at whatever size
        the window happens to be — a fixed eight is too many on a narrow
        window and too few on a wide one. Setting the box makes it yours
        and it stops moving.

        The item strip stops at whatever clears the severity floor either
        way, so raising this does not manufacture advice — it only stops
        advice that was already worth showing from being cut off.
        """
        stored = self.settings.get(key, ui_settings.DEFAULTS[key])
        if not stored:
            return self._row_capacity(key)
        return ui_settings.clamp_count(stored, self._row_capacity(key))

    def _update_suggestions(self, draft: scoring.DraftState) -> None:
        """The top of the ranked list, as a strip above the items.

        Same numbers as the History tab, same order — this is that list's
        head, not a second opinion. It stays quiet until at least one hero
        is on the board: with an empty draft every fit is zero, so a strip
        of "+0.0" would be ranking nothing and inviting the user to read it
        as a recommendation.
        """
        if not draft.allies and not draft.enemies:
            # THE BLANKS ARE THE COUNT THIS STRIP IS SET TO. An empty
            # panel is the SHAPE of its answer, and five plates under a
            # strip set to twenty is the wrong shape — the card grew the
            # moment the first pick landed. `_how_many` also resolves
            # nought, which means "as many as fit on one row", so the
            # plates then fill the width exactly.
            self.suggest_row.show_heroes(
                [], blanks=self._how_many("suggested_picks"))
            return
        # ONE LABELLED LINE PER FIGURE, at the user's request. It was a
        # sentence — "fit +12.43  (vs +6.46, with +5.97)" — carrying a
        # total and its two parts in one line, and the total is already
        # the badge on the tile. So the parts are named and the sum is
        # left where it is drawn.
        # FILTERED BEFORE IT IS CUT. Taking the top twenty and then
        # dropping the ones that miss the filter would show however many
        # of the top twenty happened to qualify — which is a different
        # answer, and a worse one: with Durable ticked it could show two
        # heroes while the list held forty more.
        wanted = self._picked_roles()
        ranked = [s for s in self.scored if self._has_roles(s.hero_id, wanted)]
        rows = [
            (s.hero_id, s.name, s.score,
             f"{s.name}\nCounter Score = {s.vs_total * 100:+.1f}"
             f"\nSynergy Score = {s.with_total * 100:+.1f}")
            for s in ranked[:self._how_many("suggested_picks")]
        ]
        # A FILTER MATCHING NOTHING SAYS SO. An empty strip is
        # indistinguishable from the app having stopped working, which is
        # the lesson the hero picker's refused rows already carry.
        self.suggest_row.show_heroes(rows, empty=(
            "No hero left in the draft is "
            + ", ".join(f"{role} {least}" for role, least in wanted.items())
            + " — turn one down to widen it."
            if wanted and not rows else ""),
            blanks=self._how_many("suggested_picks"))
        # AFTER `show_heroes`, always: it destroys every tile and builds
        # new ones, so a mark applied before this is a mark on a widget
        # that no longer exists.
        self.suggest_row.set_stars(self.stars, self._heart_count())
        self.suggest_row.set_shields(self.shields, self._shield_count())

    def _picked_roles(self) -> dict[str, int]:
        """Role -> the lowest rating asked for, in Valve's own order.

        Nought is not stored: it is the filter being off, and a dict of
        every role with most of them nought would be seven dead keys in
        everybody's settings file.
        """
        boxes = getattr(self, "role_boxes", None)
        if not boxes:
            return {}
        return {role: box.value() for role, box in boxes.items()
                if box.value() > 0}

    @staticmethod
    def _has_roles(hero_id: int, wanted: dict[str, int]) -> bool:
        """Does this hero clear the rating asked for in every role set?

        A hero the bundled table has no figures for at all fails a filter
        rather than passing it: the strip is being cut to heroes that
        ANSWER something, and "we do not know" is not an answer. With
        nothing set there is no filter and every hero is through, so a
        hero added in a patch is only ever missing from a FILTERED strip.
        """
        if not wanted:
            return True
        levels = roles_mod.levels_for(hero_id)
        return bool(levels) and all(levels.get(role, 0) >= least
                                    for role, least in wanted.items())

    def _recompute_shields(self) -> None:
        """Which heroes the field struggles to counter, from the DATASET.

        Nothing to do with the History tab: this needs no match history,
        so it is filled on a fresh install with no account ever measured,
        and it appears on heroes nobody has picked. Recomputed when the
        dataset or the bar changes, never per tile - it is one pass over
        the matrix and the strip is rebuilt on every pick.
        """
        from ..history import analyse as analyse_mod

        try:
            # NO BAR PASSED. The mark is a share of the strip now, so
            # every hero's standing comes back and the strip ranks the
            # ones it is showing; the floor inside `shield_report` is
            # only what its sentence counts against.
            self.shields, self.shields_note = analyse_mod.shield_report(
                self.ds)
        except Exception as bad:           # noqa: BLE001 - never fatal
            # STILL NEVER FATAL - a missing or malformed dataset must not
            # take the app down - but no longer SILENT. This swallow is
            # what kept the mark's absence indistinguishable from a mark
            # nothing qualified for, and that is the state it shipped in.
            self.shields = {}
            self.shields_note = (
                f"The shields could not be worked out: "
                f"{type(bad).__name__}: {bad}")
        window = getattr(self, "settings_window", None)
        if window is not None:
            window.set_shield_note(self.shields_note)

    def _heart_count(self) -> int:
        """How many suggestions may carry a heart."""
        return ui_settings.clamp_marks(self.settings.get("heart_count", 3), 3)

    def _shield_count(self) -> int:
        """How many suggestions may carry a shield."""
        return ui_settings.clamp_marks(
            self.settings.get("shield_count", 3), 3)

    def _history_run_changed(self, report) -> None:
        """The History tab loaded, ran or cleared a run.

        Recomputed HERE rather than read per tile: it is one pass over a
        few hundred matches and two rankings, and the suggestion strip is
        rebuilt on every pick — doing it there would rank the same run
        again for every hero of every draft.
        """
        from ..history import stars as stars_mod

        matches = getattr(report, "matches", None)
        # NO FLOORS. Whether a hero is marked is decided by the strip
        # against what it is showing; what `measure` decides is only
        # whether there is enough behind a hero to rank it at all.
        self.stars = None if not matches else stars_mod.measure(matches)
        # The tiles are already on screen, so this is the whole update —
        # no pick changed and nothing needs re-scoring.
        self.suggest_row.set_stars(self.stars, self._heart_count())
        # And the row at the top says whose run it is. Same signal, same
        # moment: the star bars and the face must never describe two
        # different accounts.
        self.account_row.show_report(report)
        # THE NAME, not the row's display text. With nothing measured the
        # row says "No account measured yet" — a sentence, right for a
        # callout and four times too long for a title bar, where the
        # button says "No account" instead. Passing "" is how the button
        # is told there is no name, and it chooses its own short form.
        self.profile_button.show_name(
            self.account_row.who.text() if matches else "")

    def _show_history_tab(self) -> None:
        """Clicking the account row opens the tab that fills it.

        A row that says "no account measured yet" and does nothing when
        pressed is a prompt with no way to act on it.
        """
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == "History":
                self.tabs.setCurrentIndex(index)
                return

    def _update_items(self, draft: scoring.DraftState) -> None:
        """The strip is live from the first enemy pick.

        It used to wait until the user's own hero was locked in, which made
        it blank for the whole of the draft — the one stretch where knowing
        that their line-up demands a Nullifier would change what you pick.
        Role and own-hero filtering still apply once those are known; they
        just no longer gate the whole panel.
        """
        enemy_names = [self.ds.name(h) for h in draft.enemies]
        ally_names = [self.ds.name(h) for h in draft.allies
                      if h != draft.my_hero]
        if not enemy_names and not ally_names:
            self._last_advice = []
            self.item_row.show_items(
                [], blanks=self._how_many("suggested_items"))
            return
        advice = items_mod.recommend(
            self.rules, enemy_names, ally_names, draft.my_role,
            self.rules_meta.get("current_patch", "0.0"),
            max_shown=self._how_many("suggested_items"))
        # No sentence when there is nothing to flag: silence IS the answer
        # here, and the empty plates already say the strip is working and
        # has nothing for you.
        # Kept so a click on a tile can be answered without recomputing
        # the advice — and so the answer is the one on screen.
        self._last_advice = advice
        self.item_row.show_items(
            advice, blanks=self._how_many("suggested_items"))
        # One missing icon is normal; NONE at all means the pack has never
        # been fetched, and a strip of grey plates looks broken rather than
        # unconfigured.
        if advice and not item_icons.any_downloaded():
            self.item_row.set_note(
                "No item icons on disk yet — run Settings ▸ Downloads "
                "▸ Item icons, which says why if any of them fail.")
        else:
            self.item_row.set_note("")

    # ---- status / debug ------------------------------------------------
    def _say(self, message: str, millis: int = 6000) -> None:
        """A transient status message the refresh loop will not stamp on.

        `_update_status` writes the whole line four times a second with no
        timeout, and a QStatusBar replaces a timed message with the next
        one it is given — so every "Board cleared" and "Loaded 62 item
        rules" in this app appeared for under a quarter of a second and
        was gone. Which is why pressing a button and seeing nothing happen
        was the report: the button HAD said something.
        """
        self._quiet_until = time.monotonic() + millis / 1000.0
        self.status.showMessage(message, millis)

    def _update_status(self, snap) -> None:
        """One short line: what is wrong, what is bound, what is happening.

        It used to run to seven segments — the mode, the line-up source,
        the game state, the statistics age, the ranked bracket, a count of
        item rules unverified this patch — most of which are settings the
        user chose and none of which change while a draft runs. The one
        thing a status line is for is the state, so what is left is: what
        is wrong, whether the app has found Dota's window, and what it is
        doing with it. Pipes between, nothing else.
        """
        if time.monotonic() < self._quiet_until:
            # Something the user just did is on the line and has not had
            # its few seconds yet. The state will still be here after.
            return
        parts = []
        if snap.warning:
            # The warning LEADS. It used to sit fourth, which is how "no
            # data from Dota" went unread through a whole ranked game.
            parts.append(snap.warning)
        if snap.stalled:
            parts.append("CAPTURE STALLED — the window may have stopped "
                         "presenting")
        # WHICH WINDOW. A frame the wrong size for the monitor is the tell
        # that capture bound to something other than Dota, and a session
        # once spent a whole draft capturing a File Explorer window called
        # "Dota_Draft_Assist" without anything on screen saying so.
        target = self._capture_target()
        if target == DOTA_TITLE:
            parts.append("Dota window: found")
        elif target and target != "(nothing bound)":
            parts.append(f"bound to: {target}")
        else:
            parts.append("Dota window: not found")
        parts.append(snap.mode)
        if snap.game_state:
            parts.append(snap.game_state.replace("DOTA_GAMERULES_STATE_", ""))
        # WHAT THE SCREEN READER IS DOING. At strategy time the game
        # fills the slots itself, so a full board said nothing about
        # whether recognition had run - and the portrait search takes
        # seconds on a worker with nothing on screen to say so, which is
        # long enough to close the app in the middle of.
        note = getattr(snap, "vision_note", "")
        if note:
            parts.append(note)
        server = getattr(self.provider, "server", None)
        if server is not None and getattr(server, "recording", False):
            parts.append(f"REC {server._archived}")
        if self.ds.is_empty:
            # The one thing about the statistics still worth a segment: with
            # none at all, nothing below is advice.
            parts.append("no statistics — Settings ▸ Downloads ▸ Statistics and portraits")
        # NOT `_say`: this is the state, written every tick with no
        # timeout. Through `_say` it would claim the line for six seconds
        # on every tick and the guard above would then silence it forever.
        self.status.showMessage(" | ".join(parts))

    def _update_debug(self, snap) -> None:
        # NOTHING here is worth doing while the tab is hidden. It draws an
        # overlay onto a full-resolution frame, converts it to a QImage and
        # smooth-scales it — four times a second, over a game, into a
        # widget nobody is looking at. That was most of the stutter.
        if not self.debug_image.isVisible():
            return
        set_log(self.timing_text, LOOP.report())
        if snap is None:
            return
        # Debug shows the RAW per-frame read (live confidences, flicker and
        # all); the draft panels show the stabilised one.
        read = snap.read_raw or snap.read
        if snap.frame is None or read is None:
            set_log(self.debug_text, 
                f"mode={snap.mode}  gate score={snap.gate_score:.3f}  "
                f"frames arrived={snap.frames_arrived}\n"
                "No recognised frame yet. In demo mode there is no frame at "
                "all; live and replay show the captured frame with crop "
                "boxes here as soon as recognition runs.")
            return
        from ..vision.debug import draw_overlay
        overlay = draw_overlay(snap.frame, read, self._hero_names())
        h, w = overlay.shape[:2]
        self._show_picture(overlay)
        lines = [f"gate score: {snap.gate_score:.3f}   "
                 f"frames arrived: {snap.frames_arrived}   "
                 f"frame: {w}x{h}   "
                 f"capturing: {self._capture_target()}"]
        # Ten UNKNOWNs is the CORRECT answer when the pick bar is not on
        # screen, and this log has already been read as "the crop boxes are
        # broken" during a team showcase. Say which screen it is looking at
        # rather than leaving the reader to infer it from ten failures.
        state = (snap.game_state or "").replace("DOTA_GAMERULES_STATE_", "")
        if not state:
            # BLANK IS THE COMMONEST CASE AND WAS THE ONE NOT COVERED.
            # The guard here used to be `if state and ...`, so a blank
            # one - Dota open, sitting in the menu, no match - fell
            # through and printed ten failures with nothing saying why.
            # That is exactly when somebody presses Copy everything, and
            # a log that reads as ten broken crop boxes at the moment
            # nothing is on screen is worse than no log.
            lines.append(
                "NOTE: the game is not in a match, so there is no pick "
                "bar on screen — every slot reading UNKNOWN here is "
                "RIGHT and says nothing about the crop boxes. Judge them "
                "during hero selection.")
        elif state not in _DRAFT_STATE_NAMES:
            lines.append(
                f"NOTE: the game is at {state}, not the pick screen — the "
                "pick bar is not up, so every slot reading UNKNOWN here is "
                "right. Judge the crop boxes during hero selection.")
        for s in read.slots:
            resolved = ("UNKNOWN" if s.hero_id is None else
                        "EMPTY" if s.hero_id == -1 else self.ds.name(s.hero_id))
            lines.append(f"{s.rect.team}{s.rect.slot}: {resolved:20s} "
                         f"nearest={s.best_label} d={s.distance} m={s.margin}")
        set_log(self.debug_text, "\n".join(lines))

    def _capture_target(self) -> str:
        """The window the frames are coming from, by name.

        A frame that is the wrong SIZE for the monitor is the tell that the
        app bound to something other than Dota, and the log printed the
        size without ever saying what it was a picture of.
        """
        session = self._capture_session()
        return getattr(session, "capture_title", None) or "(nothing bound)"

    def _show_picture(self, picture) -> None:
        """Put a BGR frame in the debug view, at the view's size."""
        height, width = picture.shape[:2]
        img = QImage(picture.tobytes(), width, height, 3 * width,
                     QImage.Format.Format_BGR888)
        # INTO THE CONTENTS, not the whole widget: this label is a card,
        # so a 1px border is drawn round it and a picture fitted to the
        # full rectangle is two pixels taller than the room it has. That
        # difference is also what used to make the view grow on every
        # tick — see `FrameView.minimumSizeHint`.
        self.debug_image.show_frame(
            QPixmap.fromImage(img).scaled(
                self.debug_image.contentsRect().size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation),
            width, height)

    def _copy_debug_log(self) -> None:
        """Everything needed to diagnose one game, in one paste.

        Four separate things had to be selected and copied by hand, from
        panels that rewrite themselves four times a second. Gathering them
        here is the difference between "send me the log" being a minute's
        work and being a chore nobody does.
        """
        snap = self.snapshot
        parts = [
            "=== Dota Draft Assist ===",
            f"status: {self.status.currentMessage()}",
            f"data: {self.ds.meta.get('pair_source', '?')} · "
            f"{self.ds.age_hours():.1f}h old · "
            f"brackets {self.ds.meta.get('target_brackets', '?')}",
            f"app icon: {appicon.describe()}",
            f"taskbar identity: {appicon.identity_note}",
            f"window icon: {appicon.window_icon_note}",
            f"start menu: {appicon.shortcut_note}",
            "",
            "--- what the app is reading ---",
            self.unknown_label.text(),
            self.manual_hint.text(),
        ]
        if snap is not None:
            parts += [
                f"mode={snap.mode} source={snap.source!r} "
                f"lineup_source={getattr(snap, 'lineup_source', '')!r}",
                f"game_state={snap.game_state!r} "
                f"gate={snap.gate_score:.3f} "
                f"frames_arrived={snap.frames_arrived} "
                f"frame={'yes' if snap.frame is not None else 'none'}",
                f"allies={[self.ds.name(h) for h in snap.left]}",
                f"enemies={[self.ds.name(h) for h in snap.right]}",
            ]
            for note in getattr(snap, "gsi_notes", []) or []:
                parts.append(f"note: {note}")
        parts += ["", "--- recognition log ---", self.debug_text.toPlainText(),
                  "", "--- loop timings (ms) ---", LOOP.report()]
        QApplication.clipboard().setText("\n".join(parts))
        self._say("Copied — paste it wherever you are reporting this.", 6000)

    def _hero_names(self) -> dict[int, str]:
        """Every hero's name, built once per dataset rather than per tick."""
        if getattr(self, "_names_for", None) is not self.ds:
            self._names_for = self.ds
            self._names = {hid: self.ds.name(hid) for hid in self.ds.hero_ids}
        return self._names

    def _restore_position(self) -> None:
        """Open where it was closed, at the user's request.

        The size was already remembered and the place was not, which is
        half of "where I left it" — and on an always-on-top window that
        is deliberately parked clear of the game, the place is the half
        that took the arranging.

        Nothing is restored on a first run (both keys are None, so the
        window manager places it), and nothing is restored onto a screen
        that is not there any more: `reachable` either nudges the point
        until a piece of the title bar can be grabbed or says the spot
        has gone, because the title bar is the only thing that moves this
        window and a window opened outside every display is unreachable
        rather than merely misplaced.
        """
        x, y = self.settings.get("window_x"), self.settings.get("window_y")
        if x is None or y is None:
            return
        where = chrome.reachable(QPoint(int(x), int(y)), self.size())
        if where is not None:
            self.move(where)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        # The size it was left at, so an unlocked window reopens where the
        # user left it rather than at the built-in 1240x820.
        #
        # THE NORMAL SIZE, NEVER THE MAXIMISED ONE, and that distinction
        # is what "the window height has randomly stretched very tall out
        # of the screen" actually was. `height()` while maximised is the
        # maximised height — and a FRAMELESS window maximised on Windows
        # overhangs the work area rather than fitting it — so closing
        # maximised wrote a height bigger than the screen, which the next
        # start applied with `resize()` as an ORDINARY size. The window
        # then opened taller than the display every time, with the one
        # resize handle it had off the bottom of it. One double-click on
        # the title bar and a close was the whole recipe.
        #
        # `_normal_box` is the last geometry this window had as an
        # ORDINARY window, tracked as it happens (`_remember_place`).
        # Qt's own `normalGeometry` looked like the answer and is only
        # half of one: measured here it gives the right SIZE while
        # maximised and a position of (0, 0), so it would have carried
        # the height fix and quietly reintroduced the same fault in the
        # PLACE. It is None before the window has ever been laid out, so
        # the live geometry is still the fallback.
        box = getattr(self, "_normal_box", None)
        if box is None or box.isEmpty():
            box = self.geometry()
        self.settings["window_w"] = int(box.width())
        self.settings["window_h"] = int(box.height())
        # The PLACE as well as the size, and off the same rectangle for
        # the same reason: a maximised window's position is the corner of
        # the screen, not the corner the user put it at, so saving the
        # live one would forget where it lives every time it is closed
        # maximised — exactly the fault the height had.
        self.settings["window_x"] = int(box.x())
        self.settings["window_y"] = int(box.y())
        ui_settings.save(self.settings)
        # A modeless task owns a subprocess that would otherwise keep POSTing
        # to a port nobody is listening on any more.
        for dialog in list(self._open_tasks):
            dialog.close()
        # And a match-history run owns a thread. A QThread destroyed while
        # it is still running takes the process down with it.
        self.history_tab.shutdown()
        super().closeEvent(event)

    def _save_snapshot(self) -> None:
        """Dump exactly what the app sees right now: the captured frame, the
        overlay with crop boxes, the ten slot crops, and the per-slot match
        record. This folder is the unit of evidence — commit it and the
        whole failure is reproducible offline."""
        snap = self.snapshot
        frame = snap.frame if snap is not None else None
        if frame is None:
            # Running on game data there is no live frame, but a snapshot is
            # exactly what is needed to anchor overlay positions — so grab
            # one from the Dota window on demand.
            frame = self._grab_dota_frame()
        if frame is None:
            self.snapshot_label.setText(
                "Nothing to capture: Dota must be running in borderless "
                "windowed mode (demo mode has no frame at all).")
            return
        if snap is not None:
            snap.frame = frame
        from ..vision import debug as debug_mod
        from ..vision import library as library_mod
        from ..vision.recognize import read_draft
        names = {hid: self.ds.name(hid) for hid in self.ds.hero_ids}
        read = snap.read_raw if snap is not None else None
        session = getattr(self.provider, "session", None)
        if session is not None:
            read = read_draft(frame, session.layout, session.lib,
                              session.params, keep_crops=True)
        if read is None:
            # No recognition ran (game-data mode): save the frame with the
            # current slot boxes drawn on it, which is what calibration
            # needs anyway.
            from ..vision.layout import load_layout
            from ..vision.recognize import DraftRead, SlotRead, crop_rect
            layout = load_layout()
            read = DraftRead(slots=[
                SlotRead(rect=rect, hero_id=None, best_label="(not matched)",
                         distance=0, margin=0, crop=crop_rect(frame, rect))
                for rect in layout.slots()])
        folder = debug_mod.dump(frame, read, names)
        try:
            params = library_mod.load_params()
            params_line = (f"hash_size={params.hash_size} "
                           f"max_distance={params.max_distance} "
                           f"min_margin={params.min_margin}\n")
        except Exception:
            params_line = "recognition params unavailable\n"
        (folder / "context.txt").write_text(
            f"mode={getattr(snap, 'mode', '?')}\n"
            f"source={getattr(snap, 'source', '?')}\n"
            f"game_state={getattr(snap, 'game_state', '')}\n"
            f"warning={getattr(snap, 'warning', '')}\n"
            f"frame_size={frame.shape[1]}x{frame.shape[0]}\n"
            f"gate_score={getattr(snap, 'gate_score', '')}\n"
            f"frames_arrived={getattr(snap, 'frames_arrived', 0)}\n"
            + params_line, encoding="utf-8")
        self.snapshot_label.setText(f"Saved to {folder}")
        self._say(f"Snapshot saved to {folder}", 8000)

    def _grab_dota_frame(self):
        """One-shot capture of the Dota window, independent of the current
        draft source."""
        from ..capture.oneshot import capture_once
        from ..capture.window import DOTA_TITLE, find_dota_window_title
        title = find_dota_window_title() or DOTA_TITLE
        return capture_once(title)


def make_provider(args, ds: Dataset, manual: ManualDraft):
    """Choose the draft source.

    The default is BOTH, because neither is sufficient alone. Recordings of
    real matches show GSI names no hero at all during hero selection, so a
    GSI-only app is blind for the whole draft — the only moment the advice
    matters. Screen capture reads the picks; GSI says when a draft is
    happening and which side you are on, which is what makes the pixels
    interpretable without asking the user anything.

    `--no-vision` for game data alone, `--vision` for the screen alone.
    """
    from .providers import (DemoProvider, GsiProvider, HybridProvider,
                            LiveProvider, ManualProvider, ReplayProvider)
    if args.demo:
        return DemoProvider(ds)
    if args.manual:
        return ManualProvider(manual)

    if args.replay:
        session = _capture_session()
        if session is None:
            raise SystemExit("replay needs the portrait library — run "
                             "Data > Update statistics first")
        return ReplayProvider(session, Path(args.replay))

    if args.vision:
        session = _capture_session()
        if session is None:
            raise SystemExit("screen capture needs the portrait library — "
                             "run Data > Update statistics first")
        return LiveProvider(session, title=args.window)

    from ..gsi import install as gsi_install
    from ..gsi.server import GsiServer
    # No install hint here: GsiProvider diagnoses the silence itself,
    # naming the one broken link rather than guessing at the first one.
    server = GsiServer(args.port, token=gsi_install.read_installed_token())
    gsi = GsiProvider(ds, server, manual)
    if args.no_vision:
        return gsi
    session = _capture_session()
    if session is None:
        return gsi          # no portraits yet; the banner says to fetch them
    return HybridProvider(gsi, LiveProvider(session, title=args.window))


def _capture_session():
    """A capture session, or None when there are no portraits to match
    against. Missing portraits must not stop the app opening — the first
    run has none, and the banner exists to say so."""
    from ..capture.session import CaptureSession
    from ..vision import library
    from ..vision.layout import load_layout
    try:
        params = library.load_params()
        lib = library.load(expected_hash_size=params.hash_size)
    except FileNotFoundError:
        return None
    return CaptureSession(load_layout(), lib, params)


CRASH_LOG = DEBUG_OUT / "crash.log"


def _report_crash(exc: BaseException) -> None:
    """Windowless launch (pythonw) has no console, so an unhandled error
    must announce itself: write a log and show it, rather than the app
    simply never appearing."""
    import traceback
    text = "".join(traceback.format_exception(type(exc), exc,
                                              exc.__traceback__))
    try:
        CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
        CRASH_LOG.write_text(text, encoding="utf-8")
    except OSError:
        pass
    try:
        app = QApplication.instance() or QApplication([])
        box = QMessageBox(QMessageBox.Icon.Critical, "Dota Draft Assist",
                          "The application hit an unexpected error and has "
                          "to close.")
        box.setInformativeText(f"A copy of the details was saved to\n"
                               f"{CRASH_LOG}")
        box.setDetailedText(text)
        box.exec()
    except Exception:
        print(text, file=sys.stderr)


def main() -> None:
    # Pure ctypes, and it MUST run before the first window — so it stays
    # here, ahead of the QApplication. Nothing else about the icon may:
    # see `appicon.gui_ready`.
    appicon.claim_taskbar_identity()
    try:
        _main()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - last line of defence
        _report_crash(exc)
        sys.exit(1)


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true",
                        help="scripted fake draft; no dataset needed")
    parser.add_argument("--replay", metavar="DIR",
                        help="loop saved frames instead of live capture")
    parser.add_argument("--window", metavar="TITLE",
                        help="capture this window title instead of finding "
                             "the Dota client (also selectable in the app)")
    parser.add_argument("--no-vision", action="store_true",
                        help="game data only — do not read the screen "
                             "during hero selection")
    parser.add_argument("--vision", action="store_true",
                        help="use screen capture instead of game data")
    parser.add_argument("--manual", action="store_true",
                        help="enter the draft entirely by hand")
    parser.add_argument("--port", type=int, default=None,
                        help="port the GSI listener binds (default 53000)")
    args = parser.parse_args()
    if args.port is None:
        from ..gsi.install import DEFAULT_PORT
        args.port = DEFAULT_PORT

    if args.demo:
        from .demo import demo_dataset
        ds = demo_dataset()
    else:
        ds = store.load_or_empty()

    try:
        rules, meta = items_mod.load_rules(RULES_FILE)
    except Exception:
        rules, meta = [], {}

    app = QApplication(sys.argv)
    app.setApplicationName("Dota Draft Assist")
    # BEFORE the stylesheet: a family registered afterwards is not picked
    # up by rules Qt has already resolved, so the app would open in the
    # fallback face and only look right after a restyle.
    from . import fonts as ui_fonts
    ui_fonts.load_bundled()
    app.setStyleSheet(theme.STYLESHEET)
    app.setWindowIcon(appicon.icon())
    # THE SHORTCUT THE AppUserModelID RESOLVES TO. Declaring an ID stops
    # Windows treating this as pythonw.exe and makes it its own
    # application — after which the shell looks up that application's icon
    # and name through the Start-menu shortcut carrying the same string,
    # so claiming the identity without providing the shortcut left the
    # taskbar button with nothing to resolve to and drawing a blank page.
    # HERE rather than beside `claim_taskbar_identity` in `main`: it
    # renders an .ico, which touches a QPixmap, which ABORTS the process
    # when there is no QGuiApplication yet. It was called there once and
    # the app stopped opening at all, with no traceback. Still before the
    # window is built, which is what the taskbar needs.
    appicon.ensure_start_menu_shortcut()
    manual = ManualDraft()
    provider = make_provider(args, ds, manual)
    win = MainWindow(ds, provider, rules, meta, manual)
    win.show()
    # start() never raises for live capture: an unbound source is a state
    # the user fixes from the Capture menu, not a crash.
    started = provider.start()
    win.status.showMessage(f"started: {started}")
    win._refresh_sources()
    # After show(), because it is a modal dialog and one raised over a
    # window that has not appeared yet is a dialog with nothing behind it.
    win.offer_setup()
    if getattr(provider, "error", ""):
        win.snapshot_label.setText(provider.error.splitlines()[0])
    code = app.exec()
    provider.stop()
    sys.exit(code)


if __name__ == "__main__":
    main()

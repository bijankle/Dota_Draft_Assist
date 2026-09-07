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
import subprocess
import sys
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QImage, QKeySequence, QPixmap
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox,
                             QDialog, QFrame,
                             QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QFileDialog,
                             QMainWindow, QMenuBar, QMessageBox,
                             QPlainTextEdit,
                             QDoubleSpinBox, QListWidget,
                             QPushButton,
                             QScrollArea, QSlider, QSplitter,
                             QTableWidget,
                             QTableWidgetItem, QTabWidget,
                             QToolBar, QVBoxLayout, QWidget)

from ..config import (CALIBRATION_FILE, DEBUG_OUT, RECORDINGS_DIR,
                       REPO_ROOT, RULES_FILE, pair_source,
                       save_pair_source, save_target_brackets,
                       target_brackets)
from ..data import store
from ..data.store import Dataset
from ..timing import LOOP
from ..vision import harvest
from ..model import items as items_mod
from ..model import scoring
from . import settings as ui_settings
from .. import record as record_mod
from . import theme
from .bracket_dialog import BracketDialog
from . import appicon
from .chrome import ResizeGrip, TitleBar
from .hero_picker import HeroPickerDialog
from . import item_icons
from . import portraits
from .framebox import FrameView
from .item_row import ItemRow
from .suggest_row import MAX_SHOWN as SuggestRow_MAX
from .suggest_row import SuggestRow
from .manual import ManualDraft
from .tables import (BreakdownPanel, MatrixTable, ValueItem,
                     minimum_grid_width)
from .task_dialog import TaskDialog
from .teams import TeamPanel, minimum_panel_width
from .tasks import TASKS

# Loose mapping from queued position to OpenDota hero role tags, used ONLY
# for the visual highlight (the list itself is never filtered by role).
ROLE_TAGS = {
    "carry": {"Carry"},
    "mid": {"Carry", "Nuker"},
    "offlane": {"Initiator", "Durable"},
    "soft_support": {"Support", "Disabler"},
    "hard_support": {"Support"},
}
ROLE_LABELS = [("(no role)", None), ("Carry (1)", "carry"), ("Mid (2)", "mid"),
               ("Offlane (3)", "offlane"), ("Soft support (4)", "soft_support"),
               ("Hard support (5)", "hard_support")]
# The slot menu says "Pos 1"; the scoring layer says "carry". One mapping,
# in one place, so the two cannot drift apart.
ROLE_BY_LABEL = {"Pos 1": "carry", "Pos 2": "mid", "Pos 3": "offlane",
                 "Pos 4": "soft_support", "Pos 5": "hard_support"}
HIGHLIGHT = QColor(theme.HIGHLIGHT_ROW)


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


def card(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setProperty("card", True)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 12)
    layout.setSpacing(8)
    if title:
        label = QLabel(title)
        label.setProperty("heading", True)
        layout.addWidget(label)
    return frame, layout


class MainWindow(QMainWindow):
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
        # The hero whose relations the other nine slots are showing, as
        # (side, hero id). Clicking it again clears it; it survives a
        # refresh but not the hero leaving the draft.
        self.focus: tuple[str, int] | None = None
        # Rectangles drawn on the debug picture during drag calibration.
        self._drag_rects: list[tuple[int, int, int, int]] = []
        # Heroes whose alternative portrait has been learned this session,
        # so a draft's worth of frames writes one file rather than hundreds.
        self._learned: set[int] = set()
        # A frame loaded from disk, so calibration does not need Dota to be
        # on screen at the moment the user has time to do it.
        self._still = None
        self.scored: list[scoring.ScoredHero] = []
        self.settings = ui_settings.load()
        self.setWindowTitle("Dota Draft Assist")
        self.setWindowIcon(appicon.icon())
        # Frameless: Windows' own title bar is a white strip above a dark
        # app and reads as a different program bolted on top. The cost is
        # that the drag and the resize corner have to be put back by hand,
        # which `ui/chrome.py` does.
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint)
        # The narrowest honest width. Two things are competing for it —
        # five matrix columns wide enough to print "+12.34", and five pick
        # tiles wide enough to still show a portrait — so the floor is
        # whichever of them needs more, doubled for the two halves.
        self.setMinimumWidth(
            2 * max(minimum_grid_width(), minimum_panel_width()) + 44)
        self.resize(1240, 820)
        self._build_menus()
        self._build()
        self._refresh_sources()
        self._sync_source_controls()
        self._update_first_run_banner()
        self.setWindowOpacity(
            float(self.settings.get("overlay_opacity", 0.7)))
        # Not shown here: it appears only when the window is hidden, so the
        # app is never two windows at once.
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(300)

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
        # NOT self.menuBar(): QMainWindow puts that above the central
        # widget, which would leave a menu strip sitting on top of our own
        # title bar. It goes inside the bar instead, the way Steam does it.
        bar = QMenuBar()
        self.menu_bar = bar

        setup_menu = bar.addMenu("&Setup")
        # The three downloads live together rather than as three siblings
        # of everything else: they are one idea — go and fetch the pictures
        # and numbers — and a menu you have to read twice is a menu that
        # has stopped helping.
        downloads = setup_menu.addMenu("&Download")
        self._act(downloads, "&Statistics and portraits…",
                  lambda: self.run_task("update_data"), "Ctrl+U",
                  "The hero numbers and Valve's base portrait for each")
        self._act(downloads, "&Alternative portraits…",
                  lambda: self.run_task("fetch_custom_portraits"), None,
                  "Persona, arcana and custom-set pictures, so a set "
                  "portrait stops reading as UNKNOWN")
        self._act(downloads, "&Item icons…",
                  lambda: self.run_task("fetch_item_icons"), None,
                  "Just the item pictures, with the reason if it fails")
        self._act(setup_menu, "Statistics &bracket…", self._choose_brackets,
                  None, "Which ranks the statistics are drawn from")
        self._act(setup_menu, "Choose app &icon…", self._choose_app_icon,
                  None, "Use your own .ico or .png for the window and the "
                        "taskbar")
        self._act(setup_menu, "Make a &pinnable shortcut…",
                  lambda: self.run_task("make_shortcut"), None,
                  "A .lnk with the app's icon and identity, ready to "
                  "drag onto the taskbar")
        setup_menu.addSeparator()
        self._act(setup_menu, "&Set up game data (GSI)…", self._install_gsi,
                  None, "Install Dota's Game State Integration config")
        self._act(setup_menu, "S&ettings…", self._open_settings, "Ctrl+,",
                  "What the app reads, and what it does with it")

        game_menu = bar.addMenu("&Game")
        self._act(game_menu, "&Diagnose game data…", self._diagnose_gsi,
                  "Ctrl+G",
                  "Check every requirement and name the one that is failing")
        self._act(game_menu, "Game data &status…", self._gsi_status,
                  None, "What the game is actually reporting right now")
        self._act(game_menu, "&Clear manual draft", self._clear_manual,
                  "Ctrl+Shift+C", "Empty every hand-entered slot")
        game_menu.addSeparator()
        self._act(game_menu, "Si&mulate a draft — full teams…",
                  lambda: self.run_task("simulate_gsi"), None,
                  "Both line-ups fill in — the best way to see the app work")
        self._act(game_menu, "Simulate a draft — only your hero…",
                  lambda: self.run_task("simulate_gsi_real"), None,
                  "Shows the real GSI limitation: enemy slots stay empty")

        view_menu = bar.addMenu("&View")
        self._act(view_menu, "&Reset window position",
                  self._reset_overlay_position)
        view_menu.addSeparator()
        self._act(view_menu, "Re&load data and library", self.reload_backend,
                  "F5", "Re-read the downloaded data from disk")

        # Force recognition is a real control, but it belongs beside the
        # picture it affects (Debug ▸ Live) rather than in the menu bar.
        self.force_action = QAction("&Force recognition", self)
        self.force_action.setCheckable(True)
        self.force_action.setShortcut(QKeySequence("Ctrl+F"))
        self.force_action.toggled.connect(self._set_forced)
        self.addAction(self.force_action)

        help_menu = bar.addMenu("&Help")
        self._act(help_menu, "&Update application…", self._update_app,
                  None,
                  "Pull the latest code and data, then reopen the app")
        # Everything under Advanced diagnoses the app itself. It is
        # occasionally necessary and it is not what a menu bar is for.
        advanced = help_menu.addMenu("&Advanced")
        self._act(advanced, "&Tune recognition…",
                  lambda: self.run_task("tune"), None,
                  "Search for recognition settings that never misidentify")
        self._act(advanced, "&List capture sources…",
                  lambda: self.run_task("list_windows"))
        self._act(advanced, "Run capture &probe…",
                  lambda: self.run_task("probe"))
        advanced.addSeparator()
        self._act(advanced, "&Save debug snapshot", self._save_snapshot,
                  "Ctrl+S",
                  "Write the current frame, crops and matches to disk")
        self._act(advanced, "Edit &item rules", self._edit_rules)
        self._act(advanced, "Re&load item rules", self._reload_rules)
        advanced.addSeparator()
        self._act(advanced, "Open &data folder",
                  lambda: open_folder(REPO_ROOT / "data_cache"))
        self._act(advanced, "Open de&bug folder",
                  lambda: open_folder(DEBUG_OUT))
        help_menu.addSeparator()
        self._act(help_menu, "&About", self._about)

    # ---- widgets -----------------------------------------------------
    def _build(self) -> None:
        # Built here, added to the shell below the title bar rather than
        # through addToolBar — same reason as the menu bar.
        # It rides on the TAB STRIP rather than in a row of its own: three
        # controls do not need a whole band of window height, and the tab
        # row was already half empty.
        toolbar = QToolBar()
        toolbar.setObjectName("tabStripTools")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        # Recording is one button because it is one action. It used to be a
        # menu tick for payloads, a separate probe for frames and Ctrl+S for
        # snapshots, in three folders — so the evidence for any one game was
        # scattered and usually incomplete.
        self.record_button = QPushButton("● Record")
        self.record_button.setProperty("accent", True)
        self.record_button.setMinimumWidth(110)
        self.record_button.setToolTip(
            "Record everything for this game — the data Dota sends, the "
            "draft on screen, and what the app made of both.\n"
            "Press it before you queue; it stops itself a minute after the "
            "draft ends.")
        self.record_button.clicked.connect(self._toggle_recording)
        toolbar.addWidget(self.record_button)

        self.auto_record_check = QCheckBox("Auto")
        self.auto_record_check.setToolTip(
            "Start recording by itself when Dota reaches the draft, and "
            "stop a minute after it ends")
        self.auto_record_check.setChecked(
            bool(self.settings.get("auto_record", True)))
        self.auto_record_check.toggled.connect(self._set_auto_record)
        toolbar.addWidget(self.auto_record_check)

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
        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Transparency"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setFixedWidth(90)
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.setToolTip(
            "How much of Dota shows through this window")
        self.opacity_slider.setValue(
            int(float(self.settings.get("overlay_opacity", 0.7)) * 100))
        self.opacity_slider.valueChanged.connect(
            lambda value: self._set_see_through(value / 100.0))
        toolbar.addWidget(self.opacity_slider)

        # There is no capture pill: it said the same sentence as the status
        # bar in less room, one line higher up. Keeping it around invisible
        # is how it became a window of its own.
        self.data_pill = QLabel("data: —")
        self.data_pill.setProperty("pill", True)
        toolbar.addWidget(self.data_pill)

        tabs = QTabWidget()
        self.tabs = tabs

        shell = QWidget()
        shell_lay = QVBoxLayout(shell)
        shell_lay.setContentsMargins(0, 0, 0, 0)
        shell_lay.setSpacing(0)
        self.title_bar = TitleBar("Dota Draft Assist")
        self.title_bar.add_menu_bar(self.menu_bar)
        self.title_bar.minimise.connect(self.showMinimized)
        self.title_bar.maximise.connect(self._toggle_maximised)
        self.title_bar.close_clicked.connect(self.close)
        shell_lay.addWidget(self.title_bar)
        tabs.setCornerWidget(toolbar, Qt.Corner.TopRightCorner)
        shell_lay.addWidget(tabs, 1)
        # A frameless window has no resize border, so the corner is put
        # back explicitly. Bottom-right only: one grip is enough to size a
        # window and four would be four things to mis-hit.
        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 0, 0)
        grip_row.addStretch(1)
        grip_row.addWidget(ResizeGrip(shell))
        shell_lay.addLayout(grip_row)
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
        self.banner_button.clicked.connect(lambda: self.run_task("update_data"))
        blay.addWidget(self.banner_button)
        outer.addWidget(self.banner)

        teams_row = QHBoxLayout()
        teams_row.setSpacing(10)
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
            teams_row.addWidget(panel, 1)
        outer.addLayout(teams_row)

        # The board is the top of the screen and everything under it is
        # advice about the board: first which hero to take, then what to
        # build against what is already there.
        picks_card, playy = card("Suggested picks · best draft fit")
        self.suggest_row = SuggestRow()
        playy.addWidget(self.suggest_row)
        outer.addWidget(picks_card)

        items_card, ilay = card("Items")
        self.item_row = ItemRow()
        ilay.addWidget(self.item_row)
        outer.addWidget(items_card)

        # ----- the grids, each under the team whose heroes head it.
        # Synergy is ally-by-ally, so it belongs under your five on the
        # LEFT; counters are read against their five, so its columns belong
        # under theirs on the RIGHT. A column then reads straight down from
        # the tile it is about, which is why the headers are those same
        # portraits rather than the names a second time.
        grids = QHBoxLayout()
        grids.setSpacing(10)
        with_card, withlay = card("Synergy")
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
        self.matchup_matrix.set_compact(True, short_names=False)
        self.matchup_matrix.set_icon_headers(True)
        self.matchup_matrix.set_margins(False)
        vslay.addWidget(self.matchup_matrix)
        grids.addWidget(vs_card, 1)
        outer.addLayout(grids)
        # The stretch goes at the BOTTOM, not into the grids. Giving it to
        # them left half the window blank and, worse, meant the window had
        # no shorter size to offer — a stretching widget never asks for
        # less. Now every card is its own height and the slack is slack.
        outer.addStretch(1)

        tabs.addTab(draft_widget, "Draft")

        # ----- Analysis tab: everything that ranks heroes NOT in the game.
        # It was on the draft screen and competed with it: a list of 120
        # candidates next to the ten picks made the ten harder to read.
        analysis = QWidget()
        alay = QVBoxLayout(analysis)
        alay.setContentsMargins(12, 12, 12, 12)
        split = QSplitter()
        alay.addWidget(split, 1)

        left = QWidget()
        llay = QVBoxLayout(left)
        llay.setContentsMargins(0, 0, 0, 0)
        llay.setSpacing(8)
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Filter:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(
            "Filter the list below — type any part of a hero's name")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.textChanged.connect(self._apply_filter)
        search_row.addWidget(self.search_box, 1)
        llay.addLayout(search_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Hero", "Fit", "vs enemies", "with allies"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._on_candidate_selected)
        # Sorting is on the numbers behind the cells, not their text: as
        # text "+10.0" sorts above "+9.0" and a percentage column comes out
        # alphabetical.
        self.table.setSortingEnabled(True)
        self.table.sortItems(1, Qt.SortOrder.DescendingOrder)
        header = self.table.horizontalHeader()
        header.setSortIndicatorShown(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 4):
            header.setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents)
        llay.addWidget(self.table, 1)
        split.addWidget(left)

        # The right column holds three stacked cards. On a short window
        # their combined minimum exceeds the height available, and Qt
        # resolves that by crushing them — which is what sheared the bottom
        # off the hero names. A scroll area means the column keeps its
        # proper size and the window scrolls instead.
        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(10)
        right_scroll = QScrollArea()
        right_scroll.setWidget(right)
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        split.addWidget(right_scroll)
        split.setSizes([780, 520])

        detail_card, dlay2 = card("Why this score")
        # The breakdown is the panel that catches a plausible total reached
        # for poor reasons, so it gets real estate rather than two lines,
        # and the terms sort by size so the ones that moved the number are
        # never buried under a dozen near-zeroes.
        self.detail = BreakdownPanel()
        self.detail.setMinimumHeight(190)
        self.detail.show_message(
            "Pick a hero from the list",
            "…and every term behind its score appears here, split into "
            "allies and enemies and sorted by how much it moved the "
            "number.")
        dlay2.addWidget(self.detail)
        rlay.addWidget(detail_card, 3)

        # Kept apart from "Why this score" on purpose: that panel is about
        # heroes in THIS game, and mixing a ranked list of heroes nobody has
        # picked into it made the breakdown look wrong.
        counters_card, clay2 = card("Counters to a drafted hero")
        self.counters = BreakdownPanel()
        self.counters.setMinimumHeight(150)
        self.counters.show_message(
            "Click a filled draft slot",
            "…and the heroes that beat it appear here. These are "
            "candidates, not picks in this game.")
        clay2.addWidget(self.counters)
        rlay.addWidget(counters_card, 2)

        tabs.addTab(analysis, "Analysis")

        # ----- Debug tab: the picture answers what a log never will
        dbg = QWidget()
        dlay = QVBoxLayout(dbg)
        dlay.setContentsMargins(12, 12, 12, 12)
        dlay.setSpacing(10)

        src_card, slay = card("Capture source")
        src_row = QHBoxLayout()
        self.source_combo = QComboBox()
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
        self.side_combo = QComboBox()
        self.side_combo.addItems(["left bank", "right bank"])
        self.side_combo.currentIndexChanged.connect(self._force_redraw)
        side_row.addWidget(self.side_combo)
        side_row.addStretch(1)
        elay.addLayout(side_row)
        dlay.addWidget(state_card)

        self.debug_image = FrameView("No frame captured yet.")
        self.debug_image.setMinimumHeight(320)
        self.debug_image.setProperty("card", True)
        self.debug_image.boxed.connect(self._on_box_dragged)
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
            "Press <b>Drag the boxes</b> and draw a rectangle round each "
            "bank of five in the picture above — the app measures the rest "
            "off the borders it can see. "
            "The numbers below are fractions of Dota's 16:9 HUD area, so "
            "they hold across resolutions; nudge them if a box is a few "
            "pixels out.")
        cal_note.setWordWrap(True)
        cal_note.setProperty("dim", True)
        callay.addWidget(cal_note)

        self.drag_button = QPushButton("Drag the boxes onto the portraits")
        self.drag_button.setProperty("accent", True)
        self.drag_button.setCheckable(True)
        self.drag_button.setToolTip(
            "Draw a box round each bank of five and the six numbers are "
            "measured out of the picture")
        self.drag_button.toggled.connect(self._set_drag_calibration)
        drag_row = QHBoxLayout()
        drag_row.addWidget(self.drag_button, 1)
        self.still_button = QPushButton("Use a saved picture…")
        self.still_button.setToolTip(
            "Calibrate from a frame saved earlier (Ctrl+S writes one) "
            "instead of waiting for Dota to be on screen")
        self.still_button.clicked.connect(self._choose_still)
        drag_row.addWidget(self.still_button)
        callay.addLayout(drag_row)
        self.drag_label = QLabel("")
        self.drag_label.setWordWrap(True)
        self.drag_label.setProperty("dim", True)
        callay.addWidget(self.drag_label)
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
        tabs.addTab(debug_tabs, "Debug")

        self.status = self.statusBar()

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
        self.tabs.setCurrentIndex(1)
        self.debug_tabs.setCurrentIndex(1)
        if not self.sessions:
            self.status.showMessage(
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
                "No recordings yet.\n\nPress Record before a game and Stop "
                "after the draft. Each press makes its own folder holding "
                "the data Dota sent, the draft on screen, and what the app "
                "made of both — plus a report scoring the screen reading "
                "against what the game reported afterwards.")

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
        self.status.showMessage("Report copied to the clipboard", 5000)

    def _replay_session(self) -> None:
        """Replay the selected recording. It lives here rather than in a
        menu because it is one more thing you do WITH a recording, and the
        recording is what you already have selected."""
        folder = self._current_session()
        if folder is None or not (folder / "gsi").is_dir():
            self.status.showMessage(
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
        if dialog.succeeded and task.reload_after:
            self.reload_backend()

    def _task_finished(self, dialog) -> None:
        if dialog in self._open_tasks:
            self._open_tasks.remove(dialog)
        if dialog.succeeded and dialog.task.reload_after:
            self.reload_backend()
        # Only the Update button asks for a restart, and only a pull that
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
        self.status.showMessage(
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

    def _update_first_run_banner(self) -> None:
        mismatch = self._bracket_mismatch()
        if mismatch:
            cached, wanted = mismatch
            self.banner_label.setText(
                f"<b>Statistics are for {cached}, but {wanted} is "
                "selected.</b> The numbers below are still the old bracket "
                "until the data is rebuilt.")
            self.banner_button.setText("Rebuild now")
            self.banner.setVisible(True)
            return
        if self.ds.is_empty:
            self.banner_label.setText(
                "<b>No statistics downloaded yet.</b> The hero list stays "
                "empty until the first download, which fetches match "
                "statistics for Ancient+Divine and the hero portraits used "
                "to read the draft off the screen.")
            self.banner_button.setText("Download now")
            self.banner.setVisible(True)
        elif self.ds.is_stale():
            self.banner_label.setText(
                f"<b>Statistics are {self.ds.age_hours():.0f} hours old.</b> "
                "Recommendations still work, but a refresh keeps them "
                "current with the patch.")
            self.banner_button.setText("Update now")
            self.banner.setVisible(True)
        else:
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
        self.status.showMessage(f"Loaded {len(self.rules)} item rules", 5000)

    def _about(self) -> None:
        QMessageBox.information(
            self, "About Dota Draft Assist",
            "Reads the Ranked All Pick draft from the Dota 2 window and "
            "suggests heroes and counter-items.\n\n"
            "Hero scores are measured from Ancient+Divine match statistics. "
            "Item flags are hand-authored rules.\n\n"
            "It never injects code, reads game memory, or sends input to "
            "Dota — it only reads pixels from a window already on screen.")

    # ---- the window IS the overlay --------------------------------------
    def _set_see_through(self, opacity: float) -> None:
        """Opacity is the whole reason this can sit over a game at all."""
        self.settings["overlay_opacity"] = float(opacity)
        ui_settings.save(self.settings)
        self.setWindowOpacity(opacity)

    def _reset_overlay_position(self) -> None:
        """Rescue for a window dragged off-screen or onto a monitor that is
        no longer attached. A frameless window has no system menu to do
        this from, so the app has to offer it."""
        self.move(60, 60)
        self.resize(1240, 820)
        self.status.showMessage("Window moved back to the top-left", 5000)

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

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Set up game data")
        box.setText("Game State Integration is installed."
                    if result.created else
                    "Game State Integration was already installed.")
        box.setInformativeText(
            "One more step, and Dota must be restarted for it to take "
            "effect:\n\n"
            "In Steam, right-click Dota 2 → Properties → Launch Options, "
            f"and add:\n\n    {gsi_install.LAUNCH_OPTION}\n\n"
            "Then restart Dota. This app will start receiving game data "
            "automatically.")
        box.setDetailedText(
            f"Config written to:\n{result.config_path}\n\n"
            f"Dota install:\n{result.dota_dir}\n\n"
            f"Listening on 127.0.0.1:{result.port}\n\n"
            "GSI is Valve's own feature: Dota sends this data because the "
            "config asks it to. Nothing is injected into the game and no "
            "memory is read.")
        box.exec()

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

    def _gsi_status(self) -> None:
        """Report exactly what the game is sending — the evidence that
        settles what GSI can and cannot do."""
        from ..gsi import install as gsi_install

        server = getattr(self.provider, "server", None)
        if server is None:
            QMessageBox.information(
                self, "Game data status",
                "The current source is not game data. Switch with "
                "Capture ▸ Use game data (GSI).")
            return
        reception = server.snapshot()
        lines = [f"Listening on 127.0.0.1:{server.port}",
                 f"Payloads received: {reception.count}",
                 f"Rejected (bad auth token): {reception.rejected}"]
        if reception.payload is None:
            lines += [
                "",
                "Dota has not sent anything yet. Check that:",
                "  1. the GSI config is installed (Game ▸ Set up game data)",
                f"  2. Dota's launch options include {gsi_install.LAUNCH_OPTION}",
                "  3. Dota has been restarted since adding it",
            ]
        else:
            lines.append(f"Last payload: {reception.age:.1f}s ago")
            state = getattr(self.provider, "last_state", None)
            if state is not None:
                lines += ["", f"Game state: {state.summary()}", "",
                          "Components this feed carries:"]
                for name, present in state.capabilities.items():
                    lines.append(f"  {'yes' if present else 'no ':>3}  {name}")
                if state.notes:
                    lines += ["", "Notes:"] + [f"  - {n}" for n in state.notes]
                lines += [
                    "",
                    ("GSI IS reporting the full draft — manual entry is not "
                     "needed." if state.has_full_draft else
                     "GSI is NOT reporting both line-ups, so enemy picks "
                     "must be clicked in. Click any draft slot to fill it."),
                ]
        if reception.last_error:
            lines += ["", f"Last error: {reception.last_error}"]

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Game data status")
        box.setText(("Receiving game data from Dota."
                     if reception.live else "Not receiving game data."))
        box.setDetailedText("\n".join(lines))
        box.exec()

    def _switch_to_gsi(self) -> None:
        from ..gsi import install as gsi_install
        from ..gsi.server import GsiServer
        from .providers import GsiProvider

        if isinstance(self.provider, GsiProvider):
            self.status.showMessage("Already using game data (GSI)", 5000)
            return
        token = gsi_install.read_installed_token()
        server = GsiServer(gsi_install.DEFAULT_PORT, token=token)
        self._swap_provider(GsiProvider(self.ds, server, self.manual))

    def _switch_to_vision(self) -> None:
        from .providers import LiveProvider

        if isinstance(self.provider, LiveProvider):
            self.status.showMessage("Already using screen capture", 5000)
            return
        answer = QMessageBox.question(
            self, "Use screen capture",
            "Screen capture reads the draft from pixels. It is the older, "
            "less reliable path and is kept only as a fallback.\n\n"
            "Switch to it anyway?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            from ..capture.session import CaptureSession
            from ..vision import library
            from ..vision.layout import load_layout
            params = library.load_params()
            lib = library.load(expected_hash_size=params.hash_size)
        except FileNotFoundError as exc:
            QMessageBox.warning(self, "Use screen capture",
                                f"Screen capture needs the portrait library:"
                                f"\n\n{exc}")
            return
        self._swap_provider(LiveProvider(CaptureSession(load_layout(), lib,
                                                        params)))

    def _swap_provider(self, provider) -> None:
        try:
            self.provider.stop()
        except Exception:
            pass
        self.provider = provider
        self.last_draft_key = None
        message = provider.start()
        self.status.showMessage(message, 8000)
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
        self.status.showMessage("Cleared hand-entered draft slots", 5000)

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
        self.status.showMessage(
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
        self.status.showMessage(
            f"Saved {folder.name}: {payloads} payloads, {frames} frames, "
            f"{states} states" + (f" — {reason}" if reason else ""), 15000)

    def _update_record_button(self) -> None:
        recording = self.recorder.active
        self.record_button.setText("■ Stop" if recording else "● Record")
        self.record_button.setProperty("recording", recording)
        self.record_button.style().unpolish(self.record_button)
        self.record_button.style().polish(self.record_button)
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
        self.status.showMessage(
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
        self.status.showMessage(message, 6000)
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
        self.status.showMessage(
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
        self.status.showMessage(
            f"{self.ds.name(moved)} and {self.ds.name(landed)} swapped "
            "places", 5000)
        self.refresh()

    def _set_slot_role(self, side: str, index: int, role: str | None) -> None:
        self.slot_roles[side][index] = role
        self.last_draft_key = None
        self.refresh()

    def _clear_slot(self, side: str, index: int) -> None:
        self.manual.set_slot(side, index, None)
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
        if snap is not None:
            taken |= set(snap.left) | set(snap.right)
        return taken

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
                "Download the hero data first: Data ▸ Update statistics.")
            return
        taken = self._taken_heroes()
        slots = (self.manual.allies if side == "ally" else self.manual.enemies)
        current = slots[index] if index < len(slots) else None
        caption = ("Your team" if side == "ally" else "Enemy team")
        dialog = HeroPickerDialog(self.ds, taken=taken, current=current,
                                  title=f"{caption} — slot {index + 1}",
                                  parent=self)
        if dialog.exec() != HeroPickerDialog.DialogCode.Accepted:
            return
        self.manual.set_slot(side, index,
                             None if dialog.cleared else dialog.selected)
        self.last_draft_key = None

    # ---- capture source ------------------------------------------------
    def _set_forced(self, on: bool) -> None:
        for widget in (self.force_check, self.force_action):
            widget.blockSignals(True)
            widget.setChecked(on)
            widget.blockSignals(False)
        self.provider.set_forced(on)

    def _measure_calibration(self) -> None:
        """Measure the crop boxes from a frame whose heroes the game named.

        This is the only way this project can calibrate: the person who
        can see the screen and the person who can change the numbers are
        not the same, so the app has to measure its own geometry.
        """
        snap = self.snapshot
        frame = getattr(snap, "frame", None) if snap else None
        if frame is None:
            frame = self._grab_dota_frame()
        heroes = list(getattr(snap, "left", [])) + list(
            getattr(snap, "right", [])) if snap else []
        if frame is None:
            self.cal_label.setText(
                "no frame — is Dota running in borderless windowed mode?")
            return
        if len(heroes) < 8:
            self.cal_label.setText(
                "the game has not named enough heroes yet — try this during "
                "strategy time, when all ten are known")
            return

        from ..vision import autocal
        portraits = autocal.base_portraits(heroes)
        if len(portraits) < 8:
            self.cal_label.setText(
                "portraits are not downloaded — run Setup ▸ Update "
                "statistics and portraits first")
            return

        self.measure_button.setEnabled(False)
        self.cal_label.setText("measuring… (about a minute)")
        QApplication.processEvents()
        try:
            result = autocal.calibrate(frame, portraits, self.layout_spec)
        except Exception as exc:                 # never take the app down
            self.cal_label.setText(f"measuring failed: {exc}")
            self.measure_button.setEnabled(True)
            return
        self.measure_button.setEnabled(True)
        if not result.ok:
            self.cal_label.setText(result.note)
            return
        self.layout_spec = result.layout
        for field, spin in self.cal_spins.items():
            spin.blockSignals(True)
            spin.setValue(getattr(result.layout, field))
            spin.blockSignals(False)
        self._set_calibration("y", result.layout.y)      # push and redraw
        self._save_calibration()
        self.cal_label.setText(f"{result.note} — saved")

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
        self.status.showMessage(
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

        **Only when nothing is calibrated yet.** This claimed to save "the
        first time and never again" and did no such thing: it ran on every
        measurement, so a user who dragged their boxes onto the portraits
        and watched them land had them silently replaced by whatever the
        next match measured. A calibration the user set is an ANSWER, and a
        measurement is a guess that happens to be automatic — the guess
        does not get to overwrite the answer. Setup ▸ Measure from this
        game is still there for asking for one deliberately.
        """
        result = getattr(self.provider, "measured_layout", None)
        if result is None:
            return
        self.provider.measured_layout = None
        if not result.ok:
            return
        if CALIBRATION_FILE.exists():
            self.cal_label.setText(
                "measured this game, but your saved calibration was kept — "
                "press Measure from this game to take the new one")
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
        self.status.showMessage(
            "Crop boxes measured from this game and saved — recognition "
            "should work from here.", 12000)

    # Two rectangles, one per bank, either order. It used to be three —
    # first portrait, fifth portrait, other bank — because a box round a
    # whole bank spans four pitches plus one portrait, which is one
    # equation for two unknowns. The gap is now MEASURED off the picture
    # instead (`autocal.measure_bank`), so the user draws the two boxes
    # they were always going to draw.
    DRAG_STEPS = (
        "Drag a rectangle round ALL FIVE portraits of one bank.",
        "Now round ALL FIVE of the other bank — either order is fine.",
    )

    def _choose_still(self) -> None:
        """Calibrate from a frame saved earlier rather than a live one.

        Dragging boxes onto portraits needs a picture of the portraits, and
        waiting for Dota to be on screen to do it is a poor trade when the
        user already has `frame_*.png` sitting in the debug folder from the
        last time they pressed Ctrl+S.
        """
        if self._still is not None:
            self._still = None
            self.still_button.setText("Use a saved picture…")
            self.drag_label.setText("Back to the live picture.")
            return
        path, _filter = QFileDialog.getOpenFileName(
            self, "Pick a saved frame", str(DEBUG_OUT),
            "Pictures (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        import cv2
        still = cv2.imread(path)
        if still is None:
            QMessageBox.warning(self, "Crop boxes",
                                f"Could not read {Path(path).name}.")
            return
        self._still = still
        self.still_button.setText("Back to the live picture")
        self.drag_label.setText(
            f"Showing {Path(path).name} ({still.shape[1]}x{still.shape[0]}). "
            "Press \u201cDrag the boxes\u201d and draw on it.")
        self._draw_still()

    def _set_drag_calibration(self, on: bool) -> None:
        """Calibrate by drawing on the picture instead of typing fractions.

        Six numbers, each a fraction of Dota's 16:9 HUD box rather than of
        the window, is not something anybody can convert "the boxes are 135
        pixels too far left" into. The user could see exactly what was wrong
        and had no way to say it.
        """
        self._drag_rects = []
        self.debug_image.set_picking(on)
        if not on:
            self.drag_label.setText("")
            return
        # A still is drawn on demand rather than waiting for the refresh
        # loop: the loop skips the debug view unless it is visible, and the
        # user pressing this button is the proof that it is.
        self._draw_still()
        if self.debug_image.pixmap() is None or \
                self.debug_image.pixmap().isNull():
            self.drag_button.setChecked(False)
            self.drag_label.setText(
                "No picture to draw on yet — this needs Dota running and "
                "captured. Check the capture source at the top of this tab.")
            return
        self.drag_label.setText(
            f"1 of {len(self.DRAG_STEPS)} · {self.DRAG_STEPS[0]}")

    def _on_box_dragged(self, x: int, y: int, width: int, height: int) -> None:
        if not self.drag_button.isChecked():
            return
        self._drag_rects.append((x, y, width, height))
        if len(self._drag_rects) < len(self.DRAG_STEPS):
            step = len(self._drag_rects)
            self.drag_label.setText(
                f"{step + 1} of {len(self.DRAG_STEPS)} · "
                f"{self.DRAG_STEPS[step]}")
            return

        from ..vision import autocal, layout as layout_mod
        frame = (self._still if self._still is not None
                 else getattr(self.snapshot, "frame", None))
        if frame is None:
            self.drag_button.setChecked(False)
            self.drag_label.setText("the frame went away — try again")
            return
        layout, note = autocal.layout_from_banks(
            frame, self._drag_rects[0], self._drag_rects[1], self.layout_spec)
        self.drag_button.setChecked(False)
        if layout is None:
            self.drag_label.setText(f"Not saved: {note}")
            return
        self.layout_spec = layout
        session = getattr(self.provider, "session", None)
        if session is not None:
            session.layout = layout
        for field, spin in self.cal_spins.items():
            spin.blockSignals(True)
            spin.setValue(getattr(layout, field))
            spin.blockSignals(False)
        self._force_redraw()
        try:
            layout_mod.save_calibration(layout)
        except OSError as exc:
            self.drag_label.setText(f"measured but could not save: {exc}")
            return
        self.drag_label.setText(
            f"Saved — {note}. The boxes above should now sit on the "
            "portraits; nudge the numbers if any is a pixel or two out.")
        self.cal_label.setText(f"saved to {CALIBRATION_FILE.name}")

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

    def _update_and_restart(self) -> None:
        """Pull, then relaunch.

        Reloading in place works and is what `reload_backend` does — but a
        restart is the only way to be certain nothing anywhere is still
        holding the old data, and the user asked not to have to close and
        reopen the app by hand. So the app does it for them.
        """
        self._restart_after_task = "update_data"
        self.run_task("update_data")

    def _relaunch(self) -> None:
        """Start a fresh copy of ourselves and quit.

        Detached on purpose: the new process must outlive this one, and it
        must not inherit a half-torn-down Qt event loop.
        """
        try:
            subprocess.Popen([sys.executable, "-m", "draft_assist.ui.app"],
                             cwd=str(REPO_ROOT), close_fds=True)
        except OSError as exc:
            self.status.showMessage(f"Could not restart: {exc}", 10000)
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
        self.status.showMessage(
            f"App icon set from {Path(path).name} (copied to "
            f"assets/{dest.name}). The taskbar picks it up when the app is "
            "reopened.", 12000)

    def _apply_app_icon(self) -> None:
        """Push the current icon at everything that draws one.

        Four places, and they are easy to leave out of step: the window
        (Alt-Tab), the application (the taskbar), our own title bar, and
        the floating toggle, which is the only part of the app on screen
        when the window is hidden.
        """
        art = appicon.icon()
        self.setWindowIcon(art)
        app = QApplication.instance()
        if app is not None:
            app.setWindowIcon(art)
        if getattr(self, "title_bar", None) is not None:
            self.title_bar.refresh_icon()

    def _toggle_maximised(self) -> None:
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def _open_settings(self) -> None:
        from .settings_dialog import SettingsDialog

        self.settings.setdefault("pair_source", pair_source())
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        before = dict(self.settings)
        self.settings.update(dialog.values())
        ui_settings.save(self.settings)

        self.auto_record_check.setChecked(
            bool(self.settings.get("auto_record", True)))
        if (self.settings.get("use_gsi"), self.settings.get("use_vision")) != (
                before.get("use_gsi"), before.get("use_vision")):
            self._apply_sources()
        chosen = self.settings.get("pair_source", pair_source())
        if chosen != pair_source():
            # Written to preferences.json, not just the UI settings: the
            # pull runs in a subprocess and reads it there.
            save_pair_source(chosen)
            self.status.showMessage(
                f"Statistics source set to {chosen} — run Data ▸ Update "
                "statistics to rebuild the matrices from it", 12000)

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
                "Reading the screen needs the portrait library — run "
                "Setup ▸ Update statistics and portraits first.")
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
        self.status.showMessage(message, 8000)
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

        name = getattr(snap, "player_name", "")
        team = getattr(snap, "my_team", "")
        bits = [b for b in (name, team.title()) if b]
        self.team_captions["ally"].setText(
            f"Your team — {' · '.join(bits)}" if bits else "Your team")
        self.team_captions["enemy"].setText(
            "Enemy team — " + ("Dire" if team == "radiant" else "Radiant")
            if team else "Enemy team")

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
        # measured against.
        if self.focus is not None and self.focus[1] not in (
                set(allies) | set(enemies)):
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
        self.scored = scoring.score_all(self.ds, draft)
        role = draft.my_role
        tags = ROLE_TAGS.get(role, set()) if role else set()

        self.table.blockSignals(True)
        selected = self._selected_hero_id()
        scroll_pos = self.table.verticalScrollBar().value()
        # Populate unsorted, then re-enable: Qt re-applies whichever column
        # the user chose, so a refresh every second does not fight them.
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.scored))
        for row, s in enumerate(self.scored):
            hero_roles = set(self.ds.heroes.get(s.hero_id, {})
                             .get("roles", []))
            # Every column is a signed interaction term now. The hero's own
            # win rate is not one of them and is not shown: it is not in the
            # score, and a percentage beside these numbers invited reading
            # the two as the same kind of thing.
            cells = [(s.name, None),
                     (f"{s.score * 100:+.1f}", s.score),
                     (f"{s.vs_total * 100:+.1f}", s.vs_total),
                     (f"{s.with_total * 100:+.1f}", s.with_total)]
            for col, (text, value) in enumerate(cells):
                item = (QTableWidgetItem(text) if value is None
                        else ValueItem(text, value))
                item.setData(Qt.ItemDataRole.UserRole, s.hero_id)
                if col and value:
                    item.setForeground(
                        QColor(theme.GOOD if value > 0 else theme.BAD))
                if tags and tags & hero_roles:
                    item.setBackground(HIGHLIGHT)
                self.table.setItem(row, col, item)
        self.table.setSortingEnabled(True)
        self.table.blockSignals(False)
        self.table.verticalScrollBar().setValue(scroll_pos)
        if selected is not None:
            self._select_hero_row(selected)
        self._apply_filter()
        self._update_matrices(draft)
        self._update_suggestions(draft)
        self._update_items(draft)
        self._update_relations()

    def _update_matrices(self, draft: scoring.DraftState) -> None:
        self.matchup_matrix.show_matrix(
            scoring.matchup_matrix(self.ds, draft),
            "Fill in both teams.")
        # A dataset built from OpenDota carries no ally-pair counts at all,
        # so the grid would be a wall of +0.00 that looks like "no synergy
        # anywhere" rather than "this source does not publish it".
        if self.ds.meta.get("has_synergy") is False:
            self.synergy_matrix.show_matrix(
                scoring.Matrix(rows=[], cols=[], cells=[]),
                f"{self.ds.meta.get('pair_source', 'this source')} publishes "
                "no ally-pair data — switch the statistics source to Stratz "
                "in Settings and re-pull.")
        else:
            self.synergy_matrix.show_matrix(
                scoring.synergy_matrix(self.ds, draft),
                "Fill in your own team.")

    def _apply_filter(self) -> None:
        needle = self.search_box.text().strip().lower()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            self.table.setRowHidden(
                row, bool(needle and item and needle not in item.text().lower()))

    def _selected_hero_id(self) -> int | None:
        items_sel = self.table.selectedItems()
        return items_sel[0].data(Qt.ItemDataRole.UserRole) if items_sel else None

    def _select_hero_row(self, hero_id: int) -> None:
        for row in range(self.table.rowCount()):
            it = self.table.item(row, 0)
            if it and it.data(Qt.ItemDataRole.UserRole) == hero_id:
                self.table.selectRow(row)
                return

    def _on_candidate_selected(self) -> None:
        hid = self._selected_hero_id()
        if hid is None:
            return
        draft = self._current_draft()
        terms = scoring.breakdown(self.ds, hid, draft)
        by_id = {s.hero_id: s for s in self.scored}
        s = by_id.get(hid)
        subtitle = ""
        if s:
            subtitle = (f"draft fit {s.score * 100:+.1f} "
                        f"(win rate {s.baseline * 100:.1f}%, not scored)")
        banks = [("With ally", [(t.other_name, t.delta) for t in terms
                                if t.kind != "vs"]),
                 ("Vs enemy", [(t.other_name, t.delta) for t in terms
                               if t.kind == "vs"])]
        self.detail.show_banks(
            self.ds.name(hid), subtitle, banks,
            footnote=("Individual terms in percentage points, not the sum — "
                      "check whether a plausible total has poor reasons. "
                      "Click a heading to re-sort that side."),
            empty=("No drafted heroes resolved yet — the score is pure "
                   "baseline. Fill in the draft slots and the terms appear "
                   "here."))

    def _on_slot_clicked(self) -> None:
        b = self.sender()
        hid = b.property("hero_id")
        side = b.property("side")
        if hid is None:
            self._edit_slot(side, b.property("slot_index"))
            return
        # Clicking the focused hero again clears the view, so the way out
        # is the same gesture as the way in.
        self.focus = None if self.focus == (side, hid) else (side, hid)
        self._update_relations()
        self._show_counters(hid, side)

    def _update_relations(self) -> None:
        """Write the signed numbers above the other nine slots.

        This is the matrix read one row at a time, which is how the
        question actually arrives mid-draft: not "show me the grid" but
        "what does THIS hero do to everything else".
        """
        for panel in self.team_panels.values():
            panel.clear_deltas()
        values: dict[int, float] = {}
        draft = self._current_draft()
        if self.focus is None:
            # Nothing clicked, so every tile says what that pick is worth
            # overall rather than nothing at all — the tile has a line for
            # a number either way, and an empty one wastes it.
            net = scoring.net_contributions(self.ds, draft)
            for panel in self.team_panels.values():
                for tile in panel.slots:
                    value = net.get(tile.property("hero_id"))
                    if value is not None:
                        tile.show_delta(value)
            return
        side, hid = self.focus
        relations = {r.hero_id: r for r in
                     scoring.relations_to(self.ds, hid, draft)}
        for panel in self.team_panels.values():
            for tile in panel.slots:
                other = tile.property("hero_id")
                if other is None:
                    continue
                if other == hid and panel.side == side:
                    tile.set_focused(True)
                    continue
                rel = relations.get(other)
                if rel is None:
                    # Clicking an enemy says nothing about the other
                    # enemies — that pairing is their synergy, not ours.
                    continue
                tile.show_delta(rel.delta, rel.kind)
                values[other] = rel.delta

    def _on_drafted_clicked(self) -> None:
        """Kept for callers that click a slot expecting the counters view."""
        b = self.sender()
        hid = b.property("hero_id")
        if hid is not None:
            self._show_counters(hid, b.property("side"))

    def _show_counters(self, hid: int, side: str) -> None:
        draft = self._current_draft()
        drafted = set(draft.allies) | set(draft.enemies)
        counters = scoring.counters_to(self.ds, hid, exclude=drafted)[:15]
        cap = "counters to" if side == "enemy" else "what beats your"
        self.counters.show_banks(
            f"Best against {self.ds.name(hid)}",
            f"{cap} {side} pick",
            [("Hero", [(name, delta) for _chid, name, delta in counters])],
            footnote="Percentage points against this hero alone.",
            empty="No matchup data for this hero yet.")

    def _update_suggestions(self, draft: scoring.DraftState) -> None:
        """The top of the ranked list, as a strip above the items.

        Same numbers as the Analysis tab, same order — this is that list's
        head, not a second opinion. It stays quiet until at least one hero
        is on the board: with an empty draft every fit is zero, so a strip
        of "+0.0" would be ranking nothing and inviting the user to read it
        as a recommendation.
        """
        if not draft.allies and not draft.enemies:
            self.suggest_row.show_heroes([])
            return
        rows = [
            (s.hero_id, s.name, s.score,
             f"{s.name}\nfit {s.score * 100:+.2f}"
             f"  (vs {s.vs_total * 100:+.2f}, with {s.with_total * 100:+.2f})")
            for s in self.scored[:SuggestRow_MAX]
        ]
        self.suggest_row.show_heroes(rows)

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
            self.item_row.show_items([])
            return
        advice = items_mod.recommend(
            self.rules, enemy_names, ally_names, draft.my_role,
            self.rules_meta.get("current_patch", "0.0"))
        # No sentence when there is nothing to flag: silence IS the answer
        # here, and the empty plates already say the strip is working and
        # has nothing for you.
        self.item_row.show_items(advice)
        # One missing icon is normal; NONE at all means the pack has never
        # been fetched, and a strip of grey plates looks broken rather than
        # unconfigured.
        if advice and not item_icons.any_downloaded():
            self.item_row.set_note(
                "No item icons on disk yet — press Update. If they are "
                "still missing after that, Setup ▸ Fetch item icons says "
                "why.")
        else:
            self.item_row.set_note("")

    # ---- status / debug ------------------------------------------------
    def _update_status(self, snap) -> None:
        parts = [f"mode: {snap.mode}"]
        if snap.source:
            parts.append(snap.source)
        if snap.game_state:
            parts.append(snap.game_state.replace("DOTA_GAMERULES_STATE_", ""))
        if snap.warning:
            parts.append(f"WARNING: {snap.warning}")
        if snap.stalled:
            parts.append("CAPTURE STALLED — occluded window may have "
                         "stopped presenting")
        server = getattr(self.provider, "server", None)
        if server is not None and getattr(server, "recording", False):
            parts.append(f"RECORDING ({server._archived} payloads)")
        if self.ds.is_empty:
            parts.append("data: none — use Data ▸ Update statistics")
        else:
            age = self.ds.age_hours()
            stale = " (STALE)" if self.ds.is_stale() else ""
            parts.append(f"data: {age:.0f}h old{stale}")
        brackets = "+".join(self.ds.meta.get("target_brackets", []))
        if brackets:
            parts.append(f"bracket: {brackets}")
        n_stale_rules = sum(
            1 for r in self.rules
            if items_mod.is_stale(r.verified_patch,
                                  self.rules_meta.get("current_patch", "0.0")))
        if n_stale_rules:
            parts.append(f"{n_stale_rules} item rules unverified this patch")
        self.status.showMessage("   |   ".join(parts))

        if self.ds.is_empty:
            self.data_pill.setText("no data")
            self.data_pill.setProperty("pill", "warn")
        else:
            self.data_pill.setText(f"data {self.ds.age_hours():.0f}h")
            self.data_pill.setProperty(
                "pill", "warn" if self.ds.is_stale() else "good")
        self.data_pill.style().unpolish(self.data_pill)
        self.data_pill.style().polish(self.data_pill)

    def _update_debug(self, snap) -> None:
        # NOTHING here is worth doing while the tab is hidden. It draws an
        # overlay onto a full-resolution frame, converts it to a QImage and
        # smooth-scales it — four times a second, over a game, into a
        # widget nobody is looking at. That was most of the stutter.
        if not self.debug_image.isVisible():
            return
        set_log(self.timing_text, LOOP.report())
        if self._draw_still():
            set_log(self.debug_text,
                    f"Calibrating from a saved picture "
                    f"({self._still.shape[1]}x{self._still.shape[0]}). "
                    "The boxes above are the current numbers.")
            return
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
                 f"frame: {w}x{h}"]
        for s in read.slots:
            resolved = ("UNKNOWN" if s.hero_id is None else
                        "EMPTY" if s.hero_id == -1 else self.ds.name(s.hero_id))
            lines.append(f"{s.rect.team}{s.rect.slot}: {resolved:20s} "
                         f"nearest={s.best_label} d={s.distance} m={s.margin}")
        set_log(self.debug_text, "\n".join(lines))

    def _draw_still(self) -> bool:
        """Put the loaded still on screen with the current boxes over it."""
        if self._still is None:
            return False
        from ..vision.debug import draw_boxes
        self._show_picture(draw_boxes(self._still, self.layout_spec))
        return True

    def _show_picture(self, picture) -> None:
        """Put a BGR frame in the debug view, at the view's size.

        The view is told the FRAME's own size as well, because a rectangle
        dragged on it has to come back in frame pixels rather than in
        whatever the fit happened to scale it to.
        """
        height, width = picture.shape[:2]
        img = QImage(picture.tobytes(), width, height, 3 * width,
                     QImage.Format.Format_BGR888)
        self.debug_image.show_frame(
            QPixmap.fromImage(img).scaled(
                self.debug_image.size(), Qt.AspectRatioMode.KeepAspectRatio,
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
        self.status.showMessage(
            "Copied — paste it wherever you are reporting this.", 6000)

    def _hero_names(self) -> dict[int, str]:
        """Every hero's name, built once per dataset rather than per tick."""
        if getattr(self, "_names_for", None) is not self.ds:
            self._names_for = self.ds
            self._names = {hid: self.ds.name(hid) for hid in self.ds.hero_ids}
        return self._names

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        # A modeless task owns a subprocess that would otherwise keep POSTing
        # to a port nobody is listening on any more.
        for dialog in list(self._open_tasks):
            dialog.close()
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
        self.status.showMessage(f"Snapshot saved to {folder}", 8000)

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
    hint = ""
    try:
        gsi_install.find_dota_dir()
    except gsi_install.DotaNotFound:
        hint = ("Dota install not found — use Game ▸ Set up game data once "
                "Dota is installed")
    server = GsiServer(args.port, token=gsi_install.read_installed_token())
    gsi = GsiProvider(ds, server, manual, install_hint=hint)
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
    app.setStyleSheet(theme.STYLESHEET)
    app.setWindowIcon(appicon.icon())
    manual = ManualDraft()
    provider = make_provider(args, ds, manual)
    win = MainWindow(ds, provider, rules, meta, manual)
    win.show()
    # start() never raises for live capture: an unbound source is a state
    # the user fixes from the Capture menu, not a crash.
    started = provider.start()
    win.status.showMessage(f"started: {started}")
    win._refresh_sources()
    if getattr(provider, "error", ""):
        win.snapshot_label.setText(provider.error.splitlines()[0])
    code = app.exec()
    provider.stop()
    sys.exit(code)


if __name__ == "__main__":
    main()

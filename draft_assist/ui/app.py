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
from PyQt6.QtGui import QAction, QActionGroup, QColor, QImage, QKeySequence, QPixmap
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox,
                             QDialog, QFrame,
                             QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QMainWindow, QMessageBox, QPlainTextEdit,
                             QDoubleSpinBox, QLayout, QListWidget,
                             QPushButton,
                             QScrollArea, QSplitter,
                             QTableWidget,
                             QTableWidgetItem, QTabWidget, QTextBrowser,
                             QToolBar, QVBoxLayout, QWidget)

from ..config import (CALIBRATION_FILE, DEBUG_OUT, RECORDINGS_DIR,
                       REPO_ROOT, RULES_FILE,
                       save_target_brackets, target_brackets)
from ..data import store
from ..data.store import Dataset
from ..model import items as items_mod
from ..model import scoring
from . import settings as ui_settings
from .. import record as record_mod
from . import theme
from .bracket_dialog import BracketDialog
from .hero_picker import HeroPickerDialog
from .manual import ManualDraft
from .overlay import DraftOverlay
from .tables import (BreakdownPanel, MatrixTable, QuickEntry,
                     ValueItem)
from .task_dialog import TaskDialog
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
HIGHLIGHT = QColor(theme.HIGHLIGHT_ROW)
SEV_COLORS = {3: theme.BAD, 2: theme.WARN, 1: theme.TEXT_DIM}


def open_folder(path: Path) -> None:
    """Show a folder in the system file manager."""
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - opening a local folder for the user
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


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
        # Flipped by hand when the minimap's guess at the sides is wrong;
        # cleared when the match changes.
        self.swap_sides = False
        # Position 1-5 per slot, assigned by hand. Vision reads the
        # ranked-role icons, but not until the crop geometry is right,
        # so nothing sets these automatically yet.
        self.slot_roles = {"ally": [None] * 5,
                           "enemy": [None] * 5}
        self._swap_match = ""
        # hero id -> "ally"/"enemy", for one hero put on the wrong
        # side. Cleared with the swap when the match changes.
        self.side_overrides: dict[int, str] = {}
        from ..vision import layout as layout_mod
        session = getattr(provider, "session", None)
        self.layout_spec = (getattr(session, "layout", None)
                            or layout_mod.load_layout())
        self.quick_side = "enemy"
        # (side, index) in the order they were typed, so Undo
        # removes the last pick rather than an arbitrary one.
        self._entry_order: list[tuple[str, int]] = []
        self.rules, self.rules_meta = rules, rules_meta
        self.manual = manual if manual is not None else getattr(
            provider, "manual", None) or ManualDraft()
        self.snapshot = None
        self.last_draft_key = None
        self.scored: list[scoring.ScoredHero] = []
        self.settings = ui_settings.load()
        self.overlay: DraftOverlay | None = None
        self.setWindowTitle("Dota Draft Assist")
        self.resize(1240, 820)
        self._build_menus()
        self._build()
        self._refresh_sources()
        self._sync_source_controls()
        self._update_first_run_banner()
        if self.settings.get("overlay_enabled"):
            self._set_overlay(True)
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
        bar = self.menuBar()

        setup_menu = bar.addMenu("&Setup")
        self._act(setup_menu, "&Update statistics and portraits…",
                  lambda: self.run_task("update_data"), "Ctrl+U",
                  "Download the latest hero statistics and portraits")
        self._act(setup_menu, "Statistics &bracket…", self._choose_brackets,
                  None, "Which ranks the statistics are drawn from")
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
        self.overlay_action = QAction("Draft &overlay", self)
        self.overlay_action.setCheckable(True)
        self.overlay_action.setShortcut(QKeySequence("Ctrl+O"))
        self.overlay_action.setStatusTip(
            "A small always-on-top badge over Dota that expands into the "
            "recommendations")
        self.overlay_action.toggled.connect(self._set_overlay)
        view_menu.addAction(self.overlay_action)
        self._act(view_menu, "&Reset overlay position",
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
        self._act(help_menu, "&Update application…",
                  lambda: self.run_task("update_app"), None,
                  "Pull the latest code from GitHub")
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
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        # Recording is one button because it is one action. It used to be a
        # menu tick for payloads, a separate probe for frames and Ctrl+S for
        # snapshots, in three folders — so the evidence for any one game was
        # scattered and usually incomplete.
        self.record_button = QPushButton("● Record")
        self.record_button.setProperty("accent", True)
        self.record_button.setMinimumWidth(120)
        self.record_button.setMinimumHeight(32)
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
        toolbar.addWidget(self.recording_label)

        self.open_recordings_button = QPushButton("Recordings")
        self.open_recordings_button.setMinimumHeight(32)
        self.open_recordings_button.setToolTip("Open the recordings folder")
        self.open_recordings_button.clicked.connect(
            lambda: open_folder(RECORDINGS_DIR))
        toolbar.addWidget(self.open_recordings_button)

        self.report_button = QPushButton("Report")
        self.report_button.setMinimumHeight(32)
        self.report_button.setToolTip(
            "Open the last recording's report — everything the session saw, "
            "in one document")
        self.report_button.clicked.connect(self._show_latest_report)
        toolbar.addWidget(self.report_button)

        toolbar.addSeparator()
        self.force_check = QCheckBox("Force recognition")
        self.force_check.setToolTip(
            "Recognise every frame even when the draft gate does not trip")
        self.force_check.toggled.connect(self._set_forced)
        toolbar.addWidget(self.force_check)
        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy().Expanding,
                             spacer.sizePolicy().verticalPolicy().Preferred)
        toolbar.addWidget(spacer)
        self.capture_pill = QLabel("capture: —")
        self.capture_pill.setProperty("pill", True)
        toolbar.addWidget(self.capture_pill)
        self.data_pill = QLabel("data: —")
        self.data_pill.setProperty("pill", True)
        toolbar.addWidget(self.data_pill)

        tabs = QTabWidget()
        self.tabs = tabs
        self.setCentralWidget(tabs)

        # ----- Draft tab
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

        split = QSplitter()
        outer.addWidget(split, 1)

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

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Hero", "Score", "Base", "vs enemies", "with allies"])
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
        for col in range(1, 5):
            header.setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents)
        llay.addWidget(self.table, 1)
        split.addWidget(left)

        # The right column holds four stacked cards. On a short window their
        # combined minimum exceeds the height available, and Qt resolves
        # that by crushing them — which is what sheared the bottom off the
        # hero names. A scroll area means the column keeps its proper size
        # and the window scrolls instead.
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

        teams_card, tlay = card("Draft")
        self.team_buttons = {}
        self.team_captions = {}
        for side, caption in (("ally", "Your team"), ("enemy", "Enemy team")):
            label = QLabel(caption)
            label.setProperty("dim", True)
            tlay.addWidget(label)
            self.team_captions[side] = label
            row = QHBoxLayout()
            row.setSpacing(6)
            buttons = []
            for index in range(5):
                b = QPushButton("+")
                b.setProperty("slot", True)
                # The card below is allowed to shrink, and a hero name
                # sheared in half is the result. Font metrics, not a
                # guessed pixel count, because the user's Windows font is
                # not this machine's and may be scaled.
                b.setMinimumHeight(b.fontMetrics().height() + 16)
                b.setProperty("side", side)
                b.setProperty("slot_index", index)
                b.setToolTip("Click to set this pick; click a filled slot to "
                             "see what beats it. Right-click to change it, "
                             "clear it, or give it a role.")
                # Focusable so Tab walks the ten slots in order.
                b.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                b.clicked.connect(self._on_slot_clicked)
                b.setContextMenuPolicy(
                    Qt.ContextMenuPolicy.CustomContextMenu)
                b.customContextMenuRequested.connect(
                    lambda pos, side=side, i=index:
                        self._slot_menu(side, i, pos))
                row.addWidget(b)
                buttons.append(b)
            self.team_buttons[side] = buttons
            tlay.addLayout(row)
        # Typing the draft in is the normal way the other nine picks
        # arrive, so it gets a keyboard path: type a few letters, Enter
        # fills the next empty slot on the active side and leaves the box
        # ready for the next. Tab is left alone so it walks the slots.
        quick = QHBoxLayout()
        quick.setSpacing(6)
        self.quick_side_button = QPushButton("Enemy")
        self.quick_side_button.setToolTip(
            "Which team the next entry goes to (Ctrl+Tab flips it)")
        self.quick_side_button.setFixedWidth(78)
        self.quick_side_button.clicked.connect(self._flip_quick_side)
        quick.addWidget(self.quick_side_button)
        self.quick_entry = QuickEntry()
        self.quick_entry.setPlaceholderText(
            "Type a hero and press Enter to add the pick…")
        self.quick_entry.returnPressed.connect(self._quick_add)
        # Ctrl+Tab, not Tab: Tab has to walk the draft slots.
        flip = QAction("Flip entry side", self)
        flip.setShortcut(QKeySequence("Ctrl+Tab"))
        flip.triggered.connect(self._flip_quick_side)
        self.addAction(flip)
        quick.addWidget(self.quick_entry, 1)
        self.quick_undo = QPushButton("Undo")
        self.quick_undo.setFixedWidth(64)
        self.quick_undo.setToolTip("Remove the last hand-entered pick")
        self.quick_undo.clicked.connect(self._quick_undo)
        quick.addWidget(self.quick_undo)
        tlay.addLayout(quick)

        self.swap_button = QPushButton("⇅ Swap teams")
        self.swap_button.setToolTip(
            "The game names all ten heroes but not which five are yours. "
            "If the two rows are the wrong way round, this flips them for "
            "the rest of the match.")
        # Accent-styled because it is not decoration: while the sides are
        # a guess, this is the control that makes the draft correct.
        self.swap_button.setProperty("accent", True)
        self.swap_button.clicked.connect(self._swap_sides)
        self.swap_button.setVisible(False)
        quick.addWidget(self.swap_button)

        self.unknown_label = QLabel("")
        self.unknown_label.setProperty("dim", True)
        tlay.addWidget(self.unknown_label)
        self.manual_hint = QLabel("")
        self.manual_hint.setWordWrap(True)
        self.manual_hint.setProperty("dim", True)
        tlay.addWidget(self.manual_hint)
        # Maximum let the layout squeeze the card below its own minimum
        # when the right-hand column got tight, which sheared the bottom off
        # the hero names. SetMinimumSize pins the card's minimum to what its
        # contents actually need — a wrapping hint label needs more height
        # than the card's sizeHint alone reports, so a policy derived from
        # sizeHint is not enough. The draft is the thing you read: it keeps
        # its height and the panels below it give way instead.
        tlay.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        teams_card.setSizePolicy(teams_card.sizePolicy().horizontalPolicy(),
                                 teams_card.sizePolicy().Policy.Fixed)
        # The draft and the role controls live on the LEFT, beside the
        # hero list, so the right column is free for the breakdown and
        # the counters rather than squeezing all four into one strip.
        llay.insertWidget(0, teams_card)

        controls_card, clay = card()
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("My role:"))
        self.role_combo = QComboBox()
        for label, _ in ROLE_LABELS:
            self.role_combo.addItem(label)
        self.role_combo.currentIndexChanged.connect(self._refresh_views)
        row1.addWidget(self.role_combo, 1)
        # Only meaningful when the source is pixels: the two banks are then
        # just screen positions. Game data reports player.team_name, so
        # asking would be asking about something already known.
        self.side_label = QLabel("My team:")
        row1.addWidget(self.side_label)
        self.side_combo = QComboBox()
        self.side_combo.addItems(["left bank", "right bank"])
        self.side_combo.currentIndexChanged.connect(self._force_redraw)
        row1.addWidget(self.side_combo, 1)
        clay.addLayout(row1)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("My pick:"))
        self.my_hero_combo = QComboBox()
        self.my_hero_combo.currentIndexChanged.connect(self._refresh_views)
        row2.addWidget(self.my_hero_combo, 1)
        self.lock_check = QCheckBox("Locked in")
        self.lock_check.toggled.connect(self._refresh_views)
        row2.addWidget(self.lock_check)
        clay.addLayout(row2)
        llay.insertWidget(1, controls_card)

        detail_card, dlay2 = card("Why this score")
        # The breakdown is the panel that catches a plausible total reached
        # for poor reasons, so it gets real estate rather than two lines,
        # and the terms sort by size so the ones that moved the number are
        # never buried under a dozen near-zeroes.
        self.detail = BreakdownPanel()
        self.detail.setMinimumHeight(190)
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

        items_card, ilay = card("Items")
        note = QLabel("Hand-authored rules — asserted, not measured. "
                      "Hero scores above are measured.")
        note.setWordWrap(True)
        note.setProperty("dim", True)
        ilay.addWidget(note)
        self.items_view = QTextBrowser()
        self.items_view.setMinimumHeight(140)
        ilay.addWidget(self.items_view)
        rlay.addWidget(items_card, 2)

        tabs.addTab(draft_widget, "Draft")

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
        if not hasattr(self.provider, "available_sources"):
            self.source_combo.addItem(
                "(screen capture only — the current source is game data)")
        dlay.addWidget(src_card)

        self.debug_image = QLabel("No frame captured yet.")
        self.debug_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.debug_image.setMinimumHeight(320)
        self.debug_image.setProperty("card", True)
        dlay.addWidget(self.debug_image, 3)

        self.debug_text = QPlainTextEdit()
        self.debug_text.setReadOnly(True)
        self.debug_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        dlay.addWidget(self.debug_text, 1)

        # Calibration lives beside the picture because it is only usable
        # with the picture: the boxes move as the numbers change, so being
        # off is corrected by eye in seconds rather than by editing JSON
        # and restarting.
        cal_card, callay = card("Crop boxes")
        cal_note = QLabel(
            "Nudge until the boxes sit on the hero portraits during hero "
            "selection. Values are fractions of Dota's 16:9 HUD area, so "
            "they hold across resolutions.")
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
        # ----- Matrix tab: the grid the summed score hides
        matrix_page = QWidget()
        mlay = QVBoxLayout(matrix_page)
        mlay.setContentsMargins(12, 12, 12, 12)
        mlay.setSpacing(10)
        vs_card, vslay = card("Your team against theirs")
        self.matchup_matrix = MatrixTable()
        vslay.addWidget(self.matchup_matrix)
        mlay.addWidget(vs_card, 1)
        with_card, withlay = card("Your team with itself")
        self.synergy_matrix = MatrixTable()
        withlay.addWidget(self.synergy_matrix)
        mlay.addWidget(with_card, 1)
        tabs.addTab(matrix_page, "Matrix")

        debug_tabs = QTabWidget()
        self.debug_tabs = debug_tabs
        debug_tabs.addTab(dbg, "Live")
        debug_tabs.addTab(self._build_sessions_tab(), "Recordings")
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

    def reload_backend(self) -> None:
        """Re-read dataset and portrait library from disk, and rebuild the
        capture session around them, so a data update takes effect without
        restarting the app."""
        self.ds = store.load_or_empty()
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
        if self.overlay is not None:
            self.overlay.set_dataset(self.ds)
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

    # ---- overlay --------------------------------------------------------
    def _set_overlay(self, enabled: bool) -> None:
        if enabled and self.overlay is None:
            self.overlay = DraftOverlay(
                self.ds,
                rows=int(self.settings.get("overlay_rows", 6)),
                expanded=bool(self.settings.get("overlay_expanded", True)))
            self.overlay.moved.connect(self._remember_overlay_position)
            self.overlay.toggled.connect(self._remember_overlay_expanded)
            self.overlay.move(int(self.settings.get("overlay_x", 40)),
                              int(self.settings.get("overlay_y", 40)))
        if self.overlay is not None:
            self.overlay.setVisible(enabled)
        self.settings["overlay_enabled"] = bool(enabled)
        ui_settings.save(self.settings)
        if self.overlay_action.isChecked() != enabled:
            self.overlay_action.blockSignals(True)
            self.overlay_action.setChecked(enabled)
            self.overlay_action.blockSignals(False)

    def _remember_overlay_position(self, x: int, y: int) -> None:
        self.settings["overlay_x"] = int(x)
        self.settings["overlay_y"] = int(y)
        ui_settings.save(self.settings)

    def _remember_overlay_expanded(self, expanded: bool) -> None:
        self.settings["overlay_expanded"] = bool(expanded)
        ui_settings.save(self.settings)

    def _reset_overlay_position(self) -> None:
        """Rescue for an overlay dragged off-screen or onto a monitor that
        is no longer attached."""
        self.settings["overlay_x"], self.settings["overlay_y"] = 40, 40
        ui_settings.save(self.settings)
        if self.overlay is not None:
            self.overlay.move(40, 40)
        self.status.showMessage("Overlay moved back to the top-left", 5000)

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
        self._entry_order.clear()
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

    def _set_slot_role(self, side: str, index: int, role: str | None) -> None:
        self.slot_roles[side][index] = role
        self.last_draft_key = None
        self.refresh()

    def _clear_slot(self, side: str, index: int) -> None:
        self.manual.set_slot(side, index, None)
        self._entry_order[:] = [entry for entry in self._entry_order
                                if entry != (side, index)]
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

    def _swap_sides(self) -> None:
        self.swap_sides = not self.swap_sides
        self.last_draft_key = None
        self.status.showMessage(
            "Teams swapped for this match" if self.swap_sides
            else "Teams back as the game reported them", 6000)
        self.refresh()

    def _flip_quick_side(self) -> None:
        self.quick_side = "ally" if self.quick_side == "enemy" else "enemy"
        self.quick_side_button.setText(self.quick_side.title())
        self.quick_entry.setFocus()

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

    def _quick_add(self) -> None:
        text = self.quick_entry.text().strip()
        if not text:
            return
        if self.ds.is_empty:
            self.status.showMessage(
                "No hero data yet — Data ▸ Update statistics", 6000)
            return
        hero_id = self.resolve_hero(text, exclude=self._taken_heroes())
        if hero_id is None:
            self.status.showMessage(
                f"'{text}' matches no single undrafted hero — keep typing",
                4000)
            return
        side = self.quick_side
        slots = self.manual.allies if side == "ally" else self.manual.enemies
        if None not in slots:
            self.status.showMessage(f"{side.title()} team is already full",
                                    4000)
            return
        index = slots.index(None)
        self.manual.set_slot(side, index, hero_id)
        self._entry_order.append((side, index))
        self.quick_entry.clear()
        self.last_draft_key = None
        self.status.showMessage(
            f"{self.ds.name(hero_id)} → {side} slot {index + 1}", 4000)
        self.refresh()
        # Straight on to the next pick: a draft is thirty seconds long and
        # reaching for the mouse between heroes is the whole cost.
        self.quick_entry.setFocus()

    def _quick_undo(self) -> None:
        if not self._entry_order:
            self.status.showMessage("Nothing hand-entered to undo", 4000)
            return
        side, index = self._entry_order.pop()
        self.manual.set_slot(side, index, None)
        self.last_draft_key = None
        self.refresh()

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

    def _open_settings(self) -> None:
        from .settings_dialog import SettingsDialog

        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        before = dict(self.settings)
        self.settings.update(dialog.values())
        ui_settings.save(self.settings)

        self.auto_record_check.setChecked(
            bool(self.settings.get("auto_record", True)))
        if self.settings.get("overlay_enabled") != before.get(
                "overlay_enabled"):
            self.overlay_action.setChecked(
                bool(self.settings.get("overlay_enabled")))
        if (self.settings.get("use_gsi"), self.settings.get("use_vision")) != (
                before.get("use_gsi"), before.get("use_vision")):
            self._apply_sources()

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
        snap = self.provider.poll()
        self.snapshot = snap
        allies, enemies = self._sides(snap)
        draft_key = (tuple(allies), tuple(enemies), snap.unknown)
        if draft_key != self.last_draft_key:
            self.last_draft_key = draft_key
            self._on_draft_changed(allies, enemies, snap.unknown)
        self._consider_auto_record(snap)
        self._capture_recording(snap, allies, enemies)
        self._update_status(snap)
        self._update_team_captions(snap)
        self._update_manual_hint(snap)
        self._update_debug(snap)
        if self.overlay is not None and self.overlay.isVisible():
            self.overlay.update_content(snap, self.scored,
                                        self._current_draft())

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
            self.swap_sides = False
            self.side_overrides.clear()
        # Never during the draft. There the picks come from the screen,
        # where Radiant is always the left bank and Dire the right, and the
        # game has already said which of those is yours — so the sides are
        # known, and offering a swap would only invite getting them wrong.
        # HERO_SELECTION specifically, not the whole drafting window:
        # strategy time is after the picking and is where the minimap
        # reading (and so the guess) lives.
        picking = "HERO_SELECTION" in str(getattr(snap, "game_state", ""))
        uncertain = (bool(source) and not picking
                     and not getattr(snap, "sides_certain", True))
        self.swap_button.setVisible(uncertain)
        if not snap.needs_manual:
            if source == "minimap":
                self.manual_hint.setText(
                    "All ten heroes came from the game — but which five are "
                    "yours is a guess. Check the top row against your own "
                    "team and press Swap teams if it is reversed."
                    + ("  (swapped)" if self.swap_sides else ""))
            elif source == "screen":
                self.manual_hint.setText(
                    "Both line-ups read from the Dota window.")
            else:
                self.manual_hint.setText("")
            return
        if source == "screen":
            self.manual_hint.setText(
                "Reading the picks from the Dota window — type or click in "
                "anything it has not recognised yet.")
        elif snap.game_state:
            self.manual_hint.setText(
                "The game itself reports no picks during hero selection, so "
                "the app reads them off the Dota window. If nothing appears, "
                "check the Debug tab is bound to Dota — or type them into "
                "the box above.")
        else:
            self.manual_hint.setText(
                "Click the empty slots to enter the draft by hand.")

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
            left, right = snap.left, snap.right
            if self.swap_sides and not getattr(snap, "sides_certain", True):
                left, right = right, left
            return self._apply_side_overrides(left, right)
        mine_right = self.side_combo.currentIndex() == 1
        return ((snap.right, snap.left) if mine_right
                else (snap.left, snap.right))

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
        role_idx = self.role_combo.currentIndex()
        return scoring.DraftState(
            allies=list(allies), enemies=list(enemies),
            unknown_slots=self.snapshot.unknown,
            my_role=ROLE_LABELS[role_idx][1],
            my_hero=self._my_hero() if self.lock_check.isChecked() else None)

    def _my_hero(self) -> int | None:
        return self.my_hero_combo.currentData()

    # ---- reactions -----------------------------------------------------
    def _on_draft_changed(self, allies, enemies, unknown) -> None:
        for side, ids in (("ally", allies), ("enemy", enemies)):
            for i, b in enumerate(self.team_buttons[side]):
                role = self.slot_roles[side][i]
                prefix = f"{role} · " if role else ""
                if i < len(ids):
                    b.setText(prefix + self.ds.name(ids[i]))
                    b.setProperty("hero_id", ids[i])
                else:
                    # Empty slots stay enabled: clicking one is how a pick
                    # gets entered when the game does not report it.
                    b.setText(prefix + "+" if prefix else "+")
                    b.setProperty("hero_id", None)
        self.unknown_label.setText(
            f"{unknown} slot(s) unresolved — scoring uses only confident "
            "slots" if unknown else "")

        current_my = self._my_hero()
        self.my_hero_combo.blockSignals(True)
        self.my_hero_combo.clear()
        self.my_hero_combo.addItem("(not picked yet)", None)
        for hid in allies:
            self.my_hero_combo.addItem(self.ds.name(hid), hid)
        if current_my in allies:
            self.my_hero_combo.setCurrentIndex(allies.index(current_my) + 1)
        self.my_hero_combo.blockSignals(False)

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
            cells = [(s.name, None), (f"{s.score * 100:.1f}%", s.score),
                     (f"{s.baseline * 100:.1f}%", s.baseline),
                     (f"{s.vs_total * 100:+.1f}", s.vs_total),
                     (f"{s.with_total * 100:+.1f}", s.with_total)]
            for col, (text, value) in enumerate(cells):
                item = (QTableWidgetItem(text) if value is None
                        else ValueItem(text, value))
                item.setData(Qt.ItemDataRole.UserRole, s.hero_id)
                if col == 3 and s.vs_total:
                    item.setForeground(QColor(theme.GOOD if s.vs_total > 0
                                              else theme.BAD))
                if col == 4 and s.with_total:
                    item.setForeground(QColor(theme.GOOD if s.with_total > 0
                                              else theme.BAD))
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
        self._update_items(draft)

    def _update_matrices(self, draft: scoring.DraftState) -> None:
        self.matchup_matrix.show_matrix(
            scoring.matchup_matrix(self.ds, draft),
            "Fill in both teams and every ally-versus-enemy pairing appears "
            "here.")
        self.synergy_matrix.show_matrix(
            scoring.synergy_matrix(self.ds, draft),
            "Fill in your own team and every pair's synergy appears here.")

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
            subtitle = (f"baseline {s.baseline * 100:.1f}%  →  total "
                        f"{s.score * 100:.1f}%")
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
        if hid is None:
            self._edit_slot(b.property("side"), b.property("slot_index"))
            return
        self._show_counters(hid, b.property("side"))

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

    def _update_items(self, draft: scoring.DraftState) -> None:
        if draft.my_hero is None:
            self.items_view.setHtml(
                f"<p style='color:{theme.TEXT_DIM}'>Lock your pick (choose it "
                "above and tick <b>Locked in</b>) to see item flags.</p>")
            return
        enemy_names = [self.ds.name(h) for h in draft.enemies]
        ally_names = [self.ds.name(h) for h in draft.allies
                      if h != draft.my_hero]
        advice = items_mod.recommend(
            self.rules, enemy_names, ally_names, draft.my_role,
            self.rules_meta.get("current_patch", "0.0"))
        if not advice:
            self.items_view.setHtml(
                f"<p style='color:{theme.TEXT_DIM}'>Nothing urgent flagged "
                "for this lineup — silence is a valid answer.</p>")
            return
        html = []
        for a in advice:
            color = SEV_COLORS.get(a.triggers[0].severity, theme.TEXT_DIM)
            stale = (" <b>[unverified this patch]</b>" if a.any_stale else "")
            html.append(f"<p style='margin:4px 0'><font color='{color}'>"
                        f"<b>{a.item}</b></font> "
                        f"<font color='{theme.TEXT_DIM}'>weight "
                        f"{a.score:.1f}</font>{stale}<br>")
            for t in a.triggers:
                html.append(f"<font color='{theme.TEXT_DIM}'>&nbsp;&nbsp;sev "
                            f"{t.severity}:</font> {t.reason}<br>")
            html.append("</p>")
        self.items_view.setHtml("".join(html))

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

        self.capture_pill.setText(snap.source or f"mode: {snap.mode}")
        self.capture_pill.setProperty(
            "pill", "warn" if (snap.warning or snap.stalled) else True)
        if self.ds.is_empty:
            self.data_pill.setText("no data")
            self.data_pill.setProperty("pill", "warn")
        else:
            self.data_pill.setText(f"data {self.ds.age_hours():.0f}h")
            self.data_pill.setProperty(
                "pill", "warn" if self.ds.is_stale() else "good")
        for pill in (self.capture_pill, self.data_pill):
            pill.style().unpolish(pill)
            pill.style().polish(pill)

    def _update_debug(self, snap) -> None:
        # Debug shows the RAW per-frame read (live confidences, flicker and
        # all); the draft panels show the stabilised one.
        read = snap.read_raw or snap.read
        if snap.frame is None or read is None:
            self.debug_text.setPlainText(
                f"mode={snap.mode}  gate score={snap.gate_score:.3f}  "
                f"frames arrived={snap.frames_arrived}\n"
                "No recognised frame yet. In demo mode there is no frame at "
                "all; live and replay show the captured frame with crop "
                "boxes here as soon as recognition runs.")
            return
        from ..vision.debug import draw_overlay
        names = {hid: self.ds.name(hid) for hid in self.ds.hero_ids}
        overlay = draw_overlay(snap.frame, read, names)
        h, w = overlay.shape[:2]
        img = QImage(overlay.tobytes(), w, h, 3 * w,
                     QImage.Format.Format_BGR888)
        pix = QPixmap.fromImage(img).scaled(
            self.debug_image.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self.debug_image.setPixmap(pix)
        lines = [f"gate score: {snap.gate_score:.3f}   "
                 f"frames arrived: {snap.frames_arrived}   "
                 f"frame: {w}x{h}"]
        for s in read.slots:
            resolved = ("UNKNOWN" if s.hero_id is None else
                        "EMPTY" if s.hero_id == -1 else self.ds.name(s.hero_id))
            lines.append(f"{s.rect.team}{s.rect.slot}: {resolved:20s} "
                         f"nearest={s.best_label} d={s.distance} m={s.margin}")
        self.debug_text.setPlainText("\n".join(lines))

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self.overlay is not None:
            self.overlay.close()
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

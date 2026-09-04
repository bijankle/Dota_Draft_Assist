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
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QActionGroup, QColor, QImage, QKeySequence, QPixmap
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame,
                             QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QMainWindow, QMessageBox, QPlainTextEdit,
                             QPushButton, QSplitter, QTableWidget,
                             QTableWidgetItem, QTabWidget, QTextBrowser,
                             QToolBar, QVBoxLayout, QWidget)

from ..config import (DEBUG_OUT, REPO_ROOT, RULES_FILE,
                       save_target_brackets, target_brackets)
from ..data import store
from ..data.store import Dataset
from ..model import items as items_mod
from ..model import scoring
from . import settings as ui_settings
from . import theme
from .bracket_dialog import BracketDialog
from .hero_picker import HeroPickerDialog
from .manual import ManualDraft
from .overlay import DraftOverlay
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

        data_menu = bar.addMenu("&Data")
        self._act(data_menu, "&Update statistics and portraits…",
                  lambda: self.run_task("update_data"), "Ctrl+U",
                  "Download the latest hero statistics and portraits")
        self._act(data_menu, "&Tune recognition…",
                  lambda: self.run_task("tune"), None,
                  "Search for recognition settings that never misidentify")
        data_menu.addSeparator()
        self._act(data_menu, "Statistics &bracket…", self._choose_brackets,
                  None, "Which ranks the statistics are drawn from")
        data_menu.addSeparator()
        self._act(data_menu, "&Reload data and library", self.reload_backend,
                  "F5", "Re-read the downloaded data from disk")
        self._act(data_menu, "Open data &folder",
                  lambda: open_folder(REPO_ROOT / "data_cache"))

        game_menu = bar.addMenu("&Game")
        self._act(game_menu, "&Set up game data (GSI)…", self._install_gsi,
                  None, "Install Dota's Game State Integration config")
        self._act(game_menu, "&Diagnose game data…", self._diagnose_gsi,
                  "Ctrl+G",
                  "Check every requirement and name the one that is failing")
        self._act(game_menu, "Game data &status…", self._gsi_status,
                  None, "What the game is actually reporting right now")
        self.record_action = QAction("&Record game data", self)
        self.record_action.setCheckable(True)
        self.record_action.setStatusTip(
            "Archive every payload Dota sends, using the listener already "
            "running — no second process, no port clash")
        self.record_action.toggled.connect(self._set_recording)
        game_menu.addAction(self.record_action)
        self._act(game_menu, "Open &recordings folder",
                  lambda: open_folder(REPO_ROOT / "data_cache" / "gsi"))
        game_menu.addSeparator()
        self._act(game_menu, "Si&mulate a draft — full teams…",
                  lambda: self.run_task("simulate_gsi"), None,
                  "Both line-ups fill in — the best way to see the app work")
        self._act(game_menu, "Simulate a draft — only your hero…",
                  lambda: self.run_task("simulate_gsi_real"), None,
                  "Shows the real GSI limitation: enemy slots stay empty")
        self._act(game_menu, "Replay recorded game data…",
                  lambda: self.run_task("replay_gsi"), None,
                  "Replay payloads archived from a real match")
        game_menu.addSeparator()
        self._act(game_menu, "&Clear manual draft", self._clear_manual,
                  "Ctrl+Shift+C", "Empty every hand-entered slot")

        cap_menu = bar.addMenu("&Capture")
        self._act(cap_menu, "Use screen capture (&fallback)",
                  self._switch_to_vision, None,
                  "Read the draft from pixels instead of game data")
        self._act(cap_menu, "Use &game data (GSI)", self._switch_to_gsi)
        cap_menu.addSeparator()
        self.source_menu = cap_menu.addMenu("Capture &source")
        self.source_menu.aboutToShow.connect(self._populate_source_menu)
        self._act(cap_menu, "Bind to &Dota client",
                  lambda: self._bind_title(None), "Ctrl+D",
                  "Capture the window titled exactly 'Dota 2'")
        cap_menu.addSeparator()
        self.force_action = QAction("&Force recognition", self)
        self.force_action.setCheckable(True)
        self.force_action.setShortcut(QKeySequence("Ctrl+F"))
        self.force_action.setStatusTip(
            "Recognise every frame even when the draft gate does not trip")
        self.force_action.toggled.connect(self._set_forced)
        cap_menu.addAction(self.force_action)
        cap_menu.addSeparator()
        self._act(cap_menu, "&List capture sources…",
                  lambda: self.run_task("list_windows"))
        self._act(cap_menu, "Run capture &probe…",
                  lambda: self.run_task("probe"))

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

        tools_menu = bar.addMenu("&Tools")
        self._act(tools_menu, "&Save debug snapshot", self._save_snapshot,
                  "Ctrl+S", "Write the current frame, crops and matches to disk")
        self._act(tools_menu, "Open &debug folder",
                  lambda: open_folder(DEBUG_OUT))
        tools_menu.addSeparator()
        self._act(tools_menu, "Edit &item rules", self._edit_rules,
                  None, "Open rules/items.yaml in your text editor")
        self._act(tools_menu, "Re&load item rules", self._reload_rules)

        help_menu = bar.addMenu("&Help")
        self._act(help_menu, "&Update application…",
                  lambda: self.run_task("update_app"), None,
                  "Pull the latest code from GitHub")
        self._act(help_menu, "&About", self._about)

    # ---- widgets -----------------------------------------------------
    def _build(self) -> None:
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
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
        self.search_box.setPlaceholderText("Type a hero name…")
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
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 5):
            header.setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents)
        llay.addWidget(self.table, 1)
        split.addWidget(left)

        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(10)
        split.addWidget(right)
        split.setSizes([660, 560])

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
                             "see what beats it. Right-click to change or "
                             "clear.")
                b.clicked.connect(self._on_slot_clicked)
                b.setContextMenuPolicy(
                    Qt.ContextMenuPolicy.CustomContextMenu)
                b.customContextMenuRequested.connect(
                    lambda _pos, side=side, i=index: self._edit_slot(side, i))
                row.addWidget(b)
                buttons.append(b)
            self.team_buttons[side] = buttons
            tlay.addLayout(row)
        self.unknown_label = QLabel("")
        self.unknown_label.setProperty("dim", True)
        tlay.addWidget(self.unknown_label)
        self.manual_hint = QLabel("")
        self.manual_hint.setWordWrap(True)
        self.manual_hint.setProperty("dim", True)
        tlay.addWidget(self.manual_hint)
        # Fixed, not Maximum: Maximum lets the layout squeeze the card below
        # its own minimum when the right-hand column is tight, which clipped
        # the bottom off the hero names. The draft is the thing you read —
        # it keeps its height and the panels below it give way instead.
        teams_card.setSizePolicy(teams_card.sizePolicy().horizontalPolicy(),
                                 teams_card.sizePolicy().Policy.Fixed)
        rlay.addWidget(teams_card)

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
        rlay.addWidget(controls_card)

        detail_card, dlay2 = card("Why this score")
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(False)
        # The breakdown is the panel that catches a plausible total reached
        # for poor reasons, so it gets real estate rather than two lines.
        self.detail.setMinimumHeight(170)
        dlay2.addWidget(self.detail)
        rlay.addWidget(detail_card, 3)

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
        tabs.addTab(dbg, "Debug")

        self.status = self.statusBar()

    # ---- maintenance tasks --------------------------------------------
    def run_task(self, key: str) -> None:
        task = TASKS[key]
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

    def _set_recording(self, on: bool) -> None:
        """Toggle archiving on the live listener.

        Recording used to spawn a second process, which could never work:
        only one listener can hold the port, so the recorder collided with
        the app that was already receiving everything.
        """
        from ..config import DATA_CACHE

        server = getattr(self.provider, "server", None)
        if server is None:
            QMessageBox.information(
                self, "Record game data",
                "Recording needs the game-data source. Switch with "
                "Capture ▸ Use game data (GSI).")
            self.record_action.blockSignals(True)
            self.record_action.setChecked(False)
            self.record_action.blockSignals(False)
            return
        folder = DATA_CACHE / "gsi"
        count = server.set_archive_dir(folder if on else None)
        if on:
            self.status.showMessage(
                f"Recording game data to {folder} "
                f"({count} payloads already there)", 8000)
        else:
            self.status.showMessage(
                f"Stopped recording — {count} payloads in {folder}", 8000)

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

    def _edit_slot(self, side: str, index: int) -> None:
        """Fill, change or clear a draft slot by hand."""
        if self.ds.is_empty:
            QMessageBox.information(
                self, "Choose hero",
                "Download the hero data first: Data ▸ Update statistics.")
            return
        snap = self.snapshot
        taken = set()
        if snap is not None:
            taken = set(snap.left) | set(snap.right)
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

    def _populate_source_menu(self) -> None:
        self.source_menu.clear()
        if not hasattr(self.provider, "available_sources"):
            self.source_menu.addAction("(live capture only)").setEnabled(False)
            return
        group = QActionGroup(self)
        current = getattr(getattr(self.provider, "session", None),
                          "capture_title", None)
        for title in self.provider.available_sources():
            action = QAction(title, self)
            action.setCheckable(True)
            action.setChecked(title == current)
            action.triggered.connect(
                lambda _checked, t=title: self._bind_title(t))
            group.addAction(action)
            self.source_menu.addAction(action)

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
        if not snap.needs_manual:
            self.manual_hint.setText("")
            return
        if snap.game_state:
            self.manual_hint.setText(
                "The game reports your own hero and match state, but not the "
                "other line-up — click the empty slots to fill them in.")
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
            return (snap.left, snap.right)
        mine_right = self.side_combo.currentIndex() == 1
        return ((snap.right, snap.left) if mine_right
                else (snap.left, snap.right))

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
                if i < len(ids):
                    b.setText(self.ds.name(ids[i]))
                    b.setProperty("hero_id", ids[i])
                else:
                    # Empty slots stay enabled: clicking one is how a pick
                    # gets entered when the game does not report it.
                    b.setText("+")
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
        self.table.setRowCount(len(self.scored))
        for row, s in enumerate(self.scored):
            hero_roles = set(self.ds.heroes.get(s.hero_id, {})
                             .get("roles", []))
            cells = [s.name, f"{s.score * 100:.1f}%",
                     f"{s.baseline * 100:.1f}%",
                     f"{s.vs_total * 100:+.1f}", f"{s.with_total * 100:+.1f}"]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, s.hero_id)
                if col:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                          | Qt.AlignmentFlag.AlignVCenter)
                if col == 3 and s.vs_total:
                    item.setForeground(QColor(theme.GOOD if s.vs_total > 0
                                              else theme.BAD))
                if col == 4 and s.with_total:
                    item.setForeground(QColor(theme.GOOD if s.with_total > 0
                                              else theme.BAD))
                if tags and tags & hero_roles:
                    item.setBackground(HIGHLIGHT)
                self.table.setItem(row, col, item)
        self.table.blockSignals(False)
        self.table.verticalScrollBar().setValue(scroll_pos)
        if selected is not None:
            self._select_hero_row(selected)
        self._apply_filter()
        self._update_items(draft)

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
        html = [f"<h3 style='margin:2px 0'>{self.ds.name(hid)}</h3>"]
        if s:
            html.append(f"<p style='color:{theme.TEXT_DIM}'>baseline "
                        f"{s.baseline * 100:.1f}% &rarr; total "
                        f"<b style='color:{theme.TEXT}'>"
                        f"{s.score * 100:.1f}%</b></p>")
        if not terms:
            html.append(f"<p style='color:{theme.TEXT_DIM}'>No drafted heroes "
                        "resolved yet — the score is pure baseline.</p>")
        html.append("<table cellpadding=3 width=100%>")
        for t in terms:
            kind = "vs" if t.kind == "vs" else "with"
            color = theme.GOOD if t.delta > 0 else theme.BAD
            html.append(
                f"<tr><td>{kind} {t.other_name}</td>"
                f"<td align=right><font color='{color}'>"
                f"{t.delta * 100:+.2f}</font></td></tr>")
        html.append("</table>")
        html.append(f"<p style='color:{theme.TEXT_DIM}'>Individual terms, not "
                    "the sum — check whether a plausible total has poor "
                    "reasons.</p>")
        self.detail.setHtml("".join(html))

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
        html = [f"<h3 style='margin:2px 0'>Best against "
                f"{self.ds.name(hid)}</h3>",
                f"<p style='color:{theme.TEXT_DIM}'>{cap} {side} pick</p>",
                "<table cellpadding=3 width=100%>"]
        for chid, name, delta in counters:
            color = theme.GOOD if delta > 0 else theme.BAD
            html.append(f"<tr><td>{name}</td><td align=right>"
                        f"<font color='{color}'>{delta * 100:+.2f}</font>"
                        "</td></tr>")
        html.append("</table>")
        self.detail.setHtml("".join(html))

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

    Game data (GSI) is the default: Dota reports its own state through a
    Valve-supported channel, with no pixel interpretation and no per-frame
    compute. Screen capture remains available behind --vision as a fallback
    for anything GSI turns out not to report.
    """
    from .providers import (DemoProvider, GsiProvider, LiveProvider,
                            ManualProvider, ReplayProvider)
    if args.demo:
        return DemoProvider(ds)
    if args.manual:
        return ManualProvider(manual)

    if args.vision or args.replay:
        from ..capture.session import CaptureSession
        from ..vision import library
        from ..vision.layout import load_layout
        params = library.load_params()
        try:
            lib = library.load(expected_hash_size=params.hash_size)
        except FileNotFoundError:
            # No portraits downloaded yet: an empty library still lets the
            # app open and offer Data > Update statistics.
            import numpy as np
            from ..vision.library import Library
            lib = Library(bits=np.zeros((0, params.bits), dtype=np.uint8),
                          hero_ids=np.zeros(0, dtype=np.int32), labels=[],
                          hash_size=params.hash_size)
        session = CaptureSession(load_layout(), lib, params)
        if args.replay:
            return ReplayProvider(session, Path(args.replay))
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
    return GsiProvider(ds, server, manual, install_hint=hint)


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

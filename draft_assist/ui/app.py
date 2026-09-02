"""The application window: an ordinary draggable, resizable desktop window —
no transparency, no always-on-top, no click-through. It is not an overlay;
the user reads it in front of Dota and switches to the game to pick.

Every maintenance action (update the app, pull statistics, tune recognition,
probe capture, choose a capture source) is a menu item that runs in a
progress dialog, so there is exactly one thing to launch and no console
windows. The window opens even with no data downloaded yet and explains what
to do.

Run modes (everything but live capture works with no game and no Windows):
    python -m draft_assist.ui.app              # live capture (Windows)
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

from ..config import DEBUG_OUT, REPO_ROOT, RULES_FILE
from ..data import store
from ..data.store import Dataset
from ..model import items as items_mod
from ..model import scoring
from . import theme
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
    def __init__(self, ds: Dataset, provider, rules, rules_meta):
        super().__init__()
        self.ds, self.provider = ds, provider
        self.rules, self.rules_meta = rules, rules_meta
        self.snapshot = None
        self.last_draft_key = None
        self.scored: list[scoring.ScoredHero] = []
        self.setWindowTitle("Dota Draft Assist")
        self.resize(1240, 820)
        self._build_menus()
        self._build()
        self._refresh_sources()
        self._update_first_run_banner()
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
        self._act(data_menu, "&Reload data and library", self.reload_backend,
                  "F5", "Re-read the downloaded data from disk")
        self._act(data_menu, "Open data &folder",
                  lambda: open_folder(REPO_ROOT / "data_cache"))

        cap_menu = bar.addMenu("&Capture")
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
        for side, caption in (("ally", "Your team"), ("enemy", "Enemy team")):
            label = QLabel(caption)
            label.setProperty("dim", True)
            tlay.addWidget(label)
            row = QHBoxLayout()
            row.setSpacing(6)
            buttons = []
            for _ in range(5):
                b = QPushButton("—")
                b.setEnabled(False)
                b.setProperty("slot", True)
                b.setToolTip("Click a drafted hero to see what beats it")
                b.clicked.connect(self._on_drafted_clicked)
                b.setProperty("side", side)
                row.addWidget(b)
                buttons.append(b)
            self.team_buttons[side] = buttons
            tlay.addLayout(row)
        self.unknown_label = QLabel("")
        self.unknown_label.setProperty("dim", True)
        tlay.addWidget(self.unknown_label)
        teams_card.setSizePolicy(teams_card.sizePolicy().horizontalPolicy(),
                                 teams_card.sizePolicy().Policy.Maximum)
        rlay.addWidget(teams_card)

        controls_card, clay = card()
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("My role:"))
        self.role_combo = QComboBox()
        for label, _ in ROLE_LABELS:
            self.role_combo.addItem(label)
        self.role_combo.currentIndexChanged.connect(self._refresh_views)
        row1.addWidget(self.role_combo, 1)
        row1.addWidget(QLabel("My team:"))
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
            for w in (self.source_combo, self.refresh_sources_button,
                      self.bind_button):
                w.setEnabled(False)
            self.source_combo.addItem("(live capture only)")
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
        dialog.start()
        dialog.exec()
        if dialog.succeeded and task.reload_after:
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
        self._update_first_run_banner()
        self._refresh_views()
        self.status.showMessage(
            "Reloaded: "
            + (f"{len(self.ds.hero_ids)} heroes" if not self.ds.is_empty
               else "no data downloaded yet"), 5000)

    def _update_first_run_banner(self) -> None:
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
        self._update_debug(snap)

    def _sides(self, snap) -> tuple[list[int], list[int]]:
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
                    b.setEnabled(True)
                else:
                    b.setText("—")
                    b.setProperty("hero_id", None)
                    b.setEnabled(False)
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

    def _on_drafted_clicked(self) -> None:
        b = self.sender()
        hid = b.property("hero_id")
        if hid is None:
            return
        side = b.property("side")
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
        if snap.warning:
            parts.append(f"WARNING: {snap.warning}")
        if snap.stalled:
            parts.append("CAPTURE STALLED — occluded window may have "
                         "stopped presenting")
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

    def _save_snapshot(self) -> None:
        """Dump exactly what the app sees right now: the captured frame, the
        overlay with crop boxes, the ten slot crops, and the per-slot match
        record. This folder is the unit of evidence — commit it and the
        whole failure is reproducible offline."""
        snap = self.snapshot
        if snap is None or snap.frame is None:
            self.snapshot_label.setText(
                "No captured frame to save (demo mode has none).")
            return
        from ..vision import debug as debug_mod
        from ..vision import library as library_mod
        from ..vision.recognize import read_draft
        names = {hid: self.ds.name(hid) for hid in self.ds.hero_ids}
        read = snap.read_raw
        session = getattr(self.provider, "session", None)
        if session is not None:
            read = read_draft(snap.frame, session.layout, session.lib,
                              session.params, keep_crops=True)
        if read is None:
            self.snapshot_label.setText("No recognition result yet.")
            return
        folder = debug_mod.dump(snap.frame, read, names)
        try:
            params = library_mod.load_params()
            params_line = (f"hash_size={params.hash_size} "
                           f"max_distance={params.max_distance} "
                           f"min_margin={params.min_margin}\n")
        except Exception:
            params_line = "recognition params unavailable\n"
        (folder / "context.txt").write_text(
            f"mode={snap.mode}\nsource={snap.source}\n"
            f"warning={snap.warning}\n"
            f"frame_size={snap.frame.shape[1]}x{snap.frame.shape[0]}\n"
            f"gate_score={snap.gate_score}\n"
            f"frames_arrived={snap.frames_arrived}\n" + params_line,
            encoding="utf-8")
        self.snapshot_label.setText(f"Saved to {folder}")


def make_provider(args, ds: Dataset):
    from .providers import DemoProvider, LiveProvider, ReplayProvider
    if args.demo:
        return DemoProvider(ds)
    from ..vision import library
    from ..vision.layout import load_layout
    from ..capture.session import CaptureSession
    params = library.load_params()
    try:
        lib = library.load(expected_hash_size=params.hash_size)
    except FileNotFoundError:
        # No portraits downloaded yet: an empty library still lets the app
        # open and offer Data > Update statistics.
        import numpy as np
        from ..vision.library import Library
        lib = Library(bits=np.zeros((0, params.bits), dtype=np.uint8),
                      hero_ids=np.zeros(0, dtype=np.int32), labels=[],
                      hash_size=params.hash_size)
    session = CaptureSession(load_layout(), lib, params)
    if args.replay:
        return ReplayProvider(session, Path(args.replay))
    return LiveProvider(session, title=args.window)


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
    args = parser.parse_args()

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
    provider = make_provider(args, ds)
    win = MainWindow(ds, provider, rules, meta)
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

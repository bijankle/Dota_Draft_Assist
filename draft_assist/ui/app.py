"""The application window: an ordinary draggable, resizable desktop window —
no transparency, no always-on-top, no click-through. It is not an overlay;
the user reads it in front of Dota and switches to the game to pick.

Run modes (everything but --live works with no game and no Windows):
    python -m draft_assist.ui.app --demo            # scripted fake draft
    python -m draft_assist.ui.app --replay DIR      # saved frames from disk
    python -m draft_assist.ui.app                   # live capture (Windows)
"""

import argparse
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QImage, QPixmap
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QHBoxLayout,
                             QLabel, QMainWindow, QPlainTextEdit, QPushButton,
                             QSplitter, QTableWidget, QTableWidgetItem,
                             QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from ..config import RULES_FILE
from ..data.store import Dataset
from ..model import items as items_mod
from ..model import scoring

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
HIGHLIGHT = QColor(46, 82, 46)
SEV_COLORS = {3: "#e05555", 2: "#e0a955", 1: "#8fa8c0"}


class MainWindow(QMainWindow):
    def __init__(self, ds: Dataset, provider, rules, rules_meta):
        super().__init__()
        self.ds, self.provider = ds, provider
        self.rules, self.rules_meta = rules, rules_meta
        self.snapshot = None
        self.last_draft_key = None
        self.scored: list[scoring.ScoredHero] = []
        self.setWindowTitle("Dota Draft Assist")
        self.resize(1180, 760)
        self._build()
        self._refresh_sources()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(300)

    # ---- widgets -----------------------------------------------------
    def _build(self) -> None:
        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        # ----- Draft tab
        draft_widget = QWidget()
        outer = QHBoxLayout(draft_widget)
        split = QSplitter()
        outer.addWidget(split)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Hero", "Score", "Base", "vs enemies", "with allies"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.table.itemSelectionChanged.connect(self._on_candidate_selected)
        self.table.horizontalHeader().setStretchLastSection(True)
        split.addWidget(self.table)

        right = QWidget()
        rlay = QVBoxLayout(right)
        split.addWidget(right)
        split.setSizes([620, 560])

        self.team_labels = {}
        self.team_buttons = {}
        for side, caption in (("ally", "Your team"), ("enemy", "Enemy team")):
            cap = QLabel(f"<b>{caption}</b>")
            rlay.addWidget(cap)
            row = QHBoxLayout()
            buttons = []
            for _ in range(5):
                b = QPushButton("—")
                b.setEnabled(False)
                b.clicked.connect(self._on_drafted_clicked)
                b.setProperty("side", side)
                row.addWidget(b)
                buttons.append(b)
            self.team_buttons[side] = buttons
            rlay.addLayout(row)

        self.unknown_label = QLabel("")
        rlay.addWidget(self.unknown_label)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("My role:"))
        self.role_combo = QComboBox()
        for label, _ in ROLE_LABELS:
            self.role_combo.addItem(label)
        self.role_combo.currentIndexChanged.connect(self._refresh_views)
        controls.addWidget(self.role_combo)
        controls.addWidget(QLabel("My team:"))
        self.side_combo = QComboBox()
        self.side_combo.addItems(["left bank", "right bank"])
        self.side_combo.currentIndexChanged.connect(self._force_redraw)
        controls.addWidget(self.side_combo)
        self.force_check = QCheckBox("Force recognition")
        self.force_check.toggled.connect(
            lambda on: self.provider.set_forced(on))
        controls.addWidget(self.force_check)
        controls.addStretch(1)
        rlay.addLayout(controls)

        lock_row = QHBoxLayout()
        lock_row.addWidget(QLabel("My pick:"))
        self.my_hero_combo = QComboBox()
        self.my_hero_combo.currentIndexChanged.connect(self._refresh_views)
        lock_row.addWidget(self.my_hero_combo, 1)
        self.lock_check = QCheckBox("Locked in")
        self.lock_check.toggled.connect(self._refresh_views)
        lock_row.addWidget(self.lock_check)
        rlay.addLayout(lock_row)

        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(False)
        rlay.addWidget(self.detail, 2)

        items_head = QLabel(
            "<b>Items</b> <i>(hand-authored rules — asserted, not measured; "
            "hero scores above are measured)</i>")
        rlay.addWidget(items_head)
        self.items_view = QTextBrowser()
        rlay.addWidget(self.items_view, 1)

        tabs.addTab(draft_widget, "Draft")

        # ----- Debug tab: the picture answers what a log never will
        dbg = QWidget()
        dlay = QVBoxLayout(dbg)
        self.debug_image = QLabel("no frame yet")
        self.debug_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.debug_image.setMinimumHeight(360)
        dlay.addWidget(self.debug_image, 3)
        self.debug_text = QPlainTextEdit()
        self.debug_text.setReadOnly(True)
        dlay.addWidget(self.debug_text, 1)
        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("Capture source:"))
        self.source_combo = QComboBox()
        self.source_combo.setMinimumWidth(280)
        src_row.addWidget(self.source_combo, 1)
        self.refresh_sources_button = QPushButton("Refresh list")
        self.refresh_sources_button.clicked.connect(self._refresh_sources)
        src_row.addWidget(self.refresh_sources_button)
        self.bind_button = QPushButton("Capture this window")
        self.bind_button.clicked.connect(self._bind_source)
        src_row.addWidget(self.bind_button)
        dlay.addLayout(src_row)
        if not hasattr(self.provider, "available_sources"):
            for w in (self.source_combo, self.refresh_sources_button,
                      self.bind_button):
                w.setEnabled(False)
            self.source_combo.addItem("(live capture only)")

        snap_row = QHBoxLayout()
        self.snapshot_button = QPushButton(
            "Save debug snapshot (frame + crops + matches)")
        self.snapshot_button.clicked.connect(self._save_snapshot)
        snap_row.addWidget(self.snapshot_button)
        self.snapshot_label = QLabel("")
        snap_row.addWidget(self.snapshot_label, 1)
        dlay.addLayout(snap_row)
        tabs.addTab(dbg, "Debug")

        self.status = self.statusBar()

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

    def _refresh_sources(self) -> None:
        if not hasattr(self.provider, "available_sources"):
            return
        current = self.source_combo.currentText()
        self.source_combo.clear()
        self.source_combo.addItems(self.provider.available_sources())
        idx = self.source_combo.findText(current)
        if idx >= 0:
            self.source_combo.setCurrentIndex(idx)

    def _bind_source(self) -> None:
        title = self.source_combo.currentText()
        if not title or not hasattr(self.provider, "rebind"):
            return
        message = self.provider.rebind(title)
        self.snapshot_label.setText(message)
        self.status.showMessage(message)
        self.last_draft_key = None

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
        # Re-read with crops kept so the dump contains the slot images.
        read = snap.read_raw
        if getattr(self.provider, "session", None) is not None:
            session = self.provider.session
            read = read_draft(snap.frame, session.layout, session.lib,
                              session.params, keep_crops=True)
        if read is None:
            self.snapshot_label.setText("No recognition result yet.")
            return
        folder = debug_mod.dump(snap.frame, read, names)
        params = library_mod.load_params()
        (folder / "context.txt").write_text(
            f"mode={snap.mode}\nsource={snap.source}\n"
            f"warning={snap.warning}\n"
            f"frame_size={snap.frame.shape[1]}x{snap.frame.shape[0]}\n"
            f"gate_score={snap.gate_score}\n"
            f"frames_arrived={snap.frames_arrived}\n"
            f"hash_size={params.hash_size} "
            f"max_distance={params.max_distance} "
            f"min_margin={params.min_margin}\n",
            encoding="utf-8")
        self.snapshot_label.setText(f"Saved to {folder}")

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
            f"<i>{unknown} slot(s) unresolved — scoring uses only confident "
            "slots</i>" if unknown else "")

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
                if tags and tags & hero_roles:
                    item.setBackground(HIGHLIGHT)
                self.table.setItem(row, col, item)
        self.table.blockSignals(False)
        self.table.verticalScrollBar().setValue(scroll_pos)
        if selected is not None:
            self._select_hero_row(selected)
        self._update_items(draft)

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
        html = [f"<h3>{self.ds.name(hid)} — component breakdown</h3>"]
        if s:
            html.append(f"<p>baseline {s.baseline * 100:.1f}% "
                        f"&rarr; total <b>{s.score * 100:.1f}%</b></p>")
        if not terms:
            html.append("<p><i>No drafted heroes resolved yet — the score "
                        "is pure baseline.</i></p>")
        html.append("<table cellpadding=3>")
        for t in terms:
            kind = "vs" if t.kind == "vs" else "with"
            color = "#7fd47f" if t.delta > 0 else "#d47f7f"
            html.append(
                f"<tr><td>{kind} {t.other_name}</td>"
                f"<td align=right><font color='{color}'>"
                f"{t.delta * 100:+.2f}</font></td></tr>")
        html.append("</table><p><i>Individual terms, not the sum — check "
                    "whether a plausible total has poor reasons.</i></p>")
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
        html = [f"<h3>Best against {self.ds.name(hid)} "
                f"<small>({cap} {side} pick)</small></h3>",
                "<table cellpadding=3>"]
        for chid, name, delta in counters:
            html.append(f"<tr><td>{name}</td><td align=right>"
                        f"{delta * 100:+.2f}</td></tr>")
        html.append("</table>")
        self.detail.setHtml("".join(html))

    def _update_items(self, draft: scoring.DraftState) -> None:
        if draft.my_hero is None:
            self.items_view.setHtml(
                "<i>Lock your pick (select it above and tick 'Locked in') "
                "to see item flags.</i>")
            return
        enemy_names = [self.ds.name(h) for h in draft.enemies]
        ally_names = [self.ds.name(h) for h in draft.allies
                      if h != draft.my_hero]
        advice = items_mod.recommend(
            self.rules, enemy_names, ally_names, draft.my_role,
            self.rules_meta.get("current_patch", "0.0"))
        if not advice:
            self.items_view.setHtml(
                "<i>Nothing urgent flagged for this lineup — silence is a "
                "valid answer.</i>")
            return
        html = []
        for a in advice:
            worst = a.triggers[0].severity
            color = SEV_COLORS.get(worst, "#cccccc")
            stale = (" <b>[unverified this patch]</b>" if a.any_stale else "")
            html.append(f"<p><font color='{color}'><b>{a.item}</b></font> "
                        f"(weight {a.score:.1f}){stale}<br>")
            for t in a.triggers:
                html.append(f"&nbsp;&nbsp;sev {t.severity}: {t.reason}<br>")
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
        age = self.ds.age_hours()
        stale = " (STALE — run tools/pull_data.py)" if self.ds.is_stale() else ""
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

    def _update_debug(self, snap) -> None:
        # Debug shows the RAW per-frame read (live confidences, flicker and
        # all); the draft panels show the stabilised one.
        read = snap.read_raw or snap.read
        if snap.frame is None or read is None:
            self.debug_text.setPlainText(
                f"mode={snap.mode}  gate score={snap.gate_score:.3f}  "
                f"frames arrived={snap.frames_arrived}\n"
                "No recognised frame yet. In demo mode there is no frame at "
                "all; live/replay show the captured frame with crop boxes "
                "here as soon as recognition runs.")
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
                 f"frames arrived: {snap.frames_arrived}"]
        for s in read.slots:
            resolved = ("UNKNOWN" if s.hero_id is None else
                        "EMPTY" if s.hero_id == -1 else self.ds.name(s.hero_id))
            lines.append(f"{s.rect.team}{s.rect.slot}: {resolved:20s} "
                         f"nearest={s.best_label} d={s.distance} m={s.margin}")
        self.debug_text.setPlainText("\n".join(lines))


def make_provider(args, ds: Dataset):
    from .providers import DemoProvider, LiveProvider, ReplayProvider
    if args.demo:
        return DemoProvider(ds)
    from ..vision import library
    from ..vision.layout import load_layout
    params = library.load_params()
    lib = library.load(expected_hash_size=params.hash_size)
    from ..capture.session import CaptureSession
    session = CaptureSession(load_layout(), lib, params)
    if args.replay:
        return ReplayProvider(session, Path(args.replay))
    return LiveProvider(session, title=args.window)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true",
                        help="scripted fake draft; no dataset/library needed")
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
        from ..data import store
        ds = store.load()

    rules, meta = items_mod.load_rules(RULES_FILE)

    app = QApplication(sys.argv)
    provider = make_provider(args, ds)
    win = MainWindow(ds, provider, rules, meta)
    win.show()
    # start() never raises for live capture: an unbound source is a state
    # the user fixes in the Debug tab, not a crash.
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

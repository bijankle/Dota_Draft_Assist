"""The Analysis tab: one account's match history, measured.

It replaced the ranked list of every hero not in the game, at the user's
request. That list answered "what should I pick", which the Draft tab now
answers in the one place it belongs — under the picks — and this tab
answers the other question the app was never asking: what, across a few
hundred of your own games, actually goes with winning.

**IT RUNS WHEN ASKED AND NEVER OTHERWISE.** The app's live loop makes no
network calls and this does not change that: a run is a button, on a
worker thread, against an account the user typed in. Nothing here is
touched by `MainWindow.refresh`.

**THE LOOK IS THE DRAFT TAB'S.** Same `card`, same headings, same
green-and-red for a signed deviation, same grid lines, same tick boxes.
The browser version it came from had a light theme of its own, and
carrying that across would have made one window that looks like two
programs.
"""

from datetime import datetime

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout,
                             QHeaderView, QLabel, QLineEdit, QPushButton,
                             QScrollArea, QSizePolicy, QStyledItemDelegate,
                             QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from . import theme
from .chrome import TickBox, card
from ..history import analyse, opendota, store, workbook
from ..history.report import CAPS, WINDOWS, Options
from ..history.runner import Refused, run as run_analysis

# The deviation bar's column, and how far from the datum a full-width bar
# means. Scaled per block against its own biggest eligible deviation, so a
# block of small differences is still readable rather than flat.
BAR_COLUMN = 3
BAR_MIN_SCALE = 0.08
# A bucket's bar fades with its sample: the eye should not read a 3-game
# bucket and a 90-game bucket as the same claim.
FADE_FLOOR = 0.25


class Bar(QStyledItemDelegate):
    """The deviation bar: a datum line down the middle, the bar off it.

    A number says how far from your own rate a bucket sits; the bar says it
    at a glance across twenty rows, which is what a table of percentages
    cannot do. Green right, red left, the same convention as every other
    signed number in the app.
    """

    def paint(self, painter, option, index):        # noqa: N802 - Qt naming
        rect = option.rect
        painter.save()
        middle = rect.center().x()
        # The datum, drawn in the app's own rule grey rather than the
        # border colour: a line the eye cannot find is not a datum, and
        # every bar in the column is measured from it.
        painter.setPen(QColor(theme.RULE))
        painter.drawLine(middle, rect.top() + 2, middle, rect.bottom() - 2)
        data = index.data(Qt.ItemDataRole.UserRole)
        if data:
            delta, scale, eligible, weight = data
            span = 0.0 if not scale else min(abs(delta) / scale, 1.0)
            width = int(span * (rect.width() / 2 - 6))
            if width > 0:
                colour = QColor(theme.GOOD if delta >= 0 else theme.BAD)
                colour.setAlphaF(max(FADE_FLOOR, weight)
                                 * (1.0 if eligible else 0.45))
                top = rect.top() + max(3, rect.height() // 4)
                height = rect.height() - 2 * (top - rect.top())
                left = middle if delta >= 0 else middle - width
                painter.fillRect(left, top, width, height, colour)
        painter.restore()


class BucketTable(QTableWidget):
    """One analysis block: bucket, games, the figure, and the bar.

    Sized to its rows and never scrolling, the same rule the draft grids
    live by: a scrollbar on a table that is meant to be read at a glance
    hides part of the answer while making the widget look correct.
    """

    def __init__(self, headers, parent=None):
        super().__init__(0, 4, parent)
        self.setHorizontalHeaderLabels(headers)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setItemDelegateForColumn(BAR_COLUMN, Bar(self))
        # The first column is a name, so its heading reads from the left
        # with it; the two number columns keep Qt's centring.
        item = QTableWidgetItem(headers[0])
        item.setTextAlignment(Qt.AlignmentFlag.AlignLeft
                              | Qt.AlignmentFlag.AlignVCenter)
        self.setHorizontalHeaderItem(0, item)
        head = self.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2):
            head.setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents)
        head.setSectionResizeMode(BAR_COLUMN, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(BAR_COLUMN, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    def fill(self, rows, figure, scale, no_finding=()) -> None:
        """`figure` turns a bucket into the middle column's text."""
        self.setRowCount(len(rows))
        biggest = max((row.n for row in rows), default=1) or 1
        for index, row in enumerate(rows):
            muted = not row.eligible or row.key in no_finding
            name = QTableWidgetItem(row.key)
            name.setToolTip(row.key)
            count = QTableWidgetItem(str(row.n))
            count.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                   | Qt.AlignmentFlag.AlignVCenter)
            value = QTableWidgetItem(figure(row))
            value.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                   | Qt.AlignmentFlag.AlignVCenter)
            if muted:
                # Measured, but not enough of it to act on. Shown rather
                # than hidden, so what was counted is visible.
                for item in (name, count, value):
                    item.setForeground(QColor(theme.TEXT_DIM))
            self.setItem(index, 0, name)
            self.setItem(index, 1, count)
            self.setItem(index, 2, value)
            bar = QTableWidgetItem("")
            bar.setData(Qt.ItemDataRole.UserRole,
                        (row.delta, scale, not muted,
                         (row.n / biggest) ** 0.5))
            self.setItem(index, BAR_COLUMN, bar)
        self._fit_height()

    def _fit_height(self) -> None:
        head = self.horizontalHeader()
        header_h = max(head.height(), head.sizeHint().height())
        self.setFixedHeight(header_h + self.verticalHeader().length()
                            + 2 * self.frameWidth() + 2)


class Worker(QThread):
    """The run, off the UI thread. Progress and the answer come back as
    signals, because touching a widget from another thread is how Qt
    applications crash in ways that never reproduce."""

    progress = pyqtSignal(str, int, int)
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.options = options
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:                          # noqa: D102 - QThread
        try:
            report = run_analysis(
                self.options,
                say=lambda text, done=0, total=0: self.progress.emit(
                    text, done, total),
                cancelled=lambda: self._stop)
        except Refused as refused:
            self.failed.emit(str(refused))
        except opendota.ApiError as error:
            self.failed.emit(error.message)
        except Exception as error:                  # noqa: BLE001
            self.failed.emit(f"{error.__class__.__name__}: {error}")
        else:
            self.finished_ok.emit(report)


class HistoryTab(QWidget):
    """The whole tab: who, what to measure, and what came back."""

    def __init__(self, say=None, parent=None):
        super().__init__(parent)
        self.say = say or (lambda text, millis=4000: None)
        self.report = None
        self.worker = None
        self._account = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)
        # A LONG PAGE GOES IN A SCROLL AREA. A tab widget's minimum is its
        # tallest page whether or not you are looking at it, so a report
        # thirteen blocks long would otherwise set the floor for the whole
        # window and the draft screen could never be made short again.
        scroll = QScrollArea()
        scroll.setWidget(page)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        lay.addWidget(self._build_account_card())
        lay.addWidget(self._build_options_card())
        self.results = QVBoxLayout()
        self.results.setSpacing(10)
        lay.addLayout(self.results)
        lay.addStretch(1)

        self._load_accounts()
        self._show_placeholder()

    # ---- the controls --------------------------------------------------
    def _build_account_card(self) -> QFrame:
        frame, lay = card("Match history")
        row = QHBoxLayout()
        row.setSpacing(8)
        self.account_box = QLineEdit()
        self.account_box.setPlaceholderText(
            "Friend ID, Steam ID, or a Dotabuff / OpenDota profile URL")
        self.account_box.returnPressed.connect(self.start)
        row.addWidget(self.account_box, 1)

        self.remembered = QComboBox()
        self.remembered.setMinimumWidth(190)
        self.remembered.setToolTip(
            "Accounts this machine has looked at before. Kept locally and "
            "never committed, so a copy of this app carries none of them.")
        self.remembered.activated.connect(self._pick_remembered)
        row.addWidget(self.remembered)

        self.run_button = QPushButton("Run")
        self.run_button.setProperty("accent", True)
        self.run_button.clicked.connect(self.start)
        row.addWidget(self.run_button)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.setVisible(False)
        row.addWidget(self.stop_button)
        lay.addLayout(row)

        # THE LAST RUN LIVES AT THE TOP, at the user's request: opening the
        # tab should say when this account was last measured without
        # measuring it again.
        self.last_run = QLabel("")
        self.last_run.setProperty("dim", True)
        self.last_run.setVisible(False)
        lay.addWidget(self.last_run)
        self.status = QLabel("")
        self.status.setProperty("dim", True)
        self.status.setWordWrap(True)
        self.status.setVisible(False)
        lay.addWidget(self.status)
        return frame

    @staticmethod
    def _note(label: QLabel, text: str) -> None:
        """Say it, or take up no room at all.

        An empty label is still a widget in a layout, and two of them under
        this card's one row is a card with a blank strip under it for no
        reason — the same rule the team panels' note follows.
        """
        label.setText(text)
        label.setVisible(bool(text))

    def _build_options_card(self) -> QFrame:
        frame, lay = card("What to measure")
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("Window"))
        self.window_box = QComboBox()
        for key, label, _days in WINDOWS:
            self.window_box.addItem(label, key)
        self.window_box.setCurrentIndex(3)          # last 12 months
        row.addWidget(self.window_box)
        row.addWidget(QLabel("At most"))
        self.cap_box = QComboBox()
        for cap in CAPS:
            self.cap_box.addItem(f"{cap} matches", cap)
        self.cap_box.setCurrentIndex(CAPS.index(1000))
        row.addWidget(self.cap_box)
        self.turbo_tick = TickBox("Exclude Turbo")
        self.turbo_tick.setChecked(True)
        row.addWidget(self.turbo_tick)
        self.ranked_tick = TickBox("Ranked only")
        row.addWidget(self.ranked_tick)
        row.addStretch(1)
        self.export_button = QPushButton("Export workbook…")
        self.export_button.clicked.connect(self.export)
        self.export_button.setEnabled(False)
        row.addWidget(self.export_button)
        lay.addLayout(row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(4)
        self.analysis_ticks = {}
        for index, (key, name, default, _desc) in enumerate(analyse.ANALYSES):
            tick = TickBox(name)
            tick.setChecked(default)
            tick.setToolTip(analyse.DESCS[key])
            self.analysis_ticks[key] = tick
            grid.addWidget(tick, index // 3, index % 3)
        lay.addLayout(grid)
        return frame

    # ---- remembered accounts -------------------------------------------
    def _load_accounts(self) -> None:
        self.remembered.blockSignals(True)
        self.remembered.clear()
        self.remembered.addItem("Remembered accounts…", None)
        for row in store.load():
            self.remembered.addItem(store.label(row), row["account_id"])
        self.remembered.blockSignals(False)
        rows = store.load()
        if rows and not self.account_box.text().strip():
            self._apply_remembered(rows[0])

    def _pick_remembered(self, index: int) -> None:
        account_id = self.remembered.itemData(index)
        if account_id is None:
            return
        row = next((r for r in store.load()
                    if r["account_id"] == account_id), None)
        if row:
            self._apply_remembered(row)

    def _apply_remembered(self, row: dict) -> None:
        self.account_box.setText(str(row["account_id"]))
        options = Options.from_dict(row.get("options") or {},
                                    row["account_id"])
        self._apply_options(options)
        self._show_last_run(row)

    def _apply_options(self, options: Options) -> None:
        index = self.window_box.findData(options.window)
        if index >= 0:
            self.window_box.setCurrentIndex(index)
        index = self.cap_box.findData(options.cap)
        if index >= 0:
            self.cap_box.setCurrentIndex(index)
        self.turbo_tick.setChecked(options.no_turbo)
        self.ranked_tick.setChecked(options.ranked_only)
        for key, tick in self.analysis_ticks.items():
            if key in options.picked:
                tick.setChecked(bool(options.picked[key]))

    def _show_last_run(self, row: dict) -> None:
        when = row.get("last_run") or ""
        if not when:
            self._note(self.last_run, "Not run on this machine yet.")
            return
        matches, wins = row.get("matches", 0), row.get("wins", 0)
        rate = f", {wins / matches * 100:.1f}% win rate" if matches else ""
        name = (row.get("name") or "").strip()
        who = f"{name} · {row['account_id']}" if name else row["account_id"]
        self._note(self.last_run,
                   f"Last run {when} for {who} — {matches} matches{rate}.")

    # ---- running -------------------------------------------------------
    def options(self) -> Options:
        return Options(
            account_id=0,
            window=self.window_box.currentData(),
            cap=self.cap_box.currentData(),
            no_turbo=self.turbo_tick.isChecked(),
            ranked_only=self.ranked_tick.isChecked(),
            picked={key: tick.isChecked()
                    for key, tick in self.analysis_ticks.items()})

    def start(self) -> None:
        from ..history import account as account_mod
        if self.worker is not None:
            return
        parsed = account_mod.parse(self.account_box.text())
        if parsed.error:
            self._fault(parsed.error)
            return
        if parsed.account_id is None:
            # A display name needs OpenDota's /search, which scans a very
            # large table and times out often. Saying so beats hanging.
            self._fault(
                "That reads as a display name, and looking one up needs "
                "OpenDota's search, which this app does not use because it "
                "times out more often than it answers. Use the Friend ID "
                "from your Dota 2 profile instead. " + account_mod.IN_GAME)
            return
        self._account = parsed
        options = self.options()
        options.account_id = parsed.account_id
        self._set_running(True)
        self._note(self.status, "Starting…")
        self.worker = Worker(options, self)
        self.worker.progress.connect(self._progress)
        self.worker.finished_ok.connect(self._done)
        self.worker.failed.connect(self._fault)
        self.worker.finished.connect(self._cleanup)
        self.worker.start()

    def stop(self) -> None:
        if self.worker is not None:
            self.worker.stop()
            self._note(self.status, "Stopping…")

    def _set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.stop_button.setVisible(running)
        self.account_box.setEnabled(not running)

    def _progress(self, text: str, done: int, total: int) -> None:
        self._note(self.status, f"{text} {done}/{total}" if total else text)

    def _fault(self, message: str) -> None:
        self._note(self.status, message)
        self.say("Match history: " + message.split(".")[0], 6000)
        self._set_running(False)

    def _cleanup(self) -> None:
        self.worker = None
        self._set_running(False)

    def _done(self, report) -> None:
        parsed = self._account
        report.how = parsed.how if parsed else ""
        report.name = (parsed.name or "") if parsed else ""
        self.report = report
        self.export_button.setEnabled(True)
        self._note(self.status, "")
        rows = store.remember(
            report.options.account_id, report.name,
            when=report.ran_at.strftime("%Y-%m-%d %H:%M"),
            matches=report.n, wins=report.wins,
            options=report.options.as_dict())
        self._load_accounts()
        self._show_last_run(rows[0])
        self.render(report)
        self.say(f"Match history: {report.n} matches measured", 6000)

    # ---- drawing the report --------------------------------------------
    def _clear_results(self) -> None:
        while self.results.count():
            item = self.results.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _show_placeholder(self) -> None:
        self._clear_results()
        frame, lay = card("What this measures")
        text = QLabel(
            "Your own win rate across the matches that survive the filters "
            "is the datum. Every split asks whether a bucket sits far "
            "enough off that line to be distinguishable from sampling "
            "noise — at least "
            f"{analyse.MIN_BUCKET} games in the bucket and "
            f"{analyse.SIGMA_CAT} standard errors away.\n\n"
            "Twelve analyses run at once, so some buckets clear that bar by "
            "chance alone. A finding is a hypothesis to test against the "
            "next hundred games, not a conclusion.\n\n"
            "It reads public match history from OpenDota. If nothing comes "
            "back, the usual cause is Expose Public Match Data being off in "
            "the Dota 2 settings.")
        text.setWordWrap(True)
        text.setProperty("dim", True)
        lay.addWidget(text)
        self.results.addWidget(frame)

    def render(self, report) -> None:
        self._clear_results()
        self.results.addWidget(self._headline(report))
        rates, contributions = report.split_findings()
        # THE TWO FAMILIES ARE HEADLINED APART. Contribution metrics
        # separate far harder than win-rate splits because they are partly
        # structural — a mid laner out-damages a hard support by
        # construction — so one merged ranking by sigma would be nothing
        # but damage rows with every behavioural finding buried under it.
        self.results.addWidget(self._findings_card(
            "What goes with winning", rates,
            "Nothing clears the significance floor. On this sample the "
            "variation between your buckets is noise."))
        if contributions:
            self.results.addWidget(self._findings_card(
                "What you do on each hero", contributions,
                "", metric=True))
        for block in report.blocks:
            self.results.addWidget(self._block_card(block, report))

    def _headline(self, report) -> QFrame:
        frame, lay = card("This run")
        period = report.period
        dropped = report.dropped
        lines = [
            f"{report.n} matches, {report.wins} won — "
            f"{report.baseline * 100:.1f}% is the datum every split below "
            "is measured against.",
            f"{period[0]} to {period[1]}, {report.sessions} play sessions, "
            f"{report.returned} returned by the API before filtering.",
        ]
        cut = [f"{count} {why}" for why, count in (
            ("under five minutes", dropped.get("short", 0)),
            ("outside the window", dropped.get("window", 0)),
            ("Turbo", dropped.get("turbo", 0)),
            ("not ranked", dropped.get("unranked", 0)),
            ("malformed", dropped.get("malformed", 0))) if count]
        if cut:
            lines.append("Dropped: " + ", ".join(cut) + ".")
        label = QLabel("\n".join(lines))
        label.setWordWrap(True)
        lay.addWidget(label)
        return frame

    def _findings_card(self, title: str, pairs: list, empty: str,
                       metric: bool = False) -> QFrame:
        frame, lay = card(title)
        if not pairs:
            note = QLabel(empty)
            note.setWordWrap(True)
            note.setProperty("dim", True)
            lay.addWidget(note)
            return frame
        for block, finding in pairs:
            row = QHBoxLayout()
            row.setSpacing(10)
            sigma = QLabel(f"{finding.sigma:+.1f}σ")
            sigma.setMinimumWidth(58)
            sigma.setStyleSheet(
                f"color: {theme.GOOD if finding.sigma > 0 else theme.BAD};")
            row.addWidget(sigma)
            text = QLabel(finding.text)
            text.setWordWrap(True)
            row.addWidget(text, 1)
            name = QLabel(block.name)
            name.setProperty("dim", True)
            row.addWidget(name)
            lay.addLayout(row)
        return frame

    def _block_card(self, block, report) -> QFrame:
        frame, lay = card(block.name)
        note = QLabel(block.desc)
        note.setWordWrap(True)
        note.setProperty("dim", True)
        lay.addWidget(note)

        if block.kind == "items":
            self._item_block(block, lay)
            return frame

        if not block.shown:
            empty = QLabel("No matches carry this field.")
            empty.setProperty("dim", True)
            lay.addWidget(empty)
            return frame

        if block.kind == "metric":
            headers = ["Hero", "Games", f"Mean {block.unit}",
                       f"Against your {block.datum:.{block.dp}f}"]
            figure = (lambda row, dp=block.dp: f"{row.mean:.{dp}f}")
            scale = max(abs(block.datum or 0) * 0.10,
                        max((abs(r.delta) for r in block.shown
                             if r.eligible), default=0.0))
        else:
            headers = ["Bucket", "Games", "Win rate",
                       f"Against your {report.baseline * 100:.0f}%"]
            figure = (lambda row: f"{row.rate * 100:.0f}%")
            scale = max(BAR_MIN_SCALE,
                        max((abs(r.delta) for r in block.shown
                             if r.eligible), default=0.0))
        table = BucketTable(headers)
        table.fill(block.shown, figure, scale, block.no_finding)
        lay.addWidget(table)

        if block.hidden:
            hidden = QLabel(
                f"{block.hidden} bucket(s) holding a single game are not "
                "shown — a rate next to an n of one is noise wearing a "
                "number. They are in the workbook.")
            hidden.setWordWrap(True)
            hidden.setProperty("dim", True)
            lay.addWidget(hidden)
        if block.caveat:
            caveat = QLabel(block.caveat)
            caveat.setWordWrap(True)
            caveat.setProperty("dim", True)
            lay.addWidget(caveat)
        return frame

    def _item_block(self, block, lay) -> None:
        if block.covered < block.total:
            note = QLabel(
                f"{block.covered} of {block.total} matches came back with "
                "item columns. Items are only guaranteed on OpenDota's "
                "single-match endpoint, which is one request per match.")
            note.setWordWrap(True)
            note.setProperty("dim", True)
            lay.addWidget(note)
        for group in block.groups:
            heading = QLabel(
                f"{group.hero} — {group.games} games, "
                + (f"{group.measured} with item data, "
                   f"{group.baseline * 100:.0f}% on this hero"
                   if group.baseline is not None
                   else "no item data on any of them"))
            heading.setWordWrap(True)
            lay.addWidget(heading)
            if not group.shown:
                continue
            scale = max(BAR_MIN_SCALE,
                        max((abs(r.delta) for r in group.shown
                             if r.eligible), default=0.0))
            table = BucketTable(
                ["Item", "Games", "Win rate",
                 f"Against {group.baseline * 100:.0f}%"
                 if group.baseline is not None else "—"])
            table.fill(group.shown, lambda row: f"{row.rate * 100:.0f}%",
                       scale)
            lay.addWidget(table)

    def shutdown(self) -> None:
        """Stop a run in flight, and WAIT for it.

        A QThread destroyed while it is still running takes the process
        with it, and closing the window during a thousand-match fetch is
        exactly when that happens. The wait is bounded: the worker checks
        for the stop between requests, and a request that is already out
        has a timeout of its own.
        """
        if self.worker is None:
            return
        self.worker.stop()
        self.worker.wait(5000)

    # ---- export --------------------------------------------------------
    def export(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        if self.report is None:
            return
        from ..config import REPO_ROOT
        folder = REPO_ROOT / "history_reports"
        folder.mkdir(parents=True, exist_ok=True)
        suggested = str(folder / workbook.filename(self.report))
        path, _filter = QFileDialog.getSaveFileName(
            self, "Save the workbook", suggested, "Excel workbook (*.xlsx)")
        if not path:
            return
        try:
            workbook.write(self.report, path)
        except Exception as error:                  # noqa: BLE001
            self._note(self.status,
                       f"Could not write the workbook: {error}")
            return
        self._note(self.status, f"Workbook written to {path}")
        self.say("Workbook written", 6000)

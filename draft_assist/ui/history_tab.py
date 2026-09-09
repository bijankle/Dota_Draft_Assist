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

from . import settings as ui_settings
from . import theme
from .chrome import CountBox, TickBox, card
from ..history import analyse, cache, opendota, store, workbook
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


# The three text columns, as (index, key). The bar column is the figure
# said again in ink, so it sorts by the same value rather than offering a
# fourth answer.
NAME_COL, GAMES_COL, VALUE_COL = 0, 1, 2
SORT_KEYS = {NAME_COL: "name", GAMES_COL: "games", VALUE_COL: "value"}
COL_OF = {key: col for col, key in SORT_KEYS.items()}
# What the "top N by" dropdown offers. NAME IS NOT AMONG THEM: "the top
# ten by name" is alphabetical, which is an ordering rather than a
# ranking, and a filter that cannot say what it kept OUT is not a filter.
FILTER_BY = (("games", "games"), ("value", "the figure"))
# Nought is ALL, the same convention the strips' count boxes use, and it
# is the default: a table that opens already cut has hidden something
# before the reader has asked for anything.
SHOW_ALL = 0
MAX_ROWS = 200


def sort_value(row, key: str, value_of):
    """One row's answer for one sort key."""
    if key == "name":
        return str(row.key).lower()
    if key == "value":
        return float(value_of(row))
    return int(row.n)


class TableControls(QWidget):
    """"Top [10] by [games]" — the filter, above its own table.

    TWO INPUTS, at the user's request, because the cut and the reading
    are different questions: "filter the top 10 heroes by number of games
    played, and then sort by win rate". One control doing both would make
    those the same answer — the ten shown would always be the ten the
    sort puts first, so asking for the best win rates would quietly
    reduce the table to whichever three-game buckets got lucky.
    """

    changed = pyqtSignal()

    def __init__(self, value_label: str, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(QLabel("Top"))
        # The app's own count box, with the painted arrows every other
        # number-with-arrows in this window uses.
        self.count = CountBox(SHOW_ALL, SHOW_ALL, MAX_ROWS)
        # NOUGHT READS AS "all", not as "0". The strips' count boxes use
        # the same convention and can leave it implicit because a row is
        # visibly full; a table cut to nothing looks the same as a table
        # of nothing, so this one says the word.
        self.count.setSpecialValueText("all")
        self.count.setToolTip("How many rows to show, by the ranking "
                              "beside this. Wind it down to nothing for "
                              "all of them.")
        self.count.valueChanged.connect(self.changed)
        row.addWidget(self.count)
        row.addWidget(QLabel("by"))
        self.by = QComboBox()
        for key, label in FILTER_BY:
            self.by.addItem(label if key != "value" else value_label, key)
        self.by.setToolTip(
            "Which column decides who makes the cut. The sort below is "
            "separate — click a heading to re-order what survived.")
        self.by.currentIndexChanged.connect(self.changed)
        row.addWidget(self.by)
        row.addStretch(1)

    def state(self) -> tuple:
        return (self.count.value(), self.by.currentData())

    def set_state(self, top: int, by: str) -> None:
        for widget in (self.count, self.by):
            widget.blockSignals(True)
        self.count.setValue(max(SHOW_ALL, min(MAX_ROWS, int(top))))
        index = self.by.findData(by)
        self.by.setCurrentIndex(index if index >= 0 else 0)
        for widget in (self.count, self.by):
            widget.blockSignals(False)


class BucketTable(QTableWidget):
    """One analysis block: bucket, games, the figure, and the bar.

    Sized to its rows and never scrolling, the same rule the draft grids
    live by: a scrollbar on a table that is meant to be read at a glance
    hides part of the answer while making the widget look correct.

    **THE CUT AND THE SORT ARE TWO SEPARATE THINGS**, at the user's
    request. The rows are ranked by the FILTER field and cut to the top
    N; what survives is then ordered by whatever heading was last
    clicked. Both default to games, which is the order this table has
    always been in.

    **IT RE-RENDERS RATHER THAN CALLING `sortItems`.** Qt sorts a table
    on the item's TEXT, so "10" sorts before "9" and "62%" before "9%" —
    every column here is a number wearing a suffix. Holding the rows and
    drawing them again is also what keeps the bar column honest: its
    fade is relative to the biggest sample IN THE TABLE, so a cut that
    removes the biggest bucket has to re-scale the survivors or every
    remaining bar reads too faint.
    """

    changed = pyqtSignal()

    def __init__(self, headers, parent=None):
        super().__init__(0, 4, parent)
        self.setHorizontalHeaderLabels(headers)
        self._headers = list(headers)
        self._rows: list = []
        self._figure = str
        self._scale = 1.0
        self._no_finding: tuple = ()
        self._value_of = (lambda row: 0.0)
        self._top = SHOW_ALL
        self._by = "games"
        self._sort = "games"
        self._descending = True
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setItemDelegateForColumn(BAR_COLUMN, Bar(self))
        head = self.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2):
            head.setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents)
        head.setSectionResizeMode(BAR_COLUMN, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(BAR_COLUMN, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        head.setSectionsClickable(True)
        head.sectionClicked.connect(self._clicked)
        self._label_headers()

    # ---- what it holds ------------------------------------------------
    def show_rows(self, rows, figure, scale, no_finding=(),
                  value_of=None) -> None:
        """Every row this block measured. The cut happens at render."""
        self._rows = list(rows)
        self._figure = figure
        self._scale = scale
        self._no_finding = tuple(no_finding)
        self._value_of = value_of or (lambda row: getattr(row, "rate", 0.0))
        self.render_rows()

    # Kept so a caller that only wants the old behaviour still works.
    fill = show_rows

    def set_view(self, top=None, by=None, sort=None,
                 descending=None, desc=None) -> None:
        """`desc` is the stored spelling, so a whole saved view can be
        handed straight back in."""
        if desc is not None and descending is None:
            descending = desc
        if top is not None:
            self._top = max(SHOW_ALL, min(MAX_ROWS, int(top)))
        if by in COL_OF or by == "games":
            self._by = by
        if sort in COL_OF:
            self._sort = sort
        if descending is not None:
            self._descending = bool(descending)
        self._label_headers()
        self.render_rows()

    def view(self) -> dict:
        return {"top": self._top, "by": self._by, "sort": self._sort,
                "desc": self._descending}

    def view_state(self) -> tuple:
        """Just the two the control row owns."""
        return (self._top, self._by)

    # ---- the cut, then the order --------------------------------------
    def survivors(self) -> list:
        """Ranked by the FILTER field, cut to the top N.

        Always descending, because "top ten by games" means the ten most
        played whichever way the table is being READ — tying the cut to
        the sort direction would make clicking a heading silently change
        which rows exist.
        """
        rows = list(self._rows)
        if self._top and self._top < len(rows):
            rows.sort(key=lambda r: sort_value(r, self._by, self._value_of),
                      reverse=True)
            rows = rows[:self._top]
        return rows

    def render_rows(self) -> None:
        rows = self.survivors()
        rows.sort(key=lambda r: sort_value(r, self._sort, self._value_of),
                  reverse=self._descending)
        self._draw(rows)

    def _clicked(self, column: int) -> None:
        """A heading re-orders; the bar column defers to the figure it
        draws rather than offering a fourth answer."""
        key = SORT_KEYS.get(column if column != BAR_COLUMN else VALUE_COL)
        if key is None:
            return
        # Same column again flips it; a NEW column starts descending,
        # because "most" is what anybody wants first from every one of
        # these — most games, highest rate, and A-Z is the odd one out.
        self._descending = (not self._descending if key == self._sort
                            else key != "name")
        self._sort = key
        self._label_headers()
        self.render_rows()
        self.changed.emit()

    def _label_headers(self) -> None:
        """The caret is drawn INTO the heading text.

        Qt's own sort indicator is a sub-control this stylesheet does not
        name, and the parts a stylesheet does not name are handed to the
        native style to draw — the lesson the scrollbars taught, and on
        Windows through a translucent window it is exactly the sort of
        stray mark that shows up as a speck. Two characters cost nothing
        and look the same everywhere.
        """
        caret = " ▼" if self._descending else " ▲"
        for column, key in SORT_KEYS.items():
            text = self._headers[column] + (caret if key == self._sort else "")
            item = QTableWidgetItem(text)
            if column == NAME_COL:
                # The first column is a name, so its heading reads from
                # the left with it; the number columns keep Qt's centring.
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft
                                      | Qt.AlignmentFlag.AlignVCenter)
            self.setHorizontalHeaderItem(column, item)

    def _draw(self, rows) -> None:
        self.setRowCount(len(rows))
        biggest = max((row.n for row in rows), default=1) or 1
        for index, row in enumerate(rows):
            muted = not row.eligible or row.key in self._no_finding
            name = QTableWidgetItem(row.key)
            name.setToolTip(row.key)
            count = QTableWidgetItem(str(row.n))
            count.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                   | Qt.AlignmentFlag.AlignVCenter)
            value = QTableWidgetItem(self._figure(row))
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
                        (row.delta, self._scale, not muted,
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

    def __init__(self, say=None, parent=None, settings=None):
        super().__init__(parent)
        self.say = say or (lambda text, millis=4000: None)
        self.report = None
        self.worker = None
        self._account = None
        # THE WINDOW'S OWN DICT when there is one, so the two do not write
        # over each other. `ui_settings.save` writes every key DEFAULTS
        # names from whatever dict it is handed — so a tab loading its own
        # copy at startup and saving it later would put the window's
        # startup values back over anything changed since.
        self.settings = (settings if settings is not None
                         else ui_settings.load())
        self.views = self.settings.setdefault("history_tables", {})
        # Every live table, by block id — see `_table`. Rebuilt with the
        # results, since the widgets in it are destroyed with them.
        self._tables: dict = {}

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

        self._apply_options(Options.from_dict(
            self.settings.get("history_options") or {}))
        self._load_accounts()
        # ONLY IF NOTHING CAME BACK OFF DISK. `_load_accounts` selects the
        # most recent account, which loads its cached run — and the
        # placeholder would then paint over the very thing the cache
        # exists to put there.
        if self.report is None:
            self._show_placeholder()
        self._name_the_button()

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
            "Accounts this machine has looked at before, each with the "
            "display name its run resolved. Kept locally and never "
            "committed, so a copy of this app carries none of them.")
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
    def _note(label: QLabel, text: str, warn: bool = False) -> None:
        """Say it, or take up no room at all.

        An empty label is still a widget in a layout, and two of them under
        this card's one row is a card with a blank strip under it for no
        reason — the same rule the team panels' note follows.

        `warn` turns it amber, for the notes that are asking to be acted
        on: a private match history is a Dota setting the user can change
        in ten seconds, and in the dim grey of an ordinary progress line
        it read as the app having failed at something.
        """
        label.setText(text)
        label.setVisible(bool(text))
        if label.property("warn") != warn:
            label.setProperty("warn", warn)
            # A property a stylesheet selects on is only re-read when the
            # widget is re-polished; setting it alone changes nothing.
            label.style().unpolish(label)
            label.style().polish(label)

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
        # TICKED, like Exclude Turbo beside it and for the same reason: the
        # question this tab asks is what goes with winning RANKED games,
        # and unranked answers a different one. `Options.ranked_only`
        # defaults to True to match, so a remembered run and a fresh tab
        # cannot disagree about it.
        self.ranked_tick.setChecked(True)
        row.addWidget(self.ranked_tick)
        row.addStretch(1)
        self.export_button = QPushButton("Export workbook…")
        # THE SAME BUTTON AS RUN, at the user's request — accent red once
        # there is a report behind it, and plainly disabled until then.
        # It was an ordinary push button beside an accented one, which
        # read as a different KIND of control rather than as the second
        # thing you do on this tab.
        self.export_button.setProperty("accent", True)
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
        # REMEMBERED AS THEY ARE CHANGED, rather than on Run: the point of
        # keeping them is that the next account opens with what was last
        # set, and a setting that is only written when something is
        # measured is one lost by closing the app without measuring.
        for box in (self.window_box, self.cap_box):
            box.currentIndexChanged.connect(self._remember_options)
        for tick in (self.turbo_tick, self.ranked_tick,
                     *self.analysis_ticks.values()):
            tick.toggled.connect(self._remember_options)
        return frame

    # ---- remembered accounts -------------------------------------------
    def _load_accounts(self, select_first: bool = True) -> None:
        """Refill the dropdown, and on the way in adopt the newest account.

        `select_first` is FALSE after a run has just finished. Refreshing
        the list is bookkeeping; adopting a row means loading that
        account's CACHED run, which would replace the live report that has
        this instant been measured with a copy of itself read back off
        disk.
        """
        self.remembered.blockSignals(True)
        self.remembered.clear()
        self.remembered.addItem("Remembered accounts…", None)
        for row in store.load():
            self.remembered.addItem(store.label(row), row["account_id"])
        self.remembered.blockSignals(False)
        rows = store.load()
        if select_first and rows and not self.account_box.text().strip():
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
        """Adopt an account — but NOT the options it was last run with.

        It used to restore those too, and at the user's request it no
        longer does: "if I look up someone else's account, the sorts and
        filters should be the same as I had on the previous analysis".
        The controls are the reader's, not the account's, so picking a
        different player changes WHO is measured and nothing about HOW.
        The cached run is still that account's own, and it is still drawn
        for whatever is ticked NOW — which is the same rule `cache.load`
        already followed.
        """
        self.account_box.setText(str(row["account_id"]))
        self._show_last_run(row)
        self._load_cached(row["account_id"])

    def _load_cached(self, account_id: int) -> None:
        """Draw the last run for this account straight off disk.

        THE TAB USED TO COST A FETCH EVERY TIME IT WAS OPENED, so seeing
        last week's answer again meant measuring it again over a free API.
        The whole run is kept now and re-fetched only when asked — which
        is what the button beside the box is for, and why it says Update
        rather than Run once there is something cached.
        """
        report = cache.load(account_id, self.options().picked)
        if report is None:
            self._clear_results()
            self.report = None
            self.export_button.setEnabled(False)
            self._show_placeholder()
        else:
            self.report = report
            self.export_button.setEnabled(True)
            self.render(report)
        self._name_the_button()

    def _name_the_button(self) -> None:
        """Run, or Update when there is already a run on screen."""
        fresh = self.report is None
        self.run_button.setText("Run" if fresh else "Update")
        self.run_button.setToolTip(
            "Fetch this account's matches and measure them."
            if fresh else
            "Fetch again. What is shown was measured when the line above "
            "says, and nothing is re-fetched until you press this.")

    def _apply_options(self, options: Options) -> None:
        """Put the controls where these options say, WITHOUT announcing it.

        Every one of them writes the settings file when it changes, and
        setting a control to match what was already saved is not the user
        changing it — unblocked, opening the app rewrote the file on
        every start, and the first thing a fresh install did was save.
        """
        boxes = [self.window_box, self.cap_box, self.turbo_tick,
                 self.ranked_tick, *self.analysis_ticks.values()]
        for box in boxes:
            box.blockSignals(True)
        try:
            self._set_options(options)
        finally:
            for box in boxes:
                box.blockSignals(False)

    def _set_options(self, options: Options) -> None:
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

    def _save_settings(self) -> None:
        """Write the tab's own two keys. Never fatal — a read-only disk
        costs the preference, not the run."""
        try:
            ui_settings.save(self.settings)
        except Exception:               # noqa: BLE001 - a preference
            pass

    def _save_views(self) -> None:
        self.settings["history_tables"] = self.views
        self._save_settings()

    def _remember_options(self) -> None:
        """The window, cap and tick boxes, kept across accounts."""
        options = self.options()
        self.settings["history_options"] = options.as_dict()
        self._save_settings()

    def _show_last_run(self, row: dict) -> None:
        when = row.get("last_run") or ""
        if not when:
            self._note(self.last_run, "Not run on this machine yet.")
            return
        matches, wins = row.get("matches", 0), row.get("wins", 0)
        rate = f", {wins / matches * 100:.1f}% win rate" if matches else ""
        # One spelling of an account, so the line above the box and the
        # entry in the dropdown cannot drift apart.
        self._note(self.last_run,
                   f"Last run {when} for {store.label(row)} — "
                   f"{matches} matches{rate}.")

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
        self._note(self.status, message, warn=True)
        self.say("Match history: " + message.split(".")[0], 6000)
        self._set_running(False)

    def _cleanup(self) -> None:
        self.worker = None
        self._set_running(False)

    def _done(self, report) -> None:
        parsed = self._account
        report.how = parsed.how if parsed else ""
        # The RUN resolved the display name; `parsed.name` is only ever
        # set by a Steam vanity URL, which cannot be turned into an id
        # here at all. So the lookup wins and that is the fallback.
        report.name = report.name or ((parsed.name or "") if parsed else "")
        self.report = report
        self.export_button.setEnabled(True)
        self._note(self.status, "")
        rows = store.remember(
            report.options.account_id, report.name,
            when=report.ran_at.strftime("%Y-%m-%d %H:%M"),
            matches=report.n, wins=report.wins,
            options=report.options.as_dict())
        cache.save(report)
        self._load_accounts(select_first=False)
        self._show_last_run(rows[0])
        self.render(report)
        self._name_the_button()
        self.say(f"Match history: {report.n} matches measured", 6000)

    # ---- drawing the report --------------------------------------------
    def _clear_results(self) -> None:
        # The register holds WIDGETS, and these are about to be deleted.
        # A stale entry here is a C++ object that has been destroyed and
        # a Python wrapper that has not noticed, which raises the moment
        # a sibling is told to move with it.
        self._tables = {}
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
            "Eleven analyses run at once, so some buckets clear that bar by "
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
        # NO "THIS RUN" CARD, at the user's request. It counted the
        # matches, named the window, and tallied what was dropped — all
        # true, all read once, and it stood between the tick boxes and
        # the first thing the run actually says. What it uniquely
        # carried, the datum every split is measured against, is on the
        # blocks themselves: each table's third column is headed
        # "Against 54%".
        self._clear_results()
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
            # NO SIGMA ON SCREEN, at the user's request: "it means nothing
            # to people". A count of standard errors is what DECIDES which
            # findings appear and in what order — that is what it is for —
            # but as a figure beside a sentence it is a number the reader
            # cannot act on, in the column their eye lands on first.
            # An ARROW, not a coloured sentence. Colouring the words was
            # the first try and it made a card of five findings a wall of
            # red text, which reads as five errors rather than as five
            # measurements. The direction is the only part of the sigma
            # worth showing, and it belongs in the narrow column the
            # figure used to sit in.
            mark = QLabel("▲" if finding.sigma > 0 else "▼")
            mark.setMinimumWidth(20)
            mark.setStyleSheet(
                f"color: {theme.GOOD if finding.sigma > 0 else theme.BAD};")
            row.addWidget(mark)
            text = QLabel(finding.text)
            text.setWordWrap(True)
            row.addWidget(text, 1)
            name = QLabel(block.name)
            name.setProperty("dim", True)
            row.addWidget(name)
            lay.addLayout(row)
        return frame

    def _table(self, ident, headers, rows, figure, scale, no_finding,
               value_of) -> "BucketTable":
        """A block's table, wearing whatever view was left on it.

        The view is REMEMBERED PER BLOCK AND ACROSS ACCOUNTS, at the
        user's request: "if I look up someone else's account, the sorts
        and filters should be the same as I had on the previous
        analysis". So it is keyed by the block rather than by the player,
        and it lives in the app's own settings file rather than beside
        the remembered accounts.
        """
        table = BucketTable(headers)
        table.controls = TableControls(headers[VALUE_COL])
        # SIBLINGS MOVE TOGETHER. The item block draws one table per hero
        # and all three share a key, because they are the same question
        # asked three times — so a cut set on one has to reach the others
        # or the block shows three different answers to one control.
        family = self._tables.setdefault(ident, [])
        family.append(table)
        saved = dict(self.views.get(ident) or {})
        table.set_view(top=saved.get("top", SHOW_ALL),
                       by=saved.get("by", "games"),
                       sort=saved.get("sort", "games"),
                       descending=saved.get("desc", True))
        table.controls.set_state(*table.view_state())
        table.show_rows(rows, figure, scale, no_finding, value_of)

        def remember():
            view = table.view()
            self.views[ident] = view
            for other in family:
                if other is not table:
                    other.set_view(**view)
                    other.controls.set_state(*other.view_state())
            self._save_views()

        def from_controls():
            top, by = table.controls.state()
            table.set_view(top=top, by=by)
            remember()

        table.controls.changed.connect(from_controls)
        table.changed.connect(remember)
        return table

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
        value_of = ((lambda row: row.mean) if block.kind == "metric"
                    else (lambda row: row.rate))
        table = self._table(block.id, headers, block.shown, figure, scale,
                            block.no_finding, value_of)
        lay.addWidget(table.controls)
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
            # ONE view for every hero's table in this block, keyed
            # "items": they are the same question asked three times, and
            # setting the cut separately on each would be three controls
            # doing one job.
            table = self._table(
                "items",
                ["Item", "Games", "Win rate",
                 f"Against {group.baseline * 100:.0f}%"
                 if group.baseline is not None else "—"],
                group.shown, lambda row: f"{row.rate * 100:.0f}%", scale,
                (), lambda row: row.rate)
            lay.addWidget(table.controls)
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

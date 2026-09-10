"""The History tab: one account's match history, measured.

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

from PyQt6.QtCore import QPoint, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (QFrame, QGridLayout,
                             QHBoxLayout,
                             QHeaderView, QLabel, QLineEdit, QPushButton,
                             QScrollArea, QSizePolicy, QStyledItemDelegate,
                             QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from . import settings as ui_settings
from . import theme
from .chrome import CountBox, Dropdown, TickBox, card
from .flowlayout import FlowLayout
from .section_bar import LOOK_AHEAD, SectionBar, edge
from .spread_bar import SpreadBar
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
        self.by = Dropdown()
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

    def _muted(self, row) -> bool:
        """Too little behind it to act on: under `MIN_BUCKET` games, or a
        bucket its analysis never draws a finding from."""
        return not row.eligible or row.key in self._no_finding

    def render_rows(self) -> None:
        rows = self.survivors()
        rows.sort(key=lambda r: sort_value(r, self._sort, self._value_of),
                  reverse=self._descending)
        # THE GREY ONES SINK, at the user's request, and in BOTH
        # directions — which is why this is a partition rather than a
        # second sort key. A muted row is one there is not enough behind
        # to act on, and sorting by damage put three heroes with two,
        # three and four games above every hero with a real sample: the
        # figures at the top of the table were the ones least worth
        # reading. Folding "muted" into the key instead would flip with
        # the direction and float them to the top the other way round.
        # Python's sort is stable, so each half keeps the order above.
        self._draw([r for r in rows if not self._muted(r)]
                   + [r for r in rows if self._muted(r)])

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
            muted = self._muted(row)
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

    def showEvent(self, event) -> None:             # noqa: N802 - Qt naming
        """Fit again once the header knows its own height.

        `_fit_height` runs while the rows are being filled in, and a
        header that has not been SHOWN yet reports a stale height — the
        same trap the matrix grids document. A few pixels short is
        exactly enough for the view to scroll INSIDE itself, which with
        both scrollbars off is invisible except as a page that does not
        move when you turn the wheel over a table: "there is the
        slightest little scroll happening".
        """
        super().showEvent(event)
        self._fit_height()

    def wheelEvent(self, event) -> None:            # noqa: N802 - Qt naming
        """The PAGE scrolls, never the table. Always.

        Fitting the height exactly is the other half of this and it is
        the half that can be a pixel out — a stale header, a grid line,
        a row that grows when the stylesheet resolves. This half cannot:
        a table sized to every row it holds has nothing of its own to
        scroll, so the wheel belongs to whatever is underneath it.
        """
        event.ignore()


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

        # THE ANCHOR FOR EACH SECTION THE SIDEBAR CAN REACH, by the same
        # ident the sidebar rows carry. The two control cards live here
        # for the life of the tab; the result cards are replaced with
        # every render, which is why `_clear_results` drops only those.
        self._anchors: dict = {}
        self._shown_account = None
        # A JUMP HOLDS ITS OWN HIGHLIGHT until the reader actually
        # scrolls — see `_jump_to`.
        self._pinned = None
        self._pinned_at = None

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
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
        # KEPT, because `_hold_still` needs it: a table that changes how
        # many rows it draws changes the height of this whole page.
        self.scroll = scroll
        self.page = page

        # THE SIDEBAR IS BUILT FIRST because it OWNS the analysis tick
        # boxes now, and `_build_options_card` wires them up.
        self.sections = SectionBar()
        self.sections.jumped.connect(self._jump_to)
        self._build_sections()
        # CONNECTED AFTER THE ROWS ARE BUILT. `_build_sections` sets each
        # box to its default, and setting a control to what it was always
        # going to be is not the user picking it — wired first, every box
        # fired `_picked` during construction, before the card holding
        # the rest of the options existed to be asked. Same rule
        # `_apply_options` follows when it restores from the settings.
        self.sections.picked.connect(self._picked)
        outer.addWidget(self.sections)
        outer.addWidget(edge())
        outer.addWidget(scroll, 1)
        scroll.verticalScrollBar().valueChanged.connect(self._spy)

        account_card = self._build_account_card()
        options_card = self._build_options_card()
        self._anchors["account"] = account_card
        self._anchors["sample"] = options_card
        lay.addWidget(account_card)
        lay.addWidget(options_card)
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

    # ---- the sidebar ---------------------------------------------------
    def _build_sections(self) -> None:
        """Every section of this tab, in the order the page has them.

        ALWAYS ALL OF THEM, ticked or not. Listing only what is switched
        on would move every row under the cursor as you tick down the
        list — the fault `_hold_still` exists to stop one axis over — and
        it would leave the bar empty before a run, which is the one
        moment somebody needs to see what this tab can measure.
        """
        self.sections.add("account", "Account")
        self.sections.add("sample", "Filter")
        self.sections.separator()
        self.sections.add("winning", "Win rate")
        self.sections.add("contrib", "Impact")
        self.sections.separator()
        for key in analyse.BLOCK_ORDER:
            row = self.sections.add(key, analyse.NAMES[key], tick=True)
            row.tick.setChecked(analyse.DEFAULT_ON[key])
            row.tick.setToolTip(analyse.DESCS[key])
        # The tab goes on asking the ticks what is picked, so `options`,
        # `_set_options` and `_apply_options` are unchanged by the move.
        self.analysis_ticks = dict(self.sections.ticks)

    def _sync_sections(self) -> None:
        """Tell the bar which sections are actually on the page."""
        self.sections.set_reachable(self._anchors)
        self._spy()

    def _jump_to(self, ident: str) -> None:
        widget = self._anchors.get(ident)
        if widget is None:
            return
        # Qt DEFERS layout, so a card added moments ago reports its old
        # position — the same trap `_hold_still` documents.
        layout = self.page.layout()
        if layout is not None:
            layout.activate()
        bar = self.scroll.verticalScrollBar()
        # PINNED, because the last few sections all share the bottom of
        # the page: clicking one of those scrolls as far as it can go and
        # then `_spy`'s bottom rule would light the LAST one instead of
        # the one that was clicked. You asked for this section and it is
        # on screen, so it stays lit until you scroll away from it. The
        # pin is set BEFORE the scroll, since `setValue` runs `_spy`
        # synchronously, and the value it actually reached is recorded
        # afterwards because the bar clamps.
        self._pinned, self._pinned_at = ident, None
        bar.setValue(max(0, widget.mapTo(self.page, QPoint(0, 0)).y() - 8))
        self._pinned_at = bar.value()
        self.sections.light(ident)

    def _spy(self) -> None:
        """Light whichever section the page is showing.

        By measured POSITION rather than by list order: the two agree
        today (`BLOCK_ORDER` is what builds both) and a highlight that
        silently lies the day they stop agreeing is worse than one that
        costs a sort.
        """
        if not self._anchors:
            return
        bar = self.scroll.verticalScrollBar()
        if self._pinned is not None:
            if self._pinned_at in (None, bar.value()):
                self.sections.light(self._pinned)
                return
            self._pinned = None         # the reader has moved; let go
        tops = sorted((widget.mapTo(self.page, QPoint(0, 0)).y(), ident)
                      for ident, widget in self._anchors.items())
        if bar.maximum() > 0 and bar.value() >= bar.maximum() - 2:
            # AT THE VERY BOTTOM the last section can be far too short to
            # reach the top of the viewport, so the rule below would
            # never light it however far you scrolled.
            self.sections.light(tops[-1][1])
            return
        line = bar.value() + LOOK_AHEAD
        reached = [ident for top, ident in tops if top <= line]
        self.sections.light(reached[-1] if reached else tops[0][1])

    def _picked(self, _ident: str, _on: bool) -> None:
        """A tick on the sidebar: remember it, and REDRAW.

        Ticking one used to write the setting and change nothing on
        screen — which analyses are drawn follows what is ticked NOW, but
        that was only ever re-read when an account was loaded. That was
        survivable while the boxes sat on a card of their own; with the
        box ON the bookmark it would be unbearable, since the row would
        light up next to a section that never appeared.
        """
        self._remember_options()
        if self.report is None or self._shown_account is None:
            return
        # The page is about to be rebuilt under whatever you were
        # reading, so put the scroll back where it was rather than
        # throwing the reader to the top of a thirteen-block report.
        bar = self.scroll.verticalScrollBar()
        where = bar.value()
        self._load_cached(self._shown_account)
        layout = self.page.layout()
        if layout is not None:
            layout.activate()
        self.page.adjustSize()
        bar.setValue(min(where, bar.maximum()))

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

        self.remembered = Dropdown()
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
        frame, lay = card("Filter")
        # IT WRAPS, for the reason the suggestion strips do: a row of
        # fixed controls that cannot wrap sets a MINIMUM WIDTH, and a
        # widget's minimum is the window's. Laid out across one line this
        # card asked for 925px, which fitted a 940px window with nothing
        # to spare — so the sidebar taking 178 down the left put a
        # HORIZONTAL scrollbar under the whole report and clipped the
        # remembered-accounts dropdown off the right edge. Wrapping drops
        # the card's minimum to its widest single control. Caught by
        # rendering the tab and looking at it; every test passed.
        row = FlowLayout(spacing=10)
        row.addWidget(QLabel("Window"))
        self.window_box = Dropdown()
        for key, label, _days in WINDOWS:
            self.window_box.addItem(label, key)
        self.window_box.setCurrentIndex(3)          # last 12 months
        row.addWidget(self.window_box)
        row.addWidget(QLabel("At most"))
        self.cap_box = Dropdown()
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

        # THE ELEVEN ANALYSIS TICK BOXES USED TO BE A GRID HERE, and at
        # the user's request they are on the SIDEBAR now, one per
        # bookmark: "if you can have the tick boxes on the actual
        # bookmarks as well that would be nice... don't show tick boxes
        # on the main menu in that case, duplication will be confusing".
        # Naming the same eleven analyses twice is two places to read one
        # thing, and the row that jumps to a section is the right place
        # to switch it on. What is left on this card is the SAMPLE —
        # which matches are measured — which is why it is no longer
        # called "What to measure".
        # REMEMBERED AS THEY ARE CHANGED, rather than on Run: the point of
        # keeping them is that the next account opens with what was last
        # set, and a setting that is only written when something is
        # measured is one lost by closing the app without measuring.
        for box in (self.window_box, self.cap_box):
            box.currentIndexChanged.connect(self._remember_options)
        # The analysis ticks are NOT in this list: they go through
        # `_picked`, which has to redraw the page as well as remember.
        for tick in (self.turbo_tick, self.ranked_tick):
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
        # WHOSE REPORT IS ON SCREEN, so a tick can redraw it — see
        # `_picked`. Set even when nothing came back, or turning a
        # section on after an empty load would redraw somebody else.
        self._shown_account = account_id
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

    def _hold_still(self, anchor, change) -> None:
        """Make a change, keeping `anchor` exactly where it is on screen.

        Stepping "Top 10" to "Top 9" removes a row, which shortens the
        table, which shortens this whole page — and the scroll area then
        re-clamps, so everything jumped and the arrow moved out from
        under the cursor between one click and the next. "I can't spam
        the arrow, it shifts and I have to track it."
        The fix is not to stop the page changing height — it genuinely
        has fewer rows in it — but to pin the control the user is holding
        the cursor over. Its offset from the top of the viewport is
        measured, the change is made, the layout is FORCED to run (Qt
        defers it, so measuring straight afterwards reads the old
        geometry), and the scrollbar is moved by whatever it takes to put
        that offset back.
        """
        bar = self.scroll.verticalScrollBar()
        before = anchor.mapTo(self.page, QPoint(0, 0)).y() - bar.value()
        change()
        layout = self.page.layout()
        if layout is not None:
            layout.activate()
        self.page.adjustSize()
        bar.setValue(anchor.mapTo(self.page, QPoint(0, 0)).y() - before)

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
        self._shown_account = report.options.account_id
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
        # The two control cards outlive a render; every result card does
        # not, and an anchor pointing at a destroyed widget is the same
        # stale-C++-object trap as the table register above.
        for ident in [i for i in self._anchors
                      if i not in ("account", "sample")]:
            del self._anchors[ident]
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
        self._sync_sections()

    def render(self, report) -> None:
        # NO "THIS RUN" CARD, at the user's request. It counted the
        # matches, named the window, and tallied what was dropped — all
        # true, all read once, and it stood between the tick boxes and
        # the first thing the run actually says. What it uniquely
        # carried, the datum every split is measured against, is on the
        # blocks themselves: each table's third column is headed
        # "Against 54%".
        self._clear_results()
        rates, contributions = report.summary_rows()
        # THE TWO FAMILIES ARE HEADLINED APART. Contribution metrics
        # separate far harder than win-rate splits because they are partly
        # structural — a mid laner out-damages a hard support by
        # construction — so one merged ranking by sigma would be nothing
        # but damage rows with every behavioural finding buried under it.
        names: list = []
        winning = self._findings_card(
            "Win rate", rates,
            "Nothing to compare yet — every split needs at least two "
            "buckets with enough games behind them.",
            names=names)
        self.results.addWidget(winning)
        self._anchors["winning"] = winning
        if contributions:
            contrib = self._findings_card(
                "Impact", contributions, "", names=names)
            self.results.addWidget(contrib)
            self._anchors["contrib"] = contrib
        # After BOTH cards exist, so the two agree with each other.
        self._align_names(names)
        for block in report.blocks:
            block_card = self._block_card(block, report)
            self.results.addWidget(block_card)
            self._anchors[block.id] = block_card
        self._sync_sections()

    @staticmethod
    def _align_names(labels: list) -> None:
        """One width for the block-name column, across BOTH summary cards.

        At the user's request: "where the result starts — just after the
        section ends — is all aligned for each metric". A grid already
        aligns its own rows; what it cannot do is agree with the OTHER
        card's grid, and the two sit one above the other, so left alone
        they reproduce exactly the raggedness being complained about one
        level up.

        MEASURED OFF THE LABELS THEMSELVES, once they exist. Two earlier
        attempts measured something else and both were wrong: a bare
        `QFontMetrics(self.font())` answered 200px where the label wanted
        245, because the app's font comes from the stylesheet, and it
        sliced the longest block name off mid-word at the rule; and a
        throwaway QLabel created to measure with was still a CHILD of the
        tab after `deleteLater`, drawing at (0, 0) over the top of the
        sidebar until the event loop got round to it. The labels being
        laid out are the only thing that knows its own width for certain.
        """
        if not labels:
            return
        widest = max(label.sizeHint().width() for label in labels)
        for label in labels:
            label.setFixedWidth(widest)

    def _findings_card(self, title: str, rows: list, empty: str,
                       names: list | None = None) -> QFrame:
        """One line per SECTION: its name, its two extremes, its spread.

        At the user's request the summary stopped being a ranked list of
        whatever cleared the significance floor — "I don't need so many
        results for day of the week, or time of day; just put the most
        significant, and make sure there is 1 key result from each
        section" — and then stopped consulting significance at all:
        "include the best and worst mentality for all headers seen in
        the left sidebar, even if they seem insignificant". So the card
        is a fixed list in section order, every section once.

        A GRID rather than a row of layouts, so the names, the figures
        and the bars each line up down the card. Bars that start at a
        different x on every row cannot be compared at a glance, which
        is the only thing they are for.

        AND THE NAME COLUMN IS ONE WIDTH ACROSS BOTH CARDS
        (`_align_names`), also at the user's request: "where the result
        starts — just after the section ends — is all aligned for each
        metric". A grid already aligns its own rows; what it cannot do
        is agree with the OTHER card's grid, and the two sit one above
        the other, so left to themselves they would reproduce exactly
        the raggedness being complained about one level up.
        """
        frame, lay = card(title)
        if not rows:
            note = QLabel(empty)
            note.setWordWrap(True)
            note.setProperty("dim", True)
            lay.addWidget(note)
            return frame

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)
        said = ""       # the last grey figure printed, so it is not repeated
        for line, (block, spread, best, worst) in enumerate(rows):
            name = QLabel(block.name)
            name.setProperty("dim", True)
            # NOT WRAPPED: a wrapped label negotiates its width with the
            # layout, and a column whose width is negotiated is a column
            # that lands somewhere different on each card. `_align_names`
            # gives every one of these the same fixed width afterwards.
            if names is not None:
                names.append(name)
            grid.addWidget(name, line, 0,
                           Qt.AlignmentFlag.AlignVCenter
                           | Qt.AlignmentFlag.AlignLeft)

            # NO MIDDLE COLUMN OF FIGURES. It printed "Rubick 61% ·
            # Mirana 25%" beside a bar carrying the same two facts, and
            # once the names moved onto their own dots — at the user's
            # request, sketched by hand — that column was saying
            # everything twice on one line. The bar takes the width it
            # gave up, which is what lets two close figures separate on
            # a fixed 0-100 scale.
            bar = SpreadBar()
            bar.set_spread(
                spread,
                analyse.format_figure(block, spread.low),
                analyse.format_figure(block, spread.high),
                analyse.format_figure(block, spread.datum),
                best_text=f"{analyse.format_figure(block, spread.best)} "
                          f"{best.key}",
                worst_text=f"{analyse.format_figure(block, spread.worst)} "
                           f"{worst.key}",
                note=f"{best.key} {best.n} games, {worst.key} {worst.n} games")
            # THE GREY DOT IS NAMED WHEN IT IS NOT A REPEAT. Every
            # win-rate section is measured against the same datum — your
            # own overall rate — on the same 0 to 100 scale, so its dot
            # lands at the same x on all eight rows and the column reads
            # as one line: "most of them will just be my average win rate
            # of 49% or whatever", and printing it against each row is
            # the same number eight times. Each CONTRIBUTION section has
            # a datum of its own, though, so those are all named — which
            # is why this asks what was last said rather than counting
            # rows.
            datum_says = analyse.format_figure(block, spread.datum)
            bar.name_the_datum(datum_says != said)
            said = datum_says
            grid.addWidget(bar, line, 2)
        # A RULE DOWN THE WHOLE CARD, at the user's request — "maybe even
        # have a vertical line that runs down in between section and
        # result so it's nice and tidy". One widget spanning every row
        # rather than one per line: a stack of short rules with the row
        # spacing showing between them is a dashed line, not a rule.
        rule = edge()
        rule.setSizePolicy(QSizePolicy.Policy.Fixed,
                           QSizePolicy.Policy.Expanding)
        grid.addWidget(rule, 0, 1, len(rows), 1)
        # The bar takes every pixel the name column does not.
        grid.setColumnStretch(2, 1)
        lay.addLayout(grid)
        return frame

    def _table(self, ident, headers, rows, figure, scale, no_finding,
               value_of, controls=None) -> "BucketTable":
        """A block's table, wearing whatever view was left on it.

        The view is REMEMBERED PER BLOCK AND ACROSS ACCOUNTS, at the
        user's request: "if I look up someone else's account, the sorts
        and filters should be the same as I had on the previous
        analysis". So it is keyed by the block rather than by the player,
        and it lives in the app's own settings file rather than beside
        the remembered accounts.
        """
        table = BucketTable(headers)
        # SHARED where one is handed in: the item block draws a table per
        # hero and they are the same question asked several times, so one
        # control governs all of them rather than each carrying its own.
        table.controls = controls or TableControls(headers[VALUE_COL])
        table.owns_controls = controls is None
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
            # ANCHORED ON THE CONTROL ITSELF, so the arrow stays under
            # the cursor while it is being stepped.
            self._hold_still(table.controls,
                             lambda: table.set_view(top=top, by=by))
            remember()

        table.controls.changed.connect(from_controls)
        # A heading click only RE-ORDERS what is already there, so the
        # page keeps its height and there is nothing to hold still.
        table.changed.connect(remember)
        return table

    def _block_card(self, block, report) -> QFrame:
        # THE HEADING, ONE LINE SAYING WHAT THE METRIC IS, AND THE TABLE.
        # The card once carried THREE paragraphs — what the split
        # measures, how many single-game buckets were left out, and a
        # caveat about reading the figures — and between them they pushed
        # the table most of a screen down, so all three were cut. The
        # user has since changed their mind about the first: "make it a
        # slightly smaller text and italics, and make sure it's not super
        # fluffy — still concise, but describes what the metric is."
        # So `desc` is back, one line, and it was REWRITTEN to earn the
        # space: every one of them now says what is being measured and
        # stops, where they used to add how the floors work and how to
        # read the result. It is the same string the tick box shows as
        # its tooltip, because two spellings of what a section measures
        # is one of them going stale.
        # ONLY ON THESE CARDS. The two summary cards above get none —
        # "I don't want blurbs below What goes with winning and What you
        # do on each hero" — since those name a question rather than a
        # measurement.
        frame, lay = card(block.name)
        if block.desc:
            blurb = QLabel(block.desc)
            blurb.setWordWrap(True)
            blurb.setProperty("dim", True)
            blurb.setStyleSheet(
                f"font-size: {round(theme.BODY_PX * 0.82)}px; "
                f"font-style: italic; background: transparent;")
            lay.addWidget(blurb)
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

        # `block.hidden` and `block.caveat` are NOT drawn — see above.
        # Both are still computed and both still go into the workbook,
        # which is where a caveat can be read once at leisure rather than
        # sat over the table every time it is looked at.
        return frame

    def _item_block(self, block, lay) -> None:
        """ONE HERO AT A TIME, chosen from a dropdown.

        At the user's request, and it replaces a fixed "your three most
        played" — then briefly a count of how many to stack down the
        card. Stacking is the wrong shape for this block: each hero's
        items are read against THAT HERO'S own win rate, so two tables
        side by side share nothing but a column heading, and the answer
        anybody wants is about the one hero they are thinking of picking.
        The list is ordered MOST PLAYED FIRST, so the heroes worth
        reading are the ones already at the top of it, and every hero
        with item data is in it rather than an arbitrary few.
        """
        chooser = Dropdown()
        chooser.setMinimumWidth(220)
        chooser.setToolTip("Which hero's items to show. Most played "
                           "first — the ones with a sample worth reading.")
        for group in block.groups:
            chooser.addItem(f"{group.hero}  ({group.games} games)",
                            group.hero)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("Hero"))
        row.addWidget(chooser)
        row.addStretch(1)
        lay.addLayout(row)

        if not block.groups:
            empty = QLabel("No matches came back with item data.")
            empty.setProperty("dim", True)
            lay.addWidget(empty)
            return

        # REMEMBERED BY NAME, not by position: the list is this account's
        # own heroes in its own order, so an index means a different hero
        # the moment you look somebody else up.
        wanted = (self.views.get("item_hero") or {}).get("hero")
        index = chooser.findData(wanted)
        chooser.setCurrentIndex(index if index >= 0 else 0)

        items = TableControls("Win rate")
        lay.addWidget(items)
        body = QWidget()
        inner = QVBoxLayout(body)
        inner.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(body)

        def fill():
            # THE REGISTER FIRST. It holds WIDGETS, and the ones below are
            # about to be deleted — a stale entry is a destroyed C++
            # object behind a live Python wrapper, which raises the moment
            # a sibling is told to move with it. Replacing the list rather
            # than clearing it leaves the closures that captured the old
            # one pointing at tables that are gone, which is harmless.
            self._tables["items"] = []
            while inner.count():
                held = inner.takeAt(0)
                widget = held.widget()
                if widget is not None:
                    widget.setParent(None)
                    widget.deleteLater()
            group = block.groups[max(0, chooser.currentIndex())]
            if not group.shown:
                note = QLabel("No item data on any of these games.")
                note.setProperty("dim", True)
                inner.addWidget(note)
                return
            scale = max(BAR_MIN_SCALE,
                        max((abs(r.delta) for r in group.shown
                             if r.eligible), default=0.0))
            table = self._table(
                "items",
                ["Item", "Games", "Win rate",
                 f"Against {group.baseline * 100:.0f}%"
                 if group.baseline is not None else "—"],
                group.shown, lambda r: f"{r.rate * 100:.0f}%", scale,
                (), lambda r: r.rate, controls=items)
            inner.addWidget(table)

        def chosen():
            self.views["item_hero"] = {"hero": chooser.currentData()}
            self._save_views()
            self._hold_still(chooser, fill)

        chooser.currentIndexChanged.connect(chosen)
        fill()

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

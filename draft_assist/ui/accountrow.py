"""Whose history the analysis is for, across the top of the Draft tab.

IT IS THE FIRST THING AT THE TOP OF THE CONTENT, at the user's request.
It took the strip a placeholder ad slot used to hold, and outlived it: the
reasoning is that slot's own, inverted. Reserving height for something
nobody had turned on was dead window; this row always has an answer in it,
so it earns the height the placeholder never did.

ALWAYS SHOWN, also at the user's request, including before any account has
been measured - it reads as a prompt then, and clicking it opens the
History tab. The alternative (appear on the first run) keeps a fresh
install tidier and shifts the whole draft down the moment a run lands,
which is the fault this app fixes everywhere else.

IT MAKES NO NETWORK CALL, ever. The picture was fetched during a run and
is read off disk; `history.avatars.stored` is a file check. This widget is
repainted with the draft, four times a second, so anything else here would
be the live loop making requests.

THE DATE RANGE IS THE RUN'S OWN WINDOW, not a fixed three months: the
History tab's window is a dropdown, so printing anything else would have
the row describing data that was never measured.
"""

from datetime import timedelta

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)

from . import chrome, theme

# MONTH AND YEAR, NOT THE DAY, at the user's request: "you don't need to
# say the day, just the month and year". The row is read at a glance and
# the window it describes is a DROPDOWN of months — "3 months", "12
# months" — so the day was three characters of precision the measurement
# never claimed and nobody acts on. Spelled once, because the start and
# the end must not be written two different ways.
MONTH = "%b %Y"
FACE = 34                 # the avatar's edge, in pixels
PADDING = 6
NOTHING_YET = "No account measured yet"
# The same fact in the width a TITLE BAR has for it. The long form is a
# sentence in a callout; this sits between the menus and the pin.
NO_PROFILE = "No account"
PROMPT = "Open the History tab to analyse one"
# WHAT AN EMPTY FIGURE PRINTS. An em dash rather than "0%" or "0": those
# are measurements, and nothing has been measured yet.
NOTHING = "\u2014"


def avatar_path(account_id: int):
    """The picture on disk for this account, or None.

    Here rather than imported at the top of the module: `history.avatars`
    reaches `history.cache`, and this module is imported while the window
    is being built. A file check, no network, safe in the live loop —
    which is the whole reason the avatar is fetched during a RUN.
    """
    if not account_id:
        return None
    from ..history import avatars
    return avatars.stored(int(account_id))


class Face(QWidget):
    """The avatar, or the account's initial when there is no picture.

    PAINTED rather than handed to a QLabel, for the reason every other
    mark in this app is: a rounded picture and a drawn fallback have to
    come out the same size and shape, and a stylesheet cannot put an
    initial inside a circle without an image file.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(FACE, FACE)
        self._pixmap: QPixmap | None = None
        self._initial = ""

    def show_file(self, path) -> bool:
        """True when a picture was actually loaded. A file that will not
        decode is the same as no file - it draws the initial."""
        pixmap = QPixmap(str(path)) if path else QPixmap()
        self._pixmap = None if pixmap.isNull() else pixmap
        self.update()
        return self._pixmap is not None

    def show_initial(self, name: str) -> None:
        self._initial = (name or "?").strip()[:1].upper() or "?"
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        box = self.rect().adjusted(0, 0, -1, -1)
        path = QPainterPath()
        path.addEllipse(float(box.x()), float(box.y()),
                        float(box.width()), float(box.height()))
        if self._pixmap is not None:
            painter.setClipPath(path)
            # FILLED, not fitted: a Steam avatar is square already, so
            # covering the circle cannot distort it, and a fitted one
            # would leave the corners of the clip empty.
            scaled = self._pixmap.scaled(
                box.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap(
                box.x() - (scaled.width() - box.width()) // 2,
                box.y() - (scaled.height() - box.height()) // 2, scaled)
            painter.setClipping(False)
        else:
            painter.fillPath(path, QColor(theme.BG_INPUT))
            painter.setPen(QColor(theme.TEXT_DIM))
            font = QFont(painter.font())
            font.setPixelSize(int(FACE * 0.5))
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter,
                             self._initial or "?")
        painter.end()


class AccountRow(QWidget):
    """Picture, name, and the window the numbers came from."""

    clicked = pyqtSignal()

    def __init__(self, parent=None, prompt: str = PROMPT, *,
                 clickable: bool = True):
        """`prompt` differs by WHERE the row is. The Draft tab's says to
        open the History tab; on the History tab itself that is an
        instruction to stay where you already are."""
        super().__init__(parent)
        self._prompt = prompt
        self._clickable = clickable
        self.setObjectName("accountRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, PADDING, 12, PADDING)
        row.setSpacing(10)

        self.face = Face(self)
        row.addWidget(self.face, 0, Qt.AlignmentFlag.AlignVCenter)

        # ONE LINE, at the user's request: "picture - steam name | from
        # date --> to date (XXX months)". Stacked, the two texts were a
        # block as tall as the face for two short strings, and the row had
        # to be tall enough for both; on one line it is the height of the
        # picture and nothing else.
        self.who = QLabel(NOTHING_YET, self)
        self.who.setProperty("strong", True)
        # PAINTED, not a typed "|". A pipe in a label is a glyph that
        # resizes with the font and cannot be coloured apart from the text
        # holding it - the same reason the menus, tabs and toolbar all
        # draw their rules instead of spelling them.
        self.rule = chrome.Divider(self)
        self.when = QLabel(prompt, self)
        self.when.setProperty("dim", True)
        row.addWidget(self.who, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.rule, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.when, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)

        self.face.show_initial("")

    def on_band(self) -> None:
        """Make this row read as part of the tab strip it now sits on.

        A QLabel is transparent by the app's own stylesheet rule, but
        THIS widget is a plain QWidget holding a layout — which takes the
        base `QWidget` rule, the CONTENT colour, lighter than the band.
        It drew as a pale block across the right-hand end of the tab row,
        which is the same fault the strip's own note in `chrome` warns
        about: "every child of the strip is given the band's colour
        explicitly".

        `bare` is the app's word for "this holds a layout rather than
        being a surface", and it is what the stylesheet keys on.
        """
        self.setProperty("bare", True)
        for child in self.findChildren(QWidget):
            child.setProperty("bare", True)
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event):
        if self._clickable and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def show_report(self, report) -> None:
        """Draw whichever run the History tab is showing, or the prompt.

        Takes the REPORT rather than an account id, because everything on
        the row - the name, the window, when it was measured - is already
        on it, and reading them from anywhere else would be two sources
        for one answer.
        """
        if report is None:
            self.who.setText(NOTHING_YET)
            self.when.setText(self._prompt)
            self.face.show_initial("")
            self.setToolTip("")
            return

        account = getattr(getattr(report, "options", None), "account_id", 0)
        name = (getattr(report, "name", "") or "").strip()
        self.who.setText(name or (str(account) if account else NOTHING_YET))
        self.when.setText(self.span(report))

        shown = bool(account) and self.face.show_file(avatar_path(account))
        if not shown:
            self.face.show_initial(name or str(account))
        # "Click to open the History tab" is only true on the DRAFT tab.
        # On the History tab you are already there and the row does not
        # take a click, so promising one is an instruction that does
        # nothing when followed.
        tail = " Click to open the History tab." if self._clickable else ""
        self.setToolTip(
            f"{name or account} - {len(getattr(report, 'matches', []))} "
            f"matches.{tail}")

    def show_account(self, row: dict) -> None:
        """Draw a REMEMBERED account, which is not the same as a run.

        The History tab knows who was last measured before it knows what
        was measured — the accounts come off `history_accounts.json` and
        the run itself off the cache — so the row has to be able to say
        the first without the second. A `show_report` follows a moment
        later when there IS a cached run, and overwrites this.
        """
        if not isinstance(row, dict) or not row.get("account_id"):
            self.show_report(None)
            return
        from ..history import store

        account = int(row["account_id"])
        name = (row.get("name") or "").strip()
        self.who.setText(name or str(account))
        when = (row.get("last_run") or "").strip()
        self.when.setText(f"Last run {when}" if when
                          else "Not run on this machine yet")
        if not self.face.show_file(avatar_path(account)):
            self.face.show_initial(name or str(account))
        matches, wins = row.get("matches", 0), row.get("wins", 0)
        rate = f", {wins / matches * 100:.1f}% win rate" if matches else ""
        # THE COUNT AND THE RATE MOVE HERE rather than being dropped. The
        # line they used to be printed on is gone, and losing a figure
        # while replacing the thing that carried it is how a "tidy up"
        # becomes a regression.
        self.setToolTip(f"{store.label(row)} - {matches} matches{rate}."
                        if matches else store.label(row))

    @staticmethod
    def span(report) -> str:
        """"<from> - <to>", the window this run actually used.

        The END is when the run happened, which is the "date of ping" the
        user asked for; the START is that less the window's own days. A
        window of "All history" has no start to print and says so rather
        than inventing one.
        """
        ran = getattr(report, "ran_at", None)
        options = getattr(report, "options", None)
        days = getattr(options, "days", None)
        if ran is None:
            return getattr(options, "window_label", "") or ""
        end = ran.strftime(MONTH)
        if not days:
            return f"All history \u2192 {end}"
        began = ran - timedelta(days=int(days))
        # THE YEAR IS PRINTED ONCE WHEN IT IS THE SAME YEAR, at the
        # user's request: "if its 2 months on the same year make it jan
        # --> apr 2026". "Mar 2026 - Sep 2026" spends eight characters
        # saying 2026 twice, on a row that now sits on the tab strip
        # where every character is competing with the tabs.
        start = (began.strftime("%b") if began.year == ran.year
                 else began.strftime(MONTH))
        # AND THE LENGTH IN BRACKETS IS GONE with it. It was there
        # because two dates make the reader do the subtraction — true,
        # and it was the longest part of the line. Mar and Sep of one
        # year IS six months, stated by the two dates; the tooltip still
        # carries the window's own label for the cases that are not
        # obvious.
        return f"{start} \u2192 {end}"


class ProfileButton(QWidget):
    """Picture and name in the title bar, left of the pin.

    THE SHAPE IS STEAM'S, and only the shape — at the user's request:
    "purrely the ideao of having profile just left of the pin icon ...
    and when its clicked the callout drops down ... do nto copy a bunch
    of crap fro msteam i was just usign that as an example".

    So this is a face, a name and a caret, and everything else about the
    account — the friend ID, the window the numbers came from, what to
    do when nothing has been measured — is in the callout it drops. That
    detail is `AccountRow`, unchanged and re-used, because two spellings
    of "who is this and when was it measured" is one of them going
    stale.

    A WIDGET RATHER THAN A QPushButton with an icon: the face is drawn
    (see `Face`), and a stylesheet cannot put a drawn picture and two
    pieces of text on a button without a pixmap per state.
    """

    clicked = pyqtSignal()

    FACE = 20                       # fits the title bar without raising it

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("profileButton")
        self.setProperty("bare", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 0, 6, 0)
        row.setSpacing(6)
        self.face = Face(self)
        self.face.setFixedSize(self.FACE, self.FACE)
        row.addWidget(self.face, 0, Qt.AlignmentFlag.AlignVCenter)
        self.who = QLabel(NO_PROFILE, self)
        self.who.setProperty("strong", True)
        row.addWidget(self.who, 0, Qt.AlignmentFlag.AlignVCenter)
        # The caret says it opens something. A typed glyph rather than a
        # painted one: it is punctuation beside text at the same size,
        # which is the one case this app's "draw it" rule is not about.
        self.caret = QLabel("\u25be", self)
        self.caret.setProperty("dim", True)
        row.addWidget(self.caret, 0, Qt.AlignmentFlag.AlignVCenter)
        self.face.show_initial("")
        self.setToolTip("Your account — click for the details")

    def show_run(self, name: str, account: int = 0,
                 window: str = "") -> None:
        """The name, the window in brackets, and the account's picture.

        **THE PICTURE WAS NEVER DRAWN, and that was a whole missing
        call** — "why is the thumbnail not working??". This method was
        `show_name` and set the LABEL and nothing else, so `self.face`
        kept the "?" it was given in `__init__` for the life of the app,
        on every account, however many runs had been measured. The
        picture was on disk the whole time: `AccountRow` two classes up
        has always drawn it from the same file. One widget asked and the
        other did not.

        THE WINDOW GOES IN BRACKETS AFTER THE NAME, at the user's
        request: "Instead of showign the date where it is atm next to
        bijson, i want it to be in brackets after bijson in the main menu
        look, so Bijson (6 months)". The dates it replaces — "Mar → Sep
        2026" — are two figures a reader has to subtract to get the one
        thing that line was for, which is how far back the numbers reach.
        """
        self.who.setText(
            f"{name} ({window})" if name and window else (name or NO_PROFILE))
        if not (name and self.face.show_file(avatar_path(account))):
            self.face.show_initial(name)

    def mouseReleaseEvent(self, event):          # noqa: N802 - Qt naming
        if (event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ProfileCard(QWidget):
    """What drops out of the profile button in the title bar.

    THE SHAPE IS THE USER'S, stated twice and drawn once: "when you click
    you see profiele pic  Bijson and below that you see a 6 motnhs box
    that you can click to see a dropdown and select different durations
    and an apply button next to that to change the history look back
    range", then "when the user clicks the down arrow on the profile i
    want to see win rate %, in brackets after that i want the delta from
    the previous XXX duration... and below those two i want games played
    (with a delta also, qty)". So:

        [face]  Bijson
                Win rate   53% (+2.1%)
                Games      412 (+37)
                [ Last 6 months v ] [ Apply ]

    IT REPLACES `AccountRow` HERE and does not replace it everywhere:
    the History tab still uses that row, where the question is "when was
    this account last measured" rather than "how is it going". The two
    read the same report and neither computes anything of its own.

    NOTHING ON IT MAKES A REQUEST. The face is read off disk, the figures
    are on the report, and Apply hands a window key back to the window to
    run — which is the one path in this app allowed on the network.
    """

    applied = pyqtSignal(str)          # a key from `report.WINDOWS`

    def __init__(self, parent=None):
        from ..history.report import WINDOWS
        # THE ONE HALO IN THE APP, borrowed rather than re-implemented.
        # Every signed number here is stroked — the badge on a pick, the
        # figure in a grid cell, the total beside a team's name — and a
        # second implementation is how two of them come to disagree.
        from .teams import HaloLabel

        super().__init__(parent)
        self.setObjectName("profileCard")
        self.setProperty("bare", True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.face = Face(self)
        top.addWidget(self.face, 0, Qt.AlignmentFlag.AlignVCenter)
        self.who = QLabel(NOTHING_YET, self)
        self.who.setProperty("heading", True)
        top.addWidget(self.who, 0, Qt.AlignmentFlag.AlignVCenter)
        top.addStretch(1)
        lay.addLayout(top)

        # A GRID, so the two figures and the two deltas each line up in
        # their own column — three labels per row laid out by hand would
        # put the delta wherever the figure before it happened to end.
        figures = QGridLayout()
        figures.setContentsMargins(0, 0, 0, 0)
        figures.setHorizontalSpacing(10)
        figures.setVerticalSpacing(4)
        self.values: dict[str, QLabel] = {}
        self.deltas: dict[str, HaloLabel] = {}
        for row, (key, label) in enumerate((("rate", "Win rate"),
                                            ("games", "Games"))):
            name = QLabel(label, self)
            name.setProperty("dim", True)
            figures.addWidget(name, row, 0)
            value = QLabel(NOTHING, self)
            value.setProperty("strong", True)
            figures.addWidget(value, row, 1)
            delta = HaloLabel(self)
            figures.addWidget(delta, row, 2)
            self.values[key] = value
            self.deltas[key] = delta
        figures.setColumnStretch(3, 1)
        lay.addLayout(figures)

        pick = QHBoxLayout()
        pick.setSpacing(8)
        self.window_box = chrome.Dropdown(self)
        self.window_box.setToolTip(
            "How far back to measure. Nothing changes until Update is "
            "pressed — the figures beside it are the run already on disk.")
        for key, label, _days in WINDOWS:
            self.window_box.addItem(label, key)
        pick.addWidget(self.window_box)
        # "UPDATE", NOT "APPLY", at the user's request: "i actually
        # think you should call it 'update' so that it can be hit even if
        # the user has not changed the dropdown, as sometimes you may
        # want to keep amoutn of time the same and just update it".
        # Apply names a change to the box beside it, which makes a press
        # with nothing changed look like a no-op; Update names what the
        # press actually does, which is re-measure from today backwards.
        # It is the same word the History tab's own button takes once
        # there is a run behind it.
        self.apply_button = QPushButton("Update", self)
        self.apply_button.setToolTip(
            "Measure this account again over the window chosen, from "
            "today backwards.")
        self.apply_button.setProperty("accent", True)
        self.apply_button.clicked.connect(self._apply)
        pick.addWidget(self.apply_button)
        pick.addStretch(1)
        lay.addLayout(pick)

        self.face.show_initial("")

    def _apply(self) -> None:
        key = self.window_box.currentData()
        if key:
            self.applied.emit(str(key))

    def window_key(self) -> str:
        return str(self.window_box.currentData() or "")

    def set_window(self, key: str) -> None:
        """Follow the run on screen, without announcing it as a choice.

        Nothing is connected to the box's own signal — Apply is the only
        way out of this card — so there is no signal to block here. It is
        worth saying: the moment anything IS connected, this becomes the
        `_apply_options` trap, where restoring a control to what was
        already saved rewrites the file on every start.
        """
        index = self.window_box.findData(key)
        if index >= 0:
            self.window_box.setCurrentIndex(index)

    def show_report(self, report) -> None:
        """Draw whichever run the History tab is showing, or the prompt."""
        if report is None:
            self.who.setText(NOTHING_YET)
            self.face.show_initial("")
            for key in self.values:
                self.values[key].setText(NOTHING)
                self.deltas[key].set_value("", theme.TEXT_DIM)
            return

        account = getattr(getattr(report, "options", None), "account_id", 0)
        name = (getattr(report, "name", "") or "").strip()
        self.who.setText(name or (str(account) if account else NOTHING_YET))
        if not (account and self.face.show_file(avatar_path(account))):
            self.face.show_initial(name or str(account))
        self.set_window(getattr(getattr(report, "options", None),
                                "window", "") or "")

        rate = getattr(report, "win_rate", None)
        self.values["rate"].setText(
            NOTHING if rate is None else f"{rate * 100:.0f}%")
        self.values["games"].setText(f"{getattr(report, 'n', 0)}")
        self._delta("rate", getattr(report, "win_rate_delta", None),
                    lambda value: f"{value:+.1f}%")
        self._delta("games", getattr(report, "games_delta", None),
                    lambda value: f"{value:+d}")
        self.setToolTip(self._compared(report))

    @staticmethod
    def _compared(report) -> str:
        """WHICH TWO STRETCHES the deltas are the difference between.

        It said only how many matches the earlier one held, and a reader
        who thinks a figure looks wrong cannot check that against
        anything. Naming the two spans in dates is what makes the
        comparison auditable — "6 motnhs to now my win rate is 5.8% worse
        than it was 12 months to 6 months ago???" is exactly the question
        this line exists to let somebody answer.
        """
        before = getattr(report, "before", None)
        if before is None:
            return ("Nothing to compare this against: either the window "
                    "is All history, or the stretch before it could not "
                    "be measured in full.")
        ran = getattr(report, "ran_at", None)
        days = getattr(getattr(report, "options", None), "days", None)
        span = ""
        if ran is not None and days:
            step = timedelta(days=int(days))
            span = (f" {(ran - 2 * step).strftime(MONTH)} to "
                    f"{(ran - step).strftime(MONTH)}, against "
                    f"{(ran - step).strftime(MONTH)} to "
                    f"{ran.strftime(MONTH)}.")
        return (f"The same length of time before this one held "
                f"{before.matches} matches, {before.wins} won.{span}")

    def _delta(self, key, value, spell) -> None:
        """Green up, red down, black halo round both.

        At the user's request: "for these deltas i want them to show
        green if positive and red if negative... ensure bvlack halo
        effect is on green / red text so it is readable". The halo is
        this app's rule for every signed number anyway, and it is doing
        real work here — the callout is a menu over a running game.

        NO BRACKETS AROUND NOTHING. With no stretch before this one the
        label is EMPTY rather than "(+0.0%)", which would be a
        measurement nobody made.
        """
        label = self.deltas[key]
        if value is None:
            label.set_value("", theme.TEXT_DIM)
            return
        colour = (theme.GOOD if value > 0 else
                  theme.BAD if value < 0 else theme.TEXT_DIM)
        label.set_value(f"({spell(value)})", colour)

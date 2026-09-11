"""Whose history the analysis is for, across the top of the Draft tab.

IT SITS WHERE THE AD SLOT SITS, at the user's request, and the ad now
defaults OFF - so on an ordinary install this row is the first thing at
the top of the content. The reasoning is the ad's own, inverted: reserving
a strip for something nobody turned on was dead window, and this is
something there IS always an answer for, so it earns the height the
placeholder never did.

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
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from . import chrome, theme

FACE = 34                 # the avatar's edge, in pixels
PADDING = 6
NOTHING_YET = "No account measured yet"
PROMPT = "Open the History tab to analyse one"


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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("accountRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
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
        self.when = QLabel(PROMPT, self)
        self.when.setProperty("dim", True)
        row.addWidget(self.who, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.rule, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.when, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)

        self.face.show_initial("")

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
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
            self.when.setText(PROMPT)
            self.face.show_initial("")
            self.setToolTip("")
            return

        account = getattr(getattr(report, "options", None), "account_id", 0)
        name = (getattr(report, "name", "") or "").strip()
        self.who.setText(name or (str(account) if account else NOTHING_YET))
        self.when.setText(self.span(report))

        shown = False
        if account:
            from ..history import avatars
            shown = self.face.show_file(avatars.stored(account))
        if not shown:
            self.face.show_initial(name or str(account))
        self.setToolTip(
            f"{name or account} - {len(getattr(report, 'matches', []))} "
            f"matches. Click to open the History tab.")

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
        end = ran.strftime("%d %b %Y")
        if not days:
            return f"All history  \u2192  {end}"
        start = (ran - timedelta(days=int(days))).strftime("%d %b %Y")
        # AND HOW LONG THAT IS, in brackets, at the user's request - two
        # dates make the reader do the subtraction, and the whole point of
        # the row is to be read at a glance. It is the window's OWN label
        # ("Last 3 months" less the "Last"), so it can never disagree with
        # the dates beside it the way a recomputed figure could.
        span = (getattr(options, "window_label", "") or "").strip()
        if span.lower().startswith("last "):
            span = span[5:]
        tail = f"  ({span})" if span else ""
        return f"{start}  \u2192  {end}{tail}"

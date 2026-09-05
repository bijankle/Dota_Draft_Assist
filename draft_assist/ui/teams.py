"""The two team panels on the Draft tab.

Five heroes across, as tiles, because that is the shape the same ten picks
have on Dota's own pick bar — the eye arrives already knowing the layout,
and a row of full-width name buttons cost five times the vertical space to
say less. The hero's own portrait sits behind the name where it has been
downloaded for recognition; the signed number sits directly under it.

Each tile always reserves the number line whether or not it holds a value:
tiles that grew by a text height every time something was clicked made the
panel restless, and a draft panel that moves under the cursor is one you
misclick.
"""

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel,
                             QSizePolicy, QVBoxLayout)

from . import theme
from .portraits import portrait

# "with" and "vs" are different questions and the eye should not have to
# read a legend to tell which it is looking at. Words rather than glyphs:
# a symbol that falls back to a box on the user's font would say nothing.
KIND_MARK = {"with": "with", "vs": "vs"}

TILE_HEIGHT = 116
TILE_MIN_WIDTH = 78
EMPTY_TEXT = "+"

# The portrait is background, not subject: the text has to win. A flat
# scrim over the whole tile plus a heavier band under the name is enough
# without turning the art into mud.
SCRIM = QColor(0, 0, 0, 120)
NAME_BAND = QColor(0, 0, 0, 150)


class HeroTile(QAbstractButton):
    """One pick: portrait behind, name across the top, number beneath it.

    A button rather than a composed widget because it is one click target;
    `text()` keeps the same "Pos 3 · Necrophos" form the rest of the app
    reads, so the tile is a drop-in for the row button it replaces.
    """

    def __init__(self, side: str, index: int, parent=None):
        super().__init__(parent)
        self.side = side
        self.index = index
        # Also dynamic properties: the window reads a clicked tile's side
        # and index straight off the sender, the way it did the buttons
        # these replaced.
        self.setProperty("side", side)
        self.setProperty("slot_index", index)
        self.setProperty("hero_id", None)
        self.hero_name: str | None = None
        self.role: str | None = None
        self._delta = ""
        self._delta_colour = theme.TEXT_DIM
        self._focused = False
        self.setFixedHeight(TILE_HEIGHT)
        self.setMinimumWidth(TILE_MIN_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Focusable so Tab walks the ten slots in order.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def sizeHint(self) -> QSize:            # noqa: N802 - Qt naming
        return QSize(112, TILE_HEIGHT)

    # ---- what the tile holds -------------------------------------------
    def set_pick(self, name: str | None, role: str | None,
                 hero_id: int | None) -> None:
        self.hero_name = name
        self.role = role
        self.setProperty("hero_id", hero_id)
        prefix = f"{role} · " if role else ""
        self.setText(prefix + (name or EMPTY_TEXT))
        self.update()

    @property
    def filled(self) -> bool:
        return self.hero_name is not None

    # ---- the relation line ---------------------------------------------
    def show_delta(self, delta: float, kind: str | None = None) -> None:
        mark = KIND_MARK.get(kind or "", "")
        self._delta = f"{mark} {delta * 100:+.1f}".strip()
        self._delta_colour = theme.GOOD if delta >= 0 else theme.BAD
        self.update()

    def clear_delta(self) -> None:
        self._delta = ""
        self.update()

    def delta_text(self) -> str:
        return self._delta

    # ---- the focused pick ----------------------------------------------
    def set_focused(self, on: bool) -> None:
        self._focused = bool(on)
        self.update()

    @property
    def focused(self) -> bool:
        return self._focused

    # ---- painting -------------------------------------------------------
    def paintEvent(self, event) -> None:    # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        box = self.rect().adjusted(0, 0, -1, -1)

        art = portrait(self.property("hero_id"))
        if art is not None:
            # Fill the tile and crop, rather than letterbox: a portrait with
            # bars around it stops reading as a portrait.
            scaled = art.scaled(box.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                Qt.TransformationMode.SmoothTransformation)
            source = QRect(max(0, (scaled.width() - box.width()) // 2),
                           max(0, (scaled.height() - box.height()) // 3),
                           box.width(), box.height())
            painter.drawPixmap(box, scaled, source)
            painter.fillRect(box, SCRIM)
        else:
            painter.fillRect(box, QColor(theme.BG_INPUT if self.filled
                                         else theme.BG))

        self._paint_border(painter, box)
        if not self.filled:
            self._paint_empty(painter, box)
            painter.end()
            return

        metrics_name = QFontMetrics(self._font(11, bold=True))
        band = QRect(box.left(), box.top(),
                     box.width(), metrics_name.height() + 8)
        if art is not None:
            painter.fillRect(band, NAME_BAND)
        painter.setFont(self._font(11, bold=True))
        painter.setPen(QColor(theme.TEXT_STRONG))
        painter.drawText(
            band.adjusted(4, 0, -4, 0),
            Qt.AlignmentFlag.AlignCenter,
            metrics_name.elidedText(self.hero_name or "",
                                    Qt.TextElideMode.ElideRight,
                                    band.width() - 8))

        painter.setFont(self._font(12, bold=True))
        delta_box = QRect(box.left(), band.bottom() + 2, box.width(),
                          QFontMetrics(self._font(12, bold=True)).height() + 4)
        painter.setPen(QColor(self._delta_colour))
        painter.drawText(delta_box, Qt.AlignmentFlag.AlignCenter, self._delta)

        if self.role:
            painter.setFont(self._font(9))
            painter.setPen(QColor(theme.TEXT_DIM))
            painter.drawText(box.adjusted(0, 0, 0, -4),
                             Qt.AlignmentFlag.AlignHCenter
                             | Qt.AlignmentFlag.AlignBottom, self.role)
        painter.end()

    def _paint_border(self, painter: QPainter, box: QRect) -> None:
        if self._focused:
            pen = QPen(QColor(theme.ACCENT), 2)
        elif self.hasFocus() or self.underMouse():
            pen = QPen(QColor(theme.TEXT_DIM), 1)
        elif self.filled:
            pen = QPen(QColor(theme.BORDER), 1)
        else:
            pen = QPen(QColor(theme.BORDER), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(box, 6, 6)

    def _paint_empty(self, painter: QPainter, box: QRect) -> None:
        """An empty slot is an invitation, not a pick."""
        painter.setFont(self._font(18))
        painter.setPen(QColor(theme.TEXT_DIM))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, EMPTY_TEXT)
        if self.role:
            painter.setFont(self._font(9))
            painter.drawText(box.adjusted(0, 0, 0, -4),
                             Qt.AlignmentFlag.AlignHCenter
                             | Qt.AlignmentFlag.AlignBottom, self.role)

    def _font(self, size: int, bold: bool = False) -> QFont:
        font = QFont(self.font())
        font.setPointSize(size)
        font.setBold(bold)
        return font


class TeamPanel(QFrame):
    """Five tiles under one heading — one half of the draft."""

    def __init__(self, side: str, caption: str, parent=None):
        super().__init__(parent)
        self.side = side
        self.setProperty("card", True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)

        head = QHBoxLayout()
        self.caption = QLabel(caption)
        self.caption.setProperty("heading", True)
        head.addWidget(self.caption)
        head.addStretch(1)
        self.note = QLabel("")
        self.note.setProperty("dim", True)
        head.addWidget(self.note)
        lay.addLayout(head)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.slots = [HeroTile(side, i, self) for i in range(5)]
        for tile in self.slots:
            row.addWidget(tile, 1)
        lay.addLayout(row)

    @property
    def buttons(self) -> list[HeroTile]:
        return list(self.slots)

    def clear_deltas(self) -> None:
        for tile in self.slots:
            tile.clear_delta()
            tile.set_focused(False)

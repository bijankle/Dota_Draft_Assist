"""The item strip under the two teams.

Items were a paragraph of prose in a side panel, gated behind locking your
own pick — so on the screen where they matter they were usually blank, and
by the time they appeared the decision they informed had been made. They
are now a line of icons directly under the draft, visible as soon as any
enemy is known.

Icons rather than names because the strip is read in the corner of the eye:
a Dota player recognises a BKB by its shape long before they read the words
"Black King Bar". The severity of the strongest trigger colours the bar
under each icon, and the full reasoning — which enemy, and why — is the
tooltip, because a strip that explained itself in place would be the
paragraph again.
"""

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QSizePolicy, QWidget)

from . import theme
from .item_icons import icon

ICON_W = 60
ICON_H = 46
SEVERITY_COLOUR = {3: theme.BAD, 2: theme.WARN, 1: theme.TEXT_DIM}
MAX_SHOWN = 8


class ItemTile(QWidget):
    """One recommended item: its picture, or its name if there isn't one."""

    def __init__(self, advice, parent=None):
        super().__init__(parent)
        self.advice = advice
        self.setFixedSize(ICON_W, ICON_H + 16)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setToolTip(self._tooltip())

    def _tooltip(self) -> str:
        lines = [f"<b>{self.advice.item}</b>"]
        for trigger in self.advice.triggers:
            lines.append(f"sev {trigger.severity} · {trigger.reason}")
        if self.advice.any_stale:
            lines.append("<i>unverified this patch</i>")
        lines.append("<i>Hand-authored rule, not measured.</i>")
        return "<br>".join(lines)

    def paintEvent(self, event) -> None:        # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        box = QRect(0, 0, ICON_W, ICON_H)
        art = icon(self.advice.item)
        if art is not None:
            scaled = art.scaled(box.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap(box.left() + (box.width() - scaled.width()) // 2,
                               box.top() + (box.height() - scaled.height()) // 2,
                               scaled)
        else:
            # No picture downloaded: the name still has to be readable, so
            # it is drawn small and wrapped rather than skipped.
            painter.fillRect(box, QColor(theme.BG_INPUT))
            font = QFont(self.font())
            font.setPointSize(8)
            painter.setFont(font)
            painter.setPen(QColor(theme.TEXT))
            painter.drawText(box.adjusted(2, 2, -2, -2),
                             int(Qt.AlignmentFlag.AlignCenter
                                 | Qt.TextFlag.TextWordWrap),
                             self.advice.item)

        severity = self.advice.triggers[0].severity if self.advice.triggers \
            else 1
        colour = QColor(SEVERITY_COLOUR.get(severity, theme.TEXT_DIM))
        painter.fillRect(QRect(0, ICON_H, ICON_W, 3), colour)

        font = QFont(self.font())
        font.setPointSize(8)
        painter.setFont(font)
        painter.setPen(QColor(theme.TEXT_DIM))
        metrics = QFontMetricsF(font)
        label = metrics.elidedText(self.advice.item,
                                   Qt.TextElideMode.ElideRight, ICON_W - 2)
        painter.drawText(QRect(0, ICON_H + 3, ICON_W, 13),
                         int(Qt.AlignmentFlag.AlignCenter), label)
        painter.end()

    def sizeHint(self) -> QSize:                # noqa: N802
        return self.size()


class ItemRow(QWidget):
    """A line of item tiles, or one line of text saying why there are none."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(8)
        self.message = QLabel("")
        self.message.setProperty("dim", True)
        self.row.addWidget(self.message)
        self.row.addStretch(1)
        self._tiles: list[ItemTile] = []

    def show_items(self, advice: list, empty: str) -> None:
        for tile in self._tiles:
            self.row.removeWidget(tile)
            tile.deleteLater()
        self._tiles = []
        if not advice:
            self.message.setText(empty)
            self.message.setVisible(True)
            return
        self.message.setVisible(False)
        for entry in advice[:MAX_SHOWN]:
            tile = ItemTile(entry, self)
            self.row.insertWidget(len(self._tiles), tile)
            self._tiles.append(tile)

    @property
    def items(self) -> list[str]:
        return [tile.advice.item for tile in self._tiles]

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

from PyQt6.QtCore import QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from . import theme
from .item_icons import icon
from .textfit import fit

ICON_W = 64
ICON_H = 46
NAME_H = 26
NAME_MAX_PT = 9
NAME_MIN_PT = 7
SEVERITY_COLOUR = {3: theme.BAD, 2: theme.WARN, 1: theme.TEXT_DIM}
MAX_SHOWN = 8

# Scaled copies, keyed by (item, box). Same reason as the portraits: a
# smooth rescale inside paintEvent, for a picture that never changes, on
# every repaint.
_fitted_cache: dict[tuple[str, int, int], object] = {}


def _fitted(item: str, width: int, height: int):
    art = icon(item)
    if art is None or width < 1 or height < 1:
        return None
    key = (item, width, height)
    hit = _fitted_cache.get(key)
    if hit is None:
        hit = art.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
        _fitted_cache[key] = hit
    return hit


def forget_scaled() -> None:
    """Drop the scaled copies — after an icon download, or in tests."""
    _fitted_cache.clear()


class ItemTile(QWidget):
    """One recommended item: its picture over its name.

    The name is drawn ONCE, at the bottom. An earlier version put it in the
    picture's place as a fallback and kept the label underneath, so an item
    with no downloaded icon showed its name twice.
    """

    def __init__(self, advice, parent=None):
        super().__init__(parent)
        self.advice = advice
        self.setFixedSize(ICON_W, ICON_H + NAME_H)
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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        box = QRect(0, 0, ICON_W, ICON_H)
        art = _fitted(self.advice.item, box.width(), box.height())
        if art is not None:
            painter.drawPixmap(box.left() + (box.width() - art.width()) // 2,
                               box.top() + (box.height() - art.height()) // 2,
                               art)
        else:
            # No picture: a plain plate, not the name again.
            painter.fillRect(box, QColor(theme.BG_INPUT))
            painter.setPen(QPen(QColor(theme.BORDER), 1))
            painter.drawRect(box.adjusted(0, 0, -1, -1))

        severity = (self.advice.triggers[0].severity
                    if self.advice.triggers else 1)
        painter.fillRect(QRect(0, ICON_H - 3, ICON_W, 3),
                         QColor(SEVERITY_COLOUR.get(severity, theme.TEXT_DIM)))

        self._paint_name(painter)
        painter.end()

    def _paint_name(self, painter: QPainter) -> None:
        """Shrunk, then wrapped, then elided — the same rule the hero tiles
        use, because an item called "Scythe of Vyse" in a 64px box is the
        same problem as a hero called "Keeper of the Light"."""
        area = QRectF(1, ICON_H + 2, ICON_W - 2, NAME_H - 3)
        size, lines = fit(self.advice.item, area.width(), area.height(),
                          self.font(), NAME_MAX_PT, NAME_MIN_PT)
        font = QFont(self.font())
        font.setPointSize(size)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        painter.setPen(QColor(theme.TEXT))
        painter.drawText(
            area, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
            "\n".join(metrics.elidedText(line, Qt.TextElideMode.ElideRight,
                                          area.width())
                       for line in lines))

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
        self.note = QLabel("")
        self.note.setProperty("dim", True)
        self.note.setVisible(False)
        self.row.addWidget(self.note)
        self._tiles: list[ItemTile] = []

    def set_note(self, text: str) -> None:
        """A word about the strip itself, beside it rather than in place of
        it — an unconfigured app should still show its advice."""
        self.note.setText(text)
        self.note.setVisible(bool(text))

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

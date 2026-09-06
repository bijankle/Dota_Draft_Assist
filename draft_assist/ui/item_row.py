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
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from . import theme, tilekit
from .item_icons import icon
from .tilekit import NAME_MAX_PT, NAME_MIN_PT  # noqa: F401 (re-exported)

# The same box the suggested picks use, and the same name band the ten
# picks use. Three strips that look like three different apps was the
# complaint; `tilekit` is the answer.
ICON_W = tilekit.STRIP_W
ICON_H = tilekit.STRIP_ART_H
NAME_H = tilekit.STRIP_BAND_H
SEVERITY_COLOUR = {3: theme.BAD, 2: theme.WARN, 1: theme.TEXT_DIM}
MAX_SHOWN = 8
# How many blank plates stand in for the strip before it has anything to
# say. Five, because five is what a full strip usually holds, so the row
# does not change height the moment the first item arrives.
PLACEHOLDERS = 5

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
    """One recommended item, laid out exactly like a pick.

    Name band across the top, picture underneath, severity as a bar along
    the bottom of the picture. The name used to sit under the art at a
    smaller size with no band, which made the item strip and the pick tiles
    read as two different apps.

    The name is drawn ONCE. An earlier version put it in the picture's
    place as a fallback AND kept the label underneath, so an item with no
    downloaded icon showed its name twice.
    """

    def __init__(self, advice, parent=None):
        super().__init__(parent)
        self.advice = advice
        self.setFixedSize(ICON_W, NAME_H + ICON_H)
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
        band = QRect(0, 0, ICON_W, NAME_H)
        box = QRect(0, NAME_H, ICON_W, ICON_H)
        art = _fitted(self.advice.item, box.width(), box.height())
        if not tilekit.paint_art(painter, box, art):
            # No picture: a plain plate, not the name again.
            tilekit.paint_plate(painter, box)

        severity = (self.advice.triggers[0].severity
                    if self.advice.triggers else 1)
        painter.fillRect(QRect(0, box.bottom() - 2, ICON_W, 3),
                         QColor(SEVERITY_COLOUR.get(severity, theme.TEXT_DIM)))

        tilekit.paint_band(painter, band, self.advice.item, self.font())
        painter.end()

    def sizeHint(self) -> QSize:                # noqa: N802
        return self.size()


class PlaceholderTile(QWidget):
    """An empty plate, the shape an item will be.

    A sentence saying items appear later is a sentence read once and then
    skipped forever; an outline of the row that is coming says the same
    thing in the place the answer will actually appear. Dashed, like an
    empty pick slot — but with no "+" on it, because unlike a pick slot
    there is nothing here to click.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(ICON_W, NAME_H + ICON_H)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:        # noqa: N802 - Qt naming
        painter = QPainter(self)
        tilekit.paint_plate(painter, QRect(0, 0, ICON_W, NAME_H + ICON_H),
                            dashed=True)
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
        self.note = QLabel("")
        self.note.setProperty("dim", True)
        self.note.setVisible(False)
        self.row.addWidget(self.note)
        self._tiles: list[ItemTile] = []
        self._blanks: list[PlaceholderTile] = []

    def set_note(self, text: str) -> None:
        """A word about the strip itself, beside it rather than in place of
        it — an unconfigured app should still show its advice."""
        self.note.setText(text)
        self.note.setVisible(bool(text))

    def show_items(self, advice: list, empty: str = "") -> None:
        for tile in self._tiles + self._blanks:
            self.row.removeWidget(tile)
            tile.deleteLater()
        self._tiles, self._blanks = [], []
        # `empty` is a REASON, not a stand-in for the strip: when there is
        # nothing to show the placeholders show the shape of the row and
        # the sentence, if there is one, sits beside them.
        self.message.setText(empty if not advice else "")
        self.message.setVisible(bool(empty) and not advice)
        if not advice:
            for _ in range(PLACEHOLDERS):
                blank = PlaceholderTile(self)
                self.row.insertWidget(len(self._blanks), blank)
                self._blanks.append(blank)
            return
        for entry in advice[:MAX_SHOWN]:
            tile = ItemTile(entry, self)
            self.row.insertWidget(len(self._tiles), tile)
            self._tiles.append(tile)

    @property
    def items(self) -> list[str]:
        return [tile.advice.item for tile in self._tiles]

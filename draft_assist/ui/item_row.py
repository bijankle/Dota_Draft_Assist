"""The item strip under the two teams.

Items were a paragraph of prose in a side panel, gated behind locking your
own pick — so on the screen where they matter they were usually blank, and
by the time they appeared the decision they informed had been made. They
are now a line of icons directly under the draft, visible as soon as any
enemy is known.

Icons rather than names because the strip is read in the corner of the eye:
a Dota player recognises a BKB by its shape long before they read the words
"Black King Bar". **There is no severity bar under the icon**: the strip
is already ORDERED by severity, so the bar said in colour what position
was already saying, and it cost every tile three pixels of height and a
line of chrome under an otherwise clean picture. The reasoning — which
enemy, how urgent, and why — is the tooltip and the click, because a strip
that explained itself in place would be the paragraph again.
"""

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QLabel, QSizePolicy, QWidget

from . import theme, tilekit
from .flowlayout import FlowLayout
from .item_icons import icon
from .tilekit import NAME_MAX_PT, NAME_MIN_PT  # noqa: F401 (re-exported)

# The same box the suggested picks use, and the same name band the ten
# picks use. Three strips that look like three different apps was the
# complaint; `tilekit` is the answer.
# THE ICON'S OWN SHAPE. Valve publishes item art at 88x64, and the tile
# used to be the hero strip's 78x44 box — so every icon was scaled down to
# fit the height and centred with dead pixels either side, which reads as
# the items being spaced further apart than the heroes above them. Each
# strip takes its own art's aspect; the HEIGHT is shared, so the two
# strips still line up with each other.
# The FALLBACK box. The real HEIGHT comes from the draft panel above
# (`ItemRow.set_tile_size`), so an item tile is exactly as tall as a pick
# and a suggested hero — and it keeps its own WIDTH from that height,
# because Valve publishes item art at 88x64 and a 16:9 box round it is
# dead space either side of every icon, which reads as the items being
# spaced further apart than the heroes above them.
ICON_H = tilekit.STRIP_ART_H
ICON_W = round(ICON_H * 88 / 64)
# The shape the width is derived from, in one place.
ICON_ASPECT = 88 / 64


def width_for(height: int) -> int:
    """An item tile's width at a given height — the icon's own shape."""
    return max(1, round(int(height) * ICON_ASPECT))
NAME_H = tilekit.STRIP_BAND_H
# HOW MANY IS THE CALLER'S DECISION — it is a setting, edited on the strip
# itself. A cap in here would silently overrule it, and a number you set
# that does not take effect is worse than no setting at all.
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

    Just the picture. The NAME is
    the tooltip's job: a player recognises a BKB by its shape long before
    reading the words, and a row of labelled pictures reads as a list where
    a row of pictures reads at a glance. Clicking it asks WHY, which for an
    item is a real answer: the rules are hand-authored, so they carry a
    reason in words. The name band comes back only when
    there is no icon on disk to draw.

    The name is drawn ONCE. An earlier version put it in the picture's
    place as a fallback AND kept the label underneath, so an item with no
    downloaded icon showed its name twice.
    """

    asked_why = pyqtSignal(str)

    def __init__(self, advice, parent=None,
                 size: tuple[int, int] | None = None):
        super().__init__(parent)
        self.advice = advice
        self.setFixedSize(*(size or (ICON_W, ICON_H)))
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

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if (event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.asked_why.emit(self.advice.item)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:        # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        box = self.rect()
        art = _fitted(self.advice.item, box.width(), box.height())
        if not tilekit.paint_art(painter, box, art):
            # No icon on disk: the plate plus the name, because a blank
            # plate names nothing. With an icon the name is the tooltip's.
            tilekit.paint_plate(painter, box)
            # Most of the tile rather than a band across the top: there
            # is no art competing for the space, and a name squeezed into
            # a 22px strip can fail to fit at all and draw NOTHING, which
            # is a tile that says neither picture nor name. The bottom
            # quarter is left clear so the badge does not land on it.
            tilekit.paint_band(painter,
                               box.adjusted(0, 0, 0, -box.height() // 4),
                               self.advice.item, self.font())

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

    def __init__(self, parent=None, size: tuple[int, int] | None = None):
        super().__init__(parent)
        self.setFixedSize(*(size or (ICON_W, ICON_H)))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:        # noqa: N802 - Qt naming
        painter = QPainter(self)
        # ITS OWN RECT: the plate used to be drawn `NAME_H` taller than the
        # widget, so the dashed bottom edge fell off the tile and an empty
        # strip read as a different size from a full one.
        tilekit.paint_plate(painter, self.rect(), dashed=True)
        painter.end()

    def sizeHint(self) -> QSize:                # noqa: N802
        return self.size()


class ItemRow(QWidget):
    """A line of item tiles, or one line of text saying why there are none."""

    asked_why = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # WRAPS rather than scrolls: a strip you have to scroll to read is
        # a strip you do not read at a glance, which is the one thing it is
        # for. Past the width it has been given the tiles go to a new row.
        self.row = FlowLayout(self, spacing=8)
        self.message = QLabel("")
        self.message.setProperty("dim", True)
        self.row.addWidget(self.message)
        self.note = QLabel("")
        self.note.setProperty("dim", True)
        self.note.setVisible(False)
        self.row.addWidget(self.note)
        self._tiles: list[ItemTile] = []
        self._blanks: list[PlaceholderTile] = []
        self._tile_size = (ICON_W, ICON_H)

    def set_tile_size(self, height: int) -> None:
        """Take the picks' HEIGHT and keep the icon's own width."""
        height = max(1, int(height))
        size = (width_for(height), height)
        if size == self._tile_size:
            return
        self._tile_size = size
        for tile in self._tiles + self._blanks:
            tile.setFixedSize(*size)
        self.row.invalidate()
        self.updateGeometry()

    def tile_width(self) -> int:
        return self._tile_size[0]

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
                blank = PlaceholderTile(self, self._tile_size)
                self.row.insertWidget(len(self._blanks), blank)
                self._blanks.append(blank)
            return
        for entry in advice:
            tile = ItemTile(entry, self, self._tile_size)
            tile.asked_why.connect(self.asked_why)
            self.row.insertWidget(len(self._tiles), tile)
            self._tiles.append(tile)

    @property
    def items(self) -> list[str]:
        return [tile.advice.item for tile in self._tiles]

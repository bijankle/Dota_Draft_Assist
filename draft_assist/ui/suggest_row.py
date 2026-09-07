"""The suggested picks: the ranked list, as a strip, above the items.

The Analysis tab already ranks every hero the draft has not taken by draft
fit. That answer belongs on the Draft tab too — it is the question a draft
screen is actually asking — but 120 rows of it is a table, and a table
beside the ten picks makes the ten harder to read. So the top handful come
across as tiles: best on the left, descending to the right, exactly the way
the item strip reads.

The tiles are the item strip's tiles with a hero in them (`tilekit`), and
each carries its fit in the same bottom-right badge the ten picks use — the
same number, in the same place, in the same colours, so a suggestion and a
pick can be compared without translating between two layouts.

Nothing here is clickable. A pick is entered by clicking a SLOT, and a
strip that also entered picks would be a second way to do it that behaves
differently.
"""

from PyQt6.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QLabel, QSizePolicy, QWidget

from . import theme, tilekit
from .flowlayout import FlowLayout
from .portraits import scaled

WIDTH = tilekit.STRIP_W
ART_H = tilekit.STRIP_ART_H
BAND_H = tilekit.STRIP_BAND_H
# HOW MANY IS THE CALLER'S DECISION, not this widget's: it is a setting
# (Settings ▸ How much each strip shows), and a second cap in here would
# silently overrule it — raising the setting to twelve and getting eight
# is a bug with nothing on screen to explain it. The row draws the rows it
# is handed.
PLACEHOLDERS = 5


class SuggestTile(QWidget):
    """One candidate: the portrait, with its fit in the corner.

    Clicking it ASKS WHY, and nothing more. It does not enter the pick —
    a pick is entered by clicking a slot, and a second way to do it that
    behaved differently would be worse than no way.
    """

    asked_why = pyqtSignal(int)

    def __init__(self, hero_id: int, name: str, fit_value: float,
                 tooltip: str = "", parent=None):
        super().__init__(parent)
        self.hero_id = hero_id
        self.hero_name = name
        self.fit = float(fit_value)
        self.setFixedSize(WIDTH, ART_H)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setToolTip(tooltip or name)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if (event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.asked_why.emit(self.hero_id)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:        # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform, True)
        box = QRect(0, 0, WIDTH, ART_H)
        if not tilekit.paint_art(painter, box,
                                 scaled(self.hero_id, box.width(),
                                        box.height())):
            # No portrait on disk — a fresh install has none — so the name
            # goes back, because a blank plate names nothing.
            tilekit.paint_plate(painter, box)
            # Most of the tile rather than a band across the top: there
            # is no art competing for the space, and a name squeezed into
            # a 22px strip can fail to fit at all and draw NOTHING, which
            # is a tile that says neither picture nor name. The bottom
            # quarter is left clear so the badge does not land on it.
            tilekit.paint_band(painter,
                               box.adjusted(0, 0, 0, -box.height() // 4),
                               self.hero_name, self.font())
        # Same figure, same corner, same colours as a drafted tile: a
        # suggestion and a pick have to be comparable at a glance.
        tilekit.paint_badge(painter, QRect(0, 0, WIDTH, ART_H),
                            f"{self.fit * 100:+.1f}",
                            theme.GOOD if self.fit >= 0 else theme.BAD,
                            self.font())
        painter.end()

    def sizeHint(self) -> QSize:                # noqa: N802
        return self.size()


class PlaceholderTile(QWidget):
    """The shape a suggestion will be. Same reason as the item strip's."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(WIDTH, ART_H)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:        # noqa: N802
        painter = QPainter(self)
        tilekit.paint_plate(painter, QRect(0, 0, WIDTH, BAND_H + ART_H),
                            dashed=True)
        painter.end()

    def sizeHint(self) -> QSize:                # noqa: N802
        return self.size()


class SuggestRow(QWidget):
    """A line of suggestion tiles, best first."""

    asked_why = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        # WRAPS rather than scrolls: a strip you have to scroll to read is
        # a strip you do not read at a glance, which is the one thing it is
        # for. Past the width it has been given the tiles go to a new row.
        self.row = FlowLayout(self, spacing=8)
        self.message = QLabel("")
        self.message.setProperty("dim", True)
        self.message.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.row.addWidget(self.message)
        self._tiles: list[SuggestTile] = []
        self._blanks: list[PlaceholderTile] = []

    def show_heroes(self, rows: list[tuple[int, str, float, str]],
                    empty: str = "") -> None:
        """`rows` is (hero id, name, fit, tooltip), already in order."""
        for tile in self._tiles + self._blanks:
            self.row.removeWidget(tile)
            tile.deleteLater()
        self._tiles, self._blanks = [], []
        self.message.setText(empty if not rows else "")
        self.message.setVisible(bool(empty) and not rows)
        if not rows:
            for _ in range(PLACEHOLDERS):
                blank = PlaceholderTile(self)
                self.row.insertWidget(len(self._blanks), blank)
                self._blanks.append(blank)
            return
        for hero_id, name, fit_value, tip in rows:
            tile = SuggestTile(hero_id, name, fit_value, tip, self)
            tile.asked_why.connect(self.asked_why)
            self.row.insertWidget(len(self._tiles), tile)
            self._tiles.append(tile)

    @property
    def heroes(self) -> list[str]:
        return [tile.hero_name for tile in self._tiles]

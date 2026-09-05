"""A small always-on-top companion window: a draggable badge that expands
into a compact callout of the current recommendations.

It sits OVER Dota, never inside it — an ordinary top-level window that
happens to be frameless and stay on top. Nothing is injected into the game,
its rendering chain is untouched, and no input is sent to it, so the
project's boundary holds (see CLAUDE.md).

Deliberately interactive rather than click-through: the badge has to be
clickable to expand, and the whole thing has to be draggable. It is kept
small so that parking it in a corner costs no meaningful screen space, and
it can be collapsed to a single badge mid-draft.

Requires Dota in borderless windowed mode — an exclusive-fullscreen game
draws above every other window, so no overlay of any kind can appear.
"""

from PyQt6.QtCore import QEvent, QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)

from . import theme
from ..model import scoring
from .tables import MatrixTable

BADGE_SIZE = 30
PANEL_WIDTH = 560
# Far enough that a click with a shaky hand is still a click, close enough
# that a deliberate drag starts immediately.
DRAG_THRESHOLD = 5

OVERLAY_STYLE = f"""
QWidget#overlayRoot {{ background: transparent; }}
QFrame#overlayPanel {{
    background: rgba(18, 21, 27, 235);
    border: 1px solid {theme.BORDER};
    border-radius: 9px;
}}
QPushButton#overlayBadge {{
    background: rgba(79, 140, 201, 240);
    border: 1px solid #6ba3d8;
    border-radius: {BADGE_SIZE // 2}px;
    color: #ffffff;
    font-size: 17px;
    font-weight: 600;
    padding: 0px;
}}
QPushButton#overlayBadge:hover {{ background: rgba(103, 163, 222, 250); }}
QLabel {{ color: {theme.TEXT}; background: transparent; }}
QLabel[dim="true"] {{ color: {theme.TEXT_DIM}; }}
/* The callout grids run smaller than the main window's: the same numbers,
   read at arm's length beside a game rather than studied. */
QTableWidget {{ font-size: 11px; background: transparent; }}
QHeaderView::section {{ font-size: 11px; }}
"""


class DraftOverlay(QWidget):
    """Emits moved() whenever the user drags it, so the position can be
    remembered between sessions."""

    moved = pyqtSignal(int, int)
    toggled = pyqtSignal(bool)

    def __init__(self, dataset, rows: int = 6, expanded: bool = True,
                 parent=None):
        super().__init__(parent)
        self.ds = dataset
        self.rows = rows
        self._drag_offset: QPoint | None = None
        # Badge drags are tracked separately: the badge is a button, so a
        # press on it has to stay a click until it has clearly become a
        # drag, or the overlay could never be picked up by its handle.
        self._badge_press: QPoint | None = None
        self._badge_dragging = False

        self.setObjectName("overlayRoot")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # Showing without stealing focus matters: appearing mid-draft must
        # never pull keyboard focus out of the game.
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setStyleSheet(OVERLAY_STYLE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        self.badge = QPushButton("+")
        self.badge.setObjectName("overlayBadge")
        self.badge.setFixedSize(BADGE_SIZE, BADGE_SIZE)
        self.badge.setToolTip("Show or hide the recommendations · drag to move")
        self.badge.setCursor(Qt.CursorShape.OpenHandCursor)
        self.badge.clicked.connect(self.toggle)
        self.badge.installEventFilter(self)
        badge_row.addWidget(self.badge)
        badge_row.addStretch(1)
        outer.addLayout(badge_row)

        self.panel = QFrame()
        self.panel.setObjectName("overlayPanel")
        self.panel.setFixedWidth(PANEL_WIDTH)
        play = QVBoxLayout(self.panel)
        play.setContentsMargins(10, 8, 10, 10)
        play.setSpacing(5)

        self.state_label = QLabel("waiting for game data")
        self.state_label.setProperty("dim", True)
        self.state_label.setWordWrap(True)
        play.addWidget(self.state_label)

        self.rows_holder = QVBoxLayout()
        self.rows_holder.setSpacing(2)
        play.addLayout(self.rows_holder)
        self.row_labels: list[QLabel] = []
        for _ in range(rows):
            label = QLabel("")
            label.setTextFormat(Qt.TextFormat.RichText)
            self.rows_holder.addWidget(label)
            self.row_labels.append(label)

        self.footer = QLabel("")
        self.footer.setProperty("dim", True)
        self.footer.setWordWrap(True)
        play.addWidget(self.footer)

        # The same two grids as the main window. Mid-draft the callout is
        # the only surface the user is looking at, and a ranked list of
        # candidates does not answer "which of my lanes loses" — the grids
        # do, and their margins say which hero is the problem.
        for title, attr in (("Counters — us vs them", "matchup_matrix"),
                            ("Synergy — us with us", "synergy_matrix")):
            heading = QLabel(title)
            heading.setProperty("dim", True)
            play.addWidget(heading)
            table = MatrixTable()
            table.set_compact(True)
            setattr(self, attr, table)
            play.addWidget(table)

        outer.addWidget(self.panel)
        self.set_expanded(expanded)

    # ---- expand / collapse ---------------------------------------------
    def set_expanded(self, expanded: bool) -> None:
        self.panel.setVisible(expanded)
        self.badge.setText("−" if expanded else "+")
        # Collapsed, the window must shrink to the badge itself — otherwise
        # an invisible strip keeps sitting over the game, swallowing clicks.
        if expanded:
            self.setMaximumHeight(16_777_215)
            self.setMinimumHeight(0)
            self.setFixedWidth(PANEL_WIDTH)
            self.adjustSize()
        else:
            self.setFixedSize(BADGE_SIZE, BADGE_SIZE)
        self.toggled.emit(expanded)

    def toggle(self) -> None:
        self.set_expanded(not self.panel.isVisible())

    @property
    def expanded(self) -> bool:
        return self.panel.isVisible()

    # ---- dragging -------------------------------------------------------
    def eventFilter(self, obj, event):          # noqa: N802 - Qt naming
        """Let the badge be both a button and the overlay's drag handle.

        The badge is the only part of the overlay that is always on screen,
        so it has to be what you pick the thing up by; but it is also the
        toggle, so a press cannot become a drag until it has moved far
        enough to mean one.
        """
        if obj is not self.badge:
            return super().eventFilter(obj, event)
        if (event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton):
            self._badge_press = event.globalPosition().toPoint()
            self._badge_dragging = False
            self._drag_offset = (self._badge_press
                                 - self.frameGeometry().topLeft())
        elif (event.type() == QEvent.Type.MouseMove
                and self._badge_press is not None):
            here = event.globalPosition().toPoint()
            if ((here - self._badge_press).manhattanLength() > DRAG_THRESHOLD
                    or self._badge_dragging):
                self._badge_dragging = True
                self.move(here - self._drag_offset)
                return True
        elif (event.type() == QEvent.Type.MouseButtonRelease
                and self._badge_press is not None):
            dragged = self._badge_dragging
            self._badge_press = None
            self._badge_dragging = False
            self._drag_offset = None
            if dragged:
                self.moved.emit(self.x(), self.y())
                # Swallowed, so the badge does not also toggle: you moved
                # it, you did not press it.
                return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (event.globalPosition().toPoint()
                                 - self.frameGeometry().topLeft())
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None:
            self._drag_offset = None
            self.moved.emit(self.x(), self.y())
            event.accept()

    # ---- content --------------------------------------------------------
    def set_dataset(self, dataset) -> None:
        self.ds = dataset

    def update_content(self, snapshot, scored, draft) -> None:
        """Refresh from the same state the main window renders, so the two
        can never disagree about what is being recommended."""
        self.state_label.setText(self._headline(snapshot, draft))

        role_tags = _role_tags(draft.my_role)
        shown = 0
        for label, entry in zip(self.row_labels, scored[:self.rows]):
            hero_roles = set(self.ds.heroes.get(entry.hero_id, {})
                             .get("roles", []))
            highlight = bool(role_tags and role_tags & hero_roles)
            name = entry.name
            if highlight:
                name = f"<b>{name}</b>"
            # One definition of score across the app: draft fit, no win
            # rate. The overlay and the main window cannot disagree about
            # which hero is best if they are showing the same number.
            colour = theme.GOOD if entry.score >= 0 else theme.BAD
            label.setText(
                f"<table width='100%'><tr>"
                f"<td>{name}</td>"
                f"<td align='right' width='52'>"
                f"<font color='{colour}'>{entry.score * 100:+.1f}</font></td>"
                f"</tr></table>")
            label.setVisible(True)
            shown += 1
        for label in self.row_labels[shown:]:
            label.setVisible(False)

        self.matchup_matrix.show_matrix(
            scoring.matchup_matrix(self.ds, draft),
            "Both teams needed before the grid means anything.")
        self.synergy_matrix.show_matrix(
            scoring.synergy_matrix(self.ds, draft),
            "Your own team needed before the grid means anything.")

        self.footer.setText(self._footer(snapshot, scored))
        self.adjustSize()

    def _headline(self, snapshot, draft) -> str:
        if self.ds.is_empty:
            return "No hero data yet — run Data ▸ Update statistics."
        state = (snapshot.game_state or "")
        pretty = state.replace("DOTA_GAMERULES_STATE_", "").replace("_", " ")
        picks = len(draft.allies) + len(draft.enemies)
        if pretty:
            return f"{pretty.title()} · {picks} picks known"
        return f"{picks} picks known"

    def _footer(self, snapshot, scored) -> str:
        if not scored:
            return "No recommendations yet."
        if snapshot.needs_manual:
            return "Enemy picks not reported by the game — add them in the " \
                   "main window."
        return ""


def _role_tags(role: str | None) -> set[str]:
    from .app import ROLE_TAGS
    return ROLE_TAGS.get(role, set()) if role else set()

"""The advertising banner above the draft.

A placeholder, deliberately: there is no ad network wired in and no
network call is made. What is here is the SLOT — the space an ad would
take, on the schedule it would appear on — so the layout question ("what
does the window look like with this in it") can be answered now, and so
turning it on and living with it for an evening is a thing the owner can
actually try before committing to it.

**It is off by default and it is a setting** (`ui_settings.ads_enabled`).
This is the user's own app on their own machine; something that covers
part of the board every few seconds has to be asked for.

**It reserves its height whether or not it is showing.** A banner that
appears and disappears while pushing the ten picks up and down the window
is a board that moves under the cursor mid-draft, which is how a pick gets
misclicked. The slot keeps its height and only its CONTENT comes and goes,
so nothing below it ever moves.

The live scoring loop never makes network calls (see CLAUDE.md), and that
still holds: whatever eventually fills this must fetch on its own timer,
off the draft path, or it will cost a draft the first time a network
hiccups.
"""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from . import theme

# Five seconds on, ten off, at the user's request.
SHOWING_MS = 5_000
HIDDEN_MS = 10_000
# Tall enough to be a banner, short enough not to be the screen.
HEIGHT = 60


class AdSlot(QWidget):
    """A banner that shows for `SHOWING_MS` in every cycle, or never."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("adSlot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(HEIGHT)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setObjectName("adText")
        lay.addWidget(self.label)
        self._enabled = False
        self._showing = False
        # A single-shot restarted each turn rather than two timers: one
        # clock cannot get out of step with itself.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._turn)
        self._paint()

    def set_enabled(self, on: bool) -> None:
        """Switch the whole thing on or off, keeping the reserved height."""
        on = bool(on)
        if on == self._enabled:
            return
        self._enabled = on
        self._showing = False
        self._timer.stop()
        if on:
            self._timer.start(HIDDEN_MS)
        self._paint()

    @property
    def showing(self) -> bool:
        return self._showing

    def _turn(self) -> None:
        self._showing = not self._showing
        self._timer.start(SHOWING_MS if self._showing else HIDDEN_MS)
        self._paint()

    def _paint(self) -> None:
        # The SLOT stays; only what is in it comes and goes. Hiding the
        # widget itself would move the ten picks up and down the window
        # every few seconds, and a board that moves is one you misclick.
        self.label.setText("Advertisement" if self._showing else "")
        self.setProperty("live", "true" if self._showing else "false")
        self.style().unpolish(self)
        self.style().polish(self)

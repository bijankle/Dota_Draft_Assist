"""Which ranks the advice describes — five ranges, pick exactly one.

**THE INDIVIDUAL RANKS ARE GONE**, at the user's request: "i dont like
that the rank pairings linking up with the tick boxes above. Its very
wasteful.... get ride of the tick boxes above (iondividual ranks) and and
just make the rank pairings have tick boxes to indicate which one is
selected (only allow selection of 1 pair / range) i prefer the look that
was used of the indiviusal ranks that you had - use that formatting for
the pairs."

So the shape is the eight boxes' own — a grid of `chrome.TickBox` — with
the five RANGES in it instead, and the row of push buttons underneath is
gone. It was eight boxes and five buttons saying the same thing twice,
with the buttons silently re-ticking the boxes above them: two controls
for one setting, which is the fault this project has a standing rule
about, and the reason the card took two rows it did not need.

**THE COST IS STATED RATHER THAN HIDDEN.** The individual ranks exactly
controlled the OpenDota BASELINES whatever Stratz could do with the
pairwise half, so a single bracket on its own is no longer askable from
the UI. On this account it changes nothing — the default has been
Ancient + Divine throughout, which is one of the ranges — and
`config.target_brackets()` still takes any tuple, so a hand-edited
`preferences.json` is read back and honoured.

**EXCLUSIVE, AND CLICKING THE TICKED ONE KEEPS IT.** "only allow
selection of 1 pair / range". A tick box normally toggles off, which here
would leave NO rank chosen — a state that means nothing and that the
summary would have to complain about. Radio behaviour without the radio
look: the choice moves, it never empties.

**ONE LIST, because there were two and they disagreed.** The wizard
offered plain ranges ("Legend – Ancient") while the settings dialog
offered advice ("I play Legend, climbing to Ancient" — which selected
Ancient + Divine, a bracket ABOVE what the label said). Two spellings of
one set of choices is one of them being wrong, and it was.
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QGridLayout, QWidget

from ..config import ALL_BRACKETS, DEFAULT_TARGET_BRACKETS
from . import chrome

# The five spans on offer, named by what they ARE. Two adjacent brackets
# roughly doubles the sample for a metagame difference smaller than the
# noise it removes; Herald is three because the bottom three are thin.
RANGES = (
    ("Herald – Crusader", ("HERALD", "GUARDIAN", "CRUSADER")),
    ("Archon – Legend", ("ARCHON", "LEGEND")),
    ("Legend – Ancient", ("LEGEND", "ANCIENT")),
    ("Ancient – Divine", ("ANCIENT", "DIVINE")),
    ("Divine – Immortal", ("DIVINE", "IMMORTAL")),
)

COLUMNS = 3


def best_match(current) -> tuple[str, ...]:
    """Which range a saved selection means, for opening the picker on it.

    A file written before this existed can hold any set at all — one
    bracket, or three that are not a range — so "which box is ticked"
    has to be answered for sets that were never one of these. EXACT
    first, then the range sharing the most brackets with it, and the
    default when nothing overlaps at all. It never answers nothing: a
    picker that opens with no box ticked is asking a question the file
    has already answered.
    """
    held = set(current or ())
    for _label, brackets in RANGES:
        if held == set(brackets):
            return tuple(brackets)
    best, score = None, 0
    for _label, brackets in RANGES:
        overlap = len(held & set(brackets))
        if overlap > score:
            best, score = tuple(brackets), overlap
    return best or tuple(DEFAULT_TARGET_BRACKETS)


class RangePicker(QWidget):
    """The five ranges as one exclusive set of tick boxes."""

    picked = pyqtSignal()

    def __init__(self, current=(), parent=None):
        super().__init__(parent)
        self.setProperty("bare", True)      # see `_picks_controls`
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(18)
        self._chosen = best_match(current)
        self.boxes: dict[str, chrome.TickBox] = {}
        for index, (label, brackets) in enumerate(RANGES):
            box = chrome.TickBox(label)
            box.setChecked(tuple(brackets) == self._chosen)
            box.clicked.connect(
                lambda _c, b=tuple(brackets): self._take(b))
            grid.addWidget(box, index // COLUMNS, index % COLUMNS)
            self.boxes[label] = box

    def _take(self, brackets: tuple[str, ...]) -> None:
        """Move the choice to this range, and never to nothing.

        `clicked` rather than `toggled`, because this re-ticks the box
        that was just UNTICKED — on `toggled` that second change would
        come straight back round as another signal.
        """
        self._chosen = tuple(brackets)
        for label, box in self.boxes.items():
            want = dict(RANGES)[label] == brackets
            if box.isChecked() != want:
                box.setChecked(want)
        self.picked.emit()

    @property
    def chosen(self) -> tuple[str, ...]:
        """The brackets, in `ALL_BRACKETS` order — never empty."""
        return tuple(b for b in ALL_BRACKETS if b in set(self._chosen))

    def describe(self) -> str:
        """What the pull will cover, for the line under the picker."""
        return " + ".join(b.title() for b in self.chosen)

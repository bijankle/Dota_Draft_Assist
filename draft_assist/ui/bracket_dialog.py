"""Choose which rank brackets the statistics come from.

This is not a display filter. Baselines and the interaction matrices are
built for the chosen brackets, so changing the selection invalidates the
cached dataset and requires a re-pull — the dialog says so rather than
letting the numbers quietly disagree with the label.

The guidance offered is the project's original reasoning: aim about one
bracket above where you currently play, so the advice reflects the games you
are trying to win rather than the ones you already do.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel,
                             QPushButton, QVBoxLayout)

from ..config import ALL_BRACKETS
from .chrome import TickBox

# Where a player of each rank is usually best served pulling stats from.
SUGGESTIONS = [
    ("I play Herald / Guardian", ("GUARDIAN", "CRUSADER")),
    ("I play Crusader / Archon", ("ARCHON", "LEGEND")),
    ("I play Legend, climbing to Ancient", ("ANCIENT", "DIVINE")),
    ("I play Ancient / Divine", ("DIVINE", "IMMORTAL")),
    ("Match my own bracket (Legend + Ancient)", ("LEGEND", "ANCIENT")),
]


class BracketDialog(QDialog):
    def __init__(self, current: tuple[str, ...], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Statistics bracket")
        self.setMinimumWidth(430)
        self.selected: tuple[str, ...] = tuple(current)

        layout = QVBoxLayout(self)
        heading = QLabel("Which ranks should the statistics come from?")
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        blurb = QLabel(
            "Hero win rates and matchups differ by rank. Pulling from about "
            "one bracket above where you play tilts the advice toward the "
            "games you are trying to win. Two adjacent brackets are usually "
            "combined, which roughly doubles the sample for a metagame "
            "difference smaller than the noise it removes.")
        blurb.setWordWrap(True)
        blurb.setProperty("dim", True)
        layout.addWidget(blurb)

        # PAIRS ONLY WHEN STRATZ CAN ONLY DO PAIRS — "if stratz is pari
        # only, then i want pair only options". Read from what the last
        # build actually got (`stratz_bracket_filter["exact"]` in the
        # dataset meta) rather than assumed here, so an offer Stratz
        # cannot honour is never made. Three-valued: with nothing
        # measured the individual ranks stay, because they exactly
        # control the OpenDota BASELINES whatever Stratz can do with the
        # pairwise half. Same decision as the setup wizard's own page,
        # and the same reasoning.
        from ..data.store import bracket_coverage, pair_only_brackets

        self._picked = set(current)
        self.pair_only = pair_only_brackets() is True
        self.boxes: dict[str, TickBox] = {}
        if self.pair_only:
            spans = " + ".join(b.title() for b in bracket_coverage())
            said = QLabel(
                "Stratz can only filter its pairwise data in pairs"
                + (f", so it spans {spans}." if spans else "."))
            said.setWordWrap(True)
            said.setProperty("dim", True)
            layout.addWidget(said)
        else:
            for bracket in ALL_BRACKETS:
                box = TickBox(bracket.title())
                box.setChecked(bracket in current)
                box.toggled.connect(self._update_summary)
                layout.addWidget(box)
                self.boxes[bracket] = box

        presets = QHBoxLayout()
        presets.addWidget(QLabel("Pick a pair:" if self.pair_only
                                 else "Quick pick:"))
        layout.addLayout(presets)
        for label, brackets in SUGGESTIONS:
            button = QPushButton(label)
            button.clicked.connect(
                lambda _checked, b=brackets: self._apply_preset(b))
            layout.addWidget(button)

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.ok = QPushButton("Save")
        self.ok.setProperty("accent", True)
        self.ok.setDefault(True)
        self.ok.clicked.connect(self._accept)
        buttons.addWidget(self.ok)
        layout.addLayout(buttons)

        self._update_summary()

    def _apply_preset(self, brackets: tuple[str, ...]) -> None:
        self._picked = set(brackets)
        for name, box in self.boxes.items():
            box.setChecked(name in brackets)
        if not self.boxes:
            self._update_summary()

    def _chosen(self) -> tuple[str, ...]:
        """What is ticked — or, with no ticks, what the pairs chose.

        In pair-only mode the buttons are the only input, so what they
        set is remembered; it starts at what was already saved, so
        opening this and pressing Save changes nothing.
        """
        if not self.boxes:
            return tuple(b for b in ALL_BRACKETS if b in self._picked)
        return tuple(b for b in ALL_BRACKETS if self.boxes[b].isChecked())

    def _update_summary(self) -> None:
        chosen = self._chosen()
        self.ok.setEnabled(bool(chosen))
        if not chosen:
            self.summary.setText("Select at least one bracket.")
            return
        note = ""
        if len(chosen) == 1:
            note = (" Only one bracket selected — a smaller sample, so "
                    "matchup numbers will be noisier.")
        self.summary.setText(
            f"Statistics will be pulled for <b>{' + '.join(b.title() for b in chosen)}"
            f"</b>.{note}<br>Changing this rebuilds the dataset, so a data "
            "update is needed afterwards.")

    def _accept(self) -> None:
        chosen = self._chosen()
        if chosen:
            self.selected = chosen
            self.accept()

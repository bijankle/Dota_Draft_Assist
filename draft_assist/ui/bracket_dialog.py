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
from PyQt6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel,
                             QPushButton, QVBoxLayout)

from ..config import ALL_BRACKETS

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

        self.boxes: dict[str, QCheckBox] = {}
        for bracket in ALL_BRACKETS:
            box = QCheckBox(bracket.title())
            box.setChecked(bracket in current)
            box.toggled.connect(self._update_summary)
            layout.addWidget(box)
            self.boxes[bracket] = box

        presets = QHBoxLayout()
        presets.addWidget(QLabel("Quick pick:"))
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
        for name, box in self.boxes.items():
            box.setChecked(name in brackets)

    def _chosen(self) -> tuple[str, ...]:
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

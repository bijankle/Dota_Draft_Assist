"""Choose which rank brackets the statistics come from.

This is not a display filter. Baselines and the interaction matrices are
built for the chosen brackets, so changing the selection invalidates the
cached dataset and requires a re-pull — the dialog says so rather than
letting the numbers quietly disagree with the label.

The guidance offered is the project's original reasoning: aim about one
bracket above where you currently play, so the advice reflects the games you
are trying to win rather than the ones you already do.
"""

from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel,
                             QPushButton, QVBoxLayout)

from . import rankpick

# Where a player of each rank is usually best served pulling stats from.


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

        # FIVE RANGES, EXACTLY ONE TICKED — see `ui/rankpick.py`, which
        # both this dialog and the setup wizard's own page now use, so
        # the offer cannot differ between the two places it is made. It
        # did: this one labelled the ranges by who plays them ("I play
        # Legend, climbing to Ancient") and handed back the bracket
        # ABOVE what the label said, which is a control that lies.
        self.ranks = rankpick.RangePicker(current)
        self.ranks.picked.connect(self._update_summary)
        layout.addWidget(self.ranks)

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

    def _chosen(self) -> tuple[str, ...]:
        """The ranked brackets, never empty — see `RangePicker.chosen`."""
        return self.ranks.chosen

    def _update_summary(self) -> None:
        self.summary.setText(
            f"Statistics will be pulled for <b>{self.ranks.describe()}"
            "</b>.<br>Changing this rebuilds the dataset, so a data "
            "update is needed afterwards.")

    def _accept(self) -> None:
        chosen = self._chosen()
        if chosen:
            self.selected = chosen
            self.accept()

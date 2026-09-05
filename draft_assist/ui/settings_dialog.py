"""One place for the switches that used to be menu items.

"Use game data" and "Use screen capture" were mutually exclusive menu
commands, from when the two were alternatives. They are not: the game feed
says when a draft is happening and which side you are on, the screen says
what the picks are, and the app wants both. So they are tick boxes, both on
by default, and turning one off is a debugging step rather than a mode.
"""

from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QDialog,
                             QDialogButtonBox, QFrame, QLabel, QRadioButton,
                             QVBoxLayout)

from ..config import DEFAULT_PAIR_SOURCE

# Which site's matchup and synergy numbers the matrices are built from.
# Exactly one at a time, so these are radio buttons: averaging two sites'
# interaction terms would produce a figure neither site would recognise.
# value, label, explanation
PAIR_SOURCES = (
    ("stratz", "Stratz",
     "Matchups AND synergies, filtered to your bracket. What the app has "
     "always used, and the only source that fills the synergy grid."),
    ("opendota", "OpenDota",
     "Matchups only, all brackets pooled — OpenDota publishes no ally-pair "
     "data and no rank filter, so the synergy grid comes out empty and the "
     "counter numbers are not bracket-specific."),
)

# key, label, explanation
SWITCHES = (
    ("use_gsi", "Read game data from Dota (GSI)",
     "How the app knows a draft is happening, who you are and which side "
     "you are on — and it supplies both line-ups once the game starts."),
    ("use_vision", "Read the draft from the Dota window",
     "The picks themselves during hero selection. The game feed does not "
     "report them, so without this the draft has to be typed in."),
    ("auto_record", "Record every draft automatically",
     "Starts a recording when hero selection begins and stops a minute "
     "after the draft ends. Nothing to press."),
    ("overlay_enabled", "Show the draft overlay over Dota",
     "A small always-on-top badge that expands into the recommendations."),
)


class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(480)
        self.boxes = {}

        layout = QVBoxLayout(self)
        heading = QLabel("What the app reads, and what it does with it")
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        for key, label, explanation in SWITCHES:
            box = QCheckBox(label)
            box.setChecked(bool(settings.get(key, True)))
            layout.addWidget(box)
            note = QLabel(explanation)
            note.setWordWrap(True)
            note.setProperty("dim", True)
            note.setContentsMargins(22, 0, 0, 8)
            layout.addWidget(note)
            self.boxes[key] = box

        warning = QLabel(
            "With both sources off the draft can only be typed in by hand.")
        warning.setWordWrap(True)
        warning.setProperty("dim", True)
        layout.addWidget(warning)

        rule = QFrame()
        rule.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(rule)
        stats_heading = QLabel("Where the numbers come from")
        stats_heading.setProperty("heading", True)
        layout.addWidget(stats_heading)

        self.source_group = QButtonGroup(self)
        self.source_buttons = {}
        current = settings.get("pair_source", DEFAULT_PAIR_SOURCE)
        for value, label, explanation in PAIR_SOURCES:
            button = QRadioButton(label)
            button.setChecked(value == current)
            self.source_group.addButton(button)
            layout.addWidget(button)
            note = QLabel(explanation)
            note.setWordWrap(True)
            note.setProperty("dim", True)
            note.setContentsMargins(22, 0, 0, 8)
            layout.addWidget(note)
            self.source_buttons[value] = button

        rebuild = QLabel(
            "Changing this needs Data ▸ Update statistics to re-pull — the "
            "matrices are built from whichever source was chosen, not "
            "switched between at read time.")
        rebuild.setWordWrap(True)
        rebuild.setProperty("dim", True)
        layout.addWidget(rebuild)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        out = {key: box.isChecked() for key, box in self.boxes.items()}
        out["pair_source"] = self.pair_source()
        return out

    def pair_source(self) -> str:
        for value, button in self.source_buttons.items():
            if button.isChecked():
                return value
        return DEFAULT_PAIR_SOURCE

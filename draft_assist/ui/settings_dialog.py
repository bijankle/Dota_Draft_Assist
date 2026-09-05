"""One place for the switches that used to be menu items.

"Use game data" and "Use screen capture" were mutually exclusive menu
commands, from when the two were alternatives. They are not: the game feed
says when a draft is happening and which side you are on, the screen says
what the picks are, and the app wants both. So they are tick boxes, both on
by default, and turning one off is a debugging step rather than a mode.
"""

from PyQt6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QLabel,
                             QVBoxLayout)

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

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {key: box.isChecked() for key, box in self.boxes.items()}

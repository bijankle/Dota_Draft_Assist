"""One place for the switches that used to be menu items.

"Use game data" and "Use screen capture" were mutually exclusive menu
commands, from when the two were alternatives. They are not: the game feed
says when a draft is happening and which side you are on, the screen says
what the picks are, and the app wants both. So they are tick boxes, both on
by default, and turning one off is a debugging step rather than a mode.

"How many suggestions to show" is NOT here. It was, and it was wrong: a
number you tune by looking at the result belongs on the result, so it is a
small box beside each strip's heading instead.

How old the statistics may get before the app asks about it IS here, and
it is the only place their age is mentioned at all now.
"""

from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QDialog,
                             QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
                             QRadioButton, QSpinBox, QVBoxLayout)

from ..config import DEFAULT_PAIR_SOURCE
from . import settings as ui_settings

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
    ("ads_enabled", "Show ads above the draft",
     "A banner strip above the two team panels, there the whole time the "
     "app is open. Off by default, and off takes no room at all: it is a "
     "strip of the screen the app exists to show."),
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
            # `ui_settings.DEFAULTS` decides, not a `True` written here: a
            # switch that defaults on because the loop said so is a switch
            # nobody chose.
            box.setChecked(bool(settings.get(
                key, ui_settings.DEFAULTS.get(key, True))))
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

        rule2 = QFrame()
        rule2.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(rule2)
        remind_heading = QLabel("When to remind you to update")
        remind_heading.setProperty("heading", True)
        layout.addWidget(remind_heading)

        # The ONLY place the statistics' age appears now. It used to be a
        # banner, a pill and a segment of the status line, all day, for
        # something worth acting on about twice a month.
        remind = QHBoxLayout()
        remind.addWidget(QLabel("Ask me when the statistics are older than"))
        self.reminder_days = QSpinBox()
        self.reminder_days.setRange(0, ui_settings.MAX_REMINDER_DAYS)
        self.reminder_days.setSuffix(" days")
        self.reminder_days.setValue(int(settings.get(
            "data_reminder_days", ui_settings.DATA_REMINDER_DAYS)))
        remind.addWidget(self.reminder_days)
        remind.addStretch(1)
        layout.addLayout(remind)
        remind_note = QLabel(
            "One dialog when the app opens, and nothing on screen in "
            "between. Set it to 0 to never be asked.")
        remind_note.setWordWrap(True)
        remind_note.setProperty("dim", True)
        remind_note.setContentsMargins(0, 0, 0, 8)
        layout.addWidget(remind_note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        out = {key: box.isChecked() for key, box in self.boxes.items()}
        out["pair_source"] = self.pair_source()
        out["data_reminder_days"] = ui_settings.clamp_days(
            self.reminder_days.value(), ui_settings.DATA_REMINDER_DAYS)
        return out

    def pair_source(self) -> str:
        for value, button in self.source_buttons.items():
            if button.isChecked():
                return value
        return DEFAULT_PAIR_SOURCE

"""The one window everything that is not the draft now lives in.

The menu bar was Setup | Game | View | Help and most of it was things you
do ONCE — install the game config, fetch the artwork, pick your ranks —
sitting permanently across the top of a window read at a glance during a
draft. At the user's request the bar is File | View | Help and everything
out of Setup and Game is a TAB in here, "like any typical application",
with the Debug tab and the downloads among them.

**IT IS MODELESS AND IT APPLIES AS YOU GO.** Two reasons, and the second
is the one that decides it. A preferences window with OK and Cancel is
the older convention and it is fine for a page of tick boxes — but this
one holds the DEBUG VIEW, which is a live picture of what the app is
reading right now, and a live view inside a modal dialog is a live view
you cannot look at while using the thing it is showing you. And a modal
dialog would have to borrow that widget from the main window and give it
back, which is exactly the parentless-widget trap this app has been bitten
by before. So the window owns the debug pages outright, for the life of
the app, and `MainWindow._update_debug` goes on asking whether they are
VISIBLE — which they are not while this window is shut, so it costs
nothing when it is.

Actions — download this, diagnose that — are buttons that do the thing
immediately. There is nothing to apply and nothing to cancel about
pressing them, and a button that only takes effect when you press OK
afterwards is a button nobody trusts.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QFrame,
                             QHBoxLayout, QLabel, QPushButton, QRadioButton,
                             QScrollArea, QSpinBox, QTabWidget, QVBoxLayout,
                             QWidget)

from ..config import DEFAULT_PAIR_SOURCE
from . import settings as ui_settings
from .chrome import CountBox
from .settings_dialog import PAIR_SOURCES, SWITCHES


def _note(text: str, indent: int = 0) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setProperty("dim", True)
    label.setContentsMargins(indent, 0, 0, 8)
    return label


def _heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("heading", True)
    return label


def _rule() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    return line


def _scrolling(inner: QWidget) -> QScrollArea:
    """A tall page asks for NOTHING, the same rule the Debug tab taught the
    main window: a tab widget's minimum is its tallest page, so one long
    page sets the floor for the whole window whether or not it is showing.
    """
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(inner)
    return area


class GeneralPage(QWidget):
    """The switches, the statistics source and the reminder interval.

    Emits `changed` on every edit rather than waiting for an OK that no
    longer exists; the window above saves and applies.
    """

    changed = pyqtSignal()

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.boxes: dict[str, QCheckBox] = {}
        layout.addWidget(_heading("What the app reads, and what it does "
                                  "with it"))
        for key, label, explanation in SWITCHES:
            box = QCheckBox(label)
            # `ui_settings.DEFAULTS` decides, not a `True` written here: a
            # switch that defaults on because the loop said so is a switch
            # nobody chose.
            box.setChecked(bool(settings.get(
                key, ui_settings.DEFAULTS.get(key, True))))
            box.toggled.connect(self.changed)
            layout.addWidget(box)
            layout.addWidget(_note(explanation, 22))
            self.boxes[key] = box
        layout.addWidget(_note("With both sources off the draft can only "
                               "be typed in by hand."))

        layout.addWidget(_rule())
        layout.addWidget(_heading("Where the numbers come from"))
        self.source_group = QButtonGroup(self)
        self.source_buttons: dict[str, QRadioButton] = {}
        current = settings.get("pair_source", DEFAULT_PAIR_SOURCE)
        for value, label, explanation in PAIR_SOURCES:
            button = QRadioButton(label)
            button.setChecked(value == current)
            button.toggled.connect(self.changed)
            self.source_group.addButton(button)
            layout.addWidget(button)
            layout.addWidget(_note(explanation, 22))
            self.source_buttons[value] = button
        layout.addWidget(_note(
            "Changing this needs Settings ▸ Downloads ▸ Statistics and "
            "portraits to re-pull — the matrices are BUILT from whichever "
            "source was chosen, not switched between at read time."))

        layout.addWidget(_rule())
        layout.addWidget(_heading("When to remind you to update"))
        remind = QHBoxLayout()
        remind.addWidget(QLabel("Ask me when the statistics are older than"))
        # A `CountBox` rather than a bare QSpinBox: this page SCROLLS, and
        # Qt steps a spin box on every wheel notch — the trap the History
        # tab's controls were all converted for. One that was missed is
        # one trap left, and this one sat two menus deep where a silently
        # changed reminder interval would never be noticed.
        self.reminder_days = CountBox(
            int(settings.get("data_reminder_days",
                             ui_settings.DATA_REMINDER_DAYS)),
            0, ui_settings.MAX_REMINDER_DAYS)
        self.reminder_days.setSuffix(" days")
        self.reminder_days.valueChanged.connect(self.changed)
        remind.addWidget(self.reminder_days)
        remind.addStretch(1)
        layout.addLayout(remind)
        layout.addWidget(_note("One dialog when the app opens, and nothing "
                               "on screen in between. Set it to 0 to never "
                               "be asked."))

        layout.addWidget(_rule())
        layout.addWidget(_heading("Marks on the suggested picks"))
        # A SHARE OF THE STRIP, not a bar against the whole hero pool.
        #
        # These were three percentile floors - two for the heart, one for
        # the shield - and at the user's request they are two shares of
        # whatever is being suggested right now: "if I set it to 50% and
        # I have 20 suggested heroes, that means I expect to have 10
        # heroes with hearts and 10 heroes with shields."
        #
        # HIGHER IS LOOSER HERE, which is the opposite of what the bars
        # it replaces did, so the wording has to carry it: 10% marks the
        # best one in ten, 100% marks everything. The mark now also
        # carries its RANK, so the number in a heart is what a bar could
        # never say - not "this cleared a line" but "this is the best of
        # the ones you are looking at".
        hearts = QHBoxLayout()
        hearts.addWidget(QLabel("Pink heart on the best"))
        self.heart_share = CountBox(
            ui_settings.clamp_pct(settings.get("heart_share", 30), 30),
            0, 100)
        self.heart_share.setSuffix("%")
        self.heart_share.valueChanged.connect(self.changed)
        hearts.addWidget(self.heart_share)
        hearts.addWidget(QLabel("of the suggestions"))
        hearts.addStretch(1)
        layout.addLayout(hearts)
        layout.addWidget(_note(
            "Ranked on your pick rate and win rate together, from the "
            "last History run, so it follows whichever account is loaded "
            "there. The number inside the heart is the rank: 1 is the "
            "hero you play most and win most on, of the ones suggested. "
            "Heroes with fewer than two games cannot be ranked, so a "
            "thin history gives fewer marks than the share asks for."))

        shield = QHBoxLayout()
        shield.addWidget(QLabel("Gold shield on the hardest"))
        self.shield_share = CountBox(
            ui_settings.clamp_pct(settings.get("shield_share", 30), 30),
            0, 100)
        self.shield_share.setSuffix("%")
        self.shield_share.valueChanged.connect(self.changed)
        shield.addWidget(self.shield_share)
        shield.addWidget(QLabel("of the suggestions to counter"))
        shield.addStretch(1)
        layout.addLayout(shield)
        layout.addWidget(_note(
            "A property of the hero rather than of you, read out of the "
            "ranked dataset, so it appears on heroes you have never "
            "picked. The number inside is the rank: 1 is the hardest to "
            "counter of the ones suggested. Needs hero statistics "
            "downloaded; see Hero Counters in the History tab for the "
            "same figure."))
        # WHAT THE DATA BEHIND THE SHIELD IS DOING, live, under the
        # control. "No shields" has four causes and one appearance - no
        # statistics, a dataset with no matrix, nothing measured, and the
        # ordinary case - and this mark has already shipped broken once
        # looking exactly like the last of them.
        self.shield_note = _note("")
        layout.addWidget(self.shield_note)
        layout.addStretch(1)

    def values(self) -> dict:
        out = {key: box.isChecked() for key, box in self.boxes.items()}
        out["pair_source"] = self.pair_source()
        out["data_reminder_days"] = ui_settings.clamp_days(
            self.reminder_days.value(), ui_settings.DATA_REMINDER_DAYS)
        # What the box shows IS what is stored: the share of the strip
        # that gets a mark.
        out["heart_share"] = ui_settings.clamp_pct(
            self.heart_share.value(), 30)
        out["shield_share"] = ui_settings.clamp_pct(
            self.shield_share.value(), 30)
        return out

    def pair_source(self) -> str:
        for value, button in self.source_buttons.items():
            if button.isChecked():
                return value
        return DEFAULT_PAIR_SOURCE


class ActionPage(QWidget):
    """A tab that is a list of things to do, each with its reason.

    A button and a sentence saying what it will do, because these are the
    steps somebody presses once and needs to be sure about first — "which
    of these four downloads is the one I want" is the whole question.
    """

    def __init__(self, intro: str, commands, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        if intro:
            layout.addWidget(_note(intro))
        self.buttons: dict[str, QPushButton] = {}
        for command in commands:
            button = QPushButton(command.label)
            button.clicked.connect(command.run)
            layout.addWidget(button)
            if command.detail:
                layout.addWidget(_note(command.detail, 8))
            self.buttons[command.label] = button
        layout.addStretch(1)


class SettingsWindow(QDialog):
    """Tabs, modeless, applying as it goes. See the module note."""

    applied = pyqtSignal(dict)

    def set_shield_note(self, text: str) -> None:
        """What the gold shield's bar is currently doing, in a sentence.

        Pushed in by `MainWindow` rather than worked out here, because
        the window has no dataset and no business loading one: the count
        is a by-product of the recompute that already happens whenever
        the statistics or the bar change.
        """
        page = getattr(self, "general", None)
        label = getattr(page, "shield_note", None) if page else None
        if label is not None:
            label.setText(text or "")
            label.setVisible(bool(text))

    def __init__(self, settings: dict, pages, debug=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(560, 480)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.general = GeneralPage(settings)
        self.general.changed.connect(self._apply)

        self.tabs.addTab(_scrolling(self.general), "General")
        for title, intro, commands in pages:
            self.tabs.addTab(_scrolling(ActionPage(intro, commands)), title)
        # LAST, and OWNED: the debug pages are handed over for the life of
        # the app rather than borrowed per opening. Borrowing would mean
        # handing a live widget back and forth between two parents, and a
        # widget that loses its parent in this app becomes a second window
        # in the taskbar.
        if debug is not None:
            self.tabs.addTab(debug, "Debug")

    def _apply(self) -> None:
        self.applied.emit(self.general.values())

    def show_tab(self, title: str) -> None:
        """Open on a named tab — what a search result does when it points
        at a setting rather than at something to press."""
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == title:
                self.tabs.setCurrentIndex(index)
                break
        self.show()
        self.raise_()
        self.activateWindow()

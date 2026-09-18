"""The guided fix for "the app cannot find the portraits on MY screen".

At the owner's request: "if the portraits dont align on the first go the
user should be guided through the process of portrait recognition
improvements for their specific case (+ bug reports sendng)".

**WHAT THIS REPLACES IS A BUTTON THAT EITHER WORKED OR DID NOT.** The
crop-boxes banner has had one action on it — measure the boxes off the
frame in hand — and that action needs a pick bar on screen with all ten
heroes named by the game. Press it in the menus, or ten seconds after the
draft ended, and it correctly refuses; what the person is left with is a
sentence about why, and nothing to do next. Which is the same fault this
project keeps finding in its own refusals: an honest answer that is not an
answer.

So the three things that can actually fix this are on one page, in the
order they should be tried, with the one that needs no understanding
first:

    1. Measure it now, if there is a pick bar to measure.
    2. Otherwise play one draft with recording on - the app measures
       itself off the recording's own frames and saves it, which is
       `bugreport.repair` and needs nobody to press anything.
    3. Send the numbers back, so the next person with this display is
       right on their FIRST draft rather than their second.

Step 3 is the one that is not about this user at all, and it is why the
page exists rather than a better error message: a report carrying a
measured pick bar for a resolution nobody here owns is the only way
`vision/measured.py` ever grows a row. It is offered, never taken
automatically - the zip carries pictures of their own screen.

**IT NAMES THE RESOLUTION AND WHERE THE CURRENT BOXES CAME FROM.** "The
boxes are wrong" is the same sentence for a display measured directly and
for one that fell back to its aspect group, and those are different
problems with different fixes - so `measured.describe` is printed at the
top rather than left in the diagnostic paste.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QVBoxLayout, QWidget)

from . import chrome
from .setup_wizard import paragraph, steps_list

# The dialog's own text column. The wizard's width, because these two are
# the only long-form pages in the app and a reader should not have to
# re-find the measure of the text between them.
TEXT_WIDTH = 560

RECORD_STEPS = (
    "Turn Auto on (Run menu) - it is on by default, so this is usually "
    "already done.",
    "Play one draft. Bots are fine and are quicker than a queue.",
    "The app measures the boxes off that draft's own frames and saves "
    "them, with nothing to press.",
    "If it still cannot, this page raises itself again after the draft.",
)


class FixBoxesDialog(QDialog):
    """Three things to try, most automatic first.

    Every action is a CALLBACK rather than work done here. The measuring
    lives on the window (it needs the live snapshot), the repair lives in
    `bugreport`, and the report needs the mail client - none of which a
    dialog should own. What this class owns is the order they are offered
    in and what each one said.
    """

    def __init__(self, where: str, measure, report, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Find the portraits on this screen")
        self._measure, self._report = measure, report

        page = QWidget()
        body = QVBoxLayout(page)
        body.setContentsMargins(16, 16, 16, 16)
        body.setSpacing(12)

        body.addWidget(paragraph(
            "The app knows which ten heroes are in this game, and it "
            "cannot find their portraits where it expected them on your "
            "screen. That is the crop boxes being in the wrong place, "
            "not the recogniser being unlucky - so it can be measured "
            "and fixed.", TEXT_WIDTH))
        # The resolution and which of the three answers produced the
        # boxes in use. A display measured directly being wrong and a
        # display falling back to its aspect group being wrong are not
        # the same fault, and the six numbers do not say which it is.
        source = QLabel(where)
        source.setProperty("dim", True)
        source.setWordWrap(True)
        source.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        body.addWidget(source)

        body.addWidget(self._measure_card())
        body.addWidget(self._record_card())
        body.addWidget(self._report_card())
        body.addStretch(1)

        # The page scrolls and the Close button does NOT, which is the
        # setup wizard's own lesson: a button that scrolls away with the
        # content is the fault being fixed rather than a smaller version
        # of it.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(page)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        feet = QHBoxLayout()
        feet.setContentsMargins(16, 8, 16, 12)
        feet.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        feet.addWidget(close)
        outer.addLayout(feet)
        self.resize(TEXT_WIDTH + 80, 640)

    # ---- the three steps ---------------------------------------------
    def _measure_card(self) -> QWidget:
        frame, layout = chrome.card("1. Measure it from the game")
        layout.addWidget(paragraph(
            "Works while a draft is on screen, because that is when the "
            "game names the ten heroes the measurement needs. It takes "
            "a few seconds and saves the answer for this display.",
            TEXT_WIDTH))
        self.measure_note = QLabel("")
        self.measure_note.setWordWrap(True)
        self.measure_note.setProperty("dim", True)
        button = QPushButton("Measure now")
        button.setProperty("accent", True)
        button.clicked.connect(self._do_measure)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(self.measure_note)
        return frame

    def _record_card(self) -> QWidget:
        frame, layout = chrome.card("2. Or let one draft fix it")
        layout.addWidget(paragraph(
            "If there is no draft on screen right now, there is nothing "
            "to measure yet - and nothing for you to do about that.",
            TEXT_WIDTH))
        layout.addWidget(steps_list(RECORD_STEPS))
        return frame

    def _report_card(self) -> QWidget:
        frame, layout = chrome.card("3. Send the measurement back")
        layout.addWidget(paragraph(
            "This ships the numbers for your screen size so the next "
            "person with it is right on their first draft instead of "
            "their second. It opens your mail app with a zip attached - "
            "nothing is sent until you press send, and you can open the "
            "zip first. It holds a few pictures of the Dota window and "
            "the app's own numbers.", TEXT_WIDTH))
        self.report_note = QLabel("")
        self.report_note.setWordWrap(True)
        self.report_note.setProperty("dim", True)
        button = QPushButton("Send bug report")
        button.clicked.connect(self._do_report)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(self.report_note)
        return frame

    # ---- actions ------------------------------------------------------
    def _do_measure(self) -> None:
        """Say what happened either way.

        A measurement that could not be taken is the commonest outcome
        of pressing this - it needs a live pick bar - and the whole
        reason this page exists is that a refusal used to be the end of
        the road. So a failure points at step 2 rather than only naming
        itself.
        """
        try:
            note = self._measure()
        except Exception as exc:                 # never fatal: it is a note
            note = f"could not measure: {exc}"
        self.measure_note.setText(
            note or "Nothing to measure from - try step 2 below.")

    def _do_report(self) -> None:
        try:
            note = self._report()
        except Exception as exc:
            note = f"could not open your mail app: {exc}"
        self.report_note.setText(note or "")

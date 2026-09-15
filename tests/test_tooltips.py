"""The tooltip, which this app had never named.

The bug: `QToolTip` appeared nowhere in the stylesheet, so every tip in
the app was drawn by the NATIVE style — "when i mouse over these text
boxes i see a weird black callout".

Same family as the scrollbars, and it hides in the same place: the
fallback is per platform, so this machine cannot reproduce what the user
saw. Rendered here the unstyled tip comes out in Fusion's own pale yellow
with black text (wrong for a dark app, and legible); on Windows the same
omission drew a black rectangle. Neither the screenshot nor a render on
Linux says which, and the fix is the same either way.

So there are two checks, the scrollbars' pair: that the rule EXISTS,
which is the thing that decides it on every platform, and that a tip
actually rendered here comes out in this app's palette rather than
anybody else's.
"""

import os
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint                             # noqa: E402
from PyQt6.QtGui import QImage                              # noqa: E402
from PyQt6.QtWidgets import (QApplication, QToolTip,        # noqa: E402
                             QWidget)

from draft_assist.ui import theme                           # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def styled(qapp):
    was = qapp.styleSheet()
    qapp.setStyleSheet(theme.STYLESHEET)
    yield qapp
    qapp.setStyleSheet(was)


def test_the_stylesheet_names_the_tooltip_at_all(styled):
    """The half that decides it on a platform this machine cannot draw.

    A tip left unnamed is handed to whatever the native style does, and
    what that is differs per platform — which is why this is checked as a
    RULE rather than only as pixels.
    """
    assert "QToolTip" in theme.STYLESHEET
    rule = theme.STYLESHEET[theme.STYLESHEET.index("QToolTip"):]
    rule = rule[:rule.index("}")]
    # A ground, an ink and an EDGE: a tip floats over whatever is behind
    # it, so a background alone leaves it with no boundary of its own.
    for part in ("background", "color", "border", "padding"):
        assert part in rule, f"the tooltip rule says nothing about {part}"


def _tip_pixels(app, text="Nought is off.\nSeveral set means all of them."):
    host = QWidget()
    host.resize(400, 200)
    host.show()
    app.processEvents()
    QToolTip.showText(QPoint(10, 10), text, host)
    app.processEvents()
    tips = [w for w in app.topLevelWidgets()
            if "Tip" in w.metaObject().className()]
    assert tips, "no tooltip widget was created"
    tip = tips[0]
    picture = QImage(tip.size(), QImage.Format.Format_ARGB32)
    picture.fill(0)
    tip.render(picture)
    counts = Counter(picture.pixelColor(x, y).name()
                     for y in range(picture.height())
                     for x in range(picture.width()))
    QToolTip.hideText()
    host.close()
    app.processEvents()
    return counts


def test_a_tooltip_is_drawn_in_this_apps_palette(styled):
    """And the other half, against the pixels: the ground is the app's
    darkest surface, the words are the app's text, and the edge is the
    app's border."""
    counts = _tip_pixels(styled)
    ground, _n = counts.most_common(1)[0]
    assert ground == theme.BG_DEEP, (
        f"a tooltip is drawn on {ground}, not on this app's own surface")
    assert theme.TEXT in counts, "the tip has no text in this app's ink"
    assert theme.BORDER in counts, "the tip has no edge of its own"


def test_nothing_native_is_left_in_it(styled):
    """The pale yellow Fusion draws, and the black Windows drew, are both
    the same fault — a tip nobody named. Neither may survive."""
    counts = _tip_pixels(styled)
    assert "#ffffdc" not in counts, "Fusion's own tooltip ground is showing"
    # Pure black is the Windows symptom: an unpainted tip window.
    assert counts.get("#000000", 0) < sum(counts.values()) * 0.02, (
        "the tip is mostly black, which is what was reported")

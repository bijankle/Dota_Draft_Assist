"""The painted frame.

It cannot be compared against a reference image — the point is that the
artwork it was asked to look like is Blizzard's and is NOT in this
repository — so what is checked is that it draws, that it draws INTO the
band and not over the content, and that it survives being small.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRectF                            # noqa: E402
from PyQt6.QtGui import QColor, QPainter, QPixmap          # noqa: E402
from PyQt6.QtWidgets import QApplication                   # noqa: E402

from draft_assist.ui import ornate                         # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def framed(width: int, height: int, band: int = ornate.WIDTH) -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("#101215"))
    painter = QPainter(pixmap)
    ornate.paint_frame(painter, QRectF(pixmap.rect()), band)
    painter.end()
    return pixmap


def test_it_draws_a_band_and_leaves_the_middle_alone(qapp):
    image = framed(300, 200).toImage()
    edge = QColor(image.pixel(1, 40))
    middle = QColor(image.pixel(150, 40))
    assert edge.red() > edge.blue(), "the band should read as warm metal"
    assert middle.name() != edge.name(), "it painted over the content"


def test_the_content_area_is_exactly_the_inset(qapp):
    """The shell layout is inset by WIDTH, so anything the frame draws
    inside that is drawn over the app."""
    band = ornate.WIDTH
    image = framed(300, 200, band).toImage()
    inside = QColor(image.pixel(band + 3, 100))
    assert inside.red() <= inside.blue() + 8, \
        "metal is showing inside the content area"


def test_it_survives_being_small(qapp):
    """Detail that reads at 40px and turns to mush at 8 is worse than no
    detail, so the same three shapes have to work at both."""
    for band in (4, 8, ornate.WIDTH, 20):
        assert not framed(160, 120, band).isNull()


def test_it_is_a_hairline_with_no_ornament_on_it(qapp):
    """It started as ten pixels of band with amethyst stones on it and read
    as jewellery round a tool. A frame's job here is to give a frameless
    always-on-top window an edge against whatever is behind it; past a few
    pixels it competes with the draft instead."""
    assert ornate.WIDTH <= 3
    image = framed(400, 300).toImage()
    for y in range(6, 294, 7):
        band = QColor(image.pixel(1, y))
        assert band.red() >= band.blue(), \
            f"something purple at y={y}: the studs are meant to be gone"

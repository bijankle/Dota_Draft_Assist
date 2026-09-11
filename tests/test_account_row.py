"""Whose history the numbers are for: the picture, and the row drawing it.

The avatar is the first image this app fetches that is neither Valve's nor
its own, so the guards matter: only Steam's CDN is fetched, it happens
once per run rather than per repaint, and every way it can fail draws the
fallback rather than raising.
"""

import os
from datetime import datetime
from pathlib import Path

import pytest

# BEFORE Qt is imported, the way every other Qt test file in here does it:
# there is no display in this container, and a QApplication without one
# ABORTS the process rather than raising, so no `except` would catch it.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication                       # noqa: E402

from draft_assist.history import avatars, cache, opendota
from draft_assist.history.report import Options

STEAM = "https://avatars.steamstatic.com/abc_full.jpg"


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


class Fake:
    """A report, as far as the row is concerned."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def a_report(window="6m", name="Bijson", account=195286385, n=575):
    return Fake(options=Options(account_id=account, window=window),
                name=name, matches=[1] * n,
                ran_at=datetime(2026, 9, 11, 14, 30))


# ---------------------------------------------------------- the disk ----

def test_the_picture_is_fetched_once_and_then_read_off_disk(tmp_path):
    """The row that draws it repaints with the draft, four times a second.
    Anything that fetched per draw would be the live loop on the network."""
    calls = []

    def fetch(url):
        calls.append(url)
        return b"PNGDATA"

    first = avatars.ensure(7, STEAM, fetch=fetch, where=tmp_path)
    assert first is not None and first.read_bytes() == b"PNGDATA"
    avatars.ensure(7, STEAM, fetch=fetch, where=tmp_path)
    assert len(calls) == 1, "an unchanged avatar must cost no request"
    assert avatars.stored(7, tmp_path) is not None


def test_a_changed_avatar_is_noticed_and_an_unreachable_one_is_survived(
        tmp_path):
    calls = []
    avatars.ensure(7, STEAM, fetch=lambda u: calls.append(u) or b"OLD",
                   where=tmp_path)
    avatars.ensure(7, STEAM.replace("abc", "xyz"),
                   fetch=lambda u: calls.append(u) or b"NEW", where=tmp_path)
    assert len(calls) == 2
    assert avatars.stored(7, tmp_path).read_bytes() == b"NEW"
    # A download that fails keeps what was already there rather than
    # blanking a face that was drawing perfectly well.
    kept = avatars.ensure(7, STEAM.replace("abc", "gone"),
                          fetch=lambda u: b"", where=tmp_path)
    assert kept is not None and kept.read_bytes() == b"NEW"


def test_only_steams_own_cdn_is_ever_fetched():
    """The URL arrives inside somebody's OpenDota profile, so it is not
    this app's string — a run must not be talked into fetching an
    arbitrary host by a field in a response."""
    assert opendota.avatar_bytes("https://example.com/evil.png") == b""
    assert opendota.avatar_bytes("http://avatars.steamstatic.com/x") == b""
    assert opendota.avatar_bytes("") == b""
    assert opendota.avatar_bytes(None) == b""


def test_the_avatar_folder_is_not_a_run_and_is_never_pruned(tmp_path):
    """`cache.run_files` globs the top level for runs. The avatars live in
    a SUBDIRECTORY, so the prune cannot reach them."""
    avatars.save(7, b"PNGDATA", STEAM, where=tmp_path)
    (tmp_path / "111.json").write_text("{}", encoding="utf-8")
    assert [p.name for p in cache.run_files(tmp_path)] == ["111.json"]


def test_the_url_comes_off_the_profile_row(monkeypatch):
    """It is in the SAME response the display name already comes from, so
    learning it costs no extra request — which is the whole reason the
    picture is affordable at all."""
    monkeypatch.setattr(opendota, "_get", lambda *a, **k: {
        "profile": {"personaname": "Bijson", "avatarfull": STEAM}})
    got = opendota.profile(195286385)
    assert got.name == "Bijson" and got.known is True
    assert got.avatar == STEAM

    # A profile with no picture is not a failure: "" reaches `ensure`,
    # which then keeps whatever is on disk rather than blanking it.
    monkeypatch.setattr(opendota, "_get", lambda *a, **k: {
        "profile": {"personaname": "Bijson"}})
    assert opendota.profile(195286385).avatar == ""

    # And an account OpenDota has never seen has no avatar to report.
    monkeypatch.setattr(opendota, "_get", lambda *a, **k: {})
    blank = opendota.profile(1)
    assert blank.known is False and blank.avatar == ""


# ----------------------------------------------------------- the row ----

def test_the_row_prompts_before_anything_has_been_measured(qapp):
    """Always shown, at the user's request — so before a run it has to say
    what to do rather than sit blank."""
    from draft_assist.ui.accountrow import AccountRow, NOTHING_YET
    row = AccountRow()
    row.show_report(None)
    assert row.who.text() == NOTHING_YET
    assert "History" in row.when.text()
    row.deleteLater()


@pytest.mark.parametrize("window,expected_start,expected_span", [
    ("1m", "12 Aug 2026", "(1 month)"),
    ("3m", "12 Jun 2026", "(3 months)"),
    ("12m", "11 Sep 2025", "(12 months)")])
def test_the_range_is_the_runs_own_window(qapp, window, expected_start,
                                          expected_span):
    """The History window is a DROPDOWN, so a fixed three months would
    have the row describing data that was never measured.

    AND HOW LONG IT IS, in brackets: two bare dates make the reader do
    the subtraction, on a row whose whole job is to be read at a glance.
    """
    from draft_assist.ui.accountrow import AccountRow
    row = AccountRow()
    row.show_report(a_report(window=window))
    assert row.who.text() == "Bijson"
    text = row.when.text()
    assert text.startswith(expected_start)
    assert "11 Sep 2026" in text, "the run's own date is the end"
    assert text.endswith(expected_span)
    row.deleteLater()


def test_the_row_is_one_line_with_a_PAINTED_rule(qapp):
    """"Picture - steam name | from date --> to date", at the user's
    request. The rule is a widget rather than a typed "|": a pipe in a
    label resizes with the font and cannot be coloured apart from the text
    holding it, which is why every other rule in this app is painted.

    Checked against the PIXELS, because "it is in the stylesheet" has
    twice not meant "it is on the screen" in this codebase.
    """
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QColor, QImage, QPainter, QRegion
    from PyQt6.QtWidgets import QWidget
    from draft_assist.ui import theme
    from draft_assist.ui.accountrow import FACE, PADDING, AccountRow

    row = AccountRow()
    row.resize(700, FACE + 2 * PADDING)
    row.show_report(a_report(window="3m"))
    # FORCED, because Qt defers layout: measuring straight after a resize
    # reads the geometry from before it, which is every widget at x=0.
    # The same trap `_hold_still` documents one axis over.
    row.layout().activate()

    # One line: everything sits inside the height the face needs, so the
    # name and the dates share a row rather than stacking.
    assert row.sizeHint().height() == FACE + 2 * PADDING
    assert row.who.y() < row.rule.y() + row.rule.height()
    assert row.when.x() > row.rule.x(), "dates follow the rule"
    assert "|" not in row.who.text() and "|" not in row.when.text()

    shot = QImage(700, row.height(), QImage.Format.Format_ARGB32)
    shot.fill(0)
    painter = QPainter(shot)
    row.render(painter, QPoint(), QRegion(row.rect()),
               QWidget.RenderFlag.DrawChildren)
    painter.end()

    want = QColor(theme.RULE)
    inside = [x for x in range(row.rule.x(), row.rule.x() + row.rule.width())
              for y in range(row.height())
              if QColor.fromRgba(shot.pixel(x, y)).alpha() > 0
              and abs(QColor(shot.pixel(x, y)).red() - want.red()) < 24]
    assert inside, "the rule between the name and the dates drew nothing"
    row.deleteLater()


def test_all_history_has_no_start_to_print_and_says_so(qapp):
    from draft_assist.ui.accountrow import AccountRow
    row = AccountRow()
    row.show_report(a_report(window="all"))
    assert row.when.text().startswith("All history")
    row.deleteLater()


def test_an_account_with_no_resolved_name_is_just_its_number(qapp):
    from draft_assist.ui.accountrow import AccountRow
    row = AccountRow()
    row.show_report(a_report(name=""))
    assert row.who.text() == "195286385"
    assert row.face._initial == "1"
    row.deleteLater()


def test_a_picture_on_disk_is_drawn_and_a_bad_one_falls_back(qapp, tmp_path,
                                                             monkeypatch):
    """Four causes, one appearance — no file, a file that will not decode,
    an account with no avatar, and a failed download all draw the initial
    rather than raising."""
    from PyQt6.QtGui import QColor, QPixmap
    from draft_assist.ui.accountrow import AccountRow
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)

    art = QPixmap(184, 184)
    art.fill(QColor("#4488cc"))
    source = tmp_path / "src.png"
    art.save(str(source), "PNG")
    avatars.save(195286385, source.read_bytes(), STEAM)

    row = AccountRow()
    row.show_report(a_report())
    assert row.face._pixmap is not None, "the real picture must be drawn"

    # A file that will not decode is the same as no file.
    (tmp_path / "avatars" / "999.img").write_bytes(b"not an image")
    row.show_report(a_report(account=999, name="Zed"))
    assert row.face._pixmap is None and row.face._initial == "Z"
    row.deleteLater()


def test_the_face_is_clipped_to_a_circle(qapp, tmp_path):
    """Checked against the PIXELS rather than the arithmetic, the way the
    grid borders are: a clip that silently stopped working would draw a
    square avatar and no assertion about the code would notice."""
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap, QRegion
    from PyQt6.QtWidgets import QWidget
    from draft_assist.ui.accountrow import FACE, Face

    art = QPixmap(184, 184)
    art.fill(QColor("#4488cc"))
    source = tmp_path / "a.png"
    art.save(str(source), "PNG")

    face = Face()
    assert face.show_file(source) is True
    shot = QImage(FACE, FACE, QImage.Format.Format_ARGB32)
    shot.fill(0)
    painter = QPainter(shot)
    face.render(painter, QPoint(), QRegion(face.rect()),
                QWidget.RenderFlag.DrawChildren)
    painter.end()

    assert QColor(shot.pixel(FACE // 2, FACE // 2)).name() == "#4488cc"
    assert QColor.fromRgba(shot.pixel(1, 1)).alpha() == 0, "corner clipped"
    face.deleteLater()

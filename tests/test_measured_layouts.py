"""The shipped per-display table, and the three levels that read it.

What these hold is the PROPERTY rather than the numbers: a row somebody
pastes in tomorrow must not be able to break the fallback, and the
fallback must not be able to overrule a measurement.
"""

import numpy as np
import pytest

from draft_assist.vision import measured
from draft_assist.vision.layout import DraftLayout, hud_box, load_layout

# The real method, lifted off the class so these can exercise it
# without constructing a MainWindow — which aborts the process here
# rather than failing, and whose Qt machinery none of this needs.
def _sync_method():
    """`MainWindow._sync_layout_spec`, read off the class.

    Importing `draft_assist.ui.app` pulls in Qt but constructs nothing,
    which is the line this file does not cross.
    """
    from draft_assist.ui.app import MainWindow
    return MainWindow._sync_layout_spec


def test_every_display_shape_has_an_answer():
    """A gap here is a fresh install with no boxes at all."""
    for width, height in [(800, 600), (1024, 768), (1280, 1024), (1366, 768),
                          (1440, 900), (1600, 1200), (1920, 1080),
                          (1920, 1200), (2560, 1440), (3440, 1440),
                          (3840, 2160), (5120, 1440)]:
        group = measured.group_for(width, height)
        assert group in measured.GROUPS, f"{width}x{height} fell between groups"


def test_the_groups_do_not_overlap():
    for aspect in [0.5, 1.25, 1.33, 1.6, 16 / 9, 1.9, 2.4, 3.6]:
        covering = [g for g in measured.GROUPS if g.covers(aspect)]
        assert len(covering) == 1, f"aspect {aspect} is in {len(covering)} groups"


def test_the_step_is_at_sixteen_by_nine():
    """The measured split, and the reason there is more than one group.

    16:10 has since been measured apart from 4:3/5:4 and has a band of
    its own, so the assertion here is that 16:9 is still where the WIDE
    step falls - not that everything below it is one shape.
    """
    assert measured.group_for(1920, 1080) is measured.WIDE
    assert measured.group_for(3440, 1440) is measured.WIDE
    assert measured.group_for(1920, 1200) is not measured.WIDE
    assert measured.group_for(1024, 768) is measured.TALL


def test_the_bar_widths_match_what_was_measured():
    """0.780-0.791 against 0.889-0.898, from the screenshot sweep.

    This is the whole evidence for splitting the table in two, so it is
    held against the bands rather than against the numbers that were
    typed in — retuning a fraction is fine, retuning it out of its own
    measurement is the bug.
    """
    bands = {measured.WIDE: (0.780, 0.791), measured.TALL: (0.889, 0.898),
             # 16:10 belongs to the NARROW family by its bar width - it
             # was split out of `TALL` on `slot_h` alone, and this is the
             # corroboration: the horizontal step is still at 16:9.
             measured.SIXTEEN_TEN: (0.889, 0.900)}
    for group, (low, high) in bands.items():
        layout = group.reading.layout()
        span = layout.dire_x + layout.bank_span() - layout.radiant_x
        assert low <= span <= high, f"{group.label} bar spans {span:.4f}"


def test_the_left_bank_is_the_mirror_of_the_right():
    """`radiant_x` is derived, and a hand-set one would silently drift."""
    for group in measured.GROUPS:
        r = group.reading
        layout = r.layout()
        middle_left = layout.radiant_x + layout.bank_span() / 2
        middle_right = layout.dire_x + layout.bank_span() / 2
        assert abs((middle_left + middle_right) / 2 - 0.5) < 1e-6


def test_a_bank_never_runs_off_the_hud_box():
    for width, height in [(800, 600), (1920, 1080), (3440, 1440)]:
        layout = measured.layout_for(width, height)
        _left, span = hud_box(width, height)
        assert layout.radiant_x > 0
        assert layout.dire_x + layout.bank_span() <= 1.0
        for slot in layout.slots():
            x, y, w, h = slot.to_pixels(width, height)
            assert x >= 0 and y >= 0
            assert x + w <= width, f"{slot.team}{slot.slot} off {width}x{height}"
            assert y + h <= height
        assert span > 0


def test_the_two_banks_never_overlap():
    for width, height in [(1024, 768), (1920, 1080), (3440, 1440)]:
        layout = measured.layout_for(width, height)
        assert layout.radiant_x + layout.bank_span() < layout.dire_x


def test_an_exact_row_beats_its_group(monkeypatch):
    row = measured.Reading(dire_x=0.4, y=0.1, slot_w=0.05, slot_h=0.05,
                           pitch=0.06, source="a test")
    monkeypatch.setattr(measured, "EXACT", {(1920, 1080): row})
    assert measured.reading_for(1920, 1080) is row
    # and only for that one resolution
    assert measured.reading_for(2560, 1440) is measured.WIDE.reading


def test_every_shipped_row_names_where_it_came_from():
    """A number with no provenance is one nobody can ever check."""
    readings = [g.reading for g in measured.GROUPS] + list(
        measured.EXACT.values())
    for reading in readings:
        assert reading.source.strip(), "a reading with no source"
        assert reading.frames >= 1


def test_no_shipped_row_merely_repeats_its_group():
    """An EXACT row that equals its group claims a measurement nobody took."""
    for (width, height), reading in measured.EXACT.items():
        group = measured.group_for(width, height)
        assert reading != group.reading, (
            f"{width}x{height} repeats \"{group.label}\" — delete the row "
            "rather than restating the fallback")


def test_describe_says_which_of_the_answers_was_used():
    assert "no row for" in measured.describe(1920, 1080)
    assert "no frame yet" in measured.describe(0, 0)


def test_load_layout_without_a_size_is_unchanged(tmp_path):
    """Every tool and test with no frame in hand keeps the old behaviour."""
    assert load_layout(calibration_file=tmp_path / "nope.json") == DraftLayout()


def test_load_layout_with_a_size_uses_the_table(tmp_path):
    got = load_layout(1920, 1080, calibration_file=tmp_path / "nope.json")
    assert got == measured.layout_for(1920, 1080)
    assert got != DraftLayout()


def test_a_calibration_file_beats_the_table(tmp_path):
    """This machine's own measurement is an answer; the table is a guess."""
    path = tmp_path / "calibration_local.json"
    path.write_text('{"y": 0.4242}', encoding="utf-8")
    got = load_layout(1920, 1080, calibration_file=path)
    assert got.y == pytest.approx(0.4242)


class _Stub:
    """The little of CaptureSession these tests reach."""

    def __init__(self):
        from draft_assist.capture.session import CaptureSession
        self.session = CaptureSession.__new__(CaptureSession)
        self.session.layout = DraftLayout()
        self.session._sized_for = (0, 0)
        self.session.layout_is_measured = False
        self.session.state = type("S", (), {"last_read": "x",
                                            "last_read_raw": "x"})()
        self.session._stabilizer = type("B", (), {"reset": lambda self: None})()


def _frame(width, height):
    return np.zeros((height, width, 3), dtype=np.uint8)


def test_the_session_fits_its_boxes_to_the_first_frame():
    session = _Stub().session
    assert session.fit_to_frame(_frame(1920, 1080)) is True
    assert session.layout == measured.layout_for(1920, 1080)
    # and does not keep re-fitting the same size
    assert session.fit_to_frame(_frame(1920, 1080)) is False


def test_the_session_refits_when_the_display_changes_shape():
    session = _Stub().session
    session.fit_to_frame(_frame(1920, 1080))
    assert session.fit_to_frame(_frame(1280, 1024)) is True
    assert session.layout == measured.layout_for(1280, 1024)


def test_a_measured_layout_is_never_replaced_by_the_table():
    """Without this the tick after a successful autocal throws it away."""
    session = _Stub().session
    mine = DraftLayout(y=0.4242)
    session.adopt_measured(mine)
    assert session.fit_to_frame(_frame(1920, 1080)) is False
    assert session.layout is mine


def test_fitting_survives_a_frame_with_no_shape():
    session = _Stub().session
    assert session.fit_to_frame(None) is False
    assert session.fit_to_frame(object()) is False
    assert session.fit_to_frame(_frame(0, 0) if False else np.zeros((0, 0, 3))) is False


class _Spin:
    """The little of a QDoubleSpinBox `_sync_layout_spec` touches."""

    def __init__(self, value):
        self._value, self.blocked, self.sets = value, [], 0

    def value(self):
        return self._value

    def setValue(self, value):
        self._value, self.sets = value, self.sets + 1

    def blockSignals(self, on):
        self.blocked.append(on)


class _Window:
    """`MainWindow._sync_layout_spec` and nothing else.

    Deliberately NOT a real MainWindow: building one here aborts the
    process rather than failing, which is the Qt trap this project keeps
    a list of, and the method under test touches exactly three
    attributes.
    """

    _sync_layout_spec = _sync_method()

    def __init__(self, session, spins=None):
        self.provider = type("P", (), {"session": session})()
        self.layout_spec = session.layout
        self.cal_spins = spins or {}


def test_the_window_reports_the_layout_it_is_actually_using():
    """A diagnostic naming numbers the recogniser stopped using is the
    one thing a diagnostic may never do."""
    session = _Stub().session
    window = _Window(session)
    fitted = measured.layout_for(1280, 1024)
    session.layout = fitted
    window._sync_layout_spec()
    assert window.layout_spec is fitted


def test_syncing_moves_the_spin_boxes_without_firing_them():
    """Unblocked, they would fire `_set_calibration`, which latches the
    layout as MEASURED — and it would never re-fit again."""
    session = _Stub().session
    spins = {"y": _Spin(session.layout.y)}
    window = _Window(session, spins)
    session.layout = measured.layout_for(1280, 1024)
    window._sync_layout_spec()
    assert spins["y"].value() == session.layout.y
    assert spins["y"].blocked == [True, False]
    assert session.layout_is_measured is False


def test_syncing_an_unchanged_layout_touches_nothing():
    """It runs four times a second; an identity check is the whole cost."""
    session = _Stub().session
    spins = {"y": _Spin(session.layout.y)}
    window = _Window(session, spins)
    window._sync_layout_spec()
    assert spins["y"].sets == 0
    assert spins["y"].blocked == []


def test_sixteen_ten_is_its_own_shape():
    """A 16:10 laptop read ONE hero of ten, and `slot_h` was the whole of
    it: 84px boxes over 98px portraits, on a matcher that reads 0.99 at
    the true size and 0.12 four pixels out."""
    for width, height in [(1920, 1200), (2560, 1600), (2880, 1800)]:
        assert measured.group_for(width, height) is measured.SIXTEEN_TEN
    # and the shapes either side of it are untouched
    assert measured.group_for(1920, 1080) is measured.WIDE
    assert measured.group_for(3440, 1440) is measured.WIDE
    assert measured.group_for(1280, 1024) is measured.TALL
    assert measured.group_for(1024, 768) is measured.TALL


def test_the_two_bot_drafts_behind_the_16_10_group_land_in_it():
    """What each machine actually measured, against what it is now
    served. The worst miss was 13.9px on `slot_h` and has to be under a
    pixel, or this group is not worth the risk of a third band."""
    from draft_assist.vision.layout import hud_box
    drafts = {
        (1920, 1200): dict(dire_x=0.5938, y=0.0058, slot_w=0.0682,
                           slot_h=0.0617, pitch=0.0719),
        (2560, 1600): dict(dire_x=0.5938, y=0.0056, slot_w=0.0676,
                           slot_h=0.0612, pitch=0.0719),
    }
    for (width, height), got in drafts.items():
        _, span = hud_box(width, height)
        served = measured.layout_for(width, height)
        for name, value in got.items():
            # the horizontal fractions are of the HUD span, the vertical
            # of the window - the one asymmetry this file carries
            denominator = span if name in ("dire_x", "slot_w",
                                           "pitch") else height
            out_by = abs(getattr(served, name) - value) * denominator
            assert out_by < 1.0, (
                f"{width}x{height} {name} is {out_by:.2f}px out")


def test_no_group_leaves_a_shape_without_an_answer():
    """Half-open bands, so every aspect there can be falls in exactly
    one - a gap is a fresh install with no answer at all, which is the
    state this file exists to end."""
    aspect = 0.5
    while aspect < 4.0:
        covering = [g for g in measured.GROUPS if g.covers(aspect)]
        assert len(covering) == 1, f"aspect {aspect:.3f}: {covering}"
        aspect += 0.01


def test_the_narrow_groups_do_not_move_what_was_already_measured():
    """Splitting 16:10 out of `TALL` must not touch 4:3, 5:4, or 16:9 and
    wider - adding a level may only ever make one shape better."""
    assert measured.TALL.reading.slot_h == 0.0525
    assert measured.WIDE.reading.slot_h == 0.0611
    assert measured.layout_for(1280, 1024).slot_h == 0.0488   # its own row
    assert measured.layout_for(1024, 768).slot_h == 0.0525
    assert measured.layout_for(1920, 1080).slot_h == 0.0611


def test_every_group_covers_the_frames_it_was_measured_from():
    """A group that does not answer for its own evidence is a group
    serving somebody else's numbers.

    1360x768 is 1.77083 against 16:9's 1.77778, so an exact boundary put
    one of `WIDE`'s own two screenshots on the NARROW side - taking
    `dire_x` 0.5926 against its measured 0.5708, a 31-pixel miss, for as
    long as this table has existed.
    """
    evidence = {
        measured.WIDE: [(1360, 768), (1920, 1080), (3440, 1440)],
        measured.SIXTEEN_TEN: [(1920, 1200), (2560, 1600)],
        measured.TALL: [(800, 600), (1024, 768), (1280, 1024),
                        (1600, 1200)],
    }
    for group, sizes in evidence.items():
        for width, height in sizes:
            assert measured.group_for(width, height) is group, (
                f"{width}x{height} is named in \"{group.label}\"'s source "
                f"but falls in \"{measured.group_for(width, height).label}\"")


def test_the_wide_tolerance_cannot_swallow_sixteen_ten():
    """The slack is for panels sold as 16:9, not a licence to widen the
    measured step - 16:10 sits 0.18 away and must stay its own shape."""
    assert measured.HUD_ASPECT - measured.NEARLY_WIDE == pytest.approx(0.01)
    assert measured.group_for(1920, 1200) is measured.SIXTEEN_TEN
    assert measured.SIXTEEN_TEN.high == measured.NEARLY_WIDE

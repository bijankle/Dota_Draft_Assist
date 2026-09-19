"""The captured buffer is the WINDOW; every fraction is of the CLIENT.

Measured on three displays from three real recordings, the frame came
back exactly nine pixels wider and thirty-two taller than the resolution
Dota was running at. Counting those pixels divides every fraction by a
number 2% too big AND, on two of the three, moves the display into the
wrong aspect group of the shipped table - which is a wrong geometry on a
fresh install.
"""

import numpy as np
import pytest

from draft_assist.capture.session import CaptureSession
from draft_assist.vision import measured
from draft_assist.vision.layout import DraftLayout
from draft_assist.vision.recognize import RecognitionParams

# resolution -> what the capture actually handed us, from the recordings
REAL_PADDING = {
    (1366, 768): (1375, 800),
    (1920, 1080): (1929, 1112),
    (3440, 1440): (3449, 1472),
}


def session_at(client, monkeypatch):
    """A session bound to a window whose client area is `client`."""
    session = CaptureSession(DraftLayout(), {}, RecognitionParams(8, 0.30, 0.04))
    session.capture_title = "Dota 2"
    monkeypatch.setattr(session, "_measure_client", lambda: client)
    return session


def frame(width, height):
    return np.zeros((height, width, 3), dtype=np.uint8)


@pytest.mark.parametrize("client,captured", sorted(REAL_PADDING.items()))
def test_the_padding_is_cropped_away(client, captured, monkeypatch):
    session = session_at(client, monkeypatch)
    out = session._crop_to_client(frame(*captured))
    assert (out.shape[1], out.shape[0]) == client


def test_the_content_is_taken_from_the_top_left(monkeypatch):
    """The pick bar measured 4 to 8 pixels down in every recording, so
    there is no title bar above the content - the padding is on the
    right and the bottom."""
    session = session_at((4, 3), monkeypatch)
    raw = np.arange(5 * 4, dtype=np.uint8).reshape(4, 5)
    out = session._crop_to_client(raw)
    assert np.array_equal(out, raw[:3, :4])


def test_an_unpadded_frame_is_handed_back_unchanged(monkeypatch):
    session = session_at((1920, 1080), monkeypatch)
    raw = frame(1920, 1080)
    assert session._crop_to_client(raw) is raw


def test_nothing_is_cropped_when_the_client_cannot_be_measured(monkeypatch):
    """Off Windows, or with the window gone. A frame we cannot measure
    beats no frame at all."""
    session = session_at(None, monkeypatch)
    raw = frame(1929, 1112)
    assert session._crop_to_client(raw) is raw


def test_a_client_far_smaller_than_the_buffer_is_refused(monkeypatch):
    """That is not window chrome, it is the wrong window - and cropping
    to it would throw away most of the picture."""
    session = session_at((640, 480), monkeypatch)
    raw = frame(1929, 1112)
    assert session._crop_to_client(raw) is raw


def test_a_client_bigger_than_the_buffer_is_refused(monkeypatch):
    session = session_at((3440, 1440), monkeypatch)
    raw = frame(1929, 1112)
    assert session._crop_to_client(raw) is raw


def test_the_client_is_measured_again_when_the_window_is_resized(monkeypatch):
    session = session_at((1920, 1080), monkeypatch)
    asked = []

    def measure():
        asked.append(True)
        return (1920, 1080)

    monkeypatch.setattr(session, "_measure_client", measure)
    session._crop_to_client(frame(1929, 1112))
    session._crop_to_client(frame(1929, 1112))
    assert len(asked) == 1, "same size: asked once"
    session._crop_to_client(frame(1375, 800))
    assert len(asked) == 2, "a new size re-asks"


def test_a_measurement_that_raises_is_not_fatal(monkeypatch):
    session = CaptureSession(DraftLayout(), {}, RecognitionParams(8, 0.30, 0.04))
    session.capture_title = "Dota 2"
    monkeypatch.setattr(
        "draft_assist.capture.window.client_size",
        lambda _t: (_ for _ in ()).throw(OSError("no window")))
    raw = frame(1929, 1112)
    assert session._crop_to_client(raw) is raw


@pytest.mark.parametrize("client,captured", sorted(REAL_PADDING.items()))
def test_the_padding_moved_two_of_them_into_the_wrong_group(client, captured):
    """The reason this is a bug rather than a rounding error. 1366x768 is
    16:9 and 1375x800 is not, so the table handed back the fractions for
    a narrower display than the one being played on."""
    right = measured.group_for(*client)
    wrong = measured.group_for(*captured)
    if client == (3440, 1440):
        assert right.label == wrong.label, "ultrawide stays in its group"
    else:
        assert right.label != wrong.label, (
            f"{client} and {captured} should land in different groups")


def test_tick_crops_before_anything_reads_the_size(monkeypatch):
    """`fit_to_frame` keys the shipped table on the frame's size, so a
    padded buffer reaching it is the wrong row of the table."""
    session = session_at((1920, 1080), monkeypatch)
    session.inject_frame(frame(1929, 1112))
    session.tick()
    assert session.state.last_frame is not None
    got = session.state.last_frame
    assert (got.shape[1], got.shape[0]) == (1920, 1080)

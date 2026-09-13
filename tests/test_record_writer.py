"""Frames are encoded off the refresh loop.

`cv2.imwrite` of a 3440x1440 frame measures at ~120ms, and the loop runs
four times a second — so every saved frame stalled the draft window for
most of a tick, and three separate sessions' timing tables flagged
`recording` as slow. Measured after: ~20ms on the loop, which is the
frame copy the worker has to be given.

It is the same rule this class already had, one step further: a failed
write must never take the draft window down, and a SLOW one must never
hold it up.
"""

import sys
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from draft_assist import record


@pytest.fixture()
def recorder(tmp_path):
    rec = record.Recorder(root=tmp_path / "recordings")
    rec.start()
    yield rec
    rec.stop("test over")


def frame(width=320, height=180):
    return np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)


def written(rec):
    return sorted((rec.root).glob("*/frames/*.png"))


def test_every_frame_reaches_the_disk(recorder):
    for _ in range(5):
        recorder.save_frame(frame())
    recorder._flush_frames()
    assert len(written(recorder)) == 5
    assert recorder.frames == 5
    assert recorder._dropped == 0


def test_the_numbering_has_no_holes(recorder):
    for _ in range(4):
        recorder.save_frame(frame())
    recorder._flush_frames()
    names = [p.name for p in written(recorder)]
    assert names == ["00001.png", "00002.png", "00003.png", "00004.png"]


def test_the_worker_is_handed_a_COPY(recorder):
    """The capture session overwrites its buffer, so a view would be a
    different picture by the time the worker reached it — the same
    reason the line-up search is given a copy of its frame."""
    import cv2
    first = np.zeros((180, 320, 3), np.uint8)
    recorder.save_frame(first)
    first[:] = 255                      # as capture would, next tick
    recorder._flush_frames()
    saved = cv2.imread(str(written(recorder)[0]))
    assert saved is not None
    assert saved.max() == 0, "the worker wrote the overwritten buffer"


def test_a_frame_is_DROPPED_rather_than_waited_for(recorder, monkeypatch):
    """Frames are evidence about recognition, and evidence is worth less
    than the thing it is evidence about. A full queue must not block the
    draft window."""
    import queue as queue_mod
    recorder._ensure_writer()

    def full(_item):
        raise queue_mod.Full
    monkeypatch.setattr(recorder._queue, "put_nowait", full)
    started = time.perf_counter()
    assert recorder.save_frame(frame()) is None
    assert time.perf_counter() - started < 0.05, "it waited"
    assert recorder._dropped == 1
    assert recorder.frames == 0, "a dropped frame is not a saved frame"


def test_stopping_flushes_before_it_writes_the_count(recorder):
    """`meta.json` must describe what is ON DISK, not what was queued."""
    import json
    for _ in range(3):
        recorder.save_frame(frame())
    folder = recorder.stop("done")
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["frames"] == len(sorted((folder / "frames").glob("*.png")))
    assert meta["frames_dropped"] == 0


def test_the_worker_survives_a_flush_clearing_the_queue(recorder):
    """It used to read `self._queue` from inside the thread, which raced
    with `_flush_frames` clearing it: the worker died on
    `None.task_done()` and took the rest of the session's frames with
    it, silently, on a daemon thread nobody was watching."""
    recorder.save_frame(frame())
    recorder._flush_frames()
    recorder.save_frame(frame())        # starts a fresh writer
    recorder._flush_frames()
    assert len(written(recorder)) == 2
    assert recorder._errors == []


def test_a_write_that_fails_is_recorded_and_not_raised(recorder,
                                                       monkeypatch):
    import cv2
    monkeypatch.setattr(cv2, "imwrite",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("full")))
    recorder.save_frame(frame())
    recorder._flush_frames()
    assert any("full" in note for note in recorder._errors)

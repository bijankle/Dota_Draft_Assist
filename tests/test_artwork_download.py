"""The artwork is fetched in parallel, and one failure costs one picture.

**WHY IT WAS SLOW**, at the user's request — "loading in all of the hero
portraits, item portraits, etc is very slow". 127 portraits and ~484
item icons, fetched ONE AT A TIME, each a bare `requests.get` and so a
fresh TCP and TLS handshake, with a courtesy `sleep` between them. The
sleeps alone were `127*0.1 + 484*0.05` — over half a minute of a run
doing nothing at all — and the rest was round trips, not bytes: an item
icon is a few kilobytes.

Nothing about WHERE the pictures come from changed, and nothing about
what is committed: they are Valve's artwork, downloaded to the user's
own disk at runtime, exactly as before.
"""

import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import build_library                                # noqa: E402


class FakeResponse:
    def __init__(self, content=b"\x89PNG-ish", status=200):
        self.content, self.status = content, status

    def raise_for_status(self):
        if self.status >= 400:
            import requests
            raise requests.HTTPError(f"{self.status}")


def test_the_pictures_are_fetched_in_parallel(monkeypatch, tmp_path):
    """Serial, this is the round trips added up. The test holds the
    SHAPE — several in the air at once — rather than a wall-clock
    figure, which would be a flaky test about somebody's CI machine."""
    at_once, most = 0, 0
    lock = threading.Lock()

    def slow_get(self, url, timeout=None):
        nonlocal at_once, most
        with lock:
            at_once += 1
            most = max(most, at_once)
        time.sleep(0.05)
        with lock:
            at_once -= 1
        return FakeResponse()

    monkeypatch.setattr(build_library.requests.Session, "get", slow_get)
    jobs = [(f"http://example/{n}.png", tmp_path / f"{n}.png", f"item {n}")
            for n in range(24)]
    done, failed = build_library.fetch_many(jobs, "items")
    assert (done, failed) == (24, [])
    assert most > 1, "the downloads ran one at a time"
    assert most <= build_library.WORKERS


def test_one_failure_costs_one_picture_and_says_which(monkeypatch, tmp_path):
    """An item without a picture falls back to its name; losing the
    whole build over one 404 would be absurd. That rule predates this
    and had to survive being made parallel — a raise inside a worker is
    swallowed by the pool unless somebody reads the result."""
    def get(self, url, timeout=None):
        return FakeResponse(status=404 if "bad" in url else 200)

    monkeypatch.setattr(build_library.requests.Session, "get", get)
    jobs = [("http://example/good.png", tmp_path / "good.png", "item 'Good'"),
            ("http://example/bad.png", tmp_path / "bad.png", "item 'Bad'")]
    done, failed = build_library.fetch_many(jobs, "items")
    assert done == 1
    assert (tmp_path / "good.png").exists()
    assert not (tmp_path / "bad.png").exists(), "a failure left a file"
    assert len(failed) == 1 and "item 'Bad'" in failed[0]


def test_a_half_written_picture_is_never_left_behind(monkeypatch, tmp_path):
    """Every caller SKIPS a file that already exists, so a picture cut
    off half way — a run closed mid-download, a disk that filled — is
    skipped for ever after and draws as a blank tile. That is one of the
    four causes `item_icons.why_missing` exists to tell apart, and the
    only one the download itself can prevent."""
    def dies(self, url, timeout=None):
        raise OSError("connection reset half way")

    monkeypatch.setattr(build_library.requests.Session, "get", dies)
    dest = tmp_path / "icon.png"
    why = build_library.fetch_one("http://example/icon.png", dest)
    assert why and not dest.exists()
    assert list(tmp_path.iterdir()) == [], "a .part file was left behind"


def test_the_finished_file_appears_whole_or_not_at_all(monkeypatch, tmp_path):
    """The rename is what makes that true: the name a reader checks for
    never exists holding a fraction of a picture."""
    seen = []

    def get(self, url, timeout=None):
        seen.append(sorted(f.name for f in tmp_path.iterdir()))
        return FakeResponse(b"whole picture")

    monkeypatch.setattr(build_library.requests.Session, "get", get)
    dest = tmp_path / "icon.png"
    assert build_library.fetch_one("http://example/icon.png", dest) == ""
    assert dest.read_bytes() == b"whole picture"
    assert seen == [[]], "something was on disk before the download"


def test_each_worker_keeps_its_own_session(monkeypatch):
    """A `requests.Session` is not thread-safe, and it is also what
    keeps the connection open for the fifty or so files one worker
    fetches — so one per thread is both halves of the point."""
    seen, lock = [], threading.Lock()
    # HELD OPEN while they are compared: a thread that has finished
    # releases its thread-local, and the NEXT thread can be handed the
    # same ident and the same memory — so four sessions collected one
    # after another can genuinely be one object four times over, and the
    # test would have been measuring the garbage collector.
    running = threading.Barrier(4)

    def note():
        mine = build_library.session()
        with lock:
            seen.append(mine)
        running.wait(timeout=5)

    threads = [threading.Thread(target=note) for _ in range(4)]
    for one in threads:
        one.start()
    for one in threads:
        one.join()
    assert len(seen) == 4
    assert len({id(s) for s in seen}) == 4, "a Session was shared"
    # …and the same thread asking twice gets the same one back.
    assert build_library.session() is build_library.session()


def test_the_bar_moves_while_the_pictures_arrive(monkeypatch, tmp_path, capsys):
    """These run behind a progress dialog, and before this they printed
    nothing between "484 items listed" and the final count — minutes of
    a bar that says the app has frozen."""
    monkeypatch.setattr(build_library.requests.Session, "get",
                        lambda self, url, timeout=None: FakeResponse())
    jobs = [(f"http://example/{n}.png", tmp_path / f"{n}.png", str(n))
            for n in range(10)]
    build_library.fetch_many(jobs, "items", share=lambda part: 0.2 + part * 0.8)
    lines = [ln for ln in capsys.readouterr().out.splitlines()
             if ln.startswith("PROGRESS")]
    assert len(lines) == 10, lines
    shares = [int(ln.split()[1].rstrip("%")) for ln in lines]
    assert shares == sorted(shares), "the bar went backwards"
    assert shares[0] >= 20 and shares[-1] == 100


def test_every_marked_progress_line_is_one_the_dialog_can_read():
    """`task_dialog.PERCENT` matches `^PROGRESS n%` and nothing else, so
    a line it cannot parse is a bar that stops moving. The two tools
    that had their own copy of this had already drifted — one clamped
    the share and the other did not, so overshooting printed
    `PROGRESS 120%` and the dialog refused the line outright."""
    from draft_assist import console
    from draft_assist.ui.task_dialog import PERCENT
    import io
    import contextlib

    for share in (-3.0, 0.0, 0.5, 1.0, 4.2):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            console.progress(share, "doing a thing")
        got = PERCENT.match(out.getvalue().strip())
        assert got, out.getvalue()
        assert 0 <= int(got.group(1)) <= 100


def test_the_two_tools_do_not_carry_their_own_spelling():
    """One implementation, because two had already drifted."""
    for name in ("find_portraits.py", "score_recording.py"):
        body = (ROOT / "tools" / name).read_text(encoding="utf-8")
        assert "console.progress(" in body, name
        assert 'print(f"{STEP}' not in body, name

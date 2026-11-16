"""A dataset built before the main-effect fix must not survive an update.

The fix is applied when the matrices are BUILT, and a build happens about
twice a month while the app updates itself from `main` whenever the owner
presses the button. So a copy that takes the fix still holds the previous
version's matrices - and pressing Update and seeing Techies still at +63
is this project's own standing fault: an empty update is indistinguishable
from a broken one.
"""

import numpy as np

from draft_assist.data import normalize, store


def built_by_the_old_version(tmp_path, points=0.07):
    """A cache carrying exactly the fault: one hero's row offset."""
    n = 12
    vs = np.zeros((n, n))
    with_ = np.zeros((n, n))
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 0.005, (n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            off = (points if i == 0 else 0.0) - (points if j == 0 else 0.0)
            vs[i, j] = off + (noise[i, j] - noise[j, i]) / 2
            with_[i, j] = ((points if i == 0 else 0.0)
                           + (points if j == 0 else 0.0)
                           + (noise[i, j] + noise[j, i]) / 2)
    np.fill_diagonal(vs, 0)
    np.fill_diagonal(with_, 0)
    ds = store.Dataset(
        hero_ids=list(range(n)),
        index={h: h for h in range(n)},
        heroes={h: {"name": f"Hero {h}"} for h in range(n)},
        baseline=np.full(n, 0.5), picks=np.full(n, 5000, dtype=np.int64),
        delta_vs=vs.astype(np.float32), delta_with=with_.astype(np.float32),
        meta={"pulled_at": 0.0, "target_brackets": ["ANCIENT"]},
    )
    store.save(ds)
    return ds


def net(ds, hero):
    """One ally's nine terms, the way the board sums them."""
    i = ds.index[hero]
    allies = [h for h in (1, 2, 3, 4) if h != hero]
    enemies = [5, 6, 7, 8, 9]
    total = sum(float(ds.delta_with[i, ds.index[a]]) for a in allies)
    total += sum(float(ds.delta_vs[i, ds.index[e]]) for e in enemies)
    return total * 100


def test_the_cache_really_does_carry_the_fault(tmp_path, monkeypatch):
    """THE PREMISE: read the saved arrays directly, past `load`."""
    monkeypatch.setattr(store, "MATRIX_FILE", tmp_path / "dataset.npz")
    monkeypatch.setattr(store, "META_FILE", tmp_path / "meta.json")
    monkeypatch.setattr(store, "DATA_CACHE", tmp_path)
    ds = built_by_the_old_version(tmp_path)
    assert net(ds, 0) > 55


def test_loading_it_takes_the_offset_back_out(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "MATRIX_FILE", tmp_path / "dataset.npz")
    monkeypatch.setattr(store, "META_FILE", tmp_path / "meta.json")
    monkeypatch.setattr(store, "DATA_CACHE", tmp_path)
    built_by_the_old_version(tmp_path)
    back = store.load(tmp_path / "dataset.npz")
    assert abs(net(back, 0)) < 2.0
    for honest in (1, 2, 3):
        assert abs(net(back, honest)) < 2.0


def test_it_is_idempotent_so_a_current_cache_is_untouched():
    """A freshly built dataset must come back off disk unchanged - this
    runs on every load, so a correction that crept would drift the
    matrices a little further every time the app opened."""
    rng = np.random.default_rng(3)
    raw = rng.normal(0, 0.02, (30, 30))
    vs, with_ = (raw - raw.T) / 2, (raw + raw.T) / 2
    np.fill_diagonal(vs, 0)
    np.fill_diagonal(with_, 0)
    once = normalize.recentre(vs, with_)
    twice = normalize.recentre(*once)
    for a, b in zip(once, twice):
        assert np.abs(a - b).max() < 1e-7


def test_a_pair_with_no_data_is_still_zero_after_a_reload():
    vs = np.zeros((8, 8))
    with_ = np.zeros((8, 8))
    for i in range(8):
        for j in range(8):
            if i == j or {i, j} == {0, 1}:
                continue
            vs[i, j] = 0.01 if i < j else -0.01
            with_[i, j] = 0.02
    out_vs, out_with = normalize.recentre(vs, with_)
    assert out_vs[0, 1] == 0.0 and out_vs[1, 0] == 0.0
    assert out_with[0, 1] == 0.0 and out_with[1, 0] == 0.0


def test_the_load_names_the_hero_the_baseline_was_wrong_about(
        tmp_path, monkeypatch):
    """The answer to "but why techies specifically" has to be readable on
    the owner's own machine: the development environment cannot reach
    the statistics at all."""
    monkeypatch.setattr(store, "MATRIX_FILE", tmp_path / "dataset.npz")
    monkeypatch.setattr(store, "META_FILE", tmp_path / "meta.json")
    monkeypatch.setattr(store, "DATA_CACHE", tmp_path)
    built_by_the_old_version(tmp_path, points=0.07)
    back = store.load(tmp_path / "dataset.npz")
    skew = back.meta["baseline_skew_now"]
    assert skew, "the load corrected a 7-point offset and said nothing"
    assert skew[0]["hero"] == "Hero 0"
    assert skew[0]["points"] > 5.0


def test_a_healthy_cache_names_nobody(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "MATRIX_FILE", tmp_path / "dataset.npz")
    monkeypatch.setattr(store, "META_FILE", tmp_path / "meta.json")
    monkeypatch.setattr(store, "DATA_CACHE", tmp_path)
    built_by_the_old_version(tmp_path, points=0.0)
    back = store.load(tmp_path / "dataset.npz")
    assert back.meta["baseline_skew_now"] == []

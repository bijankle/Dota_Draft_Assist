import numpy as np
import pytest

from draft_assist.data.store import Dataset
from draft_assist.model import scoring


def fake_dataset() -> Dataset:
    # 4 heroes with sparse ids, hand-set deltas.
    hero_ids = [1, 5, 9, 12]
    index = {hid: i for i, hid in enumerate(hero_ids)}
    heroes = {hid: {"name": f"Hero{hid}"} for hid in hero_ids}
    baseline = np.array([0.50, 0.52, 0.48, 0.55])
    d_vs = np.zeros((4, 4))
    # Hero1 strong vs Hero9 (+0.04); antisymmetric partner set accordingly.
    d_vs[0, 2], d_vs[2, 0] = 0.04, -0.04
    # Hero12 weak vs Hero5 (-0.03).
    d_vs[3, 1], d_vs[1, 3] = -0.03, 0.03
    d_with = np.zeros((4, 4))
    # Hero1 synergises with Hero5 (+0.02), symmetric.
    d_with[0, 1] = d_with[1, 0] = 0.02
    return Dataset(hero_ids=hero_ids, index=index, heroes=heroes,
                   baseline=baseline, picks=np.full(4, 10_000),
                   delta_vs=d_vs, delta_with=d_with,
                   meta={"pulled_at": 0})


def test_score_composition():
    ds = fake_dataset()
    # Ally Hero5, enemy Hero9; candidates are Hero1 and Hero12.
    draft = scoring.DraftState(allies=[5], enemies=[9])
    ranked = scoring.score_all(ds, draft)
    by_id = {s.hero_id: s for s in ranked}
    assert set(by_id) == {1, 12}
    # Hero1: 0.50 baseline + 0.04 vs Hero9 + 0.02 with Hero5 = 0.56.
    assert by_id[1].score == pytest.approx(0.56)
    assert by_id[1].vs_total == pytest.approx(0.04)
    assert by_id[1].with_total == pytest.approx(0.02)
    # Hero12: 0.55 baseline + 0 + 0 = 0.55.
    assert by_id[12].score == pytest.approx(0.55)
    assert ranked[0].hero_id == 1  # sorted descending


def test_drafted_heroes_excluded():
    ds = fake_dataset()
    ranked = scoring.score_all(ds, scoring.DraftState(allies=[1], enemies=[5]))
    assert {s.hero_id for s in ranked} == {9, 12}


def test_unknown_slots_do_not_poison_scoring():
    # Unknown slots are legitimate: scoring uses only resolved slots, so a
    # draft with unknowns equals a smaller draft, never an error.
    ds = fake_dataset()
    draft = scoring.DraftState(enemies=[9], unknown_slots=3)
    ranked = scoring.score_all(ds, draft)
    by_id = {s.hero_id: s for s in ranked}
    assert by_id[1].score == pytest.approx(0.54)  # baseline + vs only


def test_breakdown_terms_match_score():
    ds = fake_dataset()
    draft = scoring.DraftState(allies=[5], enemies=[9])
    terms = scoring.breakdown(ds, 1, draft)
    assert {(t.other_id, t.kind) for t in terms} == {(9, "vs"), (5, "with")}
    total = sum(t.delta for t in terms)
    by_id = {s.hero_id: s for s in scoring.score_all(ds, draft)}
    assert by_id[1].score == pytest.approx(by_id[1].baseline + total)


def test_counters_column_view():
    ds = fake_dataset()
    counters = scoring.counters_to(ds, 9)
    assert counters[0][0] == 1 and counters[0][2] == pytest.approx(0.04)
    # Excluding drafted heroes works.
    counters = scoring.counters_to(ds, 9, exclude={1})
    assert all(hid != 1 for hid, _, _ in counters)

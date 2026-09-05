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


def test_score_is_draft_fit_with_no_win_rate_in_it():
    """The score answers "what does this draft do to this hero", not "is
    this hero good" — a baseline term floats the strong heroes to the top
    of every list regardless of the draft."""
    ds = fake_dataset()
    # Ally Hero5, enemy Hero9; candidates are Hero1 and Hero12.
    draft = scoring.DraftState(allies=[5], enemies=[9])
    ranked = scoring.score_all(ds, draft)
    by_id = {s.hero_id: s for s in ranked}
    assert set(by_id) == {1, 12}
    # Hero1: 0.04 vs Hero9 + 0.02 with Hero5, and nothing else.
    assert by_id[1].score == pytest.approx(0.06)
    assert by_id[1].vs_total == pytest.approx(0.04)
    assert by_id[1].with_total == pytest.approx(0.02)
    # Hero12 interacts with neither, so this draft does nothing to it —
    # even though its 0.55 baseline is the best of the four.
    assert by_id[12].score == pytest.approx(0.0)
    assert by_id[12].baseline == pytest.approx(0.55)
    assert ranked[0].hero_id == 1  # sorted descending


def test_the_baseline_is_still_reported_just_never_scored():
    """The cost of dropping it is that a weak hero with good matchups now
    outranks a strong one with neutral matchups, so the figure has to stay
    readable somewhere."""
    ds = fake_dataset()
    ranked = scoring.score_all(ds, scoring.DraftState())
    assert all(s.score == pytest.approx(0.0) for s in ranked)
    assert {s.hero_id: round(s.baseline, 2) for s in ranked} == {
        1: 0.50, 5: 0.52, 9: 0.48, 12: 0.55}


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
    assert by_id[1].score == pytest.approx(0.04)  # the vs term alone


def test_breakdown_terms_match_score():
    ds = fake_dataset()
    draft = scoring.DraftState(allies=[5], enemies=[9])
    terms = scoring.breakdown(ds, 1, draft)
    assert {(t.other_id, t.kind) for t in terms} == {(9, "vs"), (5, "with")}
    total = sum(t.delta for t in terms)
    by_id = {s.hero_id: s for s in scoring.score_all(ds, draft)}
    assert by_id[1].score == pytest.approx(total)


def test_counters_column_view():
    ds = fake_dataset()
    counters = scoring.counters_to(ds, 9)
    assert counters[0][0] == 1 and counters[0][2] == pytest.approx(0.04)
    # Excluding drafted heroes works.
    counters = scoring.counters_to(ds, 9, exclude={1})
    assert all(hid != 1 for hid, _, _ in counters)


# ---- one hero against the other nine ------------------------------------

def test_relations_to_an_ally_covers_both_teams():
    """Clicking an ally asks two questions at once: synergy with the rest
    of your team, matchup against all of theirs."""
    ds = fake_dataset()
    draft = scoring.DraftState(allies=[1, 5], enemies=[9])
    rels = {(r.hero_id, r.kind): r.delta
            for r in scoring.relations_to(ds, 1, draft)}
    assert set(rels) == {(5, "with"), (9, "vs")}
    assert rels[(5, "with")] == pytest.approx(
        float(ds.delta_with[ds.index[1], ds.index[5]]))
    assert rels[(9, "vs")] == pytest.approx(
        float(ds.delta_vs[ds.index[1], ds.index[9]]))


def test_relations_to_an_enemy_stay_on_our_side_of_the_board():
    """Their pair-ups with each other are their synergy, not ours — the
    view says nothing about them."""
    ds = fake_dataset()
    draft = scoring.DraftState(allies=[1, 5], enemies=[9, 12])
    rels = scoring.relations_to(ds, 9, draft)
    assert {r.hero_id for r in rels} == {1, 5}
    assert all(r.kind == "vs" for r in rels)


def test_every_relation_reads_positive_as_good_for_you():
    """Green under an enemy portrait has to mean the same thing as green
    under an ally's, or the overlay teaches the wrong reflex."""
    ds = fake_dataset()
    draft = scoring.DraftState(allies=[1, 5], enemies=[9])
    from_ally = scoring.relations_to(ds, 1, draft)
    from_enemy = scoring.relations_to(ds, 9, draft)
    ally_vs_enemy = next(r.delta for r in from_ally if r.hero_id == 9)
    enemy_vs_ally = next(r.delta for r in from_enemy if r.hero_id == 1)
    assert ally_vs_enemy == pytest.approx(enemy_vs_ally)


def test_net_contributions_sum_the_right_halves():
    ds = fake_dataset()
    draft = scoring.DraftState(allies=[1, 5], enemies=[9, 12])
    net = scoring.net_contributions(ds, draft)
    assert set(net) == {1, 5, 9, 12}
    expected_ally = (float(ds.delta_with[ds.index[1], ds.index[5]])
                     + float(ds.delta_vs[ds.index[1], ds.index[9]])
                     + float(ds.delta_vs[ds.index[1], ds.index[12]]))
    assert net[1] == pytest.approx(expected_ally)
    expected_enemy = (float(ds.delta_vs[ds.index[1], ds.index[9]])
                      + float(ds.delta_vs[ds.index[5], ds.index[9]]))
    assert net[9] == pytest.approx(expected_enemy)


def test_relations_to_a_hero_not_in_the_data_are_empty_not_a_crash():
    ds = fake_dataset()
    draft = scoring.DraftState(allies=[1], enemies=[9])
    assert scoring.relations_to(ds, 99999, draft) == []


def test_an_enemys_net_figure_counts_their_synergy_against_you():
    """A hero that combos with their line-up is worth more to them than its
    matchups alone say, and the whole view is read from your side — so the
    synergy term comes in with the sign flipped."""
    ds = fake_dataset()
    # Hero1 and Hero5 synergise (+0.02) and are both on the enemy side.
    draft = scoring.DraftState(allies=[9], enemies=[1, 5])
    net = scoring.net_contributions(ds, draft)
    matchup_only = float(ds.delta_vs[ds.index[9], ds.index[1]])
    assert net[1] == pytest.approx(
        matchup_only - float(ds.delta_with[ds.index[1], ds.index[5]]))
    assert net[1] < matchup_only        # their combo is our problem


def test_matrix_margins_sum_what_is_drawn():
    ds = fake_dataset()
    draft = scoring.DraftState(allies=[1, 5], enemies=[9, 12])
    m = scoring.matchup_matrix(ds, draft)
    assert m.row_totals == [pytest.approx(sum(line)) for line in m.cells]
    assert m.col_totals[0] == pytest.approx(m.cells[0][0] + m.cells[1][0])
    assert m.total == pytest.approx(sum(sum(line) for line in m.cells))


def test_synergy_margins_are_partial_by_construction():
    """Only the upper triangle is filled, so the last row's total and the
    first column's are both zero — every pair still counted exactly once in
    the grand total."""
    ds = fake_dataset()
    draft = scoring.DraftState(allies=[1, 5, 9])
    m = scoring.synergy_matrix(ds, draft)
    assert m.row_totals[-1] == 0.0
    assert m.col_totals[0] == 0.0
    assert m.total == pytest.approx(sum(m.row_totals))
    assert m.total == pytest.approx(sum(m.col_totals))

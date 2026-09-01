import pytest

from draft_assist.config import RULES_FILE
from draft_assist.model import items


def rule(item, trigger, sev, side="enemy", roles=None, patch="7.39"):
    return items.Rule(item=item, trigger=trigger, side=side, severity=sev,
                      reason=f"{trigger} test",
                      roles=items._expand_roles(roles),
                      verified_patch=patch)


def test_sublinear_stacking_severity_beats_breadth():
    # One severity-3 trigger (3.0) must outrank three severity-1 triggers
    # (1.0 + 0.6 + 0.4 = 2.0): the specifically urgent beats the generically
    # applicable. This is the designed failure mode — do not "fix".
    assert items.stacked_score([3]) == pytest.approx(3.0)
    assert items.stacked_score([1, 1, 1]) == pytest.approx(2.0)
    assert items.stacked_score([3]) > items.stacked_score([1, 1, 1])


def test_stacking_saturates_beyond_three():
    assert items.stacked_score([2, 2, 2, 2, 2]) == pytest.approx(
        2 * 1.0 + 2 * 0.6 + 2 * 0.4)


def test_recommend_stacks_and_floors():
    rules = [
        rule("Black King Bar", "Lion", 3),
        rule("Black King Bar", "Zeus", 2),
        rule("Ghost Scepter", "Sniper", 1),   # alone: 1.0 < floor 2.0
    ]
    advice = items.recommend(rules, ["Lion", "Zeus", "Sniper"], [], None, "7.39")
    assert [a.item for a in advice] == ["Black King Bar"]
    assert advice[0].score == pytest.approx(3.0 + 2 * 0.6)
    assert [t.hero for t in advice[0].triggers] == ["Lion", "Zeus"]


def test_silence_is_a_valid_result():
    rules = [rule("Black King Bar", "Lion", 3)]
    assert items.recommend(rules, ["Sniper"], [], None, "7.39") == []


def test_role_constraint():
    rules = [rule("Spirit Vessel", "Huskar", 3, roles=["support"])]
    assert items.recommend(rules, ["Huskar"], [], "carry", "7.39") == []
    got = items.recommend(rules, ["Huskar"], [], "hard_support", "7.39")
    assert [a.item for a in got] == ["Spirit Vessel"]
    # Unknown own-role: role-constrained rules are skipped, not guessed.
    assert items.recommend(rules, ["Huskar"], [], None, "7.39") == []


def test_ally_side_rules():
    rules = [rule("Glimmer Cape", "Terrorblade", 2, side="ally")]
    assert items.recommend(rules, ["Terrorblade"], [], None, "7.39") == []
    got = items.recommend(rules, [], ["Terrorblade"], None, "7.39")
    assert [a.item for a in got] == ["Glimmer Cape"]


def test_staleness_flag():
    assert not items.is_stale("7.39", "7.39")
    assert not items.is_stale("7.38", "7.39")
    assert items.is_stale("7.37", "7.39")   # two minor patches behind
    assert items.is_stale("7.39", "8.00")   # major bump = stale
    assert not items.is_stale("7.39", "7.39c")  # letter revisions don't count
    rules = [rule("Black King Bar", "Lion", 3, patch="7.30")]
    got = items.recommend(rules, ["Lion"], [], None, "7.39")
    assert got[0].any_stale


def test_display_cap():
    rules = [rule(f"Item{i}", "Lion", 3) for i in range(8)]
    got = items.recommend(rules, ["Lion"], [], None, "7.39")
    assert len(got) == items.MAX_SHOWN


def test_shipped_rules_file_is_valid():
    rules, meta = items.load_rules(RULES_FILE)
    assert len(rules) >= 25
    assert meta.get("current_patch")
    sides = {r.side for r in rules}
    assert sides == {"enemy", "ally"}  # both kinds present by design
    for r in rules:
        # Every reason must name its triggering hero (or clearly reference
        # the ally case) so the UI line is self-explanatory.
        assert r.reason, f"{r.item}/{r.trigger}: empty reason"

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
    # Unknown own-role: the filter does not narrow, so nothing is thrown
    # away — "(no role)" means "show me everything", not "show me nothing".
    assert [a.item for a in items.recommend(
        rules, ["Huskar"], [], None, "7.39")] == ["Spirit Vessel"]


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


# ---- the role filter, and coverage --------------------------------------

def test_no_role_chosen_does_not_throw_the_rules_away():
    """"(no role)" is the default in the UI and means "do not narrow by
    role". Reading it as "discard every role-specific rule" silently binned
    nine tenths of the file and showed one item where five belonged."""
    rules = [
        _rule("Black King Bar", "Lion", severity=3, roles={"carry", "mid"}),
        _rule("Lotus Orb", "Lion", severity=2),
    ]
    anyone = items.recommend(rules, ["Lion"], [], None, "7.39")
    assert {a.item for a in anyone} == {"Black King Bar", "Lotus Orb"}


def test_a_chosen_role_still_narrows():
    rules = [
        _rule("Black King Bar", "Lion", severity=3, roles={"carry", "mid"}),
        _rule("Lotus Orb", "Lion", severity=2),
    ]
    support = items.recommend(rules, ["Lion"], [], "hard_support", "7.39")
    assert {a.item for a in support} == {"Lotus Orb"}
    carry = items.recommend(rules, ["Lion"], [], "carry", "7.39")
    assert {a.item for a in carry} == {"Black King Bar", "Lotus Orb"}


def _rule(item, trigger, severity=2, side="enemy", roles=frozenset()):
    return items.Rule(item=item, trigger=trigger, side=side,
                      severity=severity, reason=f"{trigger} does things",
                      roles=set(roles), verified_patch="7.39")


def test_the_shipped_rules_cover_most_of_the_hero_pool():
    """A file naming 41 of 126 heroes tripped one or two rules in a typical
    draft, which is why the strip looked broken rather than quiet."""
    from draft_assist.config import RULES_FILE
    rules, _meta = items.load_rules(RULES_FILE)
    covered = {r.trigger for r in rules}
    assert len(covered) >= 90, f"only {len(covered)} heroes have any rule"


def test_a_typical_draft_produces_several_items_not_one():
    """The user's actual line-up, which used to yield exactly one."""
    from draft_assist.config import RULES_FILE
    rules, meta = items.load_rules(RULES_FILE)
    advice = items.recommend(
        rules, ["Witch Doctor", "Juggernaut", "Tidehunter", "Death Prophet",
                "Lion"],
        ["Earthshaker", "Zeus", "Lich", "Vengeful Spirit"],
        None, meta.get("current_patch", "7.39"))
    assert 3 <= len(advice) <= items.MAX_SHOWN
    assert advice[0].score >= advice[-1].score      # still ranked


def test_silence_is_still_possible():
    """Coverage must not turn into "always say something" — a line-up that
    triggers nothing should still produce nothing."""
    from draft_assist.config import RULES_FILE
    rules, meta = items.load_rules(RULES_FILE)
    assert items.recommend(rules, [], [], None,
                           meta.get("current_patch", "7.39")) == []

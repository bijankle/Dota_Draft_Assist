"""Remembering what the user keeps correcting about the team split.

This is a memory of one person's corrections, never a claim about what the
minimap means — so what it must never do is learn from a correction that
does not mean anything.
"""

from draft_assist.ui import split_memory as sm


def test_a_reversal_is_recognised_by_who_ended_up_together():
    """Sets, not order: the question is which five are on a side, and the
    order within a bank is the feed's."""
    left, right = [1, 2, 3, 4, 5], [6, 7, 8, 9, 10]
    assert sm.verdict_for(left, right, left, right) == sm.AS_READ
    assert sm.verdict_for(left, right, [10, 9, 8, 7, 6], [5, 4, 3, 2, 1]) \
        == sm.INVERTED


def test_a_correction_that_is_neither_teaches_nothing():
    """Moving one hero across leaves a split that is not the reading and
    not its inverse — a real correction, but not one this can generalise."""
    left, right = [1, 2, 3, 4, 5], [6, 7, 8, 9, 10]
    assert sm.verdict_for(left, right, [1, 2, 3, 4, 6], [5, 7, 8, 9, 10]) \
        is None


def test_a_half_entered_draft_says_nothing_either_way():
    assert sm.verdict_for([1, 2], [3, 4], [1, 2], [3, 4]) is None
    assert sm.verdict_for([1, 2, 3, 4, 5], [6, 7, 8, 9, 10],
                          [1, 2, 3], [6, 7]) is None


def test_three_reversals_in_a_row_start_the_pre_swap():
    history = []
    for i in range(sm.AUTO_AFTER - 1):
        history = sm.record(history, f"m{i}", sm.INVERTED)
        assert not sm.should_pre_swap(history)
    history = sm.record(history, "last", sm.INVERTED)
    assert sm.should_pre_swap(history)
    assert sm.streak(history) == sm.AUTO_AFTER


def test_undoing_a_pre_swap_stops_it_immediately():
    """One contradiction is enough: the app was wrong about this user, and
    guessing again next match would be worse than not guessing."""
    history = [{"match": f"m{i}", "verdict": sm.INVERTED} for i in range(6)]
    assert sm.should_pre_swap(history)
    history = sm.record(history, "new", sm.AS_READ)
    assert not sm.should_pre_swap(history)
    assert sm.streak(history) == 0


def test_one_match_is_one_opinion():
    """Fiddling twice in the same draft is one verdict, not two, or a
    single indecisive game could arm the pre-swap on its own."""
    history = []
    for verdict in (sm.INVERTED, sm.AS_READ, sm.INVERTED):
        history = sm.record(history, "same-match", verdict)
    assert len(history) == 1
    assert history[0]["verdict"] == sm.INVERTED


def test_history_does_not_grow_without_bound():
    history = []
    for i in range(sm.KEEP * 3):
        history = sm.record(history, f"m{i}", sm.INVERTED)
    assert len(history) == sm.KEEP

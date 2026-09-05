"""What the user keeps having to correct about which five heroes are theirs.

The minimap names all ten heroes at strategy time but not, reliably, whose
five are whose (see CLAUDE.md — five recorded matches, no rule found, one
came out inverted). So the app guesses and offers a correction. If the same
correction is made every match, making it every match by hand is the app
failing to notice something the user has already told it five times.

This records ONLY explicit corrections, and only the verdict a correction
implies: `INVERTED` when the user ended up with exactly the two sides the
reading gave, swapped; `AS_READ` when they undid a correction the app had
pre-applied. It is a memory of what this user keeps doing, not a claim about
what the minimap means — the rule in CLAUDE.md stays unsolved, `sides_certain`
stays False, and the swap control never goes away.

One verdict per match id, because a user fiddling twice in one draft is one
opinion, not two.
"""

INVERTED = "inverted"
AS_READ = "as_read"

# How many corrections, all pointing the same way and with nothing since
# contradicting them, before the app starts pre-applying the swap. Three is
# the smallest run that is not plausibly coincidence, and the cost of being
# wrong is one click on a control that is already on screen.
AUTO_AFTER = 3
KEEP = 20


def record(history: list[dict], match_id: str, verdict: str) -> list[dict]:
    """Append (or replace) this match's verdict, newest last."""
    if verdict not in (INVERTED, AS_READ):
        return history
    out = [h for h in history if h.get("match") != match_id or not match_id]
    out.append({"match": match_id, "verdict": verdict})
    return out[-KEEP:]


def should_pre_swap(history: list[dict]) -> bool:
    """True once the last AUTO_AFTER verdicts are all 'inverted'."""
    recent = [h.get("verdict") for h in history[-AUTO_AFTER:]]
    return len(recent) == AUTO_AFTER and all(v == INVERTED for v in recent)


def streak(history: list[dict]) -> int:
    """How many corrections in a row now say the reading comes out
    inverted — what the UI says out loud before acting on it."""
    count = 0
    for entry in reversed(history):
        if entry.get("verdict") != INVERTED:
            break
        count += 1
    return count


def verdict_for(raw_left: list[int], raw_right: list[int],
                allies: list[int], enemies: list[int]) -> str | None:
    """What the user's corrected split says about the raw reading.

    Compared as SETS and only when both sides are full: the question is
    which five heroes ended up together, not what order they sit in, and a
    half-entered draft says nothing either way. Anything that is neither the
    reading nor its exact inverse is a correction this cannot learn from,
    and returns None rather than a guess.
    """
    left, right = set(raw_left), set(raw_right)
    mine, theirs = set(allies), set(enemies)
    if len(left) != 5 or len(right) != 5 or len(mine) != 5:
        return None
    if mine == left and theirs == right:
        return AS_READ
    if mine == right and theirs == left:
        return INVERTED
    return None

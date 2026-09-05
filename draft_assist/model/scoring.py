"""Hero scoring: pure functions over the cached delta matrices.

fit(candidate) = sum over resolved enemy slots of delta_vs[candidate, enemy]
               + sum over resolved ally slots  of delta_with[candidate, ally]

**The score is DRAFT FIT and nothing else — the hero's own win rate is not
in it.** Zero means the ten heroes on the board neither help nor hurt this
candidate; the number answers "what does this draft do to this hero", not
"is this hero good". That is deliberate and was asked for explicitly: a
baseline term makes the strong heroes float to the top of every list
regardless of the draft, which is the one thing the list is not for. The
cost is real and is the reason `baseline` is still carried on every
ScoredHero: a weak hero with good matchups now outranks a strong hero with
neutral ones, and nothing in the ordering will tell you so.

The linear sum assumes effects are independent and additive — a linearisation
that holds for small perturbations and degrades where heroes interact
strongly. Accepted; the drill-down views exist so the user can catch a
plausible total reached for poor reasons.

Unknown slots are a legitimate state: they are simply absent from the ally /
enemy lists and scoring proceeds on the slots that resolved confidently.
Sub-millisecond on a ~126x126 float matrix; never called from a network path.
"""

from dataclasses import dataclass, field

import numpy as np

from ..data.store import Dataset


@dataclass
class DraftState:
    """Resolved hero ids only — unresolved slots just don't appear here."""
    allies: list[int] = field(default_factory=list)
    enemies: list[int] = field(default_factory=list)
    my_hero: int | None = None      # set once the user's own pick is locked
    my_role: str | None = None      # from role icons or the manual override
    unknown_slots: int = 0          # count, for honest display in the UI


@dataclass
class ScoredHero:
    hero_id: int
    name: str
    score: float          # draft fit: vs_total + with_total, no baseline
    baseline: float       # the hero's own win rate — carried, never scored
    vs_total: float       # summed matchup deltas against resolved enemies
    with_total: float     # summed synergy deltas with resolved allies


def _side_vectors(ds: Dataset, draft: DraftState) -> tuple[np.ndarray, np.ndarray]:
    ally_vec = np.zeros(len(ds.hero_ids))
    enemy_vec = np.zeros(len(ds.hero_ids))
    for hid in draft.allies:
        if hid in ds.index:
            ally_vec[ds.index[hid]] = 1.0
    for hid in draft.enemies:
        if hid in ds.index:
            enemy_vec[ds.index[hid]] = 1.0
    return ally_vec, enemy_vec


def score_all(ds: Dataset, draft: DraftState) -> list[ScoredHero]:
    """Full ranked list of every undrafted hero, best first. No role
    filtering — the UI highlights the user's queued role instead.

    Ranked on draft fit alone: `ds.baseline` is read for the field but is
    NOT added to the score (see the module docstring).
    """
    ally_vec, enemy_vec = _side_vectors(ds, draft)
    vs_totals = ds.delta_vs @ enemy_vec
    with_totals = ds.delta_with @ ally_vec
    totals = vs_totals + with_totals

    drafted = set(draft.allies) | set(draft.enemies)
    out = [
        ScoredHero(
            hero_id=hid,
            name=ds.name(hid),
            score=float(totals[i]),
            baseline=float(ds.baseline[i]),
            vs_total=float(vs_totals[i]),
            with_total=float(with_totals[i]),
        )
        for hid, i in ds.index.items() if hid not in drafted
    ]
    out.sort(key=lambda s: s.score, reverse=True)
    return out


@dataclass
class BreakdownTerm:
    other_id: int
    other_name: str
    kind: str      # "vs" (enemy) or "with" (ally)
    delta: float


def breakdown(ds: Dataset, candidate: int, draft: DraftState) -> list[BreakdownTerm]:
    """Component view for one candidate: its row filtered to the drafted
    columns, as individual terms rather than the sum."""
    i = ds.index[candidate]
    terms = [
        BreakdownTerm(hid, ds.name(hid), "vs",
                      float(ds.delta_vs[i, ds.index[hid]]))
        for hid in draft.enemies if hid in ds.index
    ] + [
        BreakdownTerm(hid, ds.name(hid), "with",
                      float(ds.delta_with[i, ds.index[hid]]))
        for hid in draft.allies if hid in ds.index
    ]
    terms.sort(key=lambda t: abs(t.delta), reverse=True)
    return terms


def counters_to(ds: Dataset, target: int,
                exclude: set[int] = frozenset()) -> list[tuple[int, str, float]]:
    """Ranked list of heroes strong against `target` (its column of delta_vs,
    sorted descending). Works for any drafted hero, ally or enemy."""
    j = ds.index[target]
    col = ds.delta_vs[:, j]
    rows = [(hid, ds.name(hid), float(col[i]))
            for hid, i in ds.index.items()
            if hid != target and hid not in exclude]
    rows.sort(key=lambda r: r[2], reverse=True)
    return rows


@dataclass
class Matrix:
    """A grid of interaction deltas between two sets of drafted heroes."""
    rows: list[tuple[int, str]]
    cols: list[tuple[int, str]]
    cells: list[list[float | None]]     # None = no pair (or the diagonal)
    caption: str = ""

    @property
    def empty(self) -> bool:
        return not self.rows or not self.cols

    @property
    def row_totals(self) -> list[float]:
        return [sum(v for v in line if v is not None) for line in self.cells]

    @property
    def col_totals(self) -> list[float]:
        return [sum(line[col] for line in self.cells
                    if line[col] is not None)
                for col in range(len(self.cols))]

    @property
    def total(self) -> float:
        """Every cell once.

        Deliberately the sum of what is DRAWN, not of the row totals — in
        the synergy grid only the upper triangle is filled, so the row and
        column totals are each partial and adding them would count every
        pair twice. Summing the cells gives the same answer for both grids
        and matches what the eye can check.
        """
        return sum(v for line in self.cells for v in line if v is not None)


def matchup_matrix(ds: Dataset, draft: DraftState) -> Matrix:
    """Every ally against every enemy, read from your side.

    Positive is good for you. The full grid is worth more than the summed
    score it feeds: a comfortable total can hide one lane that loses badly,
    and only the cells show that.
    """
    allies = [h for h in draft.allies if h in ds.index]
    enemies = [h for h in draft.enemies if h in ds.index]
    cells = [[float(ds.delta_vs[ds.index[a], ds.index[e]]) for e in enemies]
             for a in allies]
    return Matrix(rows=[(h, ds.name(h)) for h in allies],
                  cols=[(h, ds.name(h)) for h in enemies],
                  cells=cells,
                  caption="Your team (rows) against theirs (columns), in "
                          "percentage points. Positive favours you.")


def synergy_matrix(ds: Dataset, draft: DraftState) -> Matrix:
    """Your team with itself.

    Synergy is symmetric — A with B is B with A — so only the upper triangle
    carries information and the rest is left blank rather than repeated.
    """
    allies = [h for h in draft.allies if h in ds.index]
    cells: list[list[float | None]] = []
    for row, a in enumerate(allies):
        line: list[float | None] = []
        for col, b in enumerate(allies):
            line.append(None if col <= row
                        else float(ds.delta_with[ds.index[a], ds.index[b]]))
        cells.append(line)
    return Matrix(rows=[(h, ds.name(h)) for h in allies],
                  cols=[(h, ds.name(h)) for h in allies],
                  cells=cells,
                  caption="Your team with itself. Each pair appears once — "
                          "synergy is symmetric, so the lower half would "
                          "only repeat the upper.")


@dataclass
class Relation:
    """One hero's interaction with the hero the user clicked."""
    hero_id: int
    name: str
    delta: float
    kind: str          # "with" (synergy) or "vs" (matchup)


def relations_to(ds: Dataset, focus: int, draft: DraftState) -> list[Relation]:
    """Every drafted hero's interaction with `focus`, context-aware.

    Clicking an ALLY asks two different questions at once — how it fits with
    the rest of your team, and how it fares against theirs — so both are
    answered: synergy for the other allies, matchup for all five enemies.
    Clicking an ENEMY asks only one, so each ally gets its matchup against it.

    Every number is read from YOUR team's point of view: positive is good for
    you whichever hero it sits under. Without that rule a green number under
    an enemy would mean the opposite of a green number under an ally, which
    is exactly the misreading this view exists to prevent.
    """
    if focus not in ds.index:
        return []
    out: list[Relation] = []
    if focus in draft.allies:
        for hid in draft.allies:
            if hid != focus and hid in ds.index:
                out.append(Relation(
                    hid, ds.name(hid),
                    float(ds.delta_with[ds.index[focus], ds.index[hid]]),
                    "with"))
        for hid in draft.enemies:
            if hid in ds.index:
                out.append(Relation(
                    hid, ds.name(hid),
                    float(ds.delta_vs[ds.index[focus], ds.index[hid]]),
                    "vs"))
    else:
        for hid in draft.allies:
            if hid in ds.index:
                out.append(Relation(
                    hid, ds.name(hid),
                    float(ds.delta_vs[ds.index[hid], ds.index[focus]]),
                    "vs"))
    return out


def net_contributions(ds: Dataset, draft: DraftState) -> dict[int, float]:
    """What each drafted hero is worth to your team, summed.

    An ally's figure is its synergy with the rest of your team plus its
    matchups against theirs. An enemy's is the mirror image — how well your
    five fare against it, LESS how well it works with its own four, because
    a hero that combos with their line-up is worth more to them than its
    matchups alone say. Same sign convention as `relations_to`: positive
    favours you, so a green number under an enemy portrait means that enemy
    is handled.
    """
    allies = [h for h in draft.allies if h in ds.index]
    enemies = [h for h in draft.enemies if h in ds.index]
    out: dict[int, float] = {}
    for hid in allies:
        i = ds.index[hid]
        total = sum(float(ds.delta_with[i, ds.index[o]])
                    for o in allies if o != hid)
        total += sum(float(ds.delta_vs[i, ds.index[e]]) for e in enemies)
        out[hid] = total
    for hid in enemies:
        j = ds.index[hid]
        # Their synergy counts too, with the sign flipped: a pair that works
        # well for THEM is a problem for you, and the whole view is read
        # from your side. Without the flip the same green number would mean
        # "good for us" over an ally and "good for them" over an enemy.
        theirs = sum(float(ds.delta_with[j, ds.index[o]])
                     for o in enemies if o != hid)
        out[hid] = (sum(float(ds.delta_vs[ds.index[a], j]) for a in allies)
                    - theirs)
    return out

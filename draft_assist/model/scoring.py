"""Hero scoring: pure functions over the cached delta matrices.

score(candidate) = baseline(candidate)
                 + sum over resolved enemy slots of delta_vs[candidate, enemy]
                 + sum over resolved ally slots  of delta_with[candidate, ally]

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
    score: float          # baseline + interaction deltas
    baseline: float
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
    filtering — the UI highlights the user's queued role instead."""
    ally_vec, enemy_vec = _side_vectors(ds, draft)
    vs_totals = ds.delta_vs @ enemy_vec
    with_totals = ds.delta_with @ ally_vec
    totals = ds.baseline + vs_totals + with_totals

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

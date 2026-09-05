"""Which five are yours, settled by looking at the screen.

The game feed hands over all ten heroes at strategy time but not, reliably,
whose five are whose — five recorded matches and no rule found, one of them
inverted (see CLAUDE.md). The screen has never had that ambiguity: Radiant
is always the LEFT bank of the pick bar and Dire the right, and
`player.team_name` says which of those is yours. So the split does not need
a rule at all. It needs the ten known heroes located on the bar.

That is an easier problem than recognition proper, and this module exists
because of the difference: normally the app asks "which of 126 heroes is in
this box"; here it asks "which of THESE TEN is in this box", with the
answer guaranteed to be a permutation. Ten known candidates and ten boxes
is a small assignment problem, and a wrong answer requires two heroes to
out-match each other in each other's slots rather than one hero to beat 125
rivals.

Two paths, cheap first:

* **Placed** — with calibrated crop boxes, each of the ten boxes is scored
  against each of the ten candidates and the best consistent assignment
  wins. A hundred correlations on small crops: milliseconds.
* **Searched** — no usable calibration, so every candidate is hunted across
  the top strip at an unknown scale (`autocal.locate`, which is where the
  expensive scale grid lives). Seconds, not milliseconds, so callers run it
  once per match rather than per frame.

It never guesses. Anything short of ten confident, distinct heroes falling
into two banks of five returns a reading that is `ok is False`, carrying the
reason, and the caller keeps whatever it had.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

from . import autocal
from .layout import DraftLayout, hud_box

# A placed crop is scored against a portrait resized to the same box, so
# the bar is lower than a search's: the box may be a few pixels out and the
# competition is nine heroes rather than 125.
MIN_PLACED_SCORE = 0.25
# How far the best candidate must beat the runner-up for a box. Two heroes
# scoring the same means the crop is not actually showing either of them.
MIN_MARGIN = 0.03
TEAM_SIZE = 5


@dataclass
class ScreenLineup:
    """The pick bar, read left to right."""
    left: list[int] = field(default_factory=list)    # Radiant bank
    right: list[int] = field(default_factory=list)   # Dire bank
    confidence: float = 0.0
    how: str = ""            # "placed" | "searched"
    note: str = ""

    @property
    def ok(self) -> bool:
        return len(self.left) == TEAM_SIZE and len(self.right) == TEAM_SIZE

    def sides_for(self, my_team: str) -> tuple[list[int], list[int]]:
        """(allies, enemies) given which team the player is on.

        Radiant is the left bank and Dire the right — that mapping is the
        whole reason this is worth doing, and it is not a guess.
        """
        if my_team == "dire":
            return (list(self.right), list(self.left))
        return (list(self.left), list(self.right))


def _grey(image):
    if image is None or image.size == 0:
        return None
    if image.ndim == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image


def _score(crop, template) -> float:
    """Correlation of one crop against one portrait, at the crop's size."""
    if crop is None or template is None or crop.size == 0:
        return -1.0
    height, width = crop.shape[:2]
    if height < 4 or width < 4:
        return -1.0
    resized = cv2.resize(template, (width, height),
                         interpolation=cv2.INTER_AREA)
    result = cv2.matchTemplate(crop, resized, cv2.TM_CCOEFF_NORMED)
    return float(result[0][0])


def _assign(scores: np.ndarray, hero_ids: list[int]) -> list[int] | None:
    """Best consistent slot -> hero assignment, greedily.

    Greedy rather than optimal (Hungarian) on purpose: with ten heroes that
    are actually on screen the score matrix is strongly diagonal once
    permuted, so the best pair overall is right, and taking it removes both
    a row and a column. If the matrix is NOT strongly separated the margin
    check below rejects the whole reading anyway, which is the outcome we
    want — an ambiguous board should produce nothing, not a plausible
    permutation.
    """
    remaining = scores.copy()
    placed: dict[int, int] = {}
    for _ in range(len(hero_ids)):
        slot, hero = np.unravel_index(int(np.argmax(remaining)),
                                      remaining.shape)
        best = remaining[slot, hero]
        if best < MIN_PLACED_SCORE:
            return None
        # The runner-up for this same slot, among heroes still unclaimed.
        rivals = np.delete(remaining[slot], hero)
        if rivals.size and best - float(rivals.max()) < MIN_MARGIN:
            return None
        placed[int(slot)] = hero_ids[int(hero)]
        remaining[slot, :] = -np.inf
        remaining[:, hero] = -np.inf
    return [placed[i] for i in range(len(hero_ids))]


def read_placed(frame, hero_ids: list[int],
                layout: DraftLayout,
                portraits: dict[int, np.ndarray] | None = None
                ) -> ScreenLineup:
    """Assign the ten known heroes to the ten calibrated crop boxes."""
    if frame is None or len(hero_ids) != 2 * TEAM_SIZE:
        return ScreenLineup(note="need a frame and exactly ten named heroes")
    art = portraits if portraits is not None else \
        autocal.base_portraits(hero_ids)
    greys = {hid: _grey(image) for hid, image in art.items()}
    ordered = [hid for hid in hero_ids if greys.get(hid) is not None]
    if len(ordered) != len(hero_ids):
        return ScreenLineup(note=(
            f"{len(hero_ids) - len(ordered)} of the ten have no downloaded "
            "portrait to match against"))

    height, width = frame.shape[:2]
    picture = _grey(frame)
    slots = layout.slots()
    scores = np.full((len(slots), len(ordered)), -1.0, dtype=np.float64)
    for row, rect in enumerate(slots):
        x, y, w, h = rect.to_pixels(width, height)
        if x < 0 or y < 0 or x + w > width or y + h > height:
            return ScreenLineup(note=(
                "the crop boxes fall outside the frame — calibration is off"))
        crop = picture[y:y + h, x:x + w]
        for col, hid in enumerate(ordered):
            scores[row, col] = _score(crop, greys[hid])

    assignment = _assign(scores, ordered)
    if assignment is None:
        return ScreenLineup(note=(
            "the ten heroes could not be told apart in the crop boxes — "
            "the boxes are probably not on the portraits"))
    return ScreenLineup(
        left=assignment[:TEAM_SIZE], right=assignment[TEAM_SIZE:],
        confidence=float(np.mean([
            scores[i, ordered.index(hid)]
            for i, hid in enumerate(assignment)])),
        how="placed",
        note=f"matched {len(assignment)} portraits in the calibrated boxes")


def read_searched(frame, hero_ids: list[int],
                  portraits: dict[int, np.ndarray] | None = None
                  ) -> ScreenLineup:
    """Hunt each of the ten across the top strip, no calibration needed.

    This is the expensive path — the scale grid in `autocal.find_scale` is
    hundreds of correlations — so it is for once per match, never per frame.
    """
    if frame is None or len(hero_ids) != 2 * TEAM_SIZE:
        return ScreenLineup(note="need a frame and exactly ten named heroes")
    art = portraits if portraits is not None else \
        autocal.base_portraits(hero_ids)
    found = autocal.locate(frame, art)
    if len(found) != 2 * TEAM_SIZE:
        return ScreenLineup(note=(
            f"found {len(found)} of the ten portraits on screen; all ten are "
            "needed before the sides can be read off"))

    xs = [item.x for item in found]              # locate() sorts by x
    gaps = [b - a for a, b in zip(xs, xs[1:])]
    split = gaps.index(max(gaps)) + 1
    if split != TEAM_SIZE:
        return ScreenLineup(note=(
            f"the widest gap splits the bar {split}/{len(found) - split}, "
            "not 5/5 — this frame is probably not a pick bar"))
    return ScreenLineup(
        left=[item.hero_id for item in found[:TEAM_SIZE]],
        right=[item.hero_id for item in found[TEAM_SIZE:]],
        confidence=float(np.mean([item.score for item in found])),
        how="searched",
        note=f"located all ten on the bar, mean confidence "
             f"{np.mean([item.score for item in found]):.2f}")


def read_lineup(frame, hero_ids: list[int],
                layout: DraftLayout | None = None,
                allow_search: bool = True,
                portraits: dict[int, np.ndarray] | None = None
                ) -> ScreenLineup:
    """Cheap path, then the expensive one if it is allowed and needed."""
    if layout is not None:
        placed = read_placed(frame, hero_ids, layout, portraits)
        if placed.ok:
            return placed
    else:
        placed = ScreenLineup(note="no calibration to place boxes with")
    if not allow_search:
        return placed
    searched = read_searched(frame, hero_ids, portraits)
    if searched.ok:
        return searched
    return ScreenLineup(note=f"{placed.note}; then {searched.note}")

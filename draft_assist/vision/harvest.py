"""Learn an unrecognised portrait from the ones that WERE recognised.

Alternative portraits — personas, arcanas, and whatever a cosmetic set puts
in the top bar — are not in the downloaded library, because the library is
built from Valve's one base image per hero. So a hero on a set portrait
sits at `UNKNOWN d98 m0` forever while the other nine resolve.

The answer is not to go and find that artwork somewhere. It is already on
the user's screen, at their resolution, with their HUD's badge and border on
it — which is the exact appearance that has to match, rather than a
web-sized picture of the same hero. And at strategy time the game NAMES all
ten, so the label is free and exact:

    ten heroes from the game
  - nine matched confidently on screen
  = the tenth is the one in the box that did not match

That is elimination, not a guess, and the guards below are what keep it
that way. A mislabelled crop is permanent damage — it teaches the library
that one hero looks like another — so every check has to pass, and when
they do not the answer is simply "not this frame". There are hundreds of
frames in a draft; being right on one of them is enough.
"""

from pathlib import Path

import cv2
import numpy as np

from .library import EMPTY_SLOT, VARIANTS_DIR
from .phash import phash

# How many of the ten must have matched before elimination means anything.
# At eight, the one left over is pinned down by eight independent readings
# plus the game's own list.
MIN_RESOLVED = 8
# Stop after this many appearances of one hero: they are near-duplicates
# after a while and every extra entry is another row to search.
MAX_PER_HERO = 8
# Two crops closer than this are the same picture a few frames apart. The
# refresh loop runs four times a second, so without this one draft would
# write two hundred copies of the same portrait.
DUPLICATE_FRAC = 0.08
# A near-flat crop is an empty slot or a black box from a bad crop box —
# never a portrait worth learning.
MIN_STD = 8.0


def by_elimination(read, known_ten: list[int]):
    """(hero id, the slot it is in), or (None, why not).

    `read` is a DraftRead from the screen; `known_ten` is what the game
    said is in this match.
    """
    ten = list(known_ten)
    if len(ten) != 10 or len(set(ten)) != 10:
        return None, "the game has not named ten distinct heroes"

    resolved = {s.hero_id for s in read.slots
                if s.hero_id is not None and s.hero_id != EMPTY_SLOT}
    unknown = [s for s in read.slots if s.hero_id is None]
    if len(unknown) != 1:
        return None, f"{len(unknown)} slots unresolved, need exactly one"
    if len(resolved) < MIN_RESOLVED:
        return None, f"only {len(resolved)} matched, need {MIN_RESOLVED}"
    if not resolved <= set(ten):
        # The screen named somebody the game says is not in this match, so
        # one of the two is wrong and neither can be used to pin the third.
        strays = sorted(resolved - set(ten))
        return None, f"the screen matched heroes not in this game: {strays}"
    missing = set(ten) - resolved
    if len(missing) != 1:
        return None, f"{len(missing)} heroes unaccounted for, need exactly one"
    return missing.pop(), unknown[0]


def save_variant(hero_id: int, crop, tag: str, hash_size: int = 16,
                 variants_dir: Path | None = None) -> Path | None:
    """File a learned crop under its hero. None when it was not worth it.

    Deduplicated by perceptual distance rather than by frame number,
    because four frames a second of the same portrait are four frames a
    second of the same picture.
    """
    if crop is None or crop.size == 0:
        return None
    grey = (cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3
            else crop)
    if float(grey.std()) < MIN_STD:
        return None                    # flat: an empty slot or a bad crop

    folder = (variants_dir or VARIANTS_DIR) / str(int(hero_id))
    existing = sorted(folder.glob("*.png")) if folder.is_dir() else []
    if len(existing) >= MAX_PER_HERO:
        return None
    bits = phash(crop, hash_size)
    limit = DUPLICATE_FRAC * bits.size
    for path in existing:
        other = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if other is None:
            continue
        if int(np.count_nonzero(bits != phash(other, hash_size))) <= limit:
            return None                # already know this appearance

    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{tag}.png"
    return dest if cv2.imwrite(str(dest), crop) else None

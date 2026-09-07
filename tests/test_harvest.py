"""Learning an alternative portrait by elimination.

Personas, arcanas and cosmetic sets change the top-bar picture, and the
library holds Valve's one base image per hero — so a hero on a set portrait
reads UNKNOWN while the other nine resolve. The label is free: the game
names all ten, nine matched, so the tenth is the one in the box that did
not.

Every test here is about a guard, because a mislabelled crop teaches the
library that one hero looks like another and never expires.
"""

import numpy as np
import pytest

from draft_assist.vision import harvest
from draft_assist.vision.library import EMPTY_SLOT
from draft_assist.vision.layout import SlotRect
from draft_assist.vision.recognize import DraftRead, SlotRead

TEN = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]


def read_of(hero_ids):
    """A screen reading naming these ten (None = unresolved)."""
    slots = []
    for index, hid in enumerate(hero_ids):
        team = "radiant" if index < 5 else "dire"
        slots.append(SlotRead(
            rect=SlotRect(team, index % 5, 0.1, 0.0, 0.05, 0.09),
            hero_id=hid, best_label="x", distance=0, margin=0))
    return DraftRead(slots=slots)


def textured(width=120, height=90, seed=1):
    rng = np.random.default_rng(seed)
    return rng.integers(20, 230, (height, width, 3), dtype=np.uint8)


# ---- the elimination ----------------------------------------------------

def test_nine_matched_plus_the_games_ten_names_the_tenth():
    read = read_of([1, 2, 3, 4, 5, 6, 7, 8, 9, None])
    hero_id, slot = harvest.by_elimination(read, TEN)
    assert hero_id == 10
    assert slot.rect.team == "dire" and slot.rect.slot == 4


def test_the_unresolved_slot_can_be_anywhere_in_the_bar():
    read = read_of([1, None, 3, 4, 5, 6, 7, 8, 9, 10])
    hero_id, slot = harvest.by_elimination(read, TEN)
    assert hero_id == 2
    assert slot.rect.team == "radiant" and slot.rect.slot == 1


def test_two_unresolved_slots_teach_nothing():
    """Two unknowns and two heroes left over is two ways round, and there
    is no way to tell which is which."""
    read = read_of([1, None, 3, 4, 5, 6, 7, 8, None, 10])
    hero_id, why = harvest.by_elimination(read, TEN)
    assert hero_id is None
    assert "2 slots unresolved" in why


def test_a_screen_hero_the_game_never_named_stops_everything():
    """One of the two sources is wrong, and neither can be used to pin the
    third."""
    read = read_of([1, 2, 3, 4, 5, 6, 7, 8, 99, None])
    hero_id, why = harvest.by_elimination(read, TEN)
    assert hero_id is None
    assert "not in this game" in why


def test_too_few_matches_is_not_elimination():
    read = read_of([1, 2, 3, None, EMPTY_SLOT, EMPTY_SLOT,
                    EMPTY_SLOT, EMPTY_SLOT, EMPTY_SLOT, EMPTY_SLOT])
    hero_id, why = harvest.by_elimination(read, TEN)
    assert hero_id is None
    assert "need" in why


def test_it_needs_ten_distinct_heroes_from_the_game():
    read = read_of([1, 2, 3, 4, 5, 6, 7, 8, 9, None])
    assert harvest.by_elimination(read, TEN[:9])[0] is None
    assert harvest.by_elimination(read, [1] * 10)[0] is None


def test_an_empty_slot_is_not_an_unresolved_one():
    """A slot with no pick yet is recognised, not unknown — it must not
    look like the hero that is missing."""
    read = read_of([1, 2, 3, 4, 5, 6, 7, 8, 9, EMPTY_SLOT])
    hero_id, why = harvest.by_elimination(read, TEN)
    assert hero_id is None
    assert "0 slots unresolved" in why


# ---- filing the crop ----------------------------------------------------

def test_a_crop_is_written_under_its_hero(tmp_path):
    saved = harvest.save_variant(42, textured(), "game_dire4",
                                 variants_dir=tmp_path)
    assert saved is not None and saved.exists()
    assert saved.parent.name == "42"


def test_the_same_portrait_is_not_written_twice(tmp_path):
    """The loop runs four times a second; without this one draft would
    write two hundred copies of one picture."""
    art = textured()
    assert harvest.save_variant(42, art, "a", variants_dir=tmp_path)
    assert harvest.save_variant(42, art, "b", variants_dir=tmp_path) is None
    assert len(list((tmp_path / "42").glob("*.png"))) == 1


def test_a_genuinely_different_appearance_is_kept(tmp_path):
    assert harvest.save_variant(42, textured(seed=1), "a",
                                variants_dir=tmp_path)
    assert harvest.save_variant(42, textured(seed=99), "b",
                                variants_dir=tmp_path)
    assert len(list((tmp_path / "42").glob("*.png"))) == 2


def test_a_flat_crop_is_never_learned(tmp_path):
    """Flat is an empty slot or a black box from a bad crop box — and a
    black box filed under a hero is the worst thing this could do."""
    flat = np.full((90, 120, 3), 18, np.uint8)
    assert harvest.save_variant(42, flat, "a", variants_dir=tmp_path) is None
    assert not (tmp_path / "42").exists()


def test_one_hero_cannot_fill_the_library(tmp_path):
    for i in range(harvest.MAX_PER_HERO + 4):
        harvest.save_variant(42, textured(seed=i), f"f{i}",
                             variants_dir=tmp_path)
    assert len(list((tmp_path / "42").glob("*.png"))) == harvest.MAX_PER_HERO


def test_an_empty_crop_is_refused(tmp_path):
    assert harvest.save_variant(42, None, "a", variants_dir=tmp_path) is None
    assert harvest.save_variant(42, np.zeros((0, 0, 3), np.uint8), "a",
                                variants_dir=tmp_path) is None


# ---- and it has to reach the recogniser ---------------------------------

def test_a_newly_learned_portrait_rebuilds_the_library(tmp_path):
    """A crop learned mid-draft, or a file dropped in by hand, used to sit
    in the folder doing nothing until somebody remembered to rebuild — so
    the app learned a portrait and then went on not recognising it."""
    import time

    import cv2

    from draft_assist.vision import library

    base = tmp_path / "base"
    variants = tmp_path / "variants"
    base.mkdir()
    variants.mkdir()
    cv2.imwrite(str(base / "1_antimage.png"), textured(seed=2))
    cache = tmp_path / "library.npz"

    first = library.rebuild(8, base, variants, cache)
    assert len(first.labels) == 1

    # A learned crop arrives after the cache was written.
    time.sleep(0.01)
    harvest.save_variant(1, textured(seed=7), "learned",
                         hash_size=8, variants_dir=variants)
    assert library.newest_source(base, variants) > cache.stat().st_mtime

    again = library.load(cache, base_dir=base, variants_dir=variants)
    assert len(again.labels) == 2, "the new portrait was not picked up"
    assert any("learned" in label for label in again.labels)


def test_an_unchanged_library_is_not_rebuilt_every_load(tmp_path):
    """Rehashing a few hundred images on every start would be a start-up
    cost paid for nothing."""
    import cv2

    from draft_assist.vision import library

    base = tmp_path / "base"
    variants = tmp_path / "variants"
    base.mkdir()
    variants.mkdir()
    cv2.imwrite(str(base / "1_antimage.png"), textured(seed=2))
    cache = tmp_path / "library.npz"
    library.rebuild(8, base, variants, cache)
    stamp = cache.stat().st_mtime

    library.load(cache, base_dir=base, variants_dir=variants)
    assert cache.stat().st_mtime == stamp, "it rebuilt for no reason"

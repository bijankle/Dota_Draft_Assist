"""End-to-end vision tests on the procedural proving ground: no network, no
saved frames, no Dota. If these pass, the pipeline mechanics (fractional
crops, hashing, many-to-one matching, margin rule) are sound; real-portrait
fidelity is covered by running the proving ground on downloaded art."""

import numpy as np
import pytest

from draft_assist.proving.evaluate import build_library_from_images, evaluate
from draft_assist.proving.synth import (Distortions, empty_slot_image,
                                        generate_case,
                                        procedural_portrait_set)
from draft_assist.vision.layout import DraftLayout
from draft_assist.vision.library import EMPTY_SLOT, RecognitionParams
from draft_assist.vision.phash import hamming, phash
from draft_assist.vision.recognize import match_crop, read_draft


@pytest.fixture(scope="module")
def portraits():
    return procedural_portrait_set(126)


@pytest.fixture(scope="module")
def lib(portraits):
    return build_library_from_images(
        portraits, hash_size=8, extra={EMPTY_SLOT: [empty_slot_image()]})


PARAMS = RecognitionParams(hash_size=8, max_distance_frac=0.30,
                           min_margin_frac=0.04)


def test_phash_stability_under_rescale(portraits):
    img = portraits[1]
    import cv2
    small = cv2.resize(img, (64, 36))
    assert hamming(phash(img), phash(small)) <= 6


def test_phash_separates_heroes(portraits):
    dists = [hamming(phash(portraits[1]), phash(portraits[h]))
             for h in range(2, 60)]
    assert min(dists) > 10  # distinct heroes are far apart


def test_full_frame_recognition_no_wrong_matches(portraits, lib):
    layout = DraftLayout()
    rng = np.random.default_rng(42)
    cases = [generate_case(portraits, layout, rng) for _ in range(30)]
    report = evaluate(cases, layout, lib, PARAMS)
    # Wrong matches invert recommendations; the proving ground's whole
    # purpose is to keep this at zero. Unknowns are tolerated.
    assert report.wrong == 0, f"confusions: {report.confusions}"
    assert report.unknown_rate < 0.10, report.summary()
    assert report.correct > 0


def test_ambiguous_crop_goes_unknown(lib):
    # A crop that is nothing like any portrait must resolve to unknown or
    # empty, never to a hero.
    noise = (np.random.default_rng(0).uniform(0, 255, (72, 128, 3))
             .astype(np.uint8))
    hero_id, _, dist, _ = match_crop(noise, lib, PARAMS)
    assert hero_id in (None, EMPTY_SLOT)


def test_many_to_one_variants_map_to_same_hero(portraits):
    # A persona-style variant (heavily recoloured portrait) is a separate
    # library entry mapping back to the same hero id.
    variant = portraits[7].copy()[:, ::-1]  # mirrored, e.g. new art
    lib2 = build_library_from_images(
        portraits, 8, extra={7: [variant], EMPTY_SLOT: [empty_slot_image()]})
    hero_id, label, dist, margin = match_crop(variant, lib2, PARAMS)
    assert hero_id == 7
    assert "variant" in label


def test_empty_slots_recognised(portraits, lib):
    layout = DraftLayout()
    rng = np.random.default_rng(3)
    case = generate_case(portraits, layout, rng, fill_range=(0, 0))
    read = read_draft(case.frame, layout, lib, PARAMS)
    assert all(s.hero_id in (EMPTY_SLOT, None) for s in read.slots)
    assert sum(s.hero_id == EMPTY_SLOT for s in read.slots) >= 8


def test_team_ids_exclude_unknown_and_empty(portraits, lib):
    layout = DraftLayout()
    rng = np.random.default_rng(11)
    case = generate_case(portraits, layout, rng, fill_range=(10, 10))
    read = read_draft(case.frame, layout, lib, PARAMS)
    radiant = read.team_ids("radiant")
    truth_radiant = case.truth[:5]
    # Everything reported must be true; unknowns may be missing.
    for hid in radiant:
        assert hid in truth_radiant


def test_fractional_layout_survives_resolution_change(portraits, lib):
    layout = DraftLayout()
    rng = np.random.default_rng(5)
    gentle = Distortions(jitter_frac=0.0, noise_sigma=(0, 1),
                         jpeg_quality=(90, 95), dim_chance=0)
    for resolution in [(1920, 1080), (1366, 768), (2560, 1440)]:
        case = generate_case(portraits, layout, rng, resolution=resolution,
                             distort=gentle, fill_range=(10, 10))
        report = evaluate([case], layout, lib, PARAMS)
        assert report.wrong == 0
        assert report.correct >= 8, (resolution, report.summary())


# ---- the HUD is 16:9, the monitor may not be ---------------------------

def test_crop_boxes_follow_dotas_16_9_hud_not_the_monitor():
    """On 3440x1440 the HUD is pillarboxed into the middle 2560 pixels. A
    plain fraction-of-width put the boxes hundreds of pixels left of the
    portraits, which is what a real ultrawide session showed."""
    from draft_assist.vision.layout import DraftLayout, hud_box

    left, span = hud_box(3440, 1440)
    assert (left, span) == (440.0, 2560.0)

    slot = DraftLayout().slots()[0]
    wide = slot.to_pixels(3440, 1440)
    normal = slot.to_pixels(2560, 1440)
    assert wide[0] == normal[0] + 440          # shifted, not stretched
    assert wide[2] == normal[2]                # same width in pixels
    assert wide[1:2] == normal[1:2]            # y unchanged


def test_a_16_9_display_is_unaffected():
    from draft_assist.vision.layout import DraftLayout, hud_box

    for width, height in ((1920, 1080), (2560, 1440), (1280, 720)):
        assert hud_box(width, height) == (0.0, float(width))
    slot = DraftLayout().slots()[0]
    assert slot.to_pixels(1920, 1080)[0] == round(slot.x * 1920)


def test_a_taller_than_16_9_display_uses_its_full_width():
    """4:3 and 16:10 are narrower than the HUD box, never pillarboxed."""
    from draft_assist.vision.layout import hud_box

    assert hud_box(1280, 1024) == (0.0, 1280.0)
    assert hud_box(1920, 1200) == (0.0, 1920.0)


def test_every_slot_stays_inside_the_frame_on_an_ultrawide():
    from draft_assist.vision.layout import DraftLayout

    for slot in DraftLayout().slots():
        x, y, w, h = slot.to_pixels(3440, 1440)
        assert 0 <= x and x + w <= 3440
        assert 0 <= y and y + h <= 1440

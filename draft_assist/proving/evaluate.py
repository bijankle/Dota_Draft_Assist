"""Scoring the recogniser against labeled cases (synthetic or harvested).

The metric hierarchy is deliberate: WRONG matches are the failure that
matters (a wrong hero inverts recommendations), unknowns are merely lost
information, so evaluation reports them separately and tuning treats any
wrong match as disqualifying before it starts minimising unknowns.
"""

from dataclasses import dataclass, field

import numpy as np

from ..vision.layout import DraftLayout
from ..vision.library import Library, RecognitionParams
from ..vision.recognize import read_draft
from .synth import SynthCase


@dataclass
class EvalReport:
    total_slots: int = 0
    correct: int = 0
    unknown: int = 0
    wrong: int = 0
    confusions: list[tuple[int, int]] = field(default_factory=list)  # (truth, got)

    @property
    def wrong_rate(self) -> float:
        return self.wrong / self.total_slots if self.total_slots else 0.0

    @property
    def unknown_rate(self) -> float:
        return self.unknown / self.total_slots if self.total_slots else 0.0

    def summary(self) -> str:
        return (f"{self.total_slots} slots: {self.correct} correct, "
                f"{self.unknown} unknown ({self.unknown_rate:.1%}), "
                f"{self.wrong} WRONG ({self.wrong_rate:.2%})")


def evaluate(cases: list[SynthCase], layout: DraftLayout, lib: Library,
             params: RecognitionParams) -> EvalReport:
    report = EvalReport()
    for case in cases:
        read = read_draft(case.frame, layout, lib, params)
        for slot_read, truth in zip(read.slots, case.truth):
            report.total_slots += 1
            got = slot_read.hero_id
            if got is None:
                report.unknown += 1
            elif got == truth:
                report.correct += 1
            else:
                report.wrong += 1
                report.confusions.append((truth, got))
    return report


def build_library_from_images(portraits: dict[int, np.ndarray],
                              hash_size: int,
                              extra: dict[int, list[np.ndarray]] | None = None
                              ) -> Library:
    """In-memory library straight from images (procedural or real), used by
    the proving ground so tuning can rebuild at different hash sizes without
    touching disk."""
    from ..vision.phash import phash
    bits, ids, labels = [], [], []
    for hid, img in portraits.items():
        bits.append(phash(img, hash_size))
        ids.append(hid)
        labels.append(f"mem/{hid}")
    for hid, imgs in (extra or {}).items():
        for k, img in enumerate(imgs):
            bits.append(phash(img, hash_size))
            ids.append(hid)
            labels.append(f"mem/{hid}/variant{k}")
    return Library(bits=np.stack(bits), hero_ids=np.array(ids, np.int32),
                   labels=labels, hash_size=hash_size)

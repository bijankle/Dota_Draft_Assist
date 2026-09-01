"""Disk cache for the built dataset. The live scoring loop reads only from
here and never makes network calls."""

import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import CACHE_MAX_AGE_HOURS, DATA_CACHE

MATRIX_FILE = DATA_CACHE / "dataset.npz"
META_FILE = DATA_CACHE / "dataset_meta.json"


@dataclass
class Dataset:
    hero_ids: list[int]              # sorted; row/col i belongs to hero_ids[i]
    index: dict[int, int]            # hero id -> row/col
    heroes: dict[int, dict]          # id -> {name, internal_name, img, icon}
    baseline: np.ndarray             # baseline winrate per hero (target bracket)
    picks: np.ndarray                # sample size behind each baseline
    delta_vs: np.ndarray             # NORMALISED matchup deltas (see normalize.py)
    delta_with: np.ndarray           # NORMALISED synergy deltas
    meta: dict

    def name(self, hero_id: int) -> str:
        return self.heroes.get(hero_id, {}).get("name", f"hero {hero_id}")

    def age_hours(self) -> float:
        return (time.time() - self.meta["pulled_at"]) / 3600

    def is_stale(self) -> bool:
        return self.age_hours() > CACHE_MAX_AGE_HOURS


def save(ds: Dataset) -> None:
    DATA_CACHE.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        MATRIX_FILE,
        hero_ids=np.array(ds.hero_ids, dtype=np.int32),
        baseline=ds.baseline.astype(np.float32),
        picks=ds.picks.astype(np.int64),
        delta_vs=ds.delta_vs,
        delta_with=ds.delta_with,
    )
    META_FILE.write_text(json.dumps(
        {**ds.meta, "heroes": {str(k): v for k, v in ds.heroes.items()}},
        indent=2), encoding="utf-8")


def load(path: Path = MATRIX_FILE) -> Dataset:
    if not path.exists() or not META_FILE.exists():
        raise FileNotFoundError(
            f"No dataset cache at {path}. Run `python tools/pull_data.py` "
            "first (needs network + STRATZ_API_KEY in .env).")
    z = np.load(path)
    meta = json.loads(META_FILE.read_text(encoding="utf-8"))
    heroes = {int(k): v for k, v in meta.pop("heroes").items()}
    hero_ids = [int(x) for x in z["hero_ids"]]
    return Dataset(
        hero_ids=hero_ids,
        index={hid: i for i, hid in enumerate(hero_ids)},
        heroes=heroes,
        baseline=z["baseline"].astype(np.float64),
        picks=z["picks"],
        delta_vs=z["delta_vs"].astype(np.float64),
        delta_with=z["delta_with"].astype(np.float64),
        meta=meta,
    )

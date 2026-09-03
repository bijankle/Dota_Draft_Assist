"""Daily dataset build: pull OpenDota + Stratz, verify bracket indexing,
normalise to deltas, cache to disk. The only module (besides tools/) that is
allowed to touch the network."""

import time

import numpy as np

from ..config import target_brackets
from . import normalize, opendota, store, stratz, verify


def build_dataset(skip_bracket_check: bool = False,
                  brackets: tuple[str, ...] | None = None) -> store.Dataset:
    brackets = tuple(brackets) if brackets else target_brackets()
    print(f"Building statistics for bracket(s): {'+'.join(brackets)}")
    print("Pulling OpenDota constants/heroes ...")
    heroes = opendota.fetch_heroes()
    print(f"  {len(heroes)} heroes")

    print("Pulling OpenDota heroStats ...")
    hero_stats = opendota.fetch_hero_stats()

    if skip_bracket_check:
        print("WARNING: bracket-index verification SKIPPED by flag")
        bracket_check = {"passed": None, "skipped": True}
    else:
        print("Verifying OpenDota tier indexing against Stratz brackets ...")
        bracket_check = verify.verify_tier_mapping(hero_stats, brackets)
        print(verify.format_report(bracket_check))
        if not bracket_check["passed"]:
            raise RuntimeError(
                "OpenDota tier-index verification failed; refusing to build "
                "baselines that would be silently skewed. Inspect the "
                "report above and data_cache/raw/, fix opendota.TIER_NAMES, "
                "or rerun with --skip-bracket-check if you are certain.")

    baselines = opendota.baseline_winrates(hero_stats, brackets)
    total_picks = sum(v["picks"] for v in baselines.values())
    print(f"Baselines: {brackets} combined, "
          f"{total_picks:,} hero-picks total")

    print("Introspecting Stratz matchUp schema ...")
    schema = stratz.introspect()
    bracket_filter = stratz.choose_bracket_filter(schema, brackets)
    print(f"  bracket filter: {bracket_filter['arg']} = "
          f"{bracket_filter['values']} "
          f"({'exact' if bracket_filter['exact'] else 'covers ' + str(bracket_filter['covers'])})")

    hero_ids = sorted(heroes)
    print(f"Pulling Stratz matchups for {len(hero_ids)} heroes ...")
    matchups = stratz.fetch_matchups(hero_ids, bracket_filter)

    index = normalize.hero_index(hero_ids)
    b = normalize.baseline_vector(index, baselines)
    d_vs, d_with = normalize.build_delta_matrices(index, b, matchups)
    problems = normalize.sanity_check(d_vs, d_with)
    if problems:
        raise RuntimeError("Built matrices failed sanity checks:\n  "
                           + "\n  ".join(problems))

    picks = np.zeros(len(index), dtype=np.int64)
    for hid, i in index.items():
        picks[i] = baselines.get(hid, {}).get("picks", 0)

    ds = store.Dataset(
        hero_ids=hero_ids, index=index, heroes=heroes,
        baseline=b, picks=picks, delta_vs=d_vs, delta_with=d_with,
        meta={
            "pulled_at": time.time(),
            "target_brackets": list(brackets),
            "stratz_bracket_filter": bracket_filter,
            "bracket_check": bracket_check,
            "matrices_hold": "normalised deltas (see normalize.py), NOT raw win rates",
            "shrink_prior_matches": normalize.SHRINK_PRIOR_MATCHES,
        },
    )
    store.save(ds)
    print(f"Saved dataset: {len(hero_ids)} heroes -> {store.MATRIX_FILE}")
    return ds

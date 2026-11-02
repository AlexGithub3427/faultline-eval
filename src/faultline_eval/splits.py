"""
Dev/test split for SWE-bench Lite.

The split is generated once by scripts/make_split.py and frozen in data/splits/. Downstream code should read the
frozen files, never call stratified_split again.

"""

import random
from collections import defaultdict


def stratified_split(iids: list[str], strata: list[str], seed: int) -> tuple[list[str], list[str]]:
    """
    Split cases 50/50 within each stratum.

    Strata with an odd number of cases give the extra case alternately to dev and test (in sorted stratum order).
    Because the total is even, the number of odd strata is even, so totals come out exactly equal.

    Returns (dev_iids, test_iids).
    """

    if len(iids) != len(strata):
        raise ValueError("iids and strata must have the same length")
    if len(set(iids)) != len(iids):
        raise ValueError("duplicate instance iids")


    # 1. Group iids by strata
    by_strata: dict[str, list[str]] = defaultdict(list)
    for iid, stratum in zip(iids, strata):
        by_strata[stratum].append(iid)

    rng = random.Random(seed)
    dev: list[str] = []
    test: list[str] = []
    extra_to_dev = True

    # 2. Process stratas in sorted order
    for stratum in sorted(by_strata):
        group = sorted(by_strata[stratum])
        rng.shuffle(group)

        n_dev = len(group) // 2
        if len(group) % 2 == 1:
            if extra_to_dev:
                n_dev += 1
            extra_to_dev = not extra_to_dev

        dev += group[:n_dev]
        test += group[n_dev:]

    assert set(dev).isdisjoint(test)
    assert len(dev) + len(test) == len(iids)

    return sorted(dev), sorted(test)

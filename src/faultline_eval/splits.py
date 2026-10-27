"""
Dev/test split for SWE-bench Lite.

The split is generated once by scripts/make_split.py and frozen in data/splits/. Downstream code should read the
frozen files, never call stratified_split again.

"""

import random
from collections import defaultdict


def stratified_split(iids: list[str], repos: list[str], seed: int) -> tuple[list[str], list[str]]:
    """
    Split cases 50/50 within each repo.

    Repos with an odd number of cases give the extra case alternately to dev and test (in sorted repo order), so totals
    come out exactly even when the number of odd repos is even

    Returns (dev_iids, test_iids), each sorted.
    """

    if len(iids) != len(repos):
        raise ValueError("iids and repos must have the same length")
    if len(set(iids)) != len(iids):
        raise ValueError("duplicate instance iids")


    # 1. Group iids by repo
    by_repo: dict[str, list[str]] = defaultdict(list)
    for iid, repo in zip(iids, repos):
        by_repo[repo].append(iid)

    rng = random.Random(seed)
    dev: list[str] = []
    test: list[str] = []
    extra_to_dev = True

    # 2. Process repos in sorted order
    for repo in sorted(by_repo):
        group = sorted(by_repo[repo])
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
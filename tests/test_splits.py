import random
import pytest
import hashlib
import json

from collections import Counter
from faultline_eval.splits import stratified_split
from faultline_eval.data import load_lite, load_split, ROOT
# --------------------------------------------------------------------------------------------------------------------------------------------------
# Tests for stratified_split function
# --------------------------------------------------------------------------------------------------------------------------------------------------
def toy():
    iids = [f"r{i}" for i in range(7)] + [f"s{i}" for i in range(4)] + [f"t{i}" for i in range(3)]
    repos = ["r"] * 7 + ["s"] * 4 + ["t"] * 3
    return iids, repos


def test_disjoint_and_complete():
    iids, repos = toy()
    dev, test = stratified_split(iids, repos, seed=27)

    assert set(dev).isdisjoint(test)
    assert set(dev) | set(test) == set(iids)


def test_same_seed_same_result():
    iids, repos = toy()
    dev_1, test_1 = stratified_split(iids, repos, seed=34)
    dev_2, test_2 = stratified_split(iids, repos, seed=34)

    assert dev_1 == dev_2
    assert test_1 == test_2


def test_different_seed_different_result():
    iids, repos = toy()
    dev_1, test_1 = stratified_split(iids, repos, seed=66)
    dev_2, test_2 = stratified_split(iids, repos, seed=68)

    assert (dev_1, test_1) != (dev_2, test_2)


def test_totals_balanced():
    iids, repos = toy()
    dev, test = stratified_split(iids, repos, seed=0)

    assert len(dev) == len(test) == 7


def test_per_repo_counts_differ_by_at_most_one():
    iids, repos = toy()
    repo_of = dict(zip(iids, repos))
    dev, test = stratified_split(iids, repos, seed=1)

    dev_counts = Counter(repo_of[i] for i in dev)
    test_counts = Counter(repo_of[i] for i in test)

    for repo in set(repos):
        assert (abs(dev_counts[repo] - test_counts[repo]) <= 1)


def test_input_order_does_not_matter():
    iids, repos = toy()
    pairs = list(zip(iids, repos))
    random.Random(99).shuffle(pairs)
    shuffled_iids, shuffled_repos = zip(*pairs)

    a = stratified_split(iids, repos, seed=5)
    b = stratified_split(list(shuffled_iids), list(shuffled_repos), seed=5)

    assert a == b


def test_mismatched_lengths_raise():
    with pytest.raises(ValueError):
        stratified_split(["1", "2"], ["1"], seed=0)


def test_duplicate_iids_raise():
    with pytest.raises(ValueError):
        stratified_split(["1", "1"], ["1", "1"], seed=0)


# --------------------------------------------------------------------------------------------------------------------------------------------------
# Tests for commited split
# --------------------------------------------------------------------------------------------------------------------------------------------------
EXPECTED_DEV_HASH = "e17b15285c13f9929fdfe1ce9a936f1a79cc491b5a91ecf11a46591a12025cda"
EXPECTED_TEST_HASH = "70d058f66cafd6d085bd9439ca77241e0e9eee48a6662f3116b84cc0c008e33f"
SPLITS_DIR = ROOT / "data" / "splits"

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_frozen_hashes_match_constants_and_meta():
    meta = json.loads((SPLITS_DIR / "split_meta.json").read_text())
    assert sha256(SPLITS_DIR / "dev.txt") == EXPECTED_DEV_HASH == meta["dev_hash"]
    assert sha256(SPLITS_DIR / "test.txt") == EXPECTED_TEST_HASH == meta["test_hash"]


def test_frozen_split_sizes_and_disjoint():
    dev, test = load_split("dev"), load_split("test")
    assert len(dev) == len(test) == 150
    assert set(dev).isdisjoint(test)


def test_frozen_split_covers_lite():
    lite_ids = set(load_lite()["test"]["instance_id"])
    assert set(load_split("dev")) | set(load_split("test")) == lite_ids


def test_load_split_rejects_unknown():
    with pytest.raises(ValueError):
        load_split("smoke")
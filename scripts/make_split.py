import json
import hashlib
from datetime import date
from pathlib import Path
from collections import Counter

import pandas as pd

from faultline_eval.data import LITE_REVISION, load_lite
from faultline_eval.splits import stratified_split

SEED = 20261027
ROOT = Path(__file__).resolve().parents[1]
FEATURES_CSV = ROOT / "data" / "derived" / "case_features.csv"

STRATA_COLS = ["repo", "any_mention", "traceback_misleads"]

ds = load_lite()
test = ds["test"]

# Write dev and test iids into text files
features = pd.read_csv(FEATURES_CSV).set_index("instance_id")

iids = list(test["instance_id"])
assert set(iids) == set(features.index)

strata = ["|".join(str(features.at[i, c]) for c in STRATA_COLS) for i in iids]

dev_split, test_split = stratified_split(iids, strata, seed=SEED)
assert not set(ds["dev"]["instance_id"]) & set(ds["test"]["instance_id"])
assert len(dev_split) == len(test_split) == 150

out = ROOT / "data" / "splits"
out.mkdir(parents=True, exist_ok=True)
if (out / "dev.txt").exists() or (out / "test.txt").exists() or (out / "split_meta.json").exists():
    raise FileExistsError("Split already frozen. Delete data/splits/ deliberately to regenerate.")

dev_text = "\n".join(dev_split) + "\n"
test_text = "\n".join(test_split) + "\n"

dev_hash = hashlib.sha256(dev_text.encode()).hexdigest()
test_hash = hashlib.sha256(test_text.encode()).hexdigest()

repo_of = dict(zip(test["instance_id"], test["repo"]))

dev_counts = Counter(repo_of[i] for i in dev_split)
test_counts = Counter(repo_of[i] for i in test_split)

repo_counts = {
    repo: {"dev": dev_counts[repo], "test": test_counts[repo]} 
    for repo in sorted(set(repo_of.values()))    
}

stratum_of = dict(zip(iids, strata))
dev_s = Counter(stratum_of[i] for i in dev_split)
test_s = Counter(stratum_of[i] for i in test_split)
stratum_counts = {
    s: {"dev": dev_s[s], "test": test_s[s]} for s in sorted(set(strata))
}

split_meta = {
    "seed": SEED,
    "dataset": "SWE-bench_Lite",
    "revision": LITE_REVISION,
    "repo_counts": repo_counts,
    "stratified_on": STRATA_COLS,
    "stratum_counts": stratum_counts,
    "date": date.today().isoformat(),
    "n_dev": len(dev_split),
    "dev_hash": dev_hash,
    "n_test": len(test_split),
    "test_hash": test_hash
}

(out / "dev.txt").write_bytes(dev_text.encode())
(out / "test.txt").write_bytes(test_text.encode())

with open(out / "split_meta.json", "w", encoding="utf-8") as f:
    json.dump(split_meta, f, indent=4)
    f.write("\n")
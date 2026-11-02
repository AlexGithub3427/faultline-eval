"""
Balance check for the frozen dev/test split

Reads data/derived/case_features.csv and data/splits/{dev,test}.txt.
Prints a balance table (dev vs test, SMD per feature), leak-case placement,
and gold-file overlap between splits.
"""

from math import sqrt
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FEATURES_CSV = ROOT / "data" / "derived" / "case_features.csv"
SPLITS_DIR = ROOT / "data" / "splits"

BOOL_FEATURES = [
    "any_mention",
    "has_traceback",
    "gold_in_traceback",
    "traceback_misleads"
]

NUMERIC_FEATURES = ["n_hunks", "lines_added"]
LEAK_CASES = ["django__django-12453", "sympy__sympy-22005"]
SMD_THRESHOLD = 0.2
SMD_WARNING = 0.1

def read_ids(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]

def smd_bool(a: pd.Series, b: pd.Series) -> float:
    p1, p2 = a.mean(), b.mean()
    denom = sqrt((p1 * (1-p1) + p2 * (1-p2)) / 2)
    return 0.0 if denom == 0 else (p1 - p2) / denom

def smd_numeric(a: pd.Series, b: pd.Series) -> float:
    m1, m2 = a.mean(), b.mean()
    v1, v2 = a.var(ddof=1), b.var(ddof=1)
    denom = sqrt((v1 + v2) / 2)
    return 0.0 if denom == 0 else (m1- m2) / denom

def main():
    df = pd.read_csv(FEATURES_CSV)
    dev_ids = read_ids(SPLITS_DIR / "dev.txt")
    test_ids = read_ids(SPLITS_DIR / "test.txt")

    assert set(dev_ids) | set(test_ids) == set(df.instance_id)
    assert len(dev_ids) == len(test_ids) == 150

    dev_set, test_set = set(dev_ids), set(test_ids)
    df["split"] = df.instance_id.map(lambda i : "dev" if i in set(dev_ids) else "test")
    dev = df[df.split == "dev"]
    test = df[df.split == "test"]


    # 1. Balance table
    rows = []
    for col in BOOL_FEATURES:
        rows.append({
            "feature": col,
            "dev": dev[col].mean(),
            "test": test[col].mean(),
            "smd": smd_bool(dev[col], test[col])
        })

    for col in NUMERIC_FEATURES:
        rows.append({
            "feature": col,
            "dev": dev[col].mean(),
            "test": test[col].mean(),
            "smd": smd_numeric(dev[col], test[col])
    })

    table = pd.DataFrame(rows)
    table["ok"] = table.smd.abs() < SMD_THRESHOLD
    print(table.to_string(index=False, float_format="%.3f"))

    # 2. Leak-case placement
    leak_dev = [c for c in LEAK_CASES if c in dev_set]
    leak_test = [c for c in LEAK_CASES if c in test_set]
    print("\nLeak cases:")
    for c in LEAK_CASES:
        print(f"    {c}: {"dev" if c in dev_set else "test"}")

    n_diff_dev, n_diff_test = int(dev.issue_has_diff.sum()), int(test.issue_has_diff.sum())
    print(f"\nIssues with a diff: {n_diff_dev} in dev, {n_diff_test} in test (judged by placement, not SMD)")

    # 3. Gold-file overlap
    dev_gold = set(dev.gold_file)
    shared = test.gold_file.isin(dev_gold)
    n_shared_files = len(set(test.gold_file)& dev_gold)
    print(
        f"\nGold-file overlap: {shared.sum()}/{len(test)} test cases "
        f"({shared.mean():.0%}) have a gold file that is also gold in dev; "
        f"{n_shared_files} distinct shared files"
    )

    # 4. Verdict
    failures = []
    bad = table.loc[~table.ok, "feature"].tolist()
    if bad:
        failures.append(f"|SMD| >= {SMD_THRESHOLD} for: {", ".join(bad)}")
    if len(leak_dev) == len(LEAK_CASES) or len(leak_test) == len(LEAK_CASES):
        failures.append("both leak cases are in the same split")

    print()
    if failures:
        print("FAIL")
        for f in failures:
            print(f"    -  {f}")
    else:
        print("PASS")

if __name__ == "__main__":
    main()

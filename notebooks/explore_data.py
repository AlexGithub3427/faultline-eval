import statistics
import random
import re

import pandas as pd
from pathlib import Path
from collections import Counter

from faultline_eval.data import load_lite, gold_file_shape

ds = load_lite()
test = ds["test"]


# ---------------------------------------------------------------------------
# Traceback frame extraction
# ---------------------------------------------------------------------------

FRAME_PATTERNS = [
    re.compile(r'File "([^"]+)", line (\d+), in (\S+)'),        # standard Python
    re.compile(r'File (\S+\.pyc?):(\d+), in (\S+)'),            # IPython 8+
    re.compile(r'^\s*(\S+\.pyc?) in (\S+)\(', re.MULTILINE),    # older IPython (incl. Python 2 .pyc)
]


def normalize_frame_path(p: str) -> str:
    # Python 2 tracebacks report compiled files (art3d.pyc); compare as source.
    return p[:-1] if p.endswith(".pyc") else p


def extract_frame_paths(text):
    hits = []
    for pat in FRAME_PATTERNS:
        hits += [(m.start(), normalize_frame_path(m.group(1))) for m in pat.finditer(text)]
    return [p for _, p in sorted(hits)]   # keep document order for "last frame"


# Regression checks for formats seen in the data (matplotlib-23562 used .pyc).
assert extract_frame_paths(
    "/home/u/site-packages/mpl_toolkits/mplot3d/art3d.pyc in get_facecolors(self)"
) == ["/home/u/site-packages/mpl_toolkits/mplot3d/art3d.py"]
assert extract_frame_paths('File "/x/django/db/models/query.py", line 10, in get') == [
    "/x/django/db/models/query.py"
]
assert extract_frame_paths("File /x/sympy/core/expr.py:42, in foo") == ["/x/sympy/core/expr.py"]
# A user-cell-only IPython frame or <string> frame is not a repo file.
assert extract_frame_paths("<ipython-input-3-e2060d5eec73> in <module>") == []
assert extract_frame_paths('File "<string>", line unknown') == []


# ---------------------------------------------------------------------------
# In-issue diff detection (solution leakage, e.g. sympy-22005)
# ---------------------------------------------------------------------------

DIFF_PATTERNS = [
    re.compile(r"^diff --git ", re.MULTILINE),
    re.compile(r"^--- [a-z]/\S+.*\n\+\+\+ [a-z]/", re.MULTILINE),
    re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@", re.MULTILINE),
]


def has_diff(text: str) -> bool:
    return any(p.search(text) for p in DIFF_PATTERNS)


def diff_touches(text: str, repo_path: str) -> bool:
    # Diff headers use repo-relative paths (keep src/ or lib/ prefixes).
    # Prefix may be a/ b/ or git mnemonic prefixes like i/ w/ c/.
    return bool(re.search(
        rf"^(?:diff --git [a-z]/|--- [a-z]/|\+\+\+ [a-z]/){re.escape(repo_path)}(?!\w)",
        text, re.MULTILINE,
    ))


assert has_diff("diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,2 @@\n")
assert has_diff("@@ -240,7 +240,7 @@ def f():")
assert not has_diff("I tried --- a few things\n+++ nothing worked")
assert diff_touches("diff --git a/sympy/solvers/polysys.py b/sympy/solvers/polysys.py",
                    "sympy/solvers/polysys.py")
assert has_diff("--- i/tests/test_sqlite.py\n+++ w/tests/test_sqlite.py\n")
assert diff_touches("diff --git i/tests/test_sqlite.py w/tests/test_sqlite.py",
                    "tests/test_sqlite.py")


# ---------------------------------------------------------------------------
# Inspection helpers
# ---------------------------------------------------------------------------

def show_samples(idx, pattern_for, k=5, seed=42, width=150):
    rng = random.Random(seed)
    for i in rng.sample(idx, k=min(k, len(idx))):
        text = issues[i].replace("\\", "/")
        m = re.search(pattern_for(i), text)
        s = max(0, m.start() - width) if m else 0
        e = (m.end() + width) if m else 2 * width
        print(f"--- {ids[i]}  gold: {files[i]}")
        print(text[s:e].replace("\r", " ").replace("\n", " "), "\n")


def inspect_case(iid, width=200):
    i = df.index[df.instance_id == iid][0]
    path, import_path, _, _ = file_names[i]
    text = issues[i].replace("\\", "/")

    print(f"=== {iid}  gold: {path}")
    print("frames:")
    for p in extract_frame_paths(text):
        print("   ", p)

    print("gold path mentions:")
    for m in re.finditer(re.escape(import_path) + r"c?", text):
        s, e = max(0, m.start() - width), m.end() + width
        print("   ...", text[s:e].replace("\r", " ").replace("\n", " "), "...\n")


def show_traceback_context(iid, before=300, after=1500):
    i = df.index[df.instance_id == iid][0]
    text = issues[i]
    k = text.find("Traceback")
    print(f"=== {iid}  gold: {file_names[i][0]}")
    if k == -1:
        print("(no literal 'Traceback' in text)")
    else:
        print(text[max(0, k - before): k + after])
    print()


def show_diff_context(iid, before=300, after=1500):
    i = df.index[df.instance_id == iid][0]
    text = issues[i]
    m = next((m for p in DIFF_PATTERNS if (m := p.search(text))), None)
    print(f"=== {iid}  gold: {file_names[i][0]}")
    if m is None:
        print("(no diff pattern matched)")
    else:
        print(text[max(0, m.start() - before): m.start() + after])
    print()


def file_kind(path):
    name = path.rsplit("/", 1)[-1]
    if "/tests/" in path or "/testing/" in path or name.startswith("test_") or name == "conftest.py":
        return "test"
    if path.startswith(("doc/", "docs/")) or name.endswith((".rst", ".md", ".txt")):
        return "doc"
    if name in {"setup.py", "setup.cfg", "pyproject.toml", "tox.ini"}:
        return "config"
    return "source"


assert file_kind("tests/test_foo.py") == "test"
assert file_kind("django/conftest.py") == "test"
assert file_kind("docs/usage.rst") == "doc"
assert file_kind("setup.py") == "config"
assert file_kind("src/_pytest/python.py") == "source"


# ---------------------------------------------------------------------------
# REPO DISTRIBUTION
# ---------------------------------------------------------------------------

repo_counts = Counter(test["repo"])
print(repo_counts)
EXPECTED_REPO_COUNTS = {
    "django/django": 114,
    "sympy/sympy": 77,
    "matplotlib/matplotlib": 23,
    "scikit-learn/scikit-learn": 23,
    "pytest-dev/pytest": 17,
    "sphinx-doc/sphinx": 16,
    "astropy/astropy": 6,
    "psf/requests": 6,
    "pylint-dev/pylint": 6,
    "pydata/xarray": 5,
    "mwaskom/seaborn": 4,
    "pallets/flask": 3,
}
assert repo_counts == EXPECTED_REPO_COUNTS


# ---------------------------------------------------------------------------
# GOLD FILE SHAPE
# ---------------------------------------------------------------------------

gold_file_shapes = [gold_file_shape(patch) for patch in test["patch"]]
assert all(len(case) == 1 for case in gold_file_shapes)
shapes = [case[0] for case in gold_file_shapes]
files, hunks, added, removed = zip(*shapes)

assert set(hunks) <= {1, 2, 3}
assert all(file_kind(f) == "source" for f in files)   # Lite: every gold file is source code
print(f"max lines added: {max(added)}, median lines added: {statistics.median(added)}")
print(f"max lines removed: {max(removed)}, median lines removed: {statistics.median(removed)}")


# ---------------------------------------------------------------------------
# Issue length, file mentions, tracebacks, in-issue diffs
# ---------------------------------------------------------------------------

ids = test["instance_id"]
repos = test["repo"]
issues = test["problem_statement"]

issue_lengths = [len(issue.split()) for issue in issues]
print(min(issue_lengths), statistics.median(issue_lengths), max(issue_lengths))
assert min(issue_lengths) >= 40

file_names = []
for filepath in files:
    import_path = filepath.removeprefix("src/").removeprefix("lib/")
    module = import_path.rsplit(".", 1)[0].replace("/", ".").removesuffix(".__init__")
    parts = filepath.rsplit("/", 2)
    base = "/".join(parts[-2:]) if parts[-1] == "__init__.py" else parts[-1]
    file_names.append((filepath, import_path, module, base))


mentions = []
for (path, import_path, module, base), issue, iid, repo in zip(file_names, issues, ids, repos):
    text = issue.replace("\\", "/")

    # file mentions (c? also accepts compiled names like art3d.pyc)
    path_in_issue = bool(re.search(rf"(?<![\w.]){re.escape(import_path)}c?\b", text))
    module_in_issue = bool(re.search(rf"(?<![\w.]){re.escape(module)}(?![\w]|\.\w)", text))
    basename_in_issue = bool(re.search(rf"(?<![\w.]){re.escape(base)}c?\b", text))
    any_mention = path_in_issue or module_in_issue or basename_in_issue

    # tracebacks
    # has_traceback means "the issue shows a traceback"; it may be truncated
    # ("...") or contain only user-code frames, so n_frames can be 0.
    frame_paths = extract_frame_paths(text)
    has_traceback = "Traceback (most recent call last)" in text or bool(frame_paths)
    gold_suffix = "/" + import_path

    def is_gold(p: str):
        return p == import_path or p.endswith(gold_suffix)

    gold_in_traceback = any(is_gold(p) for p in frame_paths)
    gold_is_last_frame = bool(frame_paths) and is_gold(frame_paths[-1])

    # in-issue diffs
    issue_has_diff = has_diff(text)
    diff_touches_gold = issue_has_diff and diff_touches(text, path)

    mentions.append({
        "instance_id": iid,
        "repo": repo,
        "path_in_issue": path_in_issue,
        "module_in_issue": module_in_issue,
        "basename_in_issue": basename_in_issue,
        "any_mention": any_mention,
        "has_traceback": has_traceback,
        "n_frames": len(frame_paths),
        "gold_in_traceback": gold_in_traceback,
        "gold_is_last_frame": gold_is_last_frame,
        "issue_has_diff": issue_has_diff,
        "diff_touches_gold": diff_touches_gold,
    })

df = pd.DataFrame(mentions)
print(df[["has_traceback", "gold_in_traceback", "gold_is_last_frame",
          "issue_has_diff", "diff_touches_gold"]].sum())
print(pd.crosstab(df.any_mention, df.gold_in_traceback, margins=True))

assert not (df.gold_in_traceback & ~df.any_mention).any()
assert not (df.diff_touches_gold & ~df.any_mention).any()


# Known cases found during manual inspection
def row(iid):
    return df.loc[df.instance_id == iid].iloc[0]

assert row("matplotlib__matplotlib-23562").gold_in_traceback      # .pyc frame
assert row("matplotlib__matplotlib-23562").gold_is_last_frame
assert row("matplotlib__matplotlib-23562").any_mention
assert row("sympy__sympy-22005").issue_has_diff                    # fix pasted in issue
assert row("sympy__sympy-22005").diff_touches_gold


# ---------------------------------------------------------------------------
# Manual inspection sections
# ---------------------------------------------------------------------------

# 1. Has a traceback, but the gold file isn't in it
idx1 = df.index[df.has_traceback & ~df.gold_in_traceback].tolist()
print(f"\n=== {len(idx1)} tracebacks without gold file ===")
show_samples(idx1, lambda i: r"Traceback", width=600)

# 2. Mentions an error, but no standard traceback
err = df.index[~df.has_traceback].tolist()
idx2 = [i for i in err if re.search(r"\w+Error\b", issues[i])]
print(f"\n=== {len(idx2)} errors without standard traceback ===")
show_samples(idx2, lambda i: r"\w+Error\b", width=400)

# 3. Gold file is the last frame
idx3 = df.index[df.gold_is_last_frame].tolist()
print(f"\n=== {len(idx3)} gold is last frame ===")
show_samples(idx3, lambda i: re.escape(file_names[i][1]), width=300)

# 4. Traceback present but no repo frames (truncated or user-code only).
#    Reviewed 2026-10-22: all 8 explained; see DATA.md.
odd_cases = df.loc[df.has_traceback & (df.n_frames == 0), "instance_id"].tolist()
print(f"\n=== {len(odd_cases)} tracebacks with no repo frames ===")
print(odd_cases)

# 5. Issues that contain a diff -- read every one of these.
diff_cases = df.loc[df.issue_has_diff, ["instance_id", "diff_touches_gold"]]
print(f"\n=== {len(diff_cases)} issues containing a diff ===")
print(diff_cases.to_string(index=False))


# ---------------------------------------------------------------------------
# Save features
# ---------------------------------------------------------------------------

df["gold_file"] = files
df["n_hunks"] = hunks
df["lines_added"] = added
df["lines_removed"] = removed
df["traceback_misleads"] = (df.n_frames > 0) & ~df.gold_in_traceback

print(df[["path_in_issue", "module_in_issue", "basename_in_issue", "traceback_misleads"]].sum())

out = Path(__file__).resolve().parents[1] / "data" / "derived"
out.mkdir(parents=True, exist_ok=True)
df.to_csv(out / "case_features.csv", index=False)
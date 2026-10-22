# Data

## Source
- Dataset: SWE-bench Lite, `princeton-nlp/SWE-bench_Lite`, revision `6ec7bb89b9342f664a54a6e0a6ea6501d3437cc2`
- Using the 300-case `test` split as the benchmark; the official 23-case `dev` split is used only for smoke tests.
- Lite's own selection criteria (single file edited, ≤3 hunks, no created/removed files, ≥40-word issues, no links/SHAs/PR references): https://www.swebench.com/lite.html, code in `swebench/collect/make_lite`.
- Note: the repo-distribution chart on the SWE-bench website does not match this revision (e.g. it shows Django 127; the data has 114). Counts below are from the data.

## Agent input
- The agent sees only `problem_statement` and the repo at `base_commit`.
- `hints_text` is excluded: it contains issue comments, some written after the fix.

## Ground truth
- Gold files are parsed from `patch` (never `test_patch`) with `unidiff`.
- All 300 cases modify exactly one existing file, with 1–3 hunks. Lines added: median 4.5, max 65. Lines removed: median 1, max 40.
- 18 gold files (6%) are `__init__.py`.
- All 300 gold files are source files (checked for test/doc/config files; none found; asserted in `explore_data.py`).
- Consequence for metrics: with one gold file per case, file-level precision/recall/F1 reduce to hit@k plus number of extra files predicted. Function level is the primary multi-target metric.

## Repo distribution
django 114, sympy 77, matplotlib 23, scikit-learn 23, pytest 17, sphinx 16, astropy 6, requests 6, pylint 6, xarray 5, seaborn 4, flask 3.
Results are reported overall, by Django / sympy / other, and macro-averaged by repo. Repos with <10 cases are not reported individually.

## Filters
None beyond Lite's selection criteria. No cases are excluded; leakage cases are flagged and reported separately (see below).

## Case features (`data/derived/case_features.csv`)
| Feature | Count | % |
|---|---|---|
| Issue mentions gold file (path, module, or basename) | 86 | 29% |
| — by path | 65 | |
| — by module | 21 | |
| — by basename | 68 | |
| No mention of gold file anywhere | 214 | 71% |
| Has a traceback | 71 | 24% |
| Gold file in traceback | 48 | 16% |
| Gold file is last frame | 29 | 10% |
| Traceback has frames but not the gold file (`traceback_misleads`) | 16 | 5% |
| Traceback with no repo frames | 7 | 2% |
| Issue contains a diff | 4 | 1% |
| — diff touches the gold file | 2 | 1% |

Issue length (words): min 41, median 134, max 1892.

### Feature definitions
- `has_traceback`: the issue *shows* a traceback — it contains `Traceback (most recent call last)` or at least one parsed frame. It does not guarantee frames: 7 cases have `n_frames = 0` because the reporter truncated the traceback to `...` (astropy-14365, django-14016, matplotlib-24265, sympy-22005, sympy-24102) or the only frame is user code such as `<ipython-input-...>` or `<string>` (matplotlib-23299, sympy-20590). All 7 were read by hand.
- `gold_in_traceback` / `gold_is_last_frame`: a parsed frame path equals, or ends with, the gold file's import-relative path.
- `traceback_misleads`: the traceback has frames, but none is the gold file.
- `issue_has_diff`: the issue contains `diff --git`, a `--- a/` / `+++ b/` header pair, or a `@@ -N,N +N,N @@` hunk header.
- `diff_touches_gold`: a diff header in the issue names the gold file.

### Matcher validation
Validated by reading fixed-seed random samples (seed 42) and by hand-reading every case in the edge-case lists. Fixes found this way:
- Normalized Windows backslashes; matched on import-relative path (`lib/`/`src/` stripped). Path hits rose 48 → 64.
- `__init__.py` basename produced a false positive (matched another package's `__init__.py`); now matched with parent dir.
- Added IPython traceback formats (old and 8+) and relative-path frames. Gold-in-traceback rose 32 → 47.
- Python 2 `.pyc` frames and mentions (matplotlib-23562: `.../mplot3d/art3d.pyc in get_facecolors`) were missed by both the frame parser and the mention regexes. Frame paths are now normalized `.pyc` → `.py`, and mention regexes accept a trailing `c`. Gold-in-traceback 47 → 48; mentions 85 → 86.
- Invariants asserted: every gold-in-traceback case is also an issue mention; every diff-touches-gold case is also an issue mention; regression asserts for each frame format and for the known cases above.

Known gaps:
- pytest-style traces (`file.py:123: in func`, `>` / `E` lines; e.g. sympy-18057) are not parsed as frames.
- Module matching rejects attribute references like `django.db.models.Q`.
- Some issues contain duplicated text (title and body repeated, e.g. sympy-24102). Harmless; left as-is.

## Leakage in issue text
- **In-issue diffs (measured).** 4 issues contain a diff:
  - django-12453, sympy-22005: the diff touches the gold file — the fix, or something close to it, is in the issue. Flagged as solution leaks.
  - django-12113, django-15695: reproduction diffs to test files (`tests/test_sqlite.py` settings; a new failing test in `tests/migrations/test_operations.py`). They show how to trigger the bug, not the fix. Not counted as solution leaks.
  - Diff headers may use git's mnemonic prefixes (`i/`, `w/`, seen in django-12113) as well as `a/`/`b/`; the detector accepts any single-letter prefix.
  - Final solution-leak set: **django-12453, sympy-22005**.
- **Prose solution hints (not measured).** Some issues describe the fix in words, e.g. django-14672 names the missing `make_hashable` call in `ManyToManyRel`. This is not detected by any feature. Hand-reading failures will give a sense of how common it is; an LLM pass over all issues may be added later.
- **Reporting rule (decided before any results):** headline metrics are reported on all cases and on cases without a solution-leak diff (i.e. excluding django-12453 and sympy-22005).

## Split
TODO: 150/150, stratified by repo, seed ___, IDs in `splits/dev.txt` and `splits/test.txt`.
- Odd-count repos (sympy, matplotlib, scikit-learn, pytest, xarray, flask) alternate the extra case between dev and test so totals are exactly 150/150.
- Balance check (|SMD| < 0.1 as a guide) on `any_mention`, `has_traceback`, `gold_in_traceback`, `traceback_misleads`, `issue_has_diff`, `n_hunks`, `lines_added`. With only 4 diff cases (2 solution leaks), check where each lands rather than relying on SMD.
- Report the share of test gold files that also appear as gold files in dev.
- Split generated once and frozen; any rejected split is recorded here with the reason.
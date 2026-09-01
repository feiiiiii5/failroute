# ARTIFACT — reproduction notes for the failroute study

Generated 2026-08-31 12:57 (UTC+8) by the outsourced P6 task.
Second pass 2026-08-31 18:1x (UTC+8), task S3: §5 added from a clean-virtualenv
reproduction; the §1 version-pointer discrepancy resolved; three reproducibility
defects found (§5.4, §5.5, §5.6).
This file describes what it takes to re-run the study from this repository.
Every statement below is backed by a command that was actually run in this
repository, with its output quoted. Items that were **not** run are labelled
as such rather than described as working.

---

## 0. Read this first: two things that break a naive reproduction

### 0.1 The repository path contains non-ASCII characters

The working copy lives under a directory whose name is Chinese
(`…/申请季/新项目-failroute`). Under that path an *editable* install of this
package does not work: the generated `.pth` pointer is written with a
mangled encoding, so `import failroute` fails even though `pip show`
reports the package as installed.

**Consequence:** every CLI invocation in this artifact must carry
`PYTHONPATH=src`. Without it the documented commands fail at import.

```
PYTHONPATH=src .venv/bin/python -m failroute --version
failroute 0.5.1
```

A reproducer who clones to an ASCII path does not need `PYTHONPATH=src`
if they install the package properly. Both routes are given below.

### 0.2 The pipeline is not idempotent with respect to hand-curated files

Three commands in the paper's Reproduction block **overwrite files that
contain manually written content**. Re-running them after the fact destroys
the study inputs rather than reproducing them:

| Command | Overwrites | Why re-running is destructive |
|---|---|---|
| `tools/draw_sample.py --n 80 --seed 20260831` | `paper/sample.jsonl` | the sample is the unit of annotation; a regenerated sample no longer matches `paper/annotations.csv` |
| `tools/compare_linters_corpus.py` | `bench/corpus-linter-comparison.json` | this file now also carries the merged `linters.semgrep` results; a plain re-run drops them |
| `tools/merged_pr_recall.py` | `paper/merged-pr-recall.csv` | the `note` column holds hand-written per-PR miss reasons |

🔴 **These three were deliberately NOT re-run during P6 verification.** Their
correct behaviour is therefore *unverified*, not confirmed.

---

## 1. Environment

| Item | Value | How measured |
|---|---|---|
| Python (repo venv) | the interpreter at `.venv/bin/python` | — |
| Tool version reported by the CLI | **`failroute 0.5.1`** | `PYTHONPATH=src .venv/bin/python -m failroute --version` |
| Test suite | **130 tests, exit code 0** | `.venv/bin/python -m pytest -q` → 130 progress dots, `[100%]`, `exit=0`, no `F`/`E` characters |
| Corpus on disk | **146 MB** | `du -sh paper/corpus` |
| Virtualenv on disk | **453 MB** | `du -sh .venv` |
| Wall time, full test suite | **≈1.5 s** | `time .venv/bin/python -m pytest -q` → `1.549 total` |
| Network needed | only for `tools/fetch_corpus.py` (pinned sdists from PyPI) | all other scripts read from `paper/corpus/` |

🔴 **Version pointer — resolved on the second reproduction pass (08-31 18:1x, §5).**
The `0.5.1` reading above is **superseded**. Re-measured in a clean virtualenv built
from `pyproject.toml`:

```
$ /tmp/fr_venv/bin/failroute --version
failroute 0.7.0
```

`pyproject.toml` (`version = "0.7.0"`), `src/failroute/__init__.py`
(`__version__ = "0.7.0"`) and the CLI now agree. The §0.1 `PYTHONPATH=src` requirement
is **independent of this** and still applies to the in-tree `python -m failroute` form;
it is *not* needed for the installed console script (verified in §5.1).

> **Update (H batch I2, 09-01):** the release was bumped to **0.8.0** and the same
> four locations were synchronised again (`pyproject.toml`, `__init__.py`,
> `action/action.yml` default, README `rev:`), enforced by
> `tests/test_release_consistency.py` and `tools/closure_check.py`. The historical
> 0.5.1 → 0.7.0 resolution above is kept as recorded.

---

## 2. What was actually re-run, and what it produced

### 2.1 Test suite

```
$ .venv/bin/python -m pytest -q
........................................................................ [ 55%]
..........................................................               [100%]
$ echo $?
0
```

130 dots, no failures, exit 0. Note that on this setup the usual
`130 passed in Ns` summary line was **not** emitted by `-q`; the pass claim
above rests on the exit code and the absence of failure characters, not on a
summary line.

### 2.2 Scanner, end to end on one corpus package

Re-scanned `garak` from the pinned corpus into a temporary file and compared
against the committed findings:

```
scan root exists: True paper/corpus/garak-0.16.0/garak
exit 1 | stderr tail: 16 finding(s) exported to /tmp/repro_garak.jsonl
re-scanned findings: 16 | paper/scan/garak.jsonl lines: 16 | match: True
```

The scan is **reproducible for this package**: 16 findings now, 16 findings
recorded in the paper. This is the same 16 that the P5 cross-tool comparison
uses for garak.

🔴 **Exit-code gotcha:** the CLI exits **1** when it finds anything, even
though the run succeeded and the export was written. A reproducer whose
script runs under `set -e`, or a CI step that treats non-zero as failure,
will abort on a *successful* scan. Either document this or change the exit
semantics.

### 2.3 Derived-statistics scripts (safe to re-run, they only write their own output)

```
$ .venv/bin/python tools/compute_intervals.py
wrote paper/intervals.json (41 cells)

$ .venv/bin/python tools/make_figures.py
wrote paper/figures/fig1_defect_rate_by_package.{pdf,png}
```

Both are deterministic given their inputs and both were re-run to completion
during verification.

---

## 3. What was NOT verified

The P6 task was cut short by the call budget. The following remain unverified:

- `tools/fetch_corpus.py` — not run; it re-downloads ~146 MB of pinned sdists.
- The scan for the other **seven** corpus packages (only `garak` was re-run).
- The 649-finding total and the 253 / 39.0% coverage figures — not
  independently re-derived by re-running `coverage_union.py`.
- `tools/draw_sample.py`, `tools/compare_linters_corpus.py`,
  `tools/merged_pr_recall.py` — deliberately not run, see §0.2.
- **A clean-venv install from `pyproject.toml` was never attempted.** All
  results above come from the repository's existing `.venv`. A reviewer
  following this document should still perform the clean-install path,
  because that is the one place where §0.1 is likely to bite.

Nothing in this file should be read as "the whole pipeline reproduces".
It should be read as: the test suite and one end-to-end scan do, the
derived-statistics scripts do, and the corpus-fetch plus three
hand-curated-overwriting steps have not been checked.

---

## 4. Minimal safe reproduction, as verified

```bash
cd <repo-root>

# 1. tests
.venv/bin/python -m pytest -q                 # expect exit 0, 130 tests

# 2. scanner on the already-fetched corpus (no network)
PYTHONPATH=src .venv/bin/python -m failroute \
    --export-findings /tmp/repro_garak.jsonl \
    --repo-name garak paper/corpus/garak-0.16.0/garak
# expect: "16 finding(s) exported", exit code 1 (findings present)

# 3. derived statistics and figures (overwrite only their own outputs)
.venv/bin/python tools/compute_intervals.py
.venv/bin/python tools/make_figures.py     # needs matplotlib, not declared in pyproject
```

---

## 5. Second reproduction pass — clean virtualenv, full corpus (08-31 18:1x, task S3)

Every statement below comes from a command run in this pass, on this machine, against a
**newly created** virtualenv. Nothing in `paper/` or `bench/` in the repository was
modified: destructive scripts ran against a throwaway copy at `/tmp/fr_repro` (with
`paper/corpus` symlinked back read-only), because `paper/` and `bench/` are **untracked
in git** and therefore not recoverable with `git checkout`. Wall time ≈ 25 min, most of
it `pylint` (§5.4).

### 5.1 Clean install from `pyproject.toml` — the §3 gap, now closed

```
$ uv venv --python 3.11 /tmp/fr_venv
$ uv pip install --python /tmp/fr_venv/bin/python '.[test]'      # 1.7 s
$ /tmp/fr_venv/bin/python -m failroute --version
failroute 0.7.0                     # exit 0
$ /tmp/fr_venv/bin/failroute --version
failroute 0.7.0                     # exit 0
$ /tmp/fr_venv/bin/python -c "import failroute; print(failroute.__file__)"
/tmp/fr_venv/lib/python3.11/site-packages/failroute/__init__.py
```

**A non-editable install from this path works.** §0.1's `.pth` breakage is specific to
`pip install -e`. So `PYTHONPATH=src` is a property of the *editable / in-tree*
invocation, not of the package: a reviewer who runs `pip install .` then `failroute …`
needs no workaround.

### 5.2 Test suite — clean interpreter, in-tree source

```
$ cd /tmp/fr_repro && PYTHONPATH=src /tmp/fr_venv/bin/python -m pytest -q
........................................................................ [ 55%]
..........................................................               [100%]
```

130 tests (73 + 57 dots), no `F`/`E`, 1.6 s wall, on `pytest 9.1.1` rather than the repo
venv's version. As in §2.1, `-q` emitted no `N passed` summary line here, so the pass
claim rests on the dot count and the absence of failure characters.

### 5.3 Scanner over **all eight** packages — the §3 gap, now closed

```
PYTHONPATH=src /tmp/fr_venv/bin/python -m failroute \
    --export-findings <out> --repo-name <name> paper/corpus/<dir>/<scan-root>
```

| Corpus dir | scan root | findings | vs `paper/scan/*.jsonl` |
|---|---|---|---|
| inspect_ai-0.3.260 | `src/inspect_ai` | 324 | match |
| pydantic_ai_slim-2.36.0 | `.` | 103 | match |
| deepteam-1.0.9 | `deepteam` | 140 | match |
| trl-1.12.0 | `trl` | 28 | match |
| garak-0.16.0 | `garak` | 16 | match |
| smolagents-1.26.0 | `src/smolagents` | 13 | match |
| uqlm-0.6.5 | `uqlm` | 14 | match |
| fickling-0.1.12 | `fickling` | 11 | match |
| **Total** | | **649** | **match** |

Field-by-field comparison over all 649 findings:

```
compared 649 findings, non-repo field mismatches: 0
finding keys: {context_after, context_before, end_lineno, file,
               function_signature, id, lineno, message, mode, repo, rule}
```

The scan is reproducible **for every field except `repo`**, which is just the
`--repo-name` label the caller supplies (this pass passed the versioned directory name,
which is why a naive byte-compare showed ≈649 cosmetic diffs on that single key). §2.2's
exit-code gotcha (exit **1** on a successful scan that found something) reproduced on
all eight runs.

### 5.4 🔴 What this pass could **not** re-derive

| Item | Outcome |
|---|---|
| `tools/coverage_union.py` | **Resolved (H batch, 09-01).** History: the original script hard-coded `.venv/bin/python` as a relative path and died on its own 900 s pylint timeout, so the union figure was NOT re-derived by the earlier pass. The script was fixed (interpreter resolution with env override, pylint timeout 1800 s, parameterised findings dir) and re-run live: **the 253 / 39.0% figure was reproduced on the v0.7.0 finding set (56 s wall)**, and the final v0.8.0 baseline (621 findings) measures **250 / 621 = 40.3%** (49 s). Re-run: `PYTHONPATH=src .venv/bin/python tools/coverage_union.py --findings-dir paper/scan --out /tmp/u4.json`. |
| `tools/compare_linters_corpus.py` | **Not run.** Same linter cost, and it overwrites `bench/corpus-linter-comparison.json`, which now also carries the merged `linters.semgrep` results. §0.2's warning stands, untested. |
| semgrep (5-tool union, 279 / 43.0%) | **Resolved (H batch, 09-01).** semgrep 1.175.0 installed and run live via `tools/coverage_union.py --with-semgrep`: **279 / 43.0% reproduced on the v0.7.0 finding set (73 s)**; the v0.8.0 baseline measures **269 / 621 = 43.3%** (63 s). |
| `tools/make_figures.py` | **Needs an undeclared dependency.** On the clean venv: `ModuleNotFoundError: No module named 'matplotlib'`. After installing matplotlib it produced **fig1, fig2 and fig3** (each `.pdf` + `.png`) — §2.3 and §4 mention only fig1. `matplotlib` is absent from `pyproject.toml`, so the documented clean install cannot build the figures at all. |
| `tools/fetch_corpus.py` (download path) | **Not re-downloaded.** `--verify` (disk vs lock, no network) ran clean: `8/8 packages verified`. Byte-identical re-download therefore stays unverified, though every input is sha256-locked. |

### 5.5 🔴 `tools/draw_sample.py` no longer regenerates `paper/sample.jsonl`

The most consequential finding of this pass, and it is a **content** problem, not a
plumbing one. The script was run with `--out /tmp/...` so the committed sample was not
touched.

```
$ /tmp/fr_venv/bin/python tools/draw_sample.py --n 80 --seed 20260831 --out /tmp/fr_repro_sample.jsonl
seed=20260831  sha256=fca020c56c2b259928e4a30ad17819a8
按规则: {'masked-exception': 1, 'no-action': 24, 'silent-fallback': 52, 'silent-suppress': 3}
按包  : {'garak': 3, 'deepteam': 14, 'fickling': 2, 'inspect_ai': 42, 'pydantic_ai_slim': 11, 'smolagents': 2, 'trl': 4, 'uqlm': 2}

committed sample rule mix: {'silent-fallback': 49, 'no-action': 23, 'implicit-fallback': 4, 'silent-suppress': 3, 'masked-exception': 1}
regenerated 78 unique (file,line,rule) / committed 74 unique / intersection 39
```

`paper/sample.jsonl` was drawn from the **pre-fix** scan, which still contained 10
`implicit-fallback` findings. `DRAFT.md` §4.4 reports that fixing that rule took
`implicit-fallback` from 10 to 0 on the same 563k lines. The committed sample still holds
4 of those now-nonexistent findings, so:

* the n = 80 sample and the 649-finding population are **different vintages**;
* with the seed frozen, the draw cannot be reproduced from the current `paper/scan/`;
* only 39 of the 80 sampled items remain reachable, and the stratum allocation shifts
  (`no-action` 23→24, `silent-fallback` 49→52, `inspect_ai` 41→42, `fickling` 3→2).

🔴 **Do not "fix" this by re-running the script into place** — that would silently change
which 80 findings the published label table describes. The two honest options are to
re-draw *and* re-label, or to state in §4.0/§4.2 that the sample frame is the pre-fix
659-finding scan. That is an editorial decision for the author, not a mechanical one.

### 5.6 `tools/merged_pr_recall.py` — the 1-of-10 result does reproduce

Ran in the sandbox copy (30.5 s, needs `gh` + network):

```
$ /tmp/fr_venv/bin/python tools/merged_pr_recall.py
...
wrote /private/tmp/fr_repro/paper/merged-pr-recall.csv

rerun rows 10 | committed rows 70 | committed belongs_to_family=yes 10
rerun detected=yes: ['cvs-health/uqlm#450']
committed detected=yes: ['cvs-health/uqlm#450']
same 10-PR candidate set? True
pre-fix shas match? True
```

The headline recall figure (1 of 10; the single hit being uqlm#450) reproduces
independently, with an identical candidate PR set and identical pre-fix SHAs. Two
caveats, which **confirm and quantify** §0.2's warning: the rerun loses the hand-written
`note` column on **7 of 10** rows, and it emits **10 rows where the committed file has
70** (the committed CSV keeps every merged PR with a `belongs_to_family` column; the
script now writes only the in-family candidates read from `tools/a3_candidates.tsv`).
Never run it against the real tree.

### 5.7 `tools/compute_intervals.py`

Deterministic. The regenerated `paper/intervals.json` differs from the committed one in
exactly one line — the `generated_at_utc8` stamp. All 41 cells match.

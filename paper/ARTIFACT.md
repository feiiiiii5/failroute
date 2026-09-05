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

### 5.4 Re-derivation gaps from the earlier pass — status as of the H batch (09-01)

| Item | Outcome |
|---|---|
| `tools/coverage_union.py` | **Resolved (H batch, 09-01).** History: the original script hard-coded `.venv/bin/python` as a relative path and died on its own 900 s pylint timeout, so the union figure was NOT re-derived by the earlier pass. The script was fixed (interpreter resolution with env override, pylint timeout 1800 s, parameterised findings dir) and re-run live: **the 253 / 39.0% figure was reproduced on the v0.7.0 finding set (56 s wall)**, and the final v0.8.0 baseline (621 findings) measures **250 / 621 = 40.3%** (49 s). Re-run: `PYTHONPATH=src .venv/bin/python tools/coverage_union.py --findings-dir bench/rescan-f2 --out /tmp/u4.json` for the paper's 250/621. 🔴 **M2 correction (2026-09-02): the re-run line in this row formerly said `--findings-dir paper/scan` — that is the frozen v0.7.0 649-finding set and reproduces the *deprecated* 253/649 = 39.0%; the paper figure 250/621 = 40.3% requires `bench/rescan-f2`. Never re-export over `paper/scan/` (it is the frozen baseline the 649→621 deletion accounting depends on); regenerate into `bench/` instead. See §6.4.** |
| `tools/compare_linters_corpus.py` | **Not run.** Same linter cost, and it overwrites `bench/corpus-linter-comparison.json`, which now also carries the merged `linters.semgrep` results. §0.2's warning stands, untested. |
| semgrep (5-tool union, 279 / 43.0%) | **Resolved (H batch, 09-01).** semgrep 1.175.0 installed and run live via `tools/coverage_union.py --with-semgrep`: **279 / 43.0% reproduced on the v0.7.0 finding set (73 s)**; the v0.8.0 baseline measures **269 / 621 = 43.3%** (63 s). |
| `tools/make_figures.py` | **Needs an undeclared dependency.** On the clean venv: `ModuleNotFoundError: No module named 'matplotlib'`. After installing matplotlib it produced **fig1, fig2 and fig3** (each `.pdf` + `.png`) — §2.3 and §4 mention only fig1. `matplotlib` is absent from `pyproject.toml`, so the documented clean install cannot build the figures at all. 🔴 **L3 RESOLVED (2026-09-02): `matplotlib` is now declared in the `[paper]` extra; a fresh `pip install '.[paper]'` builds all three figures with zero manual installs — see §6.3.** |
| `tools/fetch_corpus.py` (download path) | **Not re-downloaded.** `--verify` (disk vs lock, no network) ran clean: `8/8 packages verified`. Byte-identical re-download therefore stays unverified, though every input is sha256-locked. 🔴 **L1 RESOLVED (2026-09-02): `corpus-manifest.json` now pins `version`+`sha256` per package; a fresh `/tmp` re-download verified 8/8 byte-identical to the lock, and a wrong pin exits non-zero — see §6.1.** |

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

---

## 6. L batch (2026-09-02): the two §5.4 reproducibility defects fixed, dependencies declared

The K-batch clean-environment reproduction (`docs/k-batch-report.md` §K2) surfaced two defects
that made this artifact's central promise — a reviewer can rebuild the corpus byte-for-byte on
a clean machine — false, plus a third gap (undeclared dependencies). All three are fixed here,
each with the command actually run and its output. Nothing below is aspirational; §6.1–§6.3 were
re-run on 2026-09-02.

### 6.1 L1 — corpus is now version- and sha256-pinned (byte-for-byte rebuild is TRUE)

`paper/corpus-manifest.json` previously had `"version": null` for all eight packages, so
`fetch_corpus.py` resolved to the *current PyPI latest*. Measured drift on 09-02: `inspect_ai`
0.3.260→0.3.261, `pydantic_ai_slim` 2.36.0→2.37.0. The other six did not drift only because
upstream had not published since the freeze — not by design.

Fix: every package now carries an explicit `version` AND `sha256`, copied verbatim from the
committed `corpus-lock.json`. `fetch_one` already enforced `expected = pinned_sha or
info['expected_sha256']` and raised `ValueError` on mismatch, so pinning the sha256 makes a
fresh fetch either byte-identical or a hard non-zero exit.

Fresh fetch into a clean `/tmp` sandbox (09-02 15:41 UTC+8) — all eight resolved at the pinned
versions and hashed identical to the committed lock:

```
  garak              0.16.0     MATCH    fresh=71962ecf7c3a09d2 lock=71962ecf7c3a09d2
  inspect_ai         0.3.260    MATCH    fresh=5f6fbd7bc1fae0a7 lock=5f6fbd7bc1fae0a7
  pydantic_ai_slim   2.36.0     MATCH    fresh=43b53401099352bb lock=43b53401099352bb
  ... (uqlm 0.6.5 / trl 1.12.0 / smolagents 1.26.0 / deepteam 1.0.9 / fickling 0.1.12 all MATCH)
BYTE-FOR-BYTE fresh-fetch vs committed lock: 8/8 match
```

Negative test (a wrong pin must fail loud, not silently fetch something else): setting
`inspect_ai` version to 0.3.261 while keeping the 0.3.260 sha256 →
`FAILED ValueError: inspect_ai: sha256 mismatch (expected 5f6fbd7b… got 58d40586…)`, exit 1.

Also fixed a latent crash: `fetch_corpus.py` wrote `args.dest.relative_to(ROOT)` into the lock,
which raised `ValueError` when `--dest`/`--manifest` pointed outside the repo (e.g. a `/tmp`
verification sandbox) — crashing *after* a clean fetch. `_lock_path_field` now falls back to the
absolute path. §5.4's "byte-identical re-download … stays unverified" is therefore superseded:
it is now verified (8/8), and every input is genuinely sha256-locked at the manifest layer.

### 6.2 L2 — coverage_union.py no longer fails silently

`tools/coverage_union.py` ran each linter as `PY -m <tool>` and parsed `json.loads(stdout or
'[]')`. With a linter absent, stdout is empty → the empty set → `union_covered = 0`, i.e. the
script reported "failroute-only = 100%" and exited 0. That is the exact silent-failure mode this
paper studies, in the paper's own analysis script.

Fix: a `--version` preflight probes all four linters (a non-zero `--version` unambiguously means
"unusable", unlike a real scan whose non-zero exit just means "found issues"); it exits non-zero
naming every missing package. `sh()` now also treats "non-zero exit AND empty stdout" as fatal.
flake8's preflight additionally requires the flake8-bugbear plugin (else B001/B017 silently match
nothing).

Clean interpreter with no linters (`FAILROUTE_PY=/usr/bin/python3`, which lacks all four),
BEFORE vs AFTER the fix:

```
BEFORE:  union_covered=0   failroute-only=649 (100.0%)   exit 0     <- silent zero
AFTER :  error: coverage_union.py refuses to run -- missing: ruff / bandit / pylint / flake8
         exit 1
```

With the four linters installed the figure is unchanged (the fix only adds loud failure):
`250/621 = 40.3%`, per-tool ruff 72 / bandit 63 / pylint 245 / flake8+bugbear 124 — reproduced
both with the repo `.venv` (ruff 0.16.4) and a fresh `.[paper]` venv (ruff 0.16.5).

🔴 Correction to the K-batch record: `paper/scan/*.jsonl` do **not** embed absolute paths. All
649 lines store repo-relative `paper/corpus/...` (`git grep '/Users/fei' HEAD -- '*.jsonl'`
returns nothing; unchanged since commit `ae72d5d`). coverage_union resolves them via
`os.chdir(ROOT)`+`abspath`, so they are portable to any clone once `fetch_corpus.py` has run. The
only absolute paths in the artifact are the inert `bench_path` provenance fields in
corpus-manifest/lock and the `bench/*-comparison` files, none of which locates a scanned file.

### 6.3 L3 — the paper toolchain is now declared (`pip install '.[paper]'`)

`matplotlib` (make_figures.py) and the five linters (coverage_union.py) were undeclared, so §5.4's
clean install could not build the figures and the K-batch reviewer list had six manual installs.
A new `[project.optional-dependencies].paper` extra pins all six (matplotlib==3.11.1, ruff==0.16.5,
bandit==1.9.4, pylint==4.0.8, flake8==7.3.0, flake8-bugbear==25.11.29). Kept separate from `[test]`
so the test install stays lean. Fresh venv, zero manual installs (09-02 15:0x UTC+8):

```
uv venv --python 3.11 /tmp/l3-venv ; uv pip install '/tmp/l3-clean[paper]'    INSTALL_EXIT 0
matplotlib 3.11.1 · ruff 0.16.5 · bandit 1.9.4 · pylint 4.0.8 · flake8 7.3.0 (flake8-bugbear 25.11.29)
make_figures.py                              -> fig1/fig2/fig3 .pdf+.png     MAKEFIG_EXIT 0
coverage_union.py --findings-dir bench/rescan-f2 -> TOTAL=621 COVERED=250 (40.3%)
```

### 6.4 Reviewer-from-zero, updated (supersedes §4 and the K-batch list)

🔴 **Superseded in two lines as of the V1–V3 batches (2026-09-05): `158 passed`
is now 221, and `rescan_corpus.py` run on this tree yields 476 rather than 621 —
621 is a fact about the `v0.8.0` detector and needs `tools/pinned_rescan.py`.
Read §7.1 before running the block below.** The block is kept as recorded.

```bash
git clone https://github.com/feiiiiii5/failroute && cd failroute && git checkout v0.8.0
# v0.8.0 is a public tag on main (merged 2026-09-03); PyPI 0.8.0 published 2026-09-03T08:06Z.
# The earlier warning that main still yielded the v0.7.0 649 figures no longer applies.
python -m venv .venv && . .venv/bin/activate
pip install '.[test,paper]'         # tests + matplotlib + 4 linters + bugbear; NO manual installs
python tools/fetch_corpus.py        # ~150 MB; version+sha256 pinned -> byte-identical to corpus-lock.json
PYTHONPATH=src python -m pytest                               # 158 passed
PYTHONPATH=src python tools/rescan_corpus.py --out /tmp/r     # total 621
PYTHONPATH=src python tools/closure_check.py                  # CLOSURE: CLOSED (8/8)
python tools/coverage_union.py --findings-dir bench/rescan-f2 --out /tmp/u.json   # 250/621 = 40.3%
python tools/make_figures.py        # 3 figures (writes paper/figures/)
```

🔴 Two reproduction-command precisions, corrected here:
- The **250/621 (v0.8.0)** union comes from `--findings-dir bench/rescan-f2` (621 findings). The
  default `--findings-dir paper/scan` is the **v0.7.0 649** set and yields the deprecated
  253/649 = 39.0%. §5.4's re-run line conflated the two; use `bench/rescan-f2` for the paper number.
- The three §0.2 hand-curated-overwriting scripts (draw_sample, compare_linters_corpus,
  merged_pr_recall) remain deliberately NOT re-run; §0.2's warnings stand unchanged.

---

## 7. V1–V3 batches (2026-09-05): the artefact inventory §1–§6 did not have

Added by the V4 batch. §1–§6 describe this repository as of the L batch (2026-09-02).
Three batches since then — **V1** (predicate refactor), **V2** (paper rewrite), **V3**
(`covered_by` correction) — added **6 tools, 11 `bench/` artefacts, 1 annotation file,
2 claims files and 36 tests**, and invalidated two of the numbers §6.4 tells a reviewer
to expect. The paper's RQ5 reproduction block states that its outputs ship in this
repository; until this section existed there was no inventory to check that sentence
against, which is why it was raised as a blocking item rather than left as bookkeeping.

Convention, matching §5.4's: every output quoted below came from a command actually run
on **2026-09-05 (UTC+8)** in this repository. Where a command was *not* re-run for this
section, §7.8 says so instead of implying it was.

### 7.1 🔴 Two lines of §6.4 are superseded

| §6.4 as written (09-02) | measured 2026-09-05 | why |
|---|---|---|
| `PYTHONPATH=src python -m pytest` → `# 158 passed` | **`221 passed in 2.21s`** | V1 rewrote and added fixtures (158 → 185); V3 added `tests/test_lint_mapping.py`, 36 tests (185 → 221) |
| `PYTHONPATH=src python tools/rescan_corpus.py --out /tmp/r` → `# total 621` | **476** from the working tree | V1's predicate refactor changed what the detector reports. **621 is a historical fact about the `v0.8.0` detector, not a fact about this tree** |

🔴 The second row is the one that bites. A reviewer who clones this repository and runs
`rescan_corpus.py` gets 476 and will conclude the paper's 621-finding figures are wrong.
They are not: 621 is what `v0.8.0` reports, and `tools/pinned_rescan.py` reproduces it
(§7.2). Every claim asserting a v0.8.0 scan result now routes through that tool rather
than through the working tree — **11 of them, all marked `slow`**.

The remainder of §6.4 is unchanged and still correct on 09-05: `fetch_corpus.py`
(version + sha256 pinned per package),
`coverage_union.py --findings-dir bench/rescan-f2` → **250/621 = 40.3%** (pinned by
`V2.frame_621_reproducible_in_tree` and `F3.union_new_4tool`), and `make_figures.py`
through the `[paper]` extra.

🔴 **`closure_check.py` is a third superseded line, and not because of the batches.**
§6.4 tells a reviewer to expect `CLOSURE: CLOSED (8/8)`. Measured after the V4 seal
commit:

```
versions PASS · tests PASS · self_scan PASS · readme_numbers PASS
artifact PASS · roadmap PASS · source_todos PASS · git_clean FAIL
CLOSURE: 1 FAIL          git_clean detail: "1 uncommitted path(s)"
```

Seven of eight pass. `check_git_clean` counts lines of `git status --porcelain`, and
the only line left in this repository is `?? paper/arxiv/main.out` — a hyperref build
intermediate whose three siblings (`main.aux`, `main.log`, `main.blg`) are already in
`.gitignore` (lines 24–27) while `main.out` is not. So the whole gap is one missing
`.gitignore` line, not a defect in the study; it is documented rather than fixed
because `.gitignore` was outside the V4 batch's authorised paths. `KNOWN_OPEN` in
`closure_check.py` is an empty dict, so nothing is registered as expected-to-fail and
the FAIL is reported straight rather than downgraded to `KNOWN-OPEN`.

### 7.2 New tools (6)

| tool | what it does | writes | pinned by |
|---|---|---|---|
| `tools/pinned_rescan.py` | Checks the `v0.8.0` tag out into a git worktree (`/tmp/fr-pinned-v0.8.0`, rebuilt automatically if absent or at the wrong sha), symlinks the untracked `paper/corpus`, and re-scans the pinned corpus **with that tree's own `src` and exporter**. Prints `PINNED_TOTAL=621`, `PINNED_PER_RULE …`, `PINNED_PER_PKG …`, then passes the pinned exporter's own per-package table through verbatim | `--out` dir only | `V3.pinned_rescan_is_the_historical_object`, `F3.new_total`, `F3.per_rule`, `F3.per_pkg`, `F3.recall_gate_no_drop`, and the detector side of `F2.corpus_delta` / `F2.truth_check` / `F2.importerror_still_reported` |
| `tools/lint_mapping_probe.py` | Generates **68 probes** (11 caught-type forms × 6 body forms + 2 `contextlib.suppress`), really runs ruff / bandit / flake8+bugbear / pylint over them, attributes every hit to a function span, and writes the measured matrix. `--check-parity` re-derives each handler's `covered_by` through the production `handler_facts_for` and compares cell by cell, exiting non-zero on drift | `bench/lint-rule-mapping.json` | `V3.mapping_parity_exact`, `V3.bandit_is_narrower_than_ruff`, `V3.suppress_unreachable_and_w0703_is_an_alias` |
| `tools/refix_replay.py` | The fail→pass half of the `covered_by` correction's evidence: rebuilds the **pre-correction** `covered_by_for` in a scratch tree and runs the same 36 mapping tests against it | nothing (temp tree) | `V3.red_replay_prefix` |
| `tools/rq5_refactor_delta.py` | Joins the v0.8.0 frame against the refactored frame and reports the before/after delta of the `covered_by` correction, including the labelled crosstab | `bench/rq5-refactor-delta.json` | `V3.covered_by_fix_before_after`, `V2.refactor_delta_not_a_subset` |
| `tools/e722_baseline.py` | The trivial-linter baseline: runs flake8 E722 and ruff BLE001 over the corpus and reports how many labelled DEFECTs each reaches | `bench/e722-baseline.json` (`--out`) | `V2.e722_trivial_baseline` |
| `tools/check_abstract_len.py` | Measures the abstract against arXiv's 1,920-character form limit under both conventions (submission-form: environment body, stripped, newline = 1 char, TeX markup **not** stripped; and whitespace-flattened). `--tex` takes any path, which is how §7.7 checks the packaged copy | nothing | `V2.abstract_within_arxiv_form_limit` |

Three details a reproducer will otherwise trip on:

* 🔴 **`pinned_rescan.py` uses the worktree's own exporter, not the repository's.** The
  current exporter writes `severity` / `isomorphism` / `covered_by` / `verdict`; `v0.8.0`'s
  `Finding` has none of those fields, so cross-version pairing raises `AttributeError`.
  Also: `git rev-parse --short v0.8.0` returns `6bef5a2`, which is the **tag object**; the
  commit is `a73158b`. `git diff v0.8.0 HEAD -- src/` is empty, so the tag is a faithful pin.
* 🔴 **The 68 probe files are deliberately not committed.** The generated file is one long
  sequence of intentional bare `except:` blocks, and CI's `self-scan` workflow scans the
  whole repository, so committing it would poison that gate. The **matrix** is committed;
  the probes regenerate from the tool in ≈3 s.
* 🔴 **`refix_replay.py`'s pre-correction source is a reconstruction embedded in the
  script, not a git object.** V1 and V3 were both uncommitted when it was written, so no
  commit held "pre-V3 but post-V1"; at that time `HEAD` was `2e7e83c`, whose `_shared.py`
  was still `v0.8.0` and lacked `handler_facts_for`, so a plain checkout raised
  `ImportError`. 🔴 **The V4 seal does not fix that.** All four batches went in as **one**
  commit (`410fe28`), so the intermediate state "post-V1, pre-V3" still exists nowhere in
  the history and the embedded reconstruction remains the only route to the red half of the
  correction's evidence. To be precise about what is and is not missing: `HEAD`'s
  `_shared.py` now *does* define `handler_facts_for`, so the `ImportError` is gone — what
  no commit ever held is the **pre-correction `covered_by_for`**, which is the thing the
  replay needs. The script self-guards: it verifies the scratch tree is really the module
  that got imported and exits loudly otherwise (macOS `/var` vs `/private/var` aliasing
  made that check misfire once).

Output actually measured on 09-05:

```
$ PYTHONPATH=src .venv/bin/python tools/lint_mapping_probe.py --check-parity     # exit 0
probe: 68 cases, 68 functions
positive controls failed: none
rules that fired nowhere: none
unattributed hits: 0
parity check: 68 handler(s)/case(s) compared against the measured matrix
  exact agreement on every case

$ PYTHONPATH=src .venv/bin/python -m pytest --tb=no 2>&1 | tail -1
221 passed in 2.21s

$ PYTHONPATH=src .venv/bin/python -m mypy --strict src
Success: no issues found in 15 source files
```

`tools/` is **outside** the mypy gate and was never clean (`make_figures.py` alone carries
27 `--strict` errors that predate these batches). `lint_mapping_probe.py` has 41, all of
them missing-annotation and untyped-call class. 🔴 Do not read `mypy --strict src tools`
as the gate: it reports 355 errors, almost all historical.

### 7.3 Modified tools (3)

| tool | change |
|---|---|
| `tools/rescan_corpus.py` | emits `severity` / `isomorphism` / `covered_by` / `verdict` per finding; new `--with-context` |
| `tools/coverage_union.py` | `--findings-dir`, `--emit-per-finding`, `--with-semgrep` |
| `tools/compute_intervals.py` | a separate `--rq5` mode whose default output is `bench/intervals-v2.json`, deliberately leaving `paper/intervals.json` **byte-identical** so the frozen artefact RQ1–RQ4 are computed from is not disturbed |

### 7.4 New `bench/` artefacts (11)

| path | what it is | generated by | pinned by |
|---|---|---|---|
| `bench/rescan-v2/` (8 jsonl) | the refactored detector's **476** findings, one file per corpus package | `rescan_corpus.py --out bench/rescan-v2 --with-context` | `V2.coverage_refactored_frame`, `V2.paper_numbers_drive_from_exports` |
| `bench/corpus-coverage-union-v2.json` | 4-linter union over the 476 frame: **247 covered (51.9%), 229 failroute-only** | `coverage_union.py --findings-dir bench/rescan-v2 --out …` | `V2.coverage_refactored_frame` |
| `bench/corpus-coverage-per-finding-v2.jsonl` | per-finding coverage rows for the 476 frame, carrying `severity` / `isomorphism` / `covered_by_static` | same, `--emit-per-finding` | `V2.static_covered_by_over_credits`, `V2.static_covered_by_witness`, `V3.residual_five_bounded` |
| `bench/corpus-coverage-union-621frame.json` | 4-linter union over the committed 621 frame: **250 covered (40.3%), 371 failroute-only** | `coverage_union.py --findings-dir bench/rescan-f2 --out …` | `V2.frame_621_reproducible_in_tree` |
| `bench/corpus-coverage-per-finding-621.jsonl` | per-finding rows for the 621 frame — the "before" side of the refactor delta | same, `--emit-per-finding` | input to `rq5_refactor_delta.py` |
| `bench/corpus-coverage-per-finding-v2-pre-coverby-fix.jsonl` | the 476 frame as computed **before** the V3 `covered_by` correction — the other side of the before/after delta. Regenerating it needs the pre-correction predicate, which `refix_replay.py` reconstructs | `coverage_union.py` under the pre-correction predicate | input to `rq5_refactor_delta.py`; see `V3.covered_by_fix_before_after` |
| `bench/rq5-refactor-delta.json` | the measured delta: statically novel **87 (18.3%) → 224 (47.1%)**, HIGH ∧ uncovered **20 → 25**, **146** over-credited findings of which **137** became novel, findings 476 → 476 | `rq5_refactor_delta.py` | `V3.covered_by_fix_before_after` |
| `bench/lint-rule-mapping.json` | the 68-cell measured matrix: which of four linters actually fires on which caught-type × body form | `lint_mapping_probe.py` | `V3.mapping_parity_exact` |
| `bench/e722-baseline.json` | the trivial-linter baseline: E722 **134** / BLE001 **334**; DEFECT coverage **12/12** vs **0/12** | `e722_baseline.py` | `V2.e722_trivial_baseline` |
| `bench/intervals-v2.json` | RQ5's Wilson intervals from the canonical tool (`Z = 1.959963984540054`); does **not** replace `paper/intervals.json` | `compute_intervals.py --rq5` | `V2.crosstab_is_the_result`, `V2.cluster_correction`, `V2.bare_typed_stratification` |
| `bench/realworld/` (`cases.jsonl` 87 lines, `run.py`, `README.md`) | external regression bench built **before** the V1 refactor was touched, so the refactor is measured against expectations that did not come from the detector's author: 80 labelled real-world coordinates + 7 probe shapes. Gates `G0.probe-table` / `G1.no-regression` / `G2.distinguishable` / `G2.fail-closed-positive` / `G3.isomorphism-matrix`, with **24 cases deliberately not gated** so the bench cannot be tuned to them | hand-authored; run with `PYTHONPATH=src python3 bench/realworld/run.py` | **no claim** — see its own `README.md` |

🔴 **Artefact byte-stability, measured 09-05 by running each generator twice and hashing.**
Two claims invoke `rq5_refactor_delta.py` and three invoke `lint_mapping_probe.py` **without
`--out`**, so running the ledger rewrites these two shipped artefacts:

```
bench/rq5-refactor-delta.json    before=fa08b4d95e3d530f  after=fa08b4d95e3d530f  BYTE-STABLE=True
bench/lint-rule-mapping.json     before=bea28dee7486670b  after=6f82ce38ff662ee1  BYTE-STABLE=False
```

`rq5-refactor-delta.json` is now stable because V3 sorted five counters that were built by
iterating a **set** — their key order used to follow `PYTHONHASHSEED` and change between
processes, which silently broke any claim quoting it and made "byte-reproducible" false.
🔴 `lint-rule-mapping.json` changes on every run **by design**: it carries `generated_at`
and `*_utc8` keys, and a live measurement is supposed to be timestamped. No claim asserts
its bytes (they assert the tool's stdout), so nothing is red — but **do not "fix" the
timestamp, and do not claim that file is byte-reproducible.**

### 7.5 🔴 `paper/annotations-v2-additions.csv` — do not check it with `wc -l`

New file: the 60 supplementary labels RQ5 adds. The frozen `annotations.csv` and
`annotations-second-pass.csv` are untouched and remain SHA-locked. This file matches the
`paper/annotations*.csv` read-only pattern, so it is **protected truth** — created under
the V2 batch's explicit written authorisation and not modified since.

```
$ wc -l paper/annotations-v2-additions.csv
      65
$ python3 -c "import csv;print(len(list(csv.reader(open('paper/annotations-v2-additions.csv',newline='')))))"
61
```

**65 ≠ 60 and neither reading is wrong.** Four `rationale` fields contain embedded
newlines, so a line count overcounts by 4; and the csv record count includes the header,
so 61 records = 1 header + **60 labels**. The label distribution read through `csv` is
`CONTRACT 58 / DEFECT 1 / FALSE_POSITIVE 1` — exactly what the paper's RQ5 states.
🔴 A reviewer who checks "60 labels" with `wc -l` will conclude the paper overstates by
five. Same class of trap as §2.2's exit-code gotcha: **the tool's default output is not
the quantity being claimed.**

### 7.6 The claims ledger is now the authority for every number

`claims/v2.json` (12) and `claims/v3.json` (9) are new; `f1/f2/f3.json` were amended.
The ledger is **43 claims in 5 files**. Each entry is `{id, stmt, value, cmd, expect}`;
`cmd` must recompute from raw data (reading back this batch's own JSON does not count as
verification), a missing input must fail loudly, and a superseded claim keeps its original
`stmt` with the replacement prefixed.

```
.venv/bin/python tools/verify_claims.py                # all 43, including the 25 slow ones
.venv/bin/python tools/verify_claims.py --only f1      # one file
.venv/bin/python tools/verify_claims.py --skip-slow    # 🔴 never use this for acceptance
```

🔴 **`--skip-slow` still prints `ALL CLAIMS PASS`.** It marks **25 of the 43** as `SKIP`
(f1 3, f2 4, f3 10, v2 4, v3 4), and the V1 batch's acceptance was signed off on exactly
that output while 11 claims were red. The acceptance criterion is therefore
**"0 FAIL *and* 0 SKIP"**.
`V3.claims_run_without_skip_slow` asserts the structural half of it (no `f2`/`f3` claim may
still re-scan with the working-tree detector); it cannot prove an acceptor actually omitted
the flag, so the criterion has to live in the acceptance table too. Measured 2026-09-05:
**43 claims, FAIL 0, SKIP 0**.

Two dependencies a fresh clone will not have. Both fail **loudly**, but both are easy to
misread:

* **semgrep.** `F3.union_new_5tool` and `F3.union_old_5tool_repro` need semgrep 1.175.0,
  which is *not* in `pyproject.toml` (the paper's Table 3 says so explicitly), so it cannot
  be folded into the repo venv. Rebuild:
  `uv venv --seed /tmp/sgvenv --python 3.11 && uv pip install --python /tmp/sgvenv/bin/python 'semgrep==1.175.0'`.
  🔴 The failure mode is silent-looking: with `bin/semgrep` present but `import semgrep`
  broken, `coverage_union.py --with-semgrep` exits loudly, the claim's upstream `grep` finds
  no line, and the result *reads* as "the 269/43.3% figure did not reproduce" rather than
  "the environment is broken". This actually happened on 09-05.
* **the contractlens truth dataset, in a different repository.** `F2.truth_check`,
  `F2.ablation_no_fixed_loss` and `F3.truth_f3_154` read
  `新项目-contractlens/data/dataset.jsonl`. All three now pin it by commit
  (`git show b5efe7d299aaea9a78dc8a77cf314a397c393652:data/dataset.jsonl`) instead of
  reading the live file, because the live file grew **6387 → 7415 lines** on 2026-09-01
  16:15 and turned `F3.truth_f3_154` red for a reason that had nothing to do with the
  detector. 🔴 The general rule this established: **both sides of a historical comparison
  must be pinned.** Pinning only the detector leaves the claim exposed to the other
  repository's history. The pin point is derived, not guessed — `claims/f2.json` and
  `claims/f3.json` were frozen on 2026-09-01 at 12:30, contractlens `HEAD` at that moment
  was `7cfe136` (03:03), whose `data/dataset.jsonl` blob `78fbb428…` is **the same blob**
  `b5efe7d` points at.

🔴 **A third pin, and the one a clone will find strangest.** Five claims
(`F1.baseline_repro`, `F1.corpus_delta`, `F1.delta_bound`, `F2.corpus_delta`,
`F2.truth_check`) inject a *tool* into an old tree: they check out a pre-refactor commit and
then overwrite its `tools/rescan_corpus.py` with a newer copy, so what gets measured is
"current scanner harness, historical detector". That copy used to come from
`git show HEAD:tools/rescan_corpus.py` — a **floating HEAD**, fragile-claim class ② in the
ledger's own rules. It never fired, because V1–V3 all ran the ledger *without committing*,
so `HEAD` stayed parked at `2e7e83c`. The V4 batch's authorised commit is exactly what
would have detonated it: measured by dropping the working-tree copy into a `6eb7973`
worktree and running it, it exits **1** with
`AttributeError: 'Finding' object has no attribute 'severity'`, because V2 taught the
exporter four fields (`severity` / `isomorphism` / `covered_by` / `verdict`) that the old
`Finding` does not have. The HEAD copy run the same way gives `exit=0`, `total 639`.
All five claims now name `2e7e83c1f5fcb27e1ff15d746527140c92331fb7` explicitly.
🔴 That is a **no-op today** — `cmp` confirms `2e7e83c:tools/rescan_corpus.py` is
byte-identical to the copy `HEAD` held when those expects were frozen, so every expect
reproduces unchanged and none was edited; what the pin fixes is the *next* commit.
`tools/delta_findings.py` is pinned alongside it **prophylactically**: it was not modified
by any of these batches so it is not red today, but it is the same floating pattern and
would break the day someone edits it.

### 7.7 The arXiv submission package

`paper/arxiv/main.tar.gz` is **`.gitignore`d** (line 27), so it is a local submission
artefact, not a repository artefact: a clone will not have it and cannot check it.
Rebuilt 2026-09-05 by the V4 batch — **111,526 B**, sha256 `f6d8edff83af77946800c74c48029574e360f37e9dcfe77959fc65ebceba5865`,
containing `main.tex`, `refs.bib`, `main.bbl` and `figures/` (3 PDFs).

🔴 The previous package (**88,140 B, 2026-09-03 20:21**, sha256 `792203cb…`) was stale and
**would have failed on arXiv**: it contained `figures/fig3_recall.pdf`, a file that no
longer exists and that `main.tex` does not reference — the current source includes
`figures/fig3_recall_by_family.pdf`. Submitting it would have uploaded the pre-rewrite
paper and then died on the missing figure. It was copied to `/tmp` before being replaced.

Verified by unpacking into an **empty** directory rather than building in place, because
the working directory holds `.aux` / `.log` / `.blg` / `.out` intermediates that arXiv's
clean unpack will not have:

```
$ rm -rf /tmp/v4arxiv && mkdir -p /tmp/v4arxiv
$ tar xzf paper/arxiv/main.tar.gz -C /tmp/v4arxiv
$ cd /tmp/v4arxiv && tectonic -X compile main.tex --keep-logs --keep-intermediates
exit 0
```

| item | unpacked build | repository `main.pdf` |
|---|---|---|
| pages | **28** | **28** |
| log lines starting `!` | **0** | — |
| `undefined` in log | **0** | — |
| `Overfull` in log | **0** | — |
| `??` in extracted text | **0** | **0** |
| extracted text | 116,457 chars | identical, char for char |
| abstract, `check_abstract_len.py --tex /tmp/v4arxiv/main.tex` | **1903 / 1920 fits** | same |

`main.tex`, `main.bbl`, `refs.bib` and all three figures are byte-identical between the
package and the repository (`cmp`, six for six). `Underfull` lines: **7** — cosmetic,
present in the repository build too, and not part of the 0-error / 0-undefined /
0-overfull gate. 🔴 arXiv does not run BibTeX, which is why `main.bbl` must be inside the
package; it is, and it is the one built from the current `refs.bib`.

🔴 **One build artefact is not covered by `.gitignore`.** `paper/arxiv/main.out` (hyperref's
bookmark file) shows up as untracked in `git status`, while `main.aux`, `main.log`,
`main.blg` and `main.tar.gz` are all ignored (lines 24–27). It should not be committed.
Adding `paper/arxiv/main.out` to `.gitignore` is a one-line fix that the V4 batch did
**not** make, because `.gitignore` is not among the paths the batch was authorised to touch.

🔴 **Related trap, found by V3:** the repository *tracks* `paper/arxiv/main.pdf`. Compiling
with `--outdir /tmp` therefore proves the temporary copy while the tracked PDF silently
lags — it was two pages behind its own source (26 vs 28) until V3 recompiled it in place.
Any compile check must end by regenerating the tracked PDF, or by comparing page counts.

### 7.8 What this section did not re-run

The artefact-generating commands in the paper's RQ5 reproduction block (`rescan_corpus.py`,
`coverage_union.py`, `e722_baseline.py`, `compute_intervals.py --rq5`) were **not** re-run
standalone to produce §7. Two reasons, both deliberate:

1. Each overwrites a shipped `bench/` artefact, and `compute_intervals.py` writes a
   generation timestamp, so re-running them as a documentation side-effect would perturb
   artefacts whose values other claims quote. §0.2's discipline — regenerating is a
   deliberate act, not a side-effect — applies to `bench/` for the same reason it applies
   to `paper/`.
2. Their values are already pinned by the claims named in §7.4, and `verify_claims.py`
   **does** re-run them (into `/tmp` for 23 of the 43; see §7.4 for the five that write
   in-tree). It was run in full on 2026-09-05: **43 claims, 0 FAIL, 0 SKIP**.

Re-run for this section directly, with output quoted above: `lint_mapping_probe.py
--check-parity` (twice, plus twice more for the stability measurement), `pytest`,
`mypy --strict src`, `mypy --strict tools/lint_mapping_probe.py`, `check_abstract_len.py`
(both conventions, on both the repository and the unpacked copy), the csv record count, and
the whole of §7.7.


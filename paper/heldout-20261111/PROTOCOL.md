# Held-out evaluation protocol — failroute v0.8.0 vs v0.9.1

**Status:** frozen before any held-out package was fetched, scanned, or linted.
**Date:** 2026-11-11 13:15 China Standard Time (2026-11-11 05:15 UTC).
**Author:** Yufeiyang Chen.
**Purpose:** test whether the development-corpus coverage pattern replicates on
packages that were not used to design, tune, or label the detector or its
refactor.

This is a local research record. It does not modify the eight-package
development corpus, the eight-package control corpus, the frozen v0.7.0/v0.8.0
exports, the annotations, the PR ledgers, or the manuscript.

---

## 1. Question

The development study found that, from `failroute` v0.8.0 to v0.9.1 on the same
eight packages:

- findings fell from 621 to 476;
- four-linter co-location rose from 255/621 = 41.1% to 252/476 = 52.9%;
- the covered count itself fell from 255 to 252;
- a denominator decomposition attributed +12.51 percentage points to the smaller
  frame and −0.63 points to the covered-count change.

The held-out question is: **does the same direction of change appear on eight
packages that were not used in development?**

This is a replication test, not a hunt for a positive result. A negative or mixed
held-out result is a valid outcome and will be reported.

---

## 2. Package selection (fixed before fetch)

### 2.1 Criteria

A package enters the held-out set only if all of the following hold:

1. It is an AI/ML Python package distributed as a PyPI sdist.
2. Its main importable package body is large enough to plausibly contain
   exception handlers (target: at least 5,000 Python lines in the scan root).
3. It is **not** in the eight-package development corpus:
   `inspect_ai`, `pydantic_ai_slim`, `deepteam`, `trl`, `garak`,
   `smolagents`, `uqlm`, `fickling`.
4. It is **not** in the eight-package control corpus:
   `attrs`, `httpx`, `requests`, `urllib3`, `click`, `pydantic`, `anyio`,
   `msgpack`.
5. It does **not** appear in the author's curated PR ledger
   (`paper/merged-pr-recall.csv`) and has no known author contribution.
6. It is not a package that the author has used as a development target in the
   `failroute` repository.

### 2.2 Fixed package list and versions

Versions are pinned to the releases visible on PyPI on 2026-11-11 before any
scan. The lock file records URL, SHA-256, upload time and tree hash. No package
is replaced after results are seen.

| # | Package | Version | Role in the AI/ML stack |
|---|---|---|---|
| 1 | `accelerate` | 1.15.0 | training/inference runtime |
| 2 | `peft` | 0.21.2 | parameter-efficient fine-tuning |
| 3 | `datasets` | 5.2.0 | dataset loading and processing |
| 4 | `evaluate` | 0.4.6 | model/metric evaluation |
| 5 | `sentence-transformers` | 6.2.0 | embedding models |
| 6 | `dspy` | 3.5.0 | LM program optimization |
| 7 | `torchmetrics` | 1.9.0 | ML metrics |
| 8 | `optuna` | 5.0.0 | hyperparameter optimization |

### 2.3 Scan root (fixed rule)

For each extracted sdist, the scan root is:

- `src/<import_name>/` if that directory exists; otherwise
- `<import_name>/`;

where `<import_name>` is the package's import name (for
`sentence-transformers`, `sentence_transformers`; otherwise the package name as
published). Tests, examples, docs, benchmarks and vendored third-party code
outside that directory are excluded by construction.

The exact scan roots and line counts are written into `heldout-lock.json`
before any detector scan.

---

## 3. Instruments (fixed)

### 3.1 Detector versions

- **v0.8.0**: the tagged release, run from a detached git worktree at
  `v0.8.0`, using that tree's own `tools/rescan_corpus.py` and `src/`.
- **v0.9.1**: the current working tree at the commit used for this experiment,
  using its `tools/rescan_corpus.py` and `src/`.

The two versions are run over the **same extracted corpus** with the same scan
roots. The v0.8.0 exporter does not write severity/isomorphism/covered_by;
those fields are compared only for v0.9.1.

### 3.2 Baselines (fixed)

The four syntactic linters and rule selections are the same as the development
study:

| Tool | Rules |
|---|---|
| `ruff` | `S110,S112` |
| `bandit` | `B110,B112` |
| `pylint` | `W0702,W0703,W0705,W0706`, files passed explicitly (not the directory-mode invocation) |
| `flake8` + `flake8-bugbear` | `E722,B001,B017` |

Co-location tolerance is **±1 line** (`TOL = 1`). The supplementary Semgrep rule
is **not** part of the held-out headline: it was written by the author and is a
diagnostic, not a shipped baseline. If a suppress finding exists, its
four-linter coverage is reported; the Semgrep result is not used in the
replication decision.

### 3.3 Linter preflight

The run fails loudly if any linter or `flake8-bugbear` is missing. An empty
result from a failed linter is never treated as zero coverage.

### 3.4 Environment

The same Python environment and linter versions as the development study:
`ruff 0.16.4`, `bandit 1.9.4`, `pylint 4.0.8`, `flake8 7.3.0`,
`flake8-bugbear` with the version recorded in the run log. If a version differs,
the run records it and the result is marked as not exactly comparable.

---

## 4. Hypotheses (directional, stated before the run)

**H1 — pruning.** v0.9.1 reports fewer findings than v0.8.0 on the held-out
corpus (aggregate total).

**H2 — co-location share.** The four-linter co-location share is higher under
v0.9.1 than under v0.8.0.

**H3 — covered count.** The absolute covered count may fall even if the share
rises. Both numbers are reported; H3 is a descriptive check, not a requirement.

**H4 — decomposition.** If the share rises and the covered count falls, the
denominator term is positive and the covered-count term is negative, with the
same sign pattern as the development corpus. If the pattern differs, the
difference is reported without reinterpreting the development result.

**H5 — suppress boundary.** If the held-out corpus contains
`contextlib.suppress` findings, none of the four selected linters covers them
at ±1 line in either frame. This is a boundary check, not a claim that no
linter anywhere can see them.

**H6 — static/empirical agreement.** For the v0.9.1 held-out frame, the
detector's static `covered_by` prediction agrees with empirical four-linter
co-location on every finding. Any disagreement is listed with file, line, rule
and both verdicts. This tests whether the 68-probe calibration generalises.

---

## 5. Metrics

For each package and in aggregate:

- Python files and lines in the scan root;
- v0.8.0 findings; v0.9.1 findings;
- distinct handler sites in each frame (id/coordinate-based, not rule-based);
- four-linter union covered; `failroute`-only; share; per-rule counts;
- v0.9.1 severity and isomorphism counts (descriptive only);
- suppress findings and their four-linter coverage;
- static-vs-empirical disagreement count for v0.9.1;
- package-level table so a single large package cannot drive the aggregate
  unnoticed.

Decomposition, when both frames are available:

```
O1 - O0 = (C1 - C0)/N1 + C0 * (1/N1 - 1/N0)
```

where `O = C/N`. The two terms are reported in percentage points.

---

## 6. Decision rules (fixed)

1. **No tuning.** The detector, the probe matrix, the linter rules, the
   tolerance and the scan roots are not changed after seeing held-out results.
2. **No replacement.** A package that fails to fetch or scan is reported; it is
   not replaced with another package.
3. **No package-level cherry-picking.** All eight packages are reported, even
   if one dominates the aggregate.
4. **Underpowered threshold.** If the v0.9.1 held-out frame has fewer than 100
   findings, the result is labelled underpowered and no directional claim is
   made. Packages are not added to cross the threshold.
5. **Negative results are retained.** If H1–H6 fail, the paper reports the
   failure and does not reframe the development result as confirmed.
6. **No PR-scope re-estimation.** The held-out corpus has no curated,
   diff-read merged-fix set. The original 16-PR scope result remains the
   scope evidence; it is not transferred to the held-out packages.
7. **No LLM labels.** This experiment does not label held-out findings and does
   not estimate defect precision.

---

## 7. Resource and safety limits

- CPU only; no model, GPU, Ray, training or external API.
- One experiment process at a time.
- `nice -n 19`.
- Process-family memory limit 2 GiB; sampled every 0.5 s.
- Wall-time limit 30 minutes for the full fetch/scan/coverage run; per-linter
  timeout 1,800 s as in the existing tool.
- Stop if system memory pressure reaches warning level; do not kill unrelated
  processes.
- Downloads are pinned PyPI sdists, re-hashed against the lock; no package
  installation or environment change.

---

## 8. What this does not test

- **Natural incidence.** The corpus is eight pinned packages, not a random
  sample of AI/ML software.
- **Defect precision.** No human or LLM labels are produced for held-out
  findings.
- **Training or repair benefit.** No model is trained and no fix is applied.
- **PR scope.** No held-out curated fix set is built.
- **All linters.** The baseline is four selected linters; the result does not
  speak for CodeQL, Pyright, official Semgrep rules or other tools.
- **All Python versions or platforms.** The scan is one environment on macOS
  arm64; the existing CI matrix is not a scan matrix.

---

## 9. Freeze

The protocol text is frozen before the first fetch. Its SHA-256 is recorded in
`PROTOCOL.sha256` and in `README.md`. Any later correction is appended as a
dated deviation note, not silently edited into the protocol.

---

## 10. Outputs

```
paper/heldout-20261111/
  PROTOCOL.md
  PROTOCOL.sha256
  heldout-manifest.json
  heldout-lock.json
  corpus/                  # extracted sdists (not committed)
  findings-v0.8.0/         # per-package jsonl
  findings-v0.9.1/         # per-package jsonl
  coverage-v0.8.0.json
  coverage-v0.9.1.json
  comparison.json
  run.log
  README.md
```

The raw corpus and archives are not committed; the lock and results are. The
scripts are in `paper/heldout-20261111/scripts/`.

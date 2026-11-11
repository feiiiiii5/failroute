# Held-out replication — results and reproduction

**Protocol:** [`PROTOCOL.md`](PROTOCOL.md), SHA-256
`02a108b493e057d436368f6128687e750d15af16662b9c592299d6e2e1b9afdc`.
The protocol was written before any package was fetched or scanned.

**Date of run:** 2026-11-11 13:15–13:22 China Standard Time.

**Question:** does the v0.8.0 → v0.9.1 coverage pattern from the eight
development packages replicate on eight AI/ML packages that were not used in
development?

**Short answer:** the *direction* of the share change replicates; the absolute
covered-count decline does **not** replicate robustly. The held-out result is a
mixed replication, and it is reported that way.

---

## 1. Corpus

Eight pinned PyPI sdists, chosen before the run. None is in the development
corpus, the control corpus, or the author's curated PR ledger.

| Package | Version | Lines in scan root |
|---|---:|---:|
| `accelerate` | 1.15.0 | 36,293 |
| `peft` | 0.21.2 | 65,900 |
| `datasets` | 5.2.0 | 50,428 |
| `evaluate` | 0.4.6 | 6,288 |
| `sentence-transformers` | 6.2.0 | 53,638 |
| `dspy` | 3.5.0 | 81,174 |
| `torchmetrics` | 1.9.0 | 81,638 |
| `optuna` | 5.0.0 | 39,742 |
| **total** | | **415,101** |

The sdists contain 1,817 Python files / 529,073 lines in total; the scan roots
(main package body only) contain **1,564 files / 415,101 lines**. Exact URLs,
SHA-256, upload times and tree hashes are in `heldout-lock.json`; `python
tools/fetch_corpus.py --verify` re-checks all eight.

`dspy` contains a vendored `dspy/_vendor/` subtree. The primary result includes
it, because it is inside the package body. A structural sensitivity analysis
excludes it; see §3.

---

## 2. Primary result

| Package | v0.8.0 findings | v0.8.0 covered | v0.8.0 share | v0.9.1 findings | v0.9.1 covered | v0.9.1 share |
|---|---:|---:|---:|---:|---:|---:|
| accelerate | 19 | 2 | 10.5% | 21 | 4 | 19.1% |
| peft | 20 | 1 | 5.0% | 16 | 2 | 12.5% |
| datasets | 46 | 7 | 15.2% | 44 | 8 | 18.2% |
| evaluate | 9 | 4 | 44.4% | 10 | 4 | 40.0% |
| sentence-transformers | 43 | 15 | 34.9% | 33 | 17 | 51.5% |
| dspy | 175 | 69 | 39.4% | 114 | 53 | 46.5% |
| torchmetrics | 3 | 0 | 0.0% | 2 | 0 | 0.0% |
| optuna | 7 | 1 | 14.3% | 8 | 0 | 0.0% |
| **total** | **322** | **99** | **30.7%** | **248** | **88** | **35.5%** |

Distinct handler sites: **317** (v0.8.0) and **245** (v0.9.1). Findings are
not one per site because the assign channel can emit more than one finding for
the same handler.

Per-rule counts (v0.8.0 → v0.9.1):

| Rule | v0.8.0 | v0.9.1 |
|---|---:|---:|
| `silent-fallback` | 168 | 111 |
| `no-action` | 127 | 126 |
| `silent-suppress` | 24 | 9 |
| `name-shadowing` | 2 | 2 |
| `masked-exception` | 1 | 0 |

Coverage by rule under v0.9.1: `silent-fallback` 42/111 (37.8%),
`no-action` 46/126 (36.5%), `silent-suppress` 0/9, `name-shadowing` 0/2.

Severity (v0.9.1): 81 HIGH, 126 MEDIUM, 3 LOW, 38 INFO. Isomorphism: 91
non-isomorphic, 146 unknown, 11 null (the suppress findings). The isomorphism
layer again classified **none** as isomorphic.

### 2.1 Denominator decomposition

```
O1 - O0 = (C1 - C0)/N1 + C0 * (1/N1 - 1/N0)
```

With `(C0, N0) = (99, 322)` and `(C1, N1) = (88, 248)`:

- total change: **+4.74 percentage points**;
- covered-count term: **−4.44 points**;
- denominator term: **+9.17 points**.

The sign pattern is the same as the development corpus, but the magnitudes are
much smaller: the development change was +11.88 points, with −0.63 from the
covered count and +12.51 from the denominator.

---

## 3. Sensitivity: dspy and its vendored subtree

`dspy` dominates the held-out aggregate: 175 of 322 v0.8.0 findings and 114 of
248 v0.9.1 findings. Its covered count falls 69 → 53, a drop of 16; the other
seven packages gain 5 covered findings between them. The aggregate covered-count
decline is therefore driven by one package.

Two post-hoc structural sensitivities, added after dspy's dominance was
observed and reported whether or not they favour the result (see
`DEVIATIONS.md`; they are not pre-registered):

| Analysis | v0.8.0 findings | v0.8.0 covered | v0.8.0 share | v0.9.1 findings | v0.9.1 covered | v0.9.1 share |
|---|---:|---:|---:|---:|---:|---:|
| primary (all) | 322 | 99 | 30.7% | 248 | 88 | 35.5% |
| exclude `dspy/_vendor` | 235 | 55 | 23.4% | 189 | 56 | 29.6% |
| exclude `dspy` entirely | 147 | 30 | 20.4% | 134 | 35 | 26.1% |

Both sensitivities preserve the **share rise** (+6.23 and +5.71 points) but
**reverse the covered-count sign**: 55 → 56 and 30 → 35. The decomposition's
covered-count term becomes positive (+0.53 and +3.73 points).

**Interpretation:** the share rise replicates; the absolute covered-count
decline is not robust to package composition. The held-out evidence supports
the measurement point (the share is denominator-sensitive) but not a general
claim that refinement reduces absolute linter coverage.

---

## 4. Hypotheses

| Hypothesis | Verdict | Evidence |
|---|---|---|
| H1 — v0.9.1 reports fewer findings | **pass** | 322 → 248 |
| H2 — co-location share rises | **pass** | 30.7% → 35.5% |
| H3 — covered count falls | **pass in primary, not robust** | 99 → 88; 55 → 56 without `_vendor`; 30 → 35 without `dspy` |
| H4 — denominator positive, covered-count negative | **pass in primary, not robust** | +9.17 / −4.44; sensitivity +5.70 / +0.53 and +1.98 / +3.73 |
| H5 — suppress findings uncovered by four linters | **pass** | 0/24 (v0.8.0), 0/9 (v0.9.1) |
| H6 — static/empirical agreement on every v0.9.1 finding | **fail strict; pass for main rules** | 2/248 disagreements, both `name-shadowing`; 0/246 for the five main rules |

### 4.1 The two H6 disagreements

Both are in `datasets-5.2.0/src/datasets/builder.py`, lines 1575 and 1881:
`except Exception as e:` handlers that re-raise. The static mapping credits
`pylint:W0718` and `ruff:BLE001`; the empirical four-linter run records no
co-location because the handler re-raises. The static mapping models the caught
type and body shape but not this re-raise interaction. This is a real boundary
of the 68-probe calibration: it generalises to the five silent-continuation /
failure-to-value rules, not to the adjacent `name-shadowing` rule.

This is also a useful result: the development corpus contained **zero**
`name-shadowing` findings, so the development evaluation could not expose this
edge case. The held-out corpus did.

---

## 5. What this does not test

- **PR scope.** The held-out corpus has no curated, diff-read merged-fix set.
  The original 16-PR / 14-in-scope / 9-non-handler result remains the scope
  evidence; it is not transferred to the held-out packages.
- **Defect precision.** No LLM or human labels were produced for held-out
  findings.
- **Natural incidence.** Eight pinned packages are not a random sample.
- **All linters.** The baseline is four selected linters.
- **Training or repair benefit.** No model was trained and no fix was applied.

---

## 6. Reproduction

The held-out corpus is not committed (33 MB of third-party sdists). It is
rebuilt from `heldout-lock.json`:

```sh
cd <failroute checkout>
.venv/bin/python tools/fetch_corpus.py \
  --manifest paper/heldout-20261111/heldout-manifest.json \
  --lock paper/heldout-20261111/heldout-lock.json \
  --dest paper/heldout-20261111/corpus
.venv/bin/python tools/fetch_corpus.py --verify \
  --lock paper/heldout-20261111/heldout-lock.json \
  --dest paper/heldout-20261111/corpus
```

The scans were run in a temporary sandbox whose `paper/corpus` was a hardlink
copy of the held-out corpus and whose `paper/corpus-lock.json` was the held-out
lock. This keeps `paper/corpus-lock.json` and `paper/corpus/` untouched:

```sh
# current detector (v0.9.1 source)
PYTHONPATH=<checkout>/src .venv/bin/python tools/rescan_corpus.py --out findings-v0.9.1

# pinned v0.8.0
git worktree add --detach /tmp/fr-v080 v0.8.0
PYTHONPATH=/tmp/fr-v080/src /tmp/fr-v080/.venv/bin/python \
  /tmp/fr-v080/tools/rescan_corpus.py --out findings-v0.8.0
```

Coverage uses the current `tools/coverage_union.py` with the held-out lock and
corpus in the sandbox:

```sh
.venv/bin/python tools/coverage_union.py \
  --findings-dir findings-v0.8.0 --out coverage-v0.8.0.json
.venv/bin/python tools/coverage_union.py \
  --findings-dir findings-v0.9.1 --out coverage-v0.9.1.json
```

The analysis step, which reads only the saved records above, is:

```sh
.venv/bin/python paper/heldout-20261111/scripts/analyze_heldout.py
```

The held-out numbers printed in the manuscript are checked against
`comparison.json` by `scripts/check_paper_heldout.py`; its output is
`checks/paper-numbers.json` (16 checks, 0 failed).

Environment: Python 3.11.15; `failroute` 0.9.1 at
`15dffaaf3550aa3903a534b45c33d1a8b605d1d8`; v0.8.0 at
`a73158b8b69f94f21f77b57840d8e56df8275c16`; Ruff 0.16.4; Bandit 1.9.4;
Pylint 4.0.8; Flake8 7.3.0; flake8-bugbear 25.11.29.

**Resources:** the two detector scans took 6.9 s and 9.7 s; the four coverage
passes took 40.9 s, 41.3 s, 42.3 s and 41.9 s. Total ≈ 183 s, CPU-only,
`nice 19`, no model/GPU. The runs were not instrumented for peak RSS; system
memory pressure stayed at the normal level (54% free before the run) and no
resource abort occurred.

---

## 7. Files

| Path | Contents |
|---|---|
| `PROTOCOL.md`, `PROTOCOL.sha256` | pre-registered design and freeze hash |
| `DEVIATIONS.md` | post-freeze decisions (dspy `_vendor` sensitivities) |
| `heldout-manifest.json`, `heldout-lock.json` | package list and exact pins |
| `findings-v0.8.0/`, `findings-v0.9.1/` | per-package JSONL from the two detector versions |
| `coverage-v0.8.0.json`, `coverage-v0.9.1.json` | four-linter coverage aggregates |
| `coverage-v0.8.0-novendor.json`, `coverage-v0.9.1-novendor.json` | dspy `_vendor` sensitivity |
| `per-finding-v0.9.1.jsonl` | v0.9.1 per-finding static/empirical coverage |
| `comparison.json` | all aggregates, hypotheses and sensitivities |
| `RESULTS.md` | the per-package table above |
| `fetch.log`, `verify.log`, `scan-*.log`, `coverage-*.log` | run logs |
| `scripts/analyze_heldout.py` | analysis/reporting step |

**Path note:** the raw JSONL files were produced in a sandbox and use
`paper/corpus/...` as the file prefix. In this directory that means the held-out
corpus; it does not mean the development corpus. `comparison.json` rewrites the
two H6 item paths to `paper/heldout-20261111/corpus/...`.

**Boundary:** this is a local replication, not a public reproduction. The
held-out corpus is not committed; the lock allows a re-fetch. No held-out
results existed before 2026-11-11.

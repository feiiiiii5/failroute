# Re-execution record, 3–4 November 2026

Final state: tools at commit `8040aeb`. On 4 November 2026 the test suite,
`reproduce_paper.py`, `control_rescan.py --check`, `check_frozen_truth.py
--corpus` and the full claim run were repeated on that commit. The hand checks
listed under "Other checks" (BLE001 variant, all Ruff rules and default Pylint,
handler counts, v0.9.1 rescan) were run on 3 November and not repeated; the
historical path ran at commit `3b4c567`.

This file records what was actually re-run for the 3 November 2026 manuscript
revision, what is cited from earlier recorded runs, and what could not be re-run.
It is a log, not a new result: no label, ledger or frozen export was changed.

Environment: Linux x86_64 (cloud container), CPython 3.13.18, toolchain from
`pip install '.[test,paper,paper-semgrep]'` (ruff 0.16.5, bandit 1.9.4,
pylint 4.0.8, flake8 7.3.0 + bugbear 25.11.29, semgrep 1.175.0). The historical
scans were run on macOS arm64.

## 1. Current audit path (tools at commit 8040aeb)

```sh
git checkout 8040aeb
python tools/fetch_corpus.py           # "lock unchanged": all 8 package records match
python -m pytest                       # 244 tests: 243 passed, 1 skipped (POSIX permission test; run as root)
python tools/reproduce_paper.py --out-dir <new dir> --with-semgrep
PYTHONPATH=src python tools/control_rescan.py --check
python tools/benchmark.py --json
python tools/check_frozen_truth.py --corpus
python tools/verify_claims.py          # full run, slow claims included
```

`reproduce_paper.py` output, run of 4 November 2026. Comparison scope: scans
and coverage rows are compared as whole JSON rows (every field,
order-independent), and byte identity of the files is reported separately; the
delta, E722 and probe outputs are compared as JSON with only their timestamp
(and, for the probe matrix, the interpreter path) ignored.

| Step | Status | Detail |
|---|---|---|
| corpus | PASS | 8/8 packages verified (archive SHA-256 and extracted-tree hash) |
| scan-v080 | PASS | v0.8.0 from a disposable worktree at tag `v0.8.0`, exported without context windows as the frozen file was: 621 findings; every file byte-identical to `bench/rescan-f2` |
| scan-current | PASS | current detector, with context windows: 476 findings; every file byte-identical to `bench/rescan-v2` |
| coverage | PASS | 255/621 and 252/476 co-located; both per-finding files (1,097 rows) byte-identical to the frozen exports |
| delta | PASS | `rq5_refactor_delta.py` recomputed from the fresh rows: JSON equal to `bench/rq5-refactor-delta.json` apart from its timestamp and input paths |
| e722 | PASS | 134 E722 and 334 BLE001 candidates; 12/12 and 0/12 original DEFECT labels; JSON equal apart from its timestamp |
| probes | PASS | 68-probe matrix equal to `bench/lint-rule-mapping.json` apart from the interpreter path; parity exact |
| refix | PASS | 36 mapping tests: 21 fail on the reconstructed pre-fix predicate |
| semgrep | PARTIAL | see section 3 |

An earlier run on 3 November compared scans on key fields only (package, file,
line, rule) and requested context windows for the v0.8.0 scan, whose frozen file
has none; the 4 November run above replaces it.

Other checks:

* `control_rescan.py --check`: CHECK-OK for all eight control packages.
* `benchmark.py --json`: corpus v7, 68 synthetic fixtures, TP=34, TN=34, FP=0,
  FN=0. This is agreement with hand-labelled synthetic fixtures, a regression
  gate on the detector's specification; it is not defect precision on real code.
  `bench/benchmark-results.json` (previously corpus v6, 36/32) was regenerated
  from this run.
* `check_frozen_truth.py --corpus`: `protected=0 derived_rebuilt_match=True`.
  The seven protected inputs match `paper/frozen-truth-sha256.json` (and the
  hashes already locked in `annotation-corrections.json` and
  `reference-audit.json`); `intervals.json` rebuilt from its inputs equals the
  committed file apart from its timestamp. Each of the three figures, rebuilt
  with the pinned matplotlib 3.11.1, must match on two independent axes:
  - text: identical text tokens (56, 75 and 229 tokens);
  - drawn geometry (since commit 8040aeb, `tools/pdf_geometry.py`): vector marks,
    scatter-marker positions and decoded image cells, relative to the axes area.
    Measured against the committed figures (two written by matplotlib 3.11.0):
    vector marks differ by at most 0.000414 of the axes width or height
    (tolerance 0.001), image placement by at most 0.0046 (one pixel; tolerance
    0.01), and 0.66 % of heatmap samples differ by more than 8/255 (cell-boundary
    rows after resampling; tolerance 2 %).
  The figure bytes are not identical (PDFs embed version, date and glyph
  placement) and are not claimed to be.
* Figure-check blind spot, found in review and fixed in 8040aeb: the earlier
  check compared figure text only. Mirroring the figure-1 points, moving one
  point by one unit, or reversing the figure-2 cell shading, each with every
  label unchanged, passes a text-only comparison; each now fails the geometry
  comparison (vector marks moved 0.93 and 0.0093 of the frame; 71.6 % of image
  samples differ). These cases are regression tests. The committed figures were
  not affected.
* The v0.9.1 tag (worktree, its own exporter) also reproduces the 476-finding frame.
* `coverage_union.py --ruff-select S110,S112,BLE001` on the 621 frame: union 255,
  ruff co-located 127, silent-suppress 0/19.
* All 969 Ruff rules (`--select ALL`) and Pylint's default message set over the
  five files holding the 19 `silent-suppress` findings: within ±1 line of those
  sites only `E501` (4 sites) and `C0301` (1 site), both line-length messages.
* Handler counts by direct AST walk over the scan roots: 2,270 `except` handlers
  (main), 243 (control core), 842 (control, all eight).

### Claim checks (`tools/verify_claims.py`, full run)

First full run: 44 PASS, 8 HIST, 5 FAIL. After the probe fix described below, a
second full run (slow claims included) gave **47 PASS, 8 HIST, 2 FAIL**, and a
third, on the final tools (commit 8040aeb), gave the same **47 PASS, 8 HIST,
2 FAIL**; neither left any tracked file modified.

* **HIST (historical, not independently reproducible; expectations unchanged):**
  `F1.red_replay`, `F1.baseline_repro` (need commit `50275e8`),
  `F1.corpus_delta`, `F1.delta_bound`, `F2.corpus_delta` (need `6eb7973`),
  `F2.truth_check` (needs `6eb7973` and the companion repository),
  `F2.ablation_no_fixed_loss`, `F3.truth_f3_154` (need the companion
  repository). Neither commit is in any branch or tag after a full unshallow
  fetch, GitHub reports "No commit found for SHA" for both, and a commit search
  finds neither: the F-batch history was rewritten before publication. The
  companion repository (`contractlens`) is unreleased.
* **Public re-derivations, all PASS:** `F1.red_replay_public`,
  `F1.baseline_repro_public` (public commit `06eba40`, pre-F1),
  `F1.corpus_delta_public`, `F1.delta_bound_public`, `F2.corpus_delta_public`
  (public commit `82734d1`, post-F1). They reproduce the recorded expectations
  on public code; they do not prove that the trees equal the lost commits.
* **FAIL, expected:** `F3.union_old_5tool_repro` and `F3.union_new_5tool`
  require an error-free five-tool Semgrep run, which the strict harness refuses
  (section 3). The diagnostic observes their expected values, 284/649 (upper
  bound 285) and 274/621 (upper bound 275).
* The three `V3` probe claims failed in the first full run because the new
  overwrite guard treated a different interpreter path in the probe matrix as a
  content change. `lint_mapping_probe.py` now ignores the interpreter path as it
  ignores the timestamp; all nine `v3` claims pass and the tracked matrix is
  untouched.
* `V2.frozen_truth_untouched` previously compared file modification times and
  named two renamed figures, so it failed on every checkout. It now runs
  `check_frozen_truth.py --corpus` and passes.

## 2. Historical path (commit 3b4c567)

Run in a disposable worktree with its own virtual environment (only
`.[test,paper]`, as the manuscript prescribes), completed on 4 November 2026. The
corpus tree was copied from the verified local fetch and re-verified with
`fetch_corpus.py --verify` (8/8).

```sh
git worktree add <tmp>/hist 3b4c567 && cd <tmp>/hist
pip install '.[test,paper]'
python tools/fetch_corpus.py        # verifies; REWRITES paper/corpus-lock.json timestamp in this tree
PYTHONPATH=src python -m pytest     # 220 passed, 1 skipped (221 collected)
PYTHONPATH=src python tools/rescan_corpus.py --out <tmp>/h-rescan --with-context   # total 476
python tools/coverage_union.py --findings-dir bench/rescan-f2 --out <tmp>/h-union-621.json \
    --emit-per-finding <tmp>/h-621.jsonl
python tools/coverage_union.py --findings-dir bench/rescan-v2 --out <tmp>/h-union-476.json \
    --emit-per-finding <tmp>/h-476.jsonl
```

Results: both coverage runs exit 0 in about 42 s each, giving 255/621 (41.1%) and
252/476 (52.9%). Both per-finding files are byte-identical to
`bench/corpus-coverage-per-finding-621.jsonl` and `-v2.jsonl`, and all eight
rescan files are byte-identical to `bench/rescan-v2`.

Practical note: a first attempt that symlinked `paper/corpus` from another
checkout into the worktree made Pylint's parallel run stall for more than 20
minutes on `garak` (1.5 s with a real copy). Fetch or copy the corpus into the
tree; do not symlink it.

The fetch at this commit modifies a tracked file, which is why the historical
path must run in a disposable tree.

## 3. Semgrep (supplementary fifth baseline)

Semgrep 1.175.0 reports, in its JSON `errors` array, a syntax error at
`inspect_ai/model/_reasoning.py:62` (a `match` statement) and marks the file as
partially analysed. It exits 0 and its console summary reads "Scan completed
successfully" (Parsed lines ~100.0%); only the JSON and `--verbose` output show the error. It also
skips `deepteam/tests/test_core/test_vulnerabilities/test_hallucination.py`
through its default `.semgrepignore` (no detector finding in that file).

`tools/semgrep_diagnostic.py` (summary committed as
`bench/semgrep-diagnostic-2026-11-03.json`):

* 621-finding frame: 274 co-located with the four tools plus Semgrep (19 newly:
  18 `silent-suppress`, 1 `silent-fallback`), identical to the historical
  `bench/corpus-coverage-union-5tool.json`. One unmatched finding lies in the
  partially analysed file (`_reasoning.py:193`), so the upper bound is 275.
* 476-finding frame: 267/476, no finding in the affected file.
* 649-finding v0.7.0 frame (`paper/scan`, used by `F3.union_old_5tool_repro`):
  four-tool 258, with Semgrep 284 (26 newly: 25 `silent-suppress`, 1
  `silent-fallback`), upper bound 285 for the same `_reasoning.py:193` finding.

The strict harness (`coverage_union.py --with-semgrep`,
`reproduce_warning_coverage.py --with-semgrep`) still refuses this run, by design.
The five-tool figures are therefore reported as observed with a bound, not as an
error-free reproduction.

## 4. Cited, not re-run

* Pylint directory-invocation figures (250/621 union) recorded at commit 3b4c567.
* Control-corpus code readings, LLM labels and both annotation rounds (model
  identity not recorded), maintainer and tracked-site records.
* CI matrix results (Ubuntu, macOS, Windows; Python 3.9–3.13) from the project's
  GitHub Actions history.

## 5. Bibliography checks

* `do2022`: the first author's family name is "Nguyen Quang Do", as on the
  author's own website (checked online 2026-11-04) and in her DBLP author record;
  IEEE TSE 48(3):835–847, 2022, DOI 10.1109/TSE.2020.3004525. The earlier entry
  rendered the surname as "Do".
* `masters2026rolloutcards`: the official arXiv page lists version 1 as current
  (checked online 2026-11-04); the entry is pinned to arXiv:2605.12131v1 [cs.AI],
  submitted 12 May 2026.

The cloud session that ran the audit could not reach arxiv.org or dblp.org
directly; the two online checks above were made outside it.

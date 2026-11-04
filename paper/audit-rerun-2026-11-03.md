# Re-execution record, 3–4 November 2026

This file records what was actually re-run for the 3 November 2026 manuscript
revision, what is cited from earlier recorded runs, and what could not be re-run.
It is a log, not a new result: no label, ledger or frozen export was changed.

Environment: Linux x86_64 (cloud container), CPython 3.13.18, toolchain from
`pip install '.[test,paper,paper-semgrep]'` (ruff 0.16.5, bandit 1.9.4,
pylint 4.0.8, flake8 7.3.0 + bugbear 25.11.29, semgrep 1.175.0). The historical
scans were run on macOS arm64.

## 1. Current audit path (tools in this revision)

```sh
python tools/fetch_corpus.py           # "lock unchanged": all 8 package records match
python -m pytest                       # 235 passed, 1 skipped (POSIX permission test; run as root)
python tools/reproduce_paper.py --out-dir <new dir> --with-semgrep
PYTHONPATH=src python tools/control_rescan.py --check
```

`reproduce_paper.py` output (abridged):

| Step | Status | Detail |
|---|---|---|
| corpus | PASS | 8/8 packages verified (archive SHA-256 and extracted-tree hash) |
| scan-v080 | PASS | v0.8.0 from a disposable worktree at tag `v0.8.0`: 621 findings, identical to `bench/rescan-f2` |
| scan-current | PASS | current detector: 476 findings, identical to `bench/rescan-v2` |
| coverage | PASS | 255/621 and 252/476 co-located; all 1,097 per-finding rows identical to the frozen exports |
| delta | PASS | `rq5_refactor_delta.py` recomputed from the fresh rows equals `bench/rq5-refactor-delta.json` |
| e722 | PASS | 134 E722 and 334 BLE001 candidates; 12/12 and 0/12 original DEFECT labels |
| probes | PASS | 68-probe matrix identical to `bench/lint-rule-mapping.json` apart from the interpreter path; parity exact |
| refix | PASS | 36 mapping tests: 21 fail on the reconstructed pre-fix predicate |
| semgrep | PARTIAL | see section 3 |

`control_rescan.py --check`: CHECK-OK for all eight control packages.

Additional checks run by hand:

* The v0.9.1 tag (worktree, its own exporter) also reproduces the 476-finding frame.
* `coverage_union.py --ruff-select S110,S112,BLE001` on the 621 frame: union 255,
  ruff co-located 127, silent-suppress 0/19.
* All 969 Ruff rules (`--select ALL`) and Pylint's default message set over the
  five files holding the 19 `silent-suppress` findings: within ±1 line of those
  sites only `E501` (4 sites) and `C0301` (1 site), both line-length messages.
* Handler counts by direct AST walk over the scan roots: 2,270 `except` handlers
  (main), 243 (control core), 842 (control, all eight).
* `tools/verify_claims.py --skip-slow`: two claims fail, and fail identically on a
  clean checkout of `origin/main` (f02d70c): `F1.delta_bound` needs commit
  `6eb7973`, which is not in the public history, and
  `V2.frozen_truth_untouched` refers to a figure file renamed in an earlier
  revision. Neither expectation was changed.

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
252/476 (52.9%), and every per-finding row (621 and 476) is identical to
`bench/corpus-coverage-per-finding-621.jsonl` and `-v2.jsonl`.

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

Direct access to arxiv.org, doi.org, api.crossref.org and dblp.org was blocked
by the session's network policy; the following were confirmed through
search-index copies of the authoritative listings and should be re-checked on
the live pages before upload:

* `do2022`: DBLP author record "Lisa Nguyen Quang Do" (pid 183/1600); IEEE TSE
  48(3):835–847, 2022, DOI 10.1109/TSE.2020.3004525. The family name is
  "Nguyen Quang Do"; the earlier entry rendered it as "Do".
* `masters2026rolloutcards`: arXiv:2605.12131v1 [cs.AI], submitted 12 May 2026,
  the only version indexed. Pinned to v1.

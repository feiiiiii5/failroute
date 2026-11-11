# Final validation for the reconciled arXiv manuscript

Date: 11 November 2026. Release tag: `arxiv-20261111-final`.

The author cancelled the previous submission. This revision prepares a new final source package; it does not submit or accept any arXiv terms. The work is a descriptive measurement case study, not a claim of incremental defect detection or independent defect ground truth.

## Resolved issues

- Removed active 3/14 detection, 5/14 handler-reachability and 9/14 non-handler assertions from abstract, contributions, tables, figures, discussion and conclusion. The only remaining ratios explain their withdrawal. Sixteen source-linked review dispositions are reported without constructing a replacement defect denominator.
- Distinguished silent success, broader sentinel/logged continuation, adjacent hazards and semantic detection from warning proximity. Pure-additive edits are not excluded from scope merely because the old matching driver missed them.
- Repaired PR matching for pure additions, deletion/replacement hunks and renamed base files; output is explicitly `location_match`, with retrieval failures separate from misses. Twenty-one regression tests cover matching and frozen-output safety. Historical CSV and annotations remain byte-identical.
- Corrected the JSONEncoder.default rationale, Semgrep partial-analysis interpretation, fixed-denominator/read-set wording and overly strong same-handler co-location statements.
- Replaced obsolete/destructive reproduction recipes with current protected drivers, including a new fully executable held-out reproduction. Added provenance corrections without editing the original protocol, corpus locks or measured exports.
- Removed an unsupported “no other conflicts” declaration; retained the documented author/tool/selection relationships. Preserved the manuscript's existing CC BY 4.0 statement and code MIT licence.

## Executed verification

Machine-readable evidence and concise logs are under `paper/validation-20261111/`.

- Main scientific reproduction: 9 PASS. Eight development archives/trees verified; both 621/476 scans and 255/621, 252/476 per-finding coverage files are byte-identical; delta, E722 and 68-probe outputs match apart from documented timestamps/interpreter. Pre-fix mapping replay yields the expected 21 failing and 15 passing tests.
- Held-out reproduction: 9 PASS. Both recorded detector commits reconstruct 322/248 full-row findings; four primary/no-vendor coverage aggregates match, refined per-finding rows match, and all scientific fields of the analysis match. Core result remains 99/322 versus 88/248.
- Test suite: 269 passed, including 21 PR matching and four new held-out driver tests; coverage 89.84% exceeds the 88% gate. Ruff passes on the published tree and mypy passes on all 15 source files. A clean staged-tree self-scan passes its high-severity gate (one pre-existing medium finding in the lint probe instrument, zero high findings). Two pre-existing untracked human-label scripts were preserved and excluded from publication and this lint gate.
- Main numerical text gate: 16/16; independent raw-record number gate: 27/27. Rechecked after final prose changes.
- Frozen-input/derived-artifact gate: zero protected changes, derived text and figure geometry match, development corpus verified. The original held-out manifest is retained.
- Control corpus: eight packages, 154 findings, specified key comparison passes. This is not a rerun of the control linters or all-field JSON comparison.
- Python 3.11.15 AST parsing succeeds for all 2,124 development and 1,564 held-out Python files. This does not imply all linters completely parse them.
- Final PDF: 28 A4 pages, 4 figures, 14 tables, 25 cited references, embedded fonts, no encryption or JavaScript. Tectonic compile has zero errors, undefined references or overfull boxes; three harmless underfull warnings remain. Every page was visually inspected, then all seven changed pages rechecked after final layout repairs.
- Bibliography: all cited keys resolve and no duplicate labels; targeted primary-source checks of the recent Rollout Cards, Souza 2026 and Hu 2025 references found no material bibliographic error. This was not an external re-audit of every reference.

The original current-machine corpus hash failures were Finder metadata only: one added inspect_ai .DS_Store was quarantined, and an original deepteam archive .DS_Store was restored. No Python source changed. Old virtualenv console-script shebangs were bypassed only with temporary wrappers to invoke the installed Semgrep interpreter; no version or rule change was made. This run used Ruff 0.16.4, matching the historical table; the paper extra pins 0.16.5 and the manuscript documents the earlier set-equivalence checks.

## Partial results and scientific limits

Semgrep 1.175.0 remains PARTIAL: one inspect_ai file has a syntax/partial-analysis error and one deepteam test file is skipped. The baseline five-tool observed count is 274/621 with upper bound 275; the refined frame is 267/476 with bound 267. Four-tool primary results are unaffected. The diagnostic is retained, not silently treated as a complete PASS.

The evaluated mapping still disagrees on two held-out name-shadowing outputs. It was not tuned on the held-out test set. Original LLM labels lack recoverable model identity; source-based audit is not independent human adjudication. Eight historical claim checks require absent commits or an unreleased companion, and are not reported as newly reproduced. The control tracking records are secondary evidence. Eight purposive held-out packages are not a population sample; both leave-one-out analyses and vendor exclusions are post-hoc. No tolerance-window sensitivity or new human-labelled defect benchmark was created. These boundaries are stated in the manuscript rather than hidden or filled with invented results.

## Safe reproduction

Use a new output directory for each run:

```sh
git checkout arxiv-20261111-final
python3 -m venv .venv
. .venv/bin/activate
pip install '.[test,paper,paper-semgrep]'
python tools/fetch_corpus.py
PYTHONPATH=src python -m pytest
python tools/check_frozen_truth.py --corpus
python tools/reproduce_paper.py --out-dir /tmp/failroute-dev --with-semgrep
python tools/reproduce_heldout.py --out-dir /tmp/failroute-heldout --fetch
PYTHONPATH=src python tools/control_rescan.py --check
python paper/heldout-20261111/extensions-20261111/verify_numbers.py
python tools/check_abstract_len.py
make -C paper/arxiv submission
```

The development driver reports Semgrep as PARTIAL, not a clean full-coverage result. See `docs/merged-pr-matching-protocol.md` before using the PR driver. Never overwrite the historical ledgers to fabricate a repaired rate.

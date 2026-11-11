# Reconciliation — 2026-11-11

Two independent lines of work on this manuscript diverged and were merged on
2026-11-11. This file records what was taken from where, what is preserved, and
what remains **unresolved**. Nothing was deleted.

## 1. The two lines

| | Line A — held-out | Line B — PR #4 audit |
|---|---|---|
| Commit | `828f9c69` (branch `heldout-20261111`) | `370c3ed` (merged PR #4, was `main`) |
| Common ancestor | `15dffaa` (12 Oct 2026) | same |
| Manuscript date | 11 November 2026 | 3 November 2026 |
| Pages | 29 | 21 |
| Title subtitle | Representation, Calibration, and Validation Limits | Representation, File Discovery and Denominators in AI/ML Python |
| Core addition | Held-out replication on 8 unseen packages (415,101 lines), leave-one-out on **both** corpora, dspy sensitivities, 27-check independent recomputation gate | Reference audit of all 16 curated PRs, annotation rationale correction, frozen-truth byte guards, one-command audit re-execution, figure-geometry checks |

**Neither line is a superset of the other.** Line A never saw Line B's audit;
Line B never saw the held-out experiment.

## 2. What the merge did

- `paper/arxiv/main.tex`, `main.pdf`, `main.zip` → **Line A**, because that is
  the version submitted to arXiv on 2026-11-11. `main.pdf` is byte-identical to
  the submitted artefact (`fe1d1abd53ced471364b9a98fa0d7be154ab7158f0a9065be8fbac6242b355dd`).
- **All 14 Line-B-only files kept**, including `paper/reference-audit.json`,
  `paper/annotation-corrections.json`, `paper/frozen-truth-sha256.json`,
  `paper/SUBMISSION-CHECKLIST.md`, `paper/audit-rerun-2026-11-03.md`,
  `docs/annotation-revalidation-protocol.md`,
  `bench/semgrep-diagnostic-2026-11-03.json`, `tests/test_paper_reproduction.py`,
  and `tools/{reproduce_paper,check_frozen_truth,pdf_geometry,_frozen_guard,reproduce_warning_coverage,semgrep_diagnostic}.py`.
- All Line-B modifications to shared tools kept (`coverage_union.py`,
  `make_figures.py`, `verify_claims.py`, `fetch_corpus.py`, …).
- Line B's 21-page manuscript **archived** at
  [`archive/pr4-20261103/`](archive/pr4-20261103/) (tex + pdf), so its unique
  sections are not lost: *Data availability*, *Conflict of interest*,
  *Manuscript licence*, *Artefact inventory*, *Measurement corrections and
  revision history*.
- `README.md` resolved to describe Line A **and** retain Line B's withdrawal
  notice, with an explicit discrepancy banner.
- `paper/ARTIFACT.md` keeps Line B's audit entrypoint, with a banner stating
  that the current manuscript is Line A.

A force-push of Line A onto `main` would have deleted those 14 files and
reverted ~34 more (net −3,870 lines). That is why this was a merge.

## 3. 🔴 Unresolved: the submitted paper reports withdrawn ratios

`paper/reference-audit.json` (2026-11-03) lists under `withdrawn_claims`:

```
"3/14 detector matches as semantic detection"
"5/14 local-handler reachability bound"
"9/14 non-handler share"
```

Reasons recorded there:

- `historical_matching_limitation`: the historical driver derives candidate
  sites from **removed** Python lines, so additive fixes can be omitted, and
  proximity to changed lines does not prove semantic detection.
- The sixteen records are heterogeneous and "do not define a consistently
  adjudicated defect denominator".

Reclassification of the same 16 rows: **10 supported, 3 excluded, 2 uncertain,
1 location-only**. Notably `truera/trulens#2653` — counted as one of the three
detector matches in the submitted version — is **location-only**.

**The submitted 11 November manuscript still asserts all three ratios:**

| Location in submitted manuscript | Claim |
|---|---|
| Abstract | "Nine of 14 in-scope curated fixes route failure outside handlers" |
| Contributions list | "Nine of 14 in-scope curated merged fixes route failure outside exception handlers" |
| §6.4.1 | "3 of 14 in-scope fixes (21.4%)", "at most 5 of 14 (35.7%)", "nine of 14 (64.3%)" |
| Table 9 (`tab:recall`) | 2 out-of-scope / 3 detected / 2 handler-shape gap / 9 non-handler |
| Figure 3 | pooled split by defect family |
| §4 scope boundary, Discussion, Threats, Conclusion | repeated 9-of-14 framing |
| Table 2 (`tab:evidence`) | "9 of 14 in-scope merged fixes are outside handlers" |

Also unresolved: `paper/ARTIFACT.md` line "The current Figure 3 reads the audit
sidecar and reports no pooled rate" describes Line B's figure, not Line A's.

### What is NOT affected

The withdrawal is confined to the curated-fix construct-scope ratios. These
remain independently verified and unaffected:

- held-out replication: 322→248 findings, 99→88 covered, 30.7%→35.5%,
  decomposition +9.17/−4.44/+4.74, both leave-one-outs, dspy sensitivities,
  suppress 24/24 and 9/9, static/empirical 246/248
- read-set correction: 152 of 2,124 files, 34 messages, union 250→255
- 68-probe calibration: 146 over-credited = 137 + 9, 87→224, item-level
  agreement on all 476
- denominator decomposition: 621/255 → 476/252, +12.51/−0.63/+11.88
- E722 baseline: 134 candidates covering all 12 original DEFECT labels

### What an arXiv v2 would need

1. Remove or explicitly re-scope the three ratios wherever they appear (list
   above), replacing them with the audit's per-record statuses and the
   `location-only` caveat.
2. State the removed-lines matching limitation next to any curated-fix claim.
3. Fold in `annotation-corrections.json` (the `JSONEncoder.default` rationale
   correction: returning `None` serialises as JSON null and is **not** a
   not-serialisable signal).
4. Consider restoring Line B's *Data availability*, *Conflict of interest* and
   *Manuscript licence* sections from the archive.
5. Re-run `tools/reproduce_paper.py`, `tools/check_frozen_truth.py`,
   `paper/heldout-20261111/scripts/check_paper_heldout.py` and
   `extensions-20261111/verify_numbers.py`, then rebuild the source tar, PDF,
   abstract and hashes.

**This is an author decision.** No v2 was prepared or submitted here.

## 4. Preserved locations

| Content | Where |
|---|---|
| Submitted 29-page manuscript | `paper/arxiv/main.{tex,pdf,zip}`; arXiv submission of 2026-11-11 |
| PR #4 21-page manuscript | `paper/archive/pr4-20261103/`; git `370c3ed` |
| Held-out record + post-hoc extension | `paper/heldout-20261111/` (47 files; corpus gitignored) |
| Reference audit + withdrawals | `paper/reference-audit.json` |
| Annotation rationale correction | `paper/annotation-corrections.json` |
| Frozen-truth byte manifest (7 data files) | `paper/frozen-truth-sha256.json` |
| arXiv delivery package + hashes | `/Users/fei/Desktop/failroute-arxiv-20261111/` |
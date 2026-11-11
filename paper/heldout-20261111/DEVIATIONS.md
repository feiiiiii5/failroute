# Post-freeze deviations and analysis decisions

**Date:** 2026-11-11, after the primary held-out counts were produced.
**Protocol:** [`PROTOCOL.md`](PROTOCOL.md), SHA-256
`02a108b493e057d436368f6128687e750d15af16662b9c592299d6e2e1b9afdc`.
The protocol text is unchanged. This file records decisions made after the
freeze so they are not mistaken for pre-registration.

## 1. `dspy/_vendor` and dspy dominance

The primary scan found that `dspy` contains an internal `_vendor/` subtree and
contributes 175 of the 322 v0.8.0 findings and 114 of the 248 v0.9.1 findings.
The protocol said that vendored third-party code *outside* the main package
directory is excluded; it did not anticipate a vendored directory *inside* the
package body. The primary result therefore includes `dspy/_vendor` as registered.

After seeing the per-package counts, two structural sensitivities were added:

1. exclude `dspy/_vendor` from both frames;
2. exclude the `dspy` package entirely from both frames.

They are **post-hoc**, not pre-registered. They are reported because one package
dominating an aggregate is a structural concern independent of the direction of
the result. They are not used to select a "positive" outcome; the primary result
is reported first, and the sensitivities are reported as sensitivities.

The sensitivities preserve the share rise and reverse the covered-count sign.
The paper reports exactly that: the share result replicates; the absolute
covered-count result is not robust.

## 2. Analysis scripts

`scripts/analyze_heldout.py` was written after the primary counts, but it only
reads the saved JSONL/JSON records and computes the metrics that the protocol
specified. `scripts/check_paper_heldout.py` checks the manuscript's held-out
numbers against `comparison.json`.

## 3. What did not change

The package list, versions, scan roots, detector versions, linter rules,
co-location tolerance, primary metrics and H1–H6 hypotheses were not changed
after the freeze. No package was replaced. No held-out label was produced. No
result was removed.

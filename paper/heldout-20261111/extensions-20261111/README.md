# Post-freeze extension — 2026-11-11

**Status:** post-hoc analysis added during an external review pass, after the
primary held-out counts and after the two `dspy` sensitivities in
[`../DEVIATIONS.md`](../DEVIATIONS.md).

**Nothing frozen was changed.** The protocol, package list, versions, scan
roots, detector versions, linter rules, ±1-line tolerance, primary metrics and
H1–H6 are untouched. No detector, linter or model was run for this extension.
Every number here is recomputed from already-committed records.

## 1. Why this exists

The original study reported leave-one-package-out and two structural
sensitivities for the **held-out** corpus only. The development corpus was
presented as the reference result, with no equivalent robustness check. That
asymmetry made the paper's claim ("the share result replicates, the
covered-count result does not") rest on robustness evidence from one side
only.

## 2. What was computed

`dev_leave_one_out.py` recomputes the development frame's leave-one-package-out
from the committed per-package aggregates of the two frames:

- `bench/corpus-coverage-union.json` — 621 findings, 255 covered
- `bench/corpus-coverage-union-v2.json` — 476 findings, 252 covered

The script asserts that the per-package sums equal each file's headline
totals before computing anything, and exits non-zero if they do not.

## 3. Result

Primary development frame: 255/621 → 252/476, share 41.06% → 52.94%,
covered change **−3**.

| Excluded | old C/N | new C/N | share change | covered change |
|---|---|---|---:|---:|
| deepteam | 124/481 | 125/342 | +10.77 | **+1** |
| fickling | 252/611 | 248/469 | +11.63 | −4 |
| garak | 248/605 | 233/442 | +11.72 | −15 |
| inspect_ai | 160/300 | 173/274 | +9.81 | **+13** |
| pydantic_ai_slim | 247/539 | 244/429 | +11.05 | −3 |
| smolagents | 253/608 | 250/464 | +12.27 | −3 |
| trl | 251/595 | 246/450 | +12.48 | −5 |
| uqlm | 250/608 | 245/462 | +11.91 | −5 |

- Share change is **positive in all eight** exclusions, range **+9.81 to +12.48** pp.
- Covered-count change **reverses sign under two** exclusions: `deepteam` (+1)
  and `inspect_ai` (+13). Six keep the decline.

## 4. Effect on the paper's claim

The development covered-count decline is **not robust either**. The correct
claim is symmetric, and stronger than the original asymmetric one:

> The share rise survives every single-package exclusion in **both** corpora.
> The covered-count sign does not survive them in **either** corpus.

This removes a genuine internal tension: the manuscript previously said both
"the sign pattern is the same as the development corpus" and "the covered-count
result does not replicate". Both statements are now replaced by the robustness
formulation, which is what the evidence actually supports.

Held-out reversals for comparison: 1 of 8 exclusions (`dspy`), plus both
structural sensitivities (`dspy/_vendor`, whole `dspy`).

## 5. Independent verification

`verify_numbers.py` is a second gate that, unlike
`../scripts/check_paper_heldout.py`, **recomputes** every headline quantity from
the raw per-finding records before comparing it to `comparison.json` and to the
manuscript. It covers the held-out chain, both leave-one-outs, the suppress
boundary, the two `name-shadowing` disagreements, item-level static/empirical
agreement on all 476 development findings, the calibration arithmetic, and three
wording guards. Result: **27/27 passed** (`verification.json`).

The original archived checker is left byte-unchanged so the historical record
still shows what was run at freeze time.

## 6. Files

| File | Role |
|---|---|
| `dev_leave_one_out.py` | development leave-one-out; reads committed aggregates only |
| `dev-leave-one-out.json` | its output, including all eight rows and the decomposition |
| `verify_numbers.py` | independent recomputation gate (27 checks) |
| `verification.json` | its output |
| `README.md` | this record |

## 7. What this does not do

It does not add packages, change any metric, produce labels, estimate defect
precision, or re-estimate PR scope. It is a robustness check on an existing
result, reported in whichever direction it falls.
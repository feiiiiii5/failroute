# `bench/realworld/` — external regression bench for the failroute predicate

Built **before** the V1 predicate refactor was touched, so that the refactor is
measured against expectations that did not come from the person writing the
detector. The paper's own RQ4 records why this ordering matters: the
hand-written fixture corpus under `tests/corpus/` failed to catch the
detector's `for stmt in handler.body` blind spot, because the fixtures and the
detector shared an author and therefore a blind spot.

Per 委外任务清单.md §V1.2 step 1 and §V1.5, this directory is the only place the
V1 batch is authorised to create files.

## Contents

| file | what it is |
|---|---|
| `cases.jsonl` | 87 cases: 80 labelled real-world coordinates + 7 probe shapes |
| `run.py` | gate runner; exit 0 only when every gate passes |
| `README.md` | this file |

## Provenance of the 87 cases

**80 corpus cases** — one per row of `paper/annotations.csv` (read-only; never
modified by this bench). Each carries the coordinate `(file, lineno)` inside the
SHA256-locked corpus (`paper/corpus-lock.json`), the human label
(`DEFECT` / `CONTRACT` / `FALSE_POSITIVE`), the annotator's rationale, and the
structural facts read back out of the corpus source at generation time:
enclosing function name, return annotation and its bucket, handler exception
expression, whether the handler is bare / catch-all, the number of statements in
the guarded `try` body, and whether that body contains a loop or comprehension.

Labels were written twice, independently (`paper/annotations.csv` and
`paper/annotations-second-pass.csv`); all 87 cases record
`second_pass_agrees`, which is `true` for 80/80.

Labels are bound to the **coordinate**, not to a tool version. A coordinate that
the refactored detector no longer reports keeps its label; that is what makes
the pre/post comparison a comparison on one fixed set of truths.

**7 probe cases** — the shapes in 委外任务清单.md §V1.0-A table C1–C7, written
out as self-contained snippets in the `source` field. Their expectations are the
"应然" column of that table, which is where five of the seven disagreed with
failroute 0.8.0's actual behaviour.

## Gates

| gate | cases | expectation |
|---|---|---|
| `G0.probe-table` | 7 | each probe matches its §V1.0-A "应然" column |
| `G1.no-regression` | 12 | every `DEFECT` still reported at severity ≥ `MEDIUM` |
| `G2.distinguishable` | 36 | every `-> None` / `Optional[...]` contract at severity ≤ `INFO` (or not reported) |
| `G2.fail-closed-positive` | 1 | `is_private_ip` (`_ssrf.py:279`) not reported at all |
| `G3.isomorphism-matrix` | 16 | the `-> bool` cases; recorded as a confusion matrix, not pass/fail |
| *(no gate)* | 24 | recorded only — deliberately **not** gated, so the bench cannot be tuned to them |

`G2.distinguishable` is 36 cases here, not the 35 in §V1.0-B: recomputing the
annotation buckets from the corpus source puts 24 `CONTRACT` rows in `-> None`
and 12 in `Optional[...]`. The one-row difference is recorded in the V1 result
section rather than silently absorbed.

Severity lattice, ascending: `NONE` (not reported) < `INFO` < `LOW` < `MEDIUM`
< `HIGH`.

The 24 ungated cases are the honest part of this bench. Gating only the
expectations that follow from the design would let the implementation be tuned
until green; recording the rest means the report can show where the new
predicate disagrees with a human label without that disagreement being hidden.

## Running

```bash
cd 新项目-failroute
PYTHONPATH=src python3 bench/realworld/run.py            # gate report
PYTHONPATH=src python3 bench/realworld/run.py --verbose  # every case
PYTHONPATH=src python3 bench/realworld/run.py --json     # machine-readable
PYTHONPATH=src python3 bench/realworld/run.py --gate G1.no-regression
```

`PYTHONPATH=src` is mandatory: the repository path contains non-ASCII
characters, which defeats the editable-install `.pth` file.

## Pre-refactor detector

`run.py` also runs against failroute 0.8.0, which has **no per-finding
severity** — only a per-rule SARIF level. For that detector the rule's declared
level stands in (`error` → `HIGH`, `warning` → `MEDIUM`), and the runner prints
`per-finding severity supported: NO`. This is not a cosmetic gap: a detector
with only per-rule severity **cannot express** "downgrade this finding to INFO",
so gate `G2` is unreachable for 0.8.0 by construction. That baseline is recorded
in the V1 result section.

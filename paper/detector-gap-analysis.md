# Detector Gap Analysis: why handler-anchored detection misses most of the family

**2026-08-30 · derived from `paper/merged-pr-recall.csv`, with every case re-read against the pre-fix source**

---

## 1. Why this document exists

The recall measurement reported "1 of 10". That number is correct but **under-analysed**, and
reporting it as-is would be both weaker and less honest than what the data actually supports.
Two of the ten cases should not be in the denominator at all, and — far more importantly —
the seven misses are not one failure mode. They are **two**, and the larger one is a finding.

Every case below was re-read against the actual pre-fix file (`gh api .../contents/<path>?ref=<parent-sha>`),
not inferred from the diff.

---

## 2. Case-by-case, corrected

| PR | Handler at defect site? | Where the failure→success conversion happens | Verdict |
|---|---|---|---|
| **uqlm #450** | ✅ yes | `except: pass`, then empty list returned; downstream index alignment silently shifts | **detected** (`no-action`) |
| **inspect_ai #5068** | ✅ yes | handler logs at WARNING then assigns `exists = True`; code after the `try` branches on `exists` | **missed** — handler present, sink is a *local assignment*, not a return |
| **inspect_evals #2167** | ❌ no | `if not issue_id: return Score(value=0.0, ...)` — an ordinary guard branch | **missed** — no handler anywhere near |
| **uqlm #462** | ❌ no | NaN from exhausted retries reaches aggregation via data flow | **missed** — no handler |
| **uqlm #459** | ❌ no | failed judge's NaN enters panel aggregates via data flow | **missed** — no handler |
| **PyRIT #2466** | ❌ no | unresolvable techniques dropped by silent list filtering | **missed** — no handler |
| **inspect_ai #4906** | ❌ no (in user code) | `tenacity` RetryError opaquely masks the underlying cause | **missed** — conversion is inside a library |
| **uqlm #418** | ❌ no | function annotated to return a float falls through to implicit `None` | **missed** — no handler; by-design uncovered |
| **uqlm #425** | — | **pre-fix code crashed** (`ZeroDivisionError` propagated); the fix *added* a guard | 🔴 **should be excluded** — there was no failure-routing construct to detect |
| **PyRIT #2460** | — | TypeScript | 🔴 **excluded** — out of language scope |

### 2.1 Two verified excerpts

**inspect_evals #2167**, pre-fix `src/inspect_evals/swe_lancer/scorers.py`:

```python
issue_id = state.metadata.get("issue_id")
if not issue_id:
    return Score(value=0.0, answer="No issue_id found", metadata={})
```

A missing `issue_id` means the scorer *cannot evaluate anything*. It returns `0.0` — a value
squarely inside the scorer's legitimate range. An aggregate over many samples cannot separate
"the model scored zero" from "we never ran the evaluation". **No exception is involved at any
point.**

Note the second-order observation: the same file *does* contain a handler-shaped construct a
few lines earlier (`except Exception as e: logger.warning(...); patch_content = ""`), which
`failroute` does flag. So on this file the tool reports a finding **and misses the actual
defect** — a precision and a recall failure in the same function.

**inspect_ai #5068**, pre-fix `src/inspect_ai/log/_file.py`:

```python
try:
    exists = fs.exists(log_dir)
except Exception as ex:  # noqa: BLE001
    if should_suppress_azure_error(log_dir, ex):
        logger.warning(azure_warning_hint(log_dir, ex))
        exists = True
    else:
        raise
if not exists:
    return []
```

This is the closest miss. There *is* a handler, and it *is* a conditional re-raise with a
constant fallback — which is exactly what the `masked-exception` rule was written for. It is
missed because the constant is **assigned to a local that the code after the `try` branches
on**, rather than returned from the handler. The rule's sink model is too narrow by one step.

---

## 3. The corrected numbers

| Denominator | Count | Detected | Rate |
|---|---|---|---|
| All family cases in the merged-PR set | 10 | 1 | 1/10 |
| Excluding TypeScript (#2460) and the no-construct case (#425) | **8** | 1 | **1/8** |
| Restricted to cases with a handler at the defect site | **2** | 1 | **1/2** |

## 4. 🎯 The actual finding

> **In 8 expert-validated instances of this defect family, 6 (75%) convert a failure into a
> success-shaped result with no exception handler at the defect site.**

Every shipped detector for this family is anchored on the handler:

| Tool | Rules | Anchored on |
|---|---|---|
| ruff | S110, S112 | `except` block |
| Bandit | B110, B112 | `except` block |
| pylint | W0702, W0703, W0705, W0706 | `except` clause |
| flake8-bugbear | B001, B017 | `except` clause |
| **failroute** | all six detectors | `except` / `contextlib.suppress` |

They are therefore **structurally blind to three quarters of the family** — not because of
implementation weakness, but because of where they attach to the AST.

This reframes the contribution. The paper is not "here is a detector for silent failures."
It is: **the defect class is substantially wider than the syntactic anchor every existing tool
uses, and we can show that with expert-validated ground truth.**

---

## 5. Four detector gaps, each grounded in a specific case

Each is derived from a real missed defect, not from speculation.

### G1 · `handler-state-mutation` — from inspect_ai #5068

Handler assigns a success-shaped constant to a **local variable** that control flow after the
`try` block depends on.

*Shape*: `try: X = f()` / `except: ... ; X = <const>` / `if not X: <early return>`
*Why detectable*: purely intra-procedural. Track names assigned inside the handler; check
whether any is read in a branch condition after the `try` statement.
*Expected difficulty*: **low**. This is a one-step widening of the existing `masked-exception`
sink model.

### G2 · `invariant-constant` — from inspect_evals #2167

A guard branch on a **broken precondition** returns a constant that lies inside the function's
legitimate value range.

*Shape*: `if not <required>: return <constant>` where other returns of the same function
produce values of the same type and range.
*Why detectable*: intra-procedural. Collect all `return` value shapes in the function; flag a
guard-branch return whose constant is indistinguishable from a success value.
*Expected difficulty*: **medium** — needs a notion of "legitimate range", which in practice
reduces to "another return in this function produces the same literal type".
*Expected precision*: lower than the handler rules — many guard returns are the documented
contract. This one belongs behind an opt-in flag.

### G3 · `silent-drop` — from PyRIT #2466

A comprehension or filter discards elements with no count, no log, and no error.

*Shape*: `[f(x) for x in xs if <resolvable(x)>]` or an explicit loop with `continue`, where
`len(result) < len(xs)` is possible and nothing records the difference.
*Why detectable*: intra-procedural, but needs a heuristic for "the dropped items mattered".
*Expected difficulty*: **medium-high**; likely high false-positive rate.

### G4 · `contract-fallthrough` — from uqlm #418

A function annotated `-> T` (with `T` not `Optional`) has a reachable path that falls through
to an implicit `None`.

*Shape*: annotated return type is non-optional; CFG has a terminal path with no `return`.
*Why detectable*: this is close to what `mypy --warn-no-return` already does — the contribution
would be framing it as a member of this family, not the detection itself.
*Expected difficulty*: **low**, but **low novelty**.

### Out of reach (state honestly, do not attempt)

- **uqlm #462 / #459** — NaN propagating into an aggregate. Requires interprocedural
  value tracking. Not reachable by an AST-level tool; say so.
- **inspect_ai #4906** — the masking lives inside `tenacity`'s retry semantics, i.e. inside a
  third-party library. Would require library-specific modelling.

---

## 6. 🔴 Discipline for acting on this

1. **The frozen baseline must not move.** `bench/paper-baseline.json` pins commit, version and
   corpus. If new detectors are implemented, they ship as **opt-in, default-off** rules, and
   every existing figure is recomputed only under the frozen rule set.
2. **Measure the new rules against the same 8-case expert set**, and report before/after
   side by side. A recall improvement claimed on the cases the rules were designed from is
   **overfitting, and must be labelled as such** — it is a demonstration of reachability, not
   an evaluation.
3. **The negative result is the paper's spine and must survive.** "We found the gap" is the
   contribution; "we then closed part of it" is a corollary. Do not invert them — a tool paper
   with a patched-up recall number is far weaker than a characterization study with an honest
   boundary.
4. **G2 and G3 will hurt precision.** Ship them off by default and report their precision from
   the annotation study separately, not blended into the headline number.

---

## 7. What this changes in the paper

| Section | Change |
|---|---|
| **Title / framing** | From "a detector and a study" to **the defect class is wider than every tool's syntactic anchor** |
| **RQ3** | Replace bare "recall 1/10" with the corrected denominator (1/8) **and** the handler-presence split (6/8 have no handler) |
| **New RQ** | *Where does the conversion actually happen?* — answered by the table in §2 |
| **Discussion** | §5's four gaps become the concrete future-work agenda, each with a named case |
| **Threats** | Add: expert-validated set is only 8 cases; all drawn from repos the author contributed to (selection bias) |

---

## 8. Provenance

Every row in §2 was verified by fetching the pre-fix file directly:

```bash
SHA=$(gh api repos/<owner>/<repo>/pulls/<N> --jq '.merge_commit_sha')
PAR=$(gh api repos/<owner>/<repo>/commits/$SHA --jq '.parents[0].sha')
gh api "repos/<owner>/<repo>/contents/<path>?ref=$PAR" --jq '.content' | base64 -d
```

The two excerpts in §2.1 are verbatim from those fetches (2026-08-30).

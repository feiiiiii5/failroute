# Failure-Routing in AI/ML Codebases: How Often Is a Swallowed Failure a Bug?

**Draft v0.1 — 2026-08-31.** All numbers in this draft were produced by the scripts in
`tools/` against the pinned corpus in `paper/corpus-lock.json`. Every figure is
reproducible from this checkout. Numbers that could not be measured are marked
`[TODO]` rather than estimated.

> 🔴 **Author note (not for the paper):** the honesty discipline for this draft is the
> same as for the application materials — no fabricated citations, no fabricated
> numbers, no claimed measurements that were not actually run. Sections marked
> `[TODO]` are genuinely not done yet.

---

## Abstract *(draft)*

Exception handlers that convert a failure into a success-shaped value — an LLM judge
that never ran becoming a legitimate `0.0` score, a parse error becoming "no results" —
produce wrong answers with no crash and no log line. We call this pattern
**failure-routing**. Syntactic linters cannot express it: `except Exception: return 0.0`
is invisible to `ruff`, `bandit` and `flake8-bugbear`, and `ruff`'s own `SIM105` actively
recommends rewriting `try/except/pass` into `contextlib.suppress(...)`, which is
semantically identical and invisible to *every* shipped linter afterwards.

We build a six-rule AST detector for this family and apply it to eight pinned
AI/ML packages (563,270 lines). It reports 649 findings, of which 396 (61%) are not
co-located with any finding from the union of four syntactic linters; for the
`contextlib.suppress` shape the figure is 27/27 (100%).

We then do what tool papers usually skip: **we label a stratified random sample of the
findings** (n = 80). The result is a negative one. Only **12 (15%)** are genuine defects;
**64 (80%)** are deliberate, frequently commented, design contracts; **4 (5%)** were
false positives from a single detector bug that the labelling itself exposed. More
strikingly, **all 12 defects occur in one package**, and in the seven other packages
**0 of 66 sampled findings** were defects.

We further measure recall against an unusually direct ground truth: 10 upstream fixes
in this defect family, authored by us and **merged by the projects' own maintainers**.
The detector finds **1 of 10**.

The picture that emerges is that semantic failure-routing detection has *both* low
precision and low recall on mature code, and that its yield is governed far more by
**codebase maturity** than by rule design. We argue this does not make such detectors
useless — it makes them **search-space reducers** rather than oracles, and we
characterise the conditions under which the reduction pays for the triage it demands.

---

## 1. Introduction

*(Opening: the SIM105 observation. Draft prose to be written by the author; the
factual skeleton is below.)*

- `ruff`'s `SIM105` rule recommends rewriting `try/except/pass` into
  `contextlib.suppress(...)`. The two forms are semantically identical.
- After the rewrite, **no shipped Python linter reports the construct.** In our corpus,
  all 27 `contextlib.suppress` findings are invisible to the union of ruff, bandit,
  pylint and flake8+bugbear (§4.1).
- A widely adopted refactoring therefore moves an entire defect shape out of the
  tools' field of view while leaving its runtime consequences unchanged.

**Contributions.**
1. A taxonomy of six failure-routing shapes and an AST detector for them (§3).
2. A reproducible prevalence and cross-tool coverage measurement over 8 pinned
   packages (§4.1).
3. **A labelled stratified sample (n = 80) giving the first precision estimate for
   this detector family on real code** (§4.2) — the paper's main empirical result,
   and a negative one.
4. A recall measurement against maintainer-merged fixes (§4.3).
5. Evidence that systematic labelling is itself a detector-improvement method: it
   exposed a defect that accounted for 100% of one rule's real-world findings (§4.4).

---

## 2. The pattern family

Six shapes, all reducible to *"a failure became a value the caller cannot distinguish
from success"*:

| Rule | Shape | Consequence |
|---|---|---|
| `no-action` | `except ...: pass` | caller never learns the operation failed |
| `silent-fallback` | handler returns/assigns a constant without re-raising | judge outage becomes a legitimate `0.0` |
| `masked-exception` | catch-all conditionally re-raises *and* falls back to a constant | outcome depends on which branch ran |
| `silent-suppress` | `with contextlib.suppress(...)` | same semantics as `except+discard`; invisible to all shipped linters |
| `implicit-fallback` | handler neither re-raises, returns, nor records — falls through to implicit `None` | "did nothing" becomes a legitimate `None` |
| `name-shadowing` | `except E as e:` rebinds `e` inside the handler | Python deletes the binding on exit → `NameError`; original exception lost |

---

## 3. Detector

*(Short — the tool is the instrument, not the subject.)*

AST-based; six rules behind a shared registry; text/JSON/SARIF output;
`# failroute: ignore` opt-out; `[tool.failroute]` per-rule configuration.
Quality gates: **130 tests** across 3 OS × 5 Python versions, `mypy --strict`,
and a hand-labelled unit corpus (v6, 68 samples: 36 positive / 32 negative)
whose labels were written independently of tool output, held to
precision = recall = 1.0 in CI.

🔴 **Construct-validity caveat, stated up front:** that 1.0 is evidence the detector
matches its own specification, **not** evidence it finds real defects. §4.2 is the
external-validity measurement, and it tells a very different story.

---

## 4. Study

### 4.0 Corpus

Eight AI/ML packages fetched as **pinned PyPI source distributions** (not git clones),
each recorded with URL, SHA-256, upload time and extracted tree hash in
`paper/corpus-lock.json`:

| Package | Version | Scan root | .py files | Lines |
|---|---|---|---|---|
| inspect_ai | 0.3.260 | `src/inspect_ai` | 755 | 198,351 |
| pydantic_ai_slim | 2.36.0 | `.` | 298 | 119,534 |
| deepteam | 1.0.9 | `deepteam` | 588 | 71,305 |
| trl | 1.12.0 | `trl` | 155 | 65,727 |
| garak | 0.16.0 | `garak` | 201 | 38,328 |
| smolagents | 1.26.0 | `src/smolagents` | 20 | 13,355 |
| uqlm | 0.6.5 | `uqlm` | 91 | 12,605 |
| fickling | 0.1.12 | `fickling` | 16 | 5,024 |
| **Total** | | | **2,354** | **563,270** |

*Rationale:* pinned sdists make the artifact reproducible by anyone with network
access and no git history; a reviewer re-running `tools/fetch_corpus.py` gets
byte-identical inputs.

### 4.1 RQ1 — Prevalence and cross-tool coverage

`failroute` reports **649 findings**. Baselines were run on the *same* pinned trees:

| Tool | Version | Rules | Findings | Co-located with a failroute finding (±1 line) |
|---|---|---|---|---|
| **failroute** | 0.7.0 | all six | **649** | — |
| ruff | 0.16.0 | S110, S112 | 76 | 72 |
| bandit | 1.9.4 | B110, B112 | 67 | 63 |
| pylint | 4.0.8 | W0702/3/5/6 | 529 | 248 |
| flake8+bugbear | 7.3.0 / 25.11.29 | E722, B001, B017 | 268 | 124 |
| semgrep | — | — | *not run* | — |

**Union of all four syntactic linters covers 253 of 649 (39.0%).
`failroute`-only: 396 (61.0%).**

Per rule:

| Rule | Total | Covered by union | Coverage | failroute-only |
|---|---|---|---|---|
| `silent-fallback` | 400 | 178 | 44.5% | 222 |
| `no-action` | 219 | 72 | 32.9% | 147 |
| **`silent-suppress`** | **27** | **0** | **0.0%** | **27** |
| `masked-exception` | 3 | 3 | **100.0%** | 0 |
| `implicit-fallback` | 0 | — | — | — |

**Two honest observations that cut against the tool:**

1. **`pylint` is a far stronger baseline than `ruff`.** Comparing only against
   `ruff`'s `S110`/`S112` — as our own earlier benchmark did — overstates novelty by
   roughly 3.4× (72 vs 248 co-located findings). Any paper in this space that
   benchmarks against `ruff` alone should be read with that in mind.
2. **`masked-exception` is fully covered.** All 3 findings co-locate with a pylint
   broad-except warning. That rule contributes no coverage novelty here.

⚠️ **Methodological caveat on "coverage".** Co-location at ±1 line means a syntactic
tool *flags the same handler*, **not** that it expresses the same property.
`pylint W0703` fires on `except Exception:` regardless of what the handler does; it
does not distinguish "re-raises" from "returns `0.0`". 39.0% is therefore an
**upper bound** on what the syntactic tools actually say, and the semantic novelty is
correspondingly higher than 61%. We report the conservative number.

### 4.2 RQ2 — What fraction are real defects? *(main result)*

**Method.** Stratified random sample over (rule × package), fixed seed (20260831),
every stratum guaranteed ≥1 draw, remainder allocated proportionally.
n = 80. The draw is byte-reproducible (`tools/draw_sample.py`, sha256 recorded).
Each finding was labelled by reading the surrounding source in the pinned tree, into
one of three classes: **DEFECT** (the converted failure produces a wrong
caller-visible outcome with no signal), **CONTRACT** (deliberate, and either
documented, commented, or expressed in the return type), **FALSE_POSITIVE**
(the detector is wrong about the code).

**Result.**

| Label | n | Share |
|---|---|---|
| CONTRACT | 64 | **80.0%** |
| DEFECT | 12 | **15.0%** |
| FALSE_POSITIVE | 4 | 5.0% |

By rule:

| Rule | n | DEFECT | CONTRACT | FALSE_POSITIVE |
|---|---|---|---|---|
| `silent-fallback` | 49 | 12 | 37 | 0 |
| `no-action` | 23 | 0 | 23 | 0 |
| `implicit-fallback` | 4 | 0 | 0 | **4** |
| `silent-suppress` | 3 | 0 | 3 | 0 |
| `masked-exception` | 1 | 0 | 1 | 0 |

**By package — the result that matters:**

| Package | n | DEFECT | CONTRACT | FALSE_POSITIVE |
|---|---|---|---|---|
| **deepteam** | 14 | **12** | 1 | 1 |
| inspect_ai | 41 | 0 | 40 | 1 |
| pydantic_ai_slim | 11 | 0 | 10 | 1 |
| trl | 4 | 0 | 4 | 0 |
| garak | 3 | 0 | 3 | 0 |
| fickling | 3 | 0 | 2 | 1 |
| smolagents | 2 | 0 | 2 | 0 |
| uqlm | 2 | 0 | 2 | 0 |

**All 12 defects are in `deepteam`. Across the other seven packages, 0 of 66
sampled findings were defects.**

The 12 defects are not 12 independent bugs. They are **three homogeneous families**
replicated across metric classes:

1. **Silent criteria degradation (4/12).** `try: self.system_prompt =
   model.get_system_prompt() except: self.system_prompt = ""`. A custom or
   misconfigured LLM that lacks the method silently scores every subsequent case
   under empty criteria. *(This family was independently reported upstream by the
   present author before this study, as `deepteam#270`; that report is partial
   external validation of the label, not of the tool.)*
2. **Dead comparison (5/12).** `try: self.score == 1 except: self.success = False`.
   The guarded statement is a pure comparison expression that cannot raise, so the
   handler is dead code — and `self.success` is never assigned on the success path.
3. **Fail-open security verdict (3/12).** `is_vulnerable()` iterates results inside a
   `try`; on any error it returns `vulnerable = False`. In a red-teaming tool,
   *"not vulnerable"* is the most dangerous possible default: an infrastructure
   failure is converted into a clean security conclusion.

Conversely, the 64 contracts are overwhelmingly **deliberate and legible**: TUI widget
lookups that may not be mounted, optional-dependency probes, idempotent cleanup in
`finally`, and predicate functions whose `Optional`/`bool` return type *is* the contract.
Many carry an explicit comment stating the intent (e.g. inspect_ai's
`"fail open — better to skip the barrier than to hang teardown"`).

Two findings in the sample are worth citing as **positive** examples of the discipline
this paper argues for: pydantic-ai's `is_private_ip` fails **closed** on an unparseable
address (`"Invalid IP address, treat as potentially dangerous" → return True`), and its
`_run_tool` explicitly routes a caught exception onto a queue *so that the consumer
re-raises it* rather than letting it vanish.

⚠️ **Threats specific to this section** — see §6; the most serious is that labelling was
performed by a single annotator who is also the tool's author.

### 4.3 RQ3 — Recall against maintainer-merged fixes

An unusual ground truth is available: upstream fixes in this defect family that the
projects' own maintainers reviewed and merged. Of 70 merged pull requests authored by
the present author, **10** are failure-routing fixes. For each, the file was fetched at
the merge commit's **first parent** (i.e. immediately pre-fix) and scanned.

**Detected: 1 of 10.** Excluding one TypeScript change (out of language scope) and one
non-handler implicit `None` (outside the six shapes by design): **1 of 8**.

The nine misses are informative, and they all say the same thing: **the conversion
frequently happens outside the `except` block.**

| Missed case | Where the conversion actually happens |
|---|---|
| uqlm #462, #459 | retry exhaustion → `NaN` enters the aggregate downstream |
| inspect_ai #4906 | `tenacity.RetryError` masks the underlying cause |
| inspect_ai #5068 | state mutation *after* the handler (`exists = True`) |
| inspect_evals #2167 | an ordinary `if` branch writes `Score(0.0)` on a broken invariant |
| PyRIT #2466 | silent list filtering, no exception involved |
| uqlm #425 | pre-fix code crashed; the fix *added* the graceful path |

This is the paper's second negative result, and it bounds the whole approach:
**handler-shaped detection — ours included — cannot cover a defect family whose
defining event is semantic rather than syntactic.**

*Side observation:* in the pre-fix `inspect_ai #5068` file the detector flagged a
**different, unfixed** `silent-fallback` at line 356. Real code contains same-family
defects that no one has reported.

### 4.4 RQ4 — Labelling as a detector-improvement method

All four FALSE_POSITIVEs in the sample were `implicit-fallback`, and all four had the
**same root cause**: `_has_top_level_terminal()` inspected only *direct* statements of
the handler body, so a `return`/`raise` nested inside an exhaustive `if/else` was
invisible. Four real shapes triggered it:

| Package | Function | Shape |
|---|---|---|
| deepteam | `simulate_baseline_attacks` | `if ignore_errors: return [...] else: raise` |
| fickling | `check_pickle` | nested `try/except`, every path returns |
| inspect_ai | grok `generate` | `if/elif/else`, every branch returns or raises |
| pydantic_ai | `execute_output_function` | `if wrap: raise ToolRetryError else: raise` |

We implemented a recursive exhaustiveness analysis (`_always_terminates`) covering
`if/else`, `with`, `try/except/finally` and `match`, added six regression tests derived
from the four real shapes (each failing before the fix), and re-ran the corpus.

**`implicit-fallback` findings on 563k lines: 10 → 0.** Total findings: 659 → 649.
Test count: 124 → 130. No other rule changed.

Two things follow. First, the rule's entire real-world yield was false. Second — and
this is the transferable point — **a stratified labelling pass is not only an
evaluation instrument; it is the most efficient defect-finding method we applied to
our own detector.** The unit corpus (68 samples, precision = recall = 1.0) never
exposed this bug, because the corpus was written by the same person, with the same
blind spot, as the detector.

---

## 5. Discussion

**A detector this imprecise is still useful, but not as an oracle.**
On our corpus a maintainer following up every finding would read 649 handlers to reach
~97 genuine defects (extrapolating 15% — see the caveat below), of which the vast
majority are three copy-paste families in a single package. As an *alarm*, that is
unusable. As a *search-space reducer* over 563k lines, it is a different proposition:
it narrowed the space by roughly 3.5 orders of magnitude, and a human reading 80
handlers found a systematic fail-open security verdict in a red-teaming tool.

**Yield tracks codebase maturity, not rule design.** The strongest predictor of whether
a finding is a defect was not which rule fired but *which package it fired in*.
The mature, heavily-reviewed packages had essentially no defects and a large number of
carefully-commented intentional contracts; the one package with a systematic problem
had it replicated across dozens of near-identical files. This suggests triage effort
should be allocated per-package after a cheap pilot sample, not uniformly.

**The `contextlib.suppress` blind spot is real and growing.** 27/27 invisible to every
shipped linter, and a popular lint rule actively drives code toward that shape.
This is the one place where the tool's coverage claim is unambiguous.

**On "tool proposes, human adjudicates".** We report a case where we ran the detector
over a well-maintained red-teaming framework, sampled twelve semantic findings, traced
each, concluded all twelve were deliberate contracts, and **filed nothing**. Given the
15% base rate measured here, that outcome is what the numbers predict, not an anomaly.

---

## 6. Threats to validity

- 🔴 **Single annotator, who is also the tool's author.** No inter-rater agreement
  statistic is reported because there was only one rater. This is the most serious
  threat in the paper and we do not paper over it. `[TODO: recruit a second annotator
  for ≥30 items and report Cohen's κ, or state the limitation in the abstract.]`
- 🔴 **Sample size.** n = 80 of 649. Per-rule and per-package cells are small
  (`masked-exception` n = 1). Confidence intervals are wide and we do not report
  point estimates as if they were precise. `[TODO: compute Wilson intervals.]`
- **Package selection is not random.** The eight packages were chosen because the
  author had prior contribution history in them. `deepteam` in particular is a package
  where the author had *already found* a defect family, which inflates the overall
  defect rate. The seven-package 0/66 figure is the more conservative read.
- **Recall ground truth is authored by the same person.** The 10 merged fixes were
  written and submitted by the author; maintainer merge is independent validation of
  *the defect*, not of its representativeness.
- **Co-location ≠ equivalent detection** (§4.1 caveat). Reported conservatively.
- **`semgrep` was not run** — two installation attempts failed. Its absence may
  understate baseline coverage.
- **Version pinning is a snapshot.** All findings are relative to the pinned versions
  in `paper/corpus-lock.json`; upstream may have fixed or introduced instances since.

---

## 7. Related work

`[TODO — must be done without fabricating a single citation. Four lines to cover:
(1) empirical studies of exception-handling anti-patterns; (2) false positives and
actionability in static analysis; (3) silent failure and data cascades in ML systems;
(4) linter adoption and precision/recall trade-offs. Every entry needs a verifiable
DOI or arXiv ID. See 06-开源与项目/failroute-arXiv-工作计划.md §4 C1.]`

---

## 8. Conclusion

Failure-routing is a real and prevalent shape in AI/ML Python: 649 instances in
563k lines, 61% of them outside the reach of four mainstream syntactic linters and
100% of the `contextlib.suppress` variant outside the reach of all of them. But
prevalence is not defectiveness. In a labelled stratified sample, 15% were genuine
defects and 80% were deliberate contracts, with the defects concentrated entirely in a
single package as three copy-paste families. Against maintainer-merged ground truth
the detector's recall was 1 in 10, because the failure-to-success conversion routinely
happens outside the handler that a syntactic tool can see.

We think the useful conclusion is not "this class is undetectable" but that detectors
for it should be designed, evaluated and *deployed* as search-space reducers with an
explicit human adjudication step — and that the labelling pass which establishes that
should be run early, because in our case it was also the fastest way to find a bug in
the detector itself.

---

## Reproduction

```bash
cd 新项目-failroute
.venv/bin/python tools/fetch_corpus.py            # pinned sdists → paper/corpus/
PYTHONPATH=src .venv/bin/python -m failroute --export-findings paper/scan/<pkg>.jsonl \
    --repo-name <pkg> paper/corpus/<pkg>/<scan_root>
.venv/bin/python tools/compare_linters_corpus.py  # → bench/corpus-linter-comparison.json
.venv/bin/python tools/coverage_union.py          # → bench/corpus-coverage-union.json
.venv/bin/python tools/draw_sample.py --n 80 --seed 20260831   # → paper/sample.jsonl
.venv/bin/python tools/merged_pr_recall.py        # → paper/merged-pr-recall.csv
.venv/bin/python -m pytest -q                     # 130 tests
```

Artifacts: `paper/corpus-lock.json` (inputs) · `paper/sample.jsonl` (sample) ·
`paper/annotations.csv` (labels + rationale) · `paper/merged-pr-recall.csv` (recall) ·
`bench/corpus-coverage-union.json` (coverage).

---

## Remaining work before submission

| # | Item | Blocking? |
|---|---|---|
| 1 | Related work with verifiable DOIs / arXiv IDs | **yes** |
| 2 | Second annotator + Cohen's κ (or explicit single-annotator statement in abstract) | **yes** |
| 3 | Wilson confidence intervals on all proportions | yes |
| 4 | Figures: per-package defect rate; coverage Venn; recall table | no |
| 5 | LaTeX conversion (arXiv template) | no |
| 6 | `semgrep` baseline retry | no |

🔴 **Materials discipline:** until this is on arXiv it is *a draft*, not *a preprint*.
Application materials may say **"a preprint describing the tool and the study"** only
after an arXiv ID exists — never "published", "peer-reviewed", or "accepted".

# How Often Is a Swallowed Failure a Bug? A Tri-Source Study of Except-Handler Failure-Routing in AI/ML Codebases

**Draft v0.2 — 2026-09-01 (J batch).** All numbers are the v0.8.0 frozen values
(工作计划 §1 重冻结表) and are traceable through the mapping table at the end of
this file (`claims/*.json` in `新项目-contractlens`). The v0.7.0-era draft is
preserved unchanged as `paper/DRAFT-v0.7.0-frozen.md`.

> 🔴 **Author note (not for the paper):** the honesty discipline is unchanged —
> no fabricated citations, no fabricated numbers, no claimed measurements that
> were not actually run. **Scope notice (new):** this paper studies the
> *except-handler* subfamily of failure-routing, because that is what the
> detector operationalises; our own recall audit (§4.4) shows the phenomenon
> extends beyond this subfamily, and we say so in the title, the abstract, and
> the conclusion rather than implying full-family coverage.

---

## Abstract

Exception handlers that convert a failure into a success-shaped value — an LLM
judge outage becoming a legitimate `0.0` score, a decode error becoming an
empty string — produce wrong answers with no crash and no log line. We call
this pattern **failure-routing**. This paper studies its **except-handler
subfamily**: the shapes a syntactic tool can see.

We build a six-rule AST detector for this subfamily and apply it to eight
pinned AI/ML packages (2,354 files, 563,270 lines). It reports **621 findings**,
of which **371 (59.7%)** are not co-located with any finding from the union of
four syntactic linters (union coverage 250/621 = 40.3%); for the
`contextlib.suppress` shape the four shipped linters cover **0 of 19**.

We then do what tool papers usually skip: we label a stratified random sample
of the findings (n = 80). 🔴 **Both labelling rounds were performed by LLM
agents, not humans**, and agreed on all 80 items — which we report as a shared
bias, not as quality. Only **12 (15%)** are genuine defects; **64 (80%)** are
deliberate design contracts; **4 (5%)** were false positives from a detector
bug that the labelling itself exposed. **All 12 defects occur in one package.**

The paper's central question is methodological: **how do you validate a defect
detector for defects whose defining property is that nobody notices them?**
Standard validation — "maintainers fixed it, so it was real; nobody fixed it,
so it is not" — fails structurally for this family. We triangulate three
orthogonal truth sources: maintainer **consequence labelling** (15% defect,
LLM-judged), maintainer **spontaneous behaviour** (13/478 = 2.7% of family
sites ever fixed), and maintainer **reaction when told** (16/43 = 37.2% of our
family fix PRs accepted). The intervals are disjoint, which **supports** —
does not prove — the "nobody noticed" reading over the "false positive"
reading.

Finally, a recall audit against 14 in-scope ground-truth defects finds
**3 of 14** detected, and shows that **9 of 14 (64.3%)** route the failure
outside any handler — the named phenomenon is larger than the operationalised
subfamily. We scope our claims accordingly and argue detectors of this kind
are **search-space reducers**, not oracles.

---

## 1. Introduction

*(Opening: the SIM105 observation. Draft prose to be written by the author; the
factual skeleton is below.)*

- `ruff`'s `SIM105` rule recommends rewriting `try/except/pass` into
  `contextlib.suppress(...)`. The two forms are semantically identical.
- After the rewrite, **no shipped Python linter reports the construct.** In our
  corpus, all 19 `contextlib.suppress` findings are invisible to the union of
  ruff, bandit, pylint and flake8+bugbear (§4.1). (A semgrep rule **we wrote**
  covers 18/19; citing it requires stating the rule is ours.)
- A widely adopted refactoring therefore moves an entire defect shape out of
  the tools' field of view while leaving its runtime consequences unchanged.

**Contributions.**
1. A taxonomy of six failure-routing shapes and an AST detector for them (§3),
   with the construct-validity caveat that the operationalisation covers the
   except-handler subfamily only.
2. A reproducible prevalence and cross-tool coverage measurement over 8 pinned
   packages (§4.1).
3. A labelled stratified sample (n = 80) giving a precision estimate for this
   detector family on real code (§4.2) — a negative result, and one whose
   labelling was done by LLM agents, which we disclose and analyse.
4. **A tri-source triangulation method for defect families where standard
   validation fails structurally** (§4.3): consequence labelling, spontaneous
   maintainer behaviour, and maintainer reaction when told.
5. **A recall audit against maintainer-merged fixes** (§4.4) that doubles as a
   construct-validity measurement: 64.3% of ground-truth defects do not route
   through an except-handler at all.

---

## 2. The pattern family

Six shapes, all reducible to *"a failure became a value the caller cannot
distinguish from success"*:

| Rule | Shape | Consequence |
|---|---|---|
| `no-action` | `except ...: pass` | caller never learns the operation failed |
| `silent-fallback` | handler returns/assigns a constant without re-raising | judge outage becomes a legitimate `0.0` |
| `masked-exception` | catch-all conditionally re-raises *and* falls back to a constant | outcome depends on which branch ran |
| `silent-suppress` | `with contextlib.suppress(...)` | same semantics as `except+discard`; invisible to all shipped linters |
| `implicit-fallback` | handler neither re-raises, returns, nor records — falls through to implicit `None` | "did nothing" becomes a legitimate `None` |
| `name-shadowing` | `except E as e:` rebinds `e` inside the handler | Python deletes the binding on exit → `NameError`; original exception lost |

🔴 **Scope.** All six shapes are *handler* shapes. Failure-routing also occurs
without any handler (NaN propagation into aggregates, silent list filtering,
branch-level fallbacks); §4.4 measures how much of the phenomenon this
restriction costs.

---

## 3. Detector

*(Short — the tool is the instrument, not the subject.)*

AST-based; six rules behind a shared registry; text/JSON/SARIF output;
`# failroute: ignore` opt-out; `[tool.failroute]` per-rule configuration.
Version **0.8.0**. Quality gates: **158 tests** across 3 OS × 5 Python
versions, `mypy --strict`, and a hand-labelled unit corpus (v6, 68 samples:
36 positive / 32 negative) whose labels were written independently of tool
output, held to precision = recall = 1.0 in CI.

🔴 **Construct-validity caveat, stated up front:** that 1.0 is evidence the
detector matches its own specification, **not** evidence it finds real
defects. §4.2 is the external-validity measurement, and §4.4 bounds how much
of the phenomenon the handler-shaped operationalisation can reach at all.

---

## 4. Study

### 4.0 Corpus

Eight AI/ML packages fetched as **pinned PyPI source distributions** (not git
clones), each recorded with URL, SHA-256, upload time and extracted tree hash
in `paper/corpus-lock.json`:

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

*Rationale:* pinned sdists make the artifact reproducible by anyone with
network access and no git history; a reviewer re-running
`tools/fetch_corpus.py` gets byte-identical inputs.

### 4.1 RQ1 — Prevalence and cross-tool coverage

`failroute` (v0.8.0) reports **621 findings**. Baselines were run on the
*same* pinned trees:

| Tool | Version | Rules | Findings | Co-located with a failroute finding (±1 line) |
|---|---|---|---|---|
| **failroute** | 0.8.0 | all six | **621** | — |
| ruff | 0.16.0 | S110, S112 | 76 | 72 |
| bandit | 1.9.4 | B110, B112 | 67 | 63 |
| pylint | 4.0.8 | W0702/3/5/6 | 529 | 248 |
| flake8+bugbear | 7.3.0 / 25.11.29 | E722, B001, B017 | 268 | 124 |
| semgrep | 1.175.0 | **rules we wrote** | — | see below |

**Union of the four syntactic linters covers 250 of 621 (40.3%,
Wilson95 [36.5%, 44.2%]). `failroute`-only: 371 (59.7%).** Adding our
self-written semgrep rule as a fifth tool raises union coverage to 269/621 =
43.3% [39.5%, 47.2%]; the rule is ours, and it mostly adds the
`contextlib.suppress` shape (18/19 of it).

Per rule (covered-by-4 = the four shipped linters; covered-by-5 adds our
semgrep rule):

| Rule | Total | Covered by 4 | Covered by 5 | failroute-only (vs 4) |
|---|---|---|---|---|
| `silent-fallback` | 386 | 175 | 176 | 211 |
| `no-action` | 213 | 72 | 72 | 141 |
| **`silent-suppress`** | **19** | **0 (0.0%)** | **18 (94.7%)** | **19** |
| `masked-exception` | 3 | 3 (100.0%) | 3 | 0 |
| `implicit-fallback` | 0 | — | — | — |
| `name-shadowing` | 0 | — | — | — |

`implicit-fallback` and `name-shadowing` fire zero times on this corpus; they
remain in the tool because the unit corpus exercises them.
🔴 On `silent-suppress`: none of the four shipped linters reports any of the
19 findings (0/19); only a rule we wrote for semgrep reaches them (18/19).

**Two honest observations that cut against the tool:**

1. **`pylint` is a far stronger baseline than `ruff`.** Comparing only against
   `ruff`'s `S110`/`S112` — as our own earlier benchmark did — overstates
   novelty by roughly 3.4× (72 vs 248 co-located findings). Any paper in this
   space that benchmarks against `ruff` alone should be read with that in
   mind.
2. **`masked-exception` is fully covered.** All 3 findings co-locate with a
   pylint broad-except warning. That rule contributes no coverage novelty
   here.

⚠️ **Methodological caveat on "coverage".** Co-location at ±1 line means a
syntactic tool *flags the same handler*, **not** that it expresses the same
property. `pylint W0703` fires on `except Exception:` regardless of what the
handler does; it does not distinguish "re-raises" from "returns `0.0`". 40.3%
is therefore an **upper bound** on what the syntactic tools actually say, and
the semantic novelty is correspondingly higher than 59.7%. We report the
conservative number.

### 4.2 RQ2 — What fraction are real defects? *(precision result)*

**Method.** Stratified random sample over (rule × package), fixed seed
(20260831), every stratum guaranteed ≥1 draw, remainder allocated
proportionally. n = 80. Each finding was labelled by reading the surrounding
source in the pinned tree, into one of three classes: **DEFECT** (the
converted failure produces a wrong caller-visible outcome with no signal),
**CONTRACT** (deliberate, and either documented, commented, or expressed in
the return type), **FALSE_POSITIVE** (the detector is wrong about the code).

🔴 **Labelling was performed by LLM agents.** Two independent rounds were
run, both by LLM agents (not human raters), and they agreed on 80/80 items.
We do not report this as label quality: identical agreement between two runs
of the same model family is evidence of **shared bias**, not of reliability.
The sample remains useful as (a) a debugging instrument (§4.5) and (b) the
consequence arm of the triangulation in §4.3, where its limits are part of
the design.

🔴 **Sampling frame.** The draw was taken from the **v0.7.0 finding set
(n = 659)**. Two subsequent corrections changed the frame: labelling itself
exposed the `implicit-fallback` bug whose 10 findings were all false
(659 → 649), and the v0.8.0 precision fixes removed 28 more (649 → 621,
§4.5). Of the 80 sampled coordinates, **72 survive** in the 621 set; the 4
deleted `implicit-fallback` items were all labelled FALSE_POSITIVE and the 4
audit-gate deletions were likewise — **zero labelled DEFECT was lost**. The
label proportions below therefore hold **within the v0.7.0 frame**, and the
resample is not random with respect to the 621 frame.

**Result (v0.7.0 frame, LLM-labelled).**

| Label | n | Share | Wilson95 |
|---|---|---|---|
| CONTRACT | 64 | **80.0%** | [70.0%, 87.3%] |
| DEFECT | 12 | **15.0%** | [8.8%, 24.4%] |
| FALSE_POSITIVE | 4 | 5.0% | [2.0%, 12.2%] |

Restricting to the 76 samples that survive as findings: 12/76 = 15.8%,
64/76 = 84.2%, false positives 0 — the labelling pass closed the loop on the
one detector bug it found.

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
sampled findings were defects (Wilson95 upper bound 5.5%).**

The 12 defects are not 12 independent bugs. They are **three homogeneous
families** replicated across metric classes:

1. **Silent criteria degradation (4/12).** `try: self.system_prompt =
   model.get_system_prompt() except: self.system_prompt = ""`. A custom or
   misconfigured LLM that lacks the method silently scores every subsequent
   case under empty criteria. *(This family was independently reported
   upstream by the present author before this study, as `deepteam#270`; that
   report is partial external validation of the label, not of the tool.)*
2. **Dead comparison (5/12).** `try: self.score == 1 except: self.success =
   False`. The guarded statement is a pure comparison expression that cannot
   raise, so the handler is dead code — and `self.success` is never assigned
   on the success path.
3. **Fail-open security verdict (3/12).** `is_vulnerable()` iterates results
   inside a `try`; on any error it returns `vulnerable = False`. In a
   red-teaming tool, *"not vulnerable"* is the most dangerous possible
   default: an infrastructure failure is converted into a clean security
   conclusion.

Conversely, the 64 contracts are overwhelmingly **deliberate and legible**:
TUI widget lookups that may not be mounted, optional-dependency probes,
idempotent cleanup in `finally`, and predicate functions whose
`Optional`/`bool` return type *is* the contract. Many carry an explicit
comment stating the intent (e.g. inspect_ai's `"fail open — better to skip
the barrier than to hang teardown"`).

Two findings in the sample are worth citing as **positive** examples of the
discipline this paper argues for: pydantic-ai's `is_private_ip` fails
**closed** on an unparseable address (`"Invalid IP address, treat as
potentially dangerous" → return True`), and its `_run_tool` explicitly routes
a caught exception onto a queue *so that the consumer re-raises it* rather
than letting it vanish.

⚠️ **Threats specific to this section** — see §6; the most serious are that
labelling was performed by two runs of LLM agents (shared bias) and that the
sample frame is the v0.7.0 finding set.

### 4.3 RQ3 — A tri-source triangulation *(method result)*

The precision result above invites the obvious rebuttal: *if 85% of findings
are not defects, the detector is noise*. The equally obvious defence — *the
defects are real, maintainers just have not noticed them* — is exactly what a
false-positive-heavy tool would say, and on spontaneous behaviour alone it is
unfalsifiable. We triangulate three truth sources that measure **orthogonal**
questions:

| Arm | Measures | Value | Wilson95 |
|---|---|---|---|
| **Arm 1 · consequence labelling** (§4.2) | "if triggered, how bad is it?" | 12/80 = 15.0% defect, all in one package | [8.8%, 24.4%] |
| **Arm 2 · maintainer spontaneous behaviour** | "did anyone notice without prompting?" | 13/478 = 2.7% of family sites ever fixed by maintainers | [1.6%, 4.6%] |
| **Arm 3 · maintainer reaction when told** | "when surfaced, do they accept?" | 16/43 = 37.2% of our family fix PRs merged | [24.4%, 52.1%] |

Arm 2 ground truth is a maintainer-behaviour dataset we built over the same
eight pinned packages: every family site classified as FIXED or SURVIVED by
reading the package's own history (478 sites, 13 FIXED). The 12 arm-1
defects in `deepteam` sit in sites whose history shows **no** maintainer
action.

Arm 3 ground truth is the merged/closed record of fix PRs in this family
authored by the present author: of 75 merged PRs across these ecosystems,
**16** are family fixes (every one adjudicated by reading the diff, not the
title), and of the closed-unmerged family PRs the maintainer-closed subset
contains **no** case where a maintainer disputed the defect's existence.
Excluding PRs the author closed himself, acceptance is 16/24 = 66.7%
[46.7%, 82.0%].

**Verdict.** Arm 3's interval lower bound (24.4%) is above arm 2's interval
upper bound (4.6%); the intervals are disjoint. The data **support** the
reading *"nobody noticed"* over the reading *"false positive"*: defects that
maintainers were never shown were essentially never fixed (2.7%), while the
self-selected subset that was shown to them was accepted about a third of the
time. 🔴 We write *support*, not *prove*: arm 3 suffers irreducible selection
bias (the author chose which defects to report), and the comparison is
between a prompted, self-selected sample and an unprompted population.

**The three limitations, stated with the result:**
1. **Arm 1 is LLM-judged** (two rounds, same model family, 80/80 agreement =
   shared bias, not quality).
2. **Arm 2's SURVIVED label is only readable as "nobody acted", never as
   "deliberate contract"** — for this family the two are indistinguishable,
   which is precisely why spontaneous behaviour cannot validate the detector.
3. **Arm 3's selection bias is irreducible**: acceptance applies only to the
   self-selected reports, not to the detector's findings at large.

### 4.4 Recall audit and construct validity *(recall result)*

An unusual ground truth is available: upstream fixes in this defect family
that the projects' own maintainers reviewed and merged. Of 75 merged pull
requests authored by the present author, **16** are failure-routing fixes —
every exclusion adjudicated by reading the PR diff (52 earlier
title-only judgements were re-checked against diffs in a dedicated pass; 49
stood, 3 flipped). For each family fix, the file was fetched at the merge
commit's **first parent** (i.e. immediately pre-fix) and scanned.

**Classification of the 16:**

| Class | n | Cases |
|---|---|---|
| Out of scope for recall | 2 | one TypeScript change (language scope); one pre-fix crash with no family shape |
| **Detected** | **3** | `uqlm#450`, `agent-sweep#197`, `trulens#2653` |
| Handler-shape gap (design-reachable) | 2 | `inspect_ai#5068` (post-handler state mutation), `#4906` (tenacity `RetryError` masking) — both adjudicated as candidate patterns, not shipped |
| **Non-handler routing** | **9** | NaN reaching aggregates, silent list filtering, branch-level `Score(0.0)`, implicit-`None` contract violations, silent character stripping, silent symbol dropping, laundered verdicts |

**Recall on the corrected denominator: 3 of 14 = 21.4% (Wilson95
[7.6%, 47.6%]).** The ceiling for *any* handler-shaped detector on this
ground truth is 5 of 14 = 35.7%, because **9 of 14 = 64.3% [38.8%, 83.7%] of
the defects route the failure outside any except-handler**.

This is the paper's construct-validity result, and it bounds the whole
approach: the phenomenon named in the title is larger than the subfamily the
tool (and every handler-shaped detector) operationalises. We state this as a
boundary **and** a roadmap — dataflow-shaped failure-routing is future work —
and we scope all claims in this paper to the except-handler subfamily
accordingly.

*Side observation:* in the pre-fix `inspect_ai #5068` file the detector
flagged a **different, unfixed** `silent-fallback` at line 356. Real code
contains same-family defects that no one has reported.

### 4.5 RQ4 — Labelling as a detector-improvement method

All four FALSE_POSITIVEs in the sample were `implicit-fallback`, and all four
had the **same root cause**: `_has_top_level_terminal()` inspected only
*direct* statements of the handler body, so a `return`/`raise` nested inside
an exhaustive `if/else` was invisible. Four real shapes triggered it
(deepteam, fickling, inspect_ai, pydantic-ai).

We implemented a recursive exhaustiveness analysis (`_always_terminates`)
covering `if/else`, `with`, `try/except/finally` and `match`, added six
regression tests derived from the four real shapes (each failing before the
fix), and re-ran the corpus. **`implicit-fallback` findings on 563k lines:
10 → 0.** Total findings: **659 → 649** (v0.7.0). The v0.8.0 precision
release removed 28 more findings through four audited fixes (tuple-typed
handlers, `warnings.warn` recognised as a signal, `StopAsyncIteration` added
to the ignore list, conservative optional-dependency probe): **649 → 621**,
with every deletion traceable to a labelled category or a mechanical criterion
— **no labelled DEFECT was removed**. Test count: 124 → 130 → **158**.

Two things follow. First, the rule's entire real-world yield was false.
Second — and this is the transferable point — **a stratified labelling pass is
not only an evaluation instrument; it is the most efficient defect-finding
method we applied to our own detector.** The unit corpus (68 samples,
precision = recall = 1.0) never exposed this bug, because the corpus was
written by the same person, with the same blind spot, as the detector.

---

## 5. Discussion

**A detector this imprecise is still useful, but not as an oracle.**
On our corpus a maintainer following up every finding would read 621 handlers
to reach ~93 genuine defects (extrapolating the 15% LLM-labelled defect share —
see §6), of which the vast majority are three copy-paste families in a single
package. As an *alarm*, that is unusable. As a *search-space reducer* over
563k lines, it is a different proposition: it narrowed the space by roughly
3.4 orders of magnitude, and a reading of 80 sampled handlers found a
systematic fail-open security verdict in a red-teaming tool.

**The triangulation reframes the negative precision result.** 15% defects is
bad for an alarm and unremarkable for a search tool; the interesting fact is
that the family's defining property — silence — also disables the usual
external check on the number. Spontaneous repair was 2.7%; when the same
defects were surfaced deliberately, acceptance was 37.2%. The difference is
what "nobody noticed" looks like when measured rather than asserted. 🔴 The
evidence supports that reading; with a self-selected arm 3 it cannot prove it.

**Yield tracks codebase maturity, not rule design.** The strongest predictor
of whether a finding is a defect was not which rule fired but *which package
it fired in*. The mature, heavily-reviewed packages had essentially no
defects and a large number of carefully-commented intentional contracts; the
one package with a systematic problem had it replicated across dozens of
near-identical files. Triage effort should be allocated per-package after a
cheap pilot sample, not uniformly.

**The `contextlib.suppress` blind spot is real.** 0/19 of the findings are
visible to any shipped linter; a popular lint rule actively drives code
toward that shape. Only a semgrep rule we wrote reaches them (18/19).

**Adoption, honestly.** The tool is published on PyPI; at the measurement
moment it has **1 star and 0 forks**. We claim no adoption and no impact
beyond the measurements in this paper; the maintainer-behaviour dataset and
the triangulation method are the contributions we ask the reader to weigh.

**On "tool proposes, human adjudicates".** We report a case where we ran the
detector over a well-maintained red-teaming framework, sampled twelve
semantic findings, traced each, concluded all twelve were deliberate
contracts, and **filed nothing**. Given the 15% base rate measured here, that
outcome is what the numbers predict, not an anomaly.

---

## 6. Threats to validity

- 🔴 **Limitation 1 — the labelling arm is LLM-judged.** Both labelling
  rounds were performed by LLM agents, not human raters; the rounds agreed on
  80/80 items, which we read as **shared bias of one model family, not as
  inter-rater reliability**. No Cohen's κ is possible between two runs of the
  same rater species. All arm-1 proportions inherit this limit.
- 🔴 **Limitation 2 — SURVIVED is ambiguous in this family.** In the
  maintainer-behaviour dataset, SURVIVED can only be read as **"nobody
  acted"**; it can **not** be read as "maintainers consider it a deliberate
  contract", because for silent defects the two are observationally
  identical. Any number derived from arm 2 inherits this reading restriction.
- 🔴 **Limitation 3 — arm-3 selection bias is irreducible.** The author chose
  which defects to report as PRs; acceptance (16/43) applies only to that
  self-selected set and cannot be extrapolated to the detector's findings.
  Reporting only merged PRs would have made this worse; the closed-unmerged
  family PRs are counted in the denominator, and none of the
  maintainer-closed ones disputed the defect's existence.
- **Sample size.** n = 80 of the v0.7.0 frame (659). Per-rule and per-package
  cells are small (`masked-exception` n = 1). Wilson intervals are reported
  throughout instead of bare point estimates.
- **Sample frame changed under the sample.** The draw came from v0.7.0's 659;
  72/80 coordinates survive in v0.8.0's 621, and the deletions removed zero
  labelled DEFECTs — but the surviving 72 are no longer a random sample of
  the current frame. Label proportions are stated for the v0.7.0 frame only.
- **Package selection is not random.** The eight packages were chosen because
  the author had prior contribution history in them. `deepteam` in particular
  is a package where the author had *already found* a defect family, which
  inflates the overall defect rate. The seven-package 0/66 figure is the more
  conservative read.
- **Recall ground truth is authored by the same person.** The 16 merged
  family fixes were written and submitted by the author; maintainer merge is
  independent validation of *the defect*, not of its representativeness. The
  family adjudication of all 75 merged PRs was done by reading diffs (52
  earlier title-only judgements were re-verified from diffs in a dedicated
  pass, with 3 corrections).
- **Co-location ≠ equivalent detection** (§4.1 caveat). Reported
  conservatively as an upper bound on baseline coverage.
- **The fifth baseline tool is ours.** The semgrep rule counted in the
  five-tool union was written by the authors; coverage attributed to it is
  self-supplied.
- **Construct validity (§4.4).** The detector operationalises the
  except-handler subfamily only; 64.3% of ground-truth defects lie outside
  it. All prevalence/recall claims are scoped to the subfamily.
- **Version pinning is a snapshot.** All findings are relative to the pinned
  versions in `paper/corpus-lock.json`; upstream may have fixed or introduced
  instances since.

---

## 7. Related work

`[TODO — must be done without fabricating a single citation. Four lines to
cover: (1) empirical studies of exception-handling anti-patterns; (2) false
positives and actionability in static analysis; (3) silent failure and data
cascades in ML systems; (4) linter adoption and precision/recall trade-offs.
Every entry needs a verifiable DOI or arXiv ID. See
06-开源与项目/failroute-arXiv-工作计划.md §4 C1.]`

---

## 8. Conclusion

Except-handler failure-routing is a real and prevalent shape in AI/ML Python:
621 instances in 563k lines, 59.7% of them outside the reach of four
mainstream syntactic linters and 100% of the `contextlib.suppress` variant
outside the reach of all shipped linters. But prevalence is not
defectiveness: in an LLM-labelled stratified sample, 15% were genuine defects
and 80% were deliberate contracts, with the defects concentrated entirely in a
single package.

The methodological contribution is the triangulation: for a defect family
whose defining property is silence, "did maintainers fix it?" is a broken
validation instrument — spontaneous repair was 2.7% — while the same defects,
when surfaced, were accepted 37.2% of the time. The disjoint intervals
support (not prove) the "nobody noticed" reading. And the recall audit
supplies the honest boundary: 3 of 14 ground-truth defects detected, and
64.3% of them route the failure outside any handler — the phenomenon is
larger than the subfamily we, and every handler-shaped detector, can see.

Detectors for this family should be designed, evaluated and *deployed* as
search-space reducers with an explicit human adjudication step — and the
labelling pass that establishes that should be run early, because in our case
it was also the fastest way to find a bug in the detector itself.

---

## Number → source mapping (frozen-table row / claim id)

| Number in this draft | Home |
|---|---|
| 621 findings; per-rule 386/213/19/3; 0.8.0; 158 tests; corpus 2,354/563,270 | 冻结表「扫描发现/逐规则/版本/测试/语料」行 · `I1.*`, `I2.version_five_spots` |
| Union 250/621 = 40.3% [36.5, 44.2]; only 371 = 59.7% | 冻结表「四工具并集」行 · `F3.union_new_4tool` |
| Five-tool 269/621 = 43.3% (self-written semgrep rule) | 冻结表「五工具并集」行 · `F3.union_new_5tool` |
| n=80 labels 64/12/4; LLM-labelled; 659 frame; 72/80 survive | 冻结表「标注 n=80 / 标注结果」行 · `H3.table_arm1`, `H4.*` |
| Arm 2 = 13/478 = 2.7% [1.6, 4.6] | 冻结表「臂 2」行 · `H1.arm2_spontaneous` |
| Arm 3 = 16/43 = 37.2% [24.4, 52.1]; excl-self 16/24 = 66.7% | `J1.recall_superseded`（J1 更新；原 `H1.arm3_acceptance_primary` 13/40 被取代）|
| Verdict: intervals disjoint → supports "nobody noticed" | 冻结表「三角验证判决」行 · `H3.verdict` |
| Recall 3/14 = 21.4% [7.6, 47.6]; handler ceiling 5/14; non-handler 9/14 = 64.3% | `J1.recall_superseded`（J1 更新；原 `H1.recall_audit` 2/11 被取代）|
| Ground truth 16 family fixes / 75 merged PRs, all diff-read | `J1.ledger_recompute`, `J1.zero_title_screened`, `J1.three_flips` |
| Truth coverage of findings by maintainer data 171/621 = 27.5% | `H2.*` (not cited in body; available for reviewers) |
| Adoption: 1 star / 0 fork | 冻结表「采用度」行 — never written as adoption |

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
.venv/bin/python tools/j1_adjudicate.py           # J1 diff-read adjudication (idempotent)
.venv/bin/python -m pytest                        # 158 tests
cd ../新项目-contractlens
python3 tools/h1_stats.py j1                      # recall 3/14, acceptance 16/43 recomputed
python3 tools/verify_claims.py --slow             # every claim recomputes from raw data
```

Artifacts: `paper/corpus-lock.json` (inputs) · `paper/sample.jsonl` (sample) ·
`paper/annotations.csv` (labels + rationale) · `paper/merged-pr-recall.csv`
(recall ledger, all rows diff-read) · `paper/j1-trulens2653-prefix.py`
(pre-fix evidence for the trulens#2653 detection) ·
`bench/corpus-coverage-union-5tool.json` (coverage).

---

## Remaining work before submission

| # | Item | Blocking? |
|---|---|---|
| 1 | Related work with verifiable DOIs / arXiv IDs | **yes** |
| 2 | Author block and affiliations (personal info — applicant only) | **yes** |
| 3 | Figures regenerated for the J1 recall values (fig3 cell 2/11 → 3/14) | no |
| 4 | Merge `fix/v0.8-precision` and publish 0.8.0 before submission (artifact honesty) | **yes** |

🔴 **Materials discipline:** until this is on arXiv it is *a draft*, not *a
preprint*. Application materials may say **"a preprint describing the tool
and the study"** only after an arXiv ID exists — never "published",
"peer-reviewed", or "accepted".

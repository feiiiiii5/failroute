# How Often Is a Swallowed Failure a Bug? A Tri-Source Study of Except-Handler Failure-Routing in AI/ML Codebases

**Draft v0.3 — N batch (overnight 09-02→09-03).** All numbers are the v0.8.0 frozen values
(工作计划 §1 重冻结表) and are traceable through the mapping table at the end of
this file (`claims/*.json` in `新项目-contractlens`). The v0.7.0-era draft is
preserved unchanged as `paper/DRAFT-v0.7.0-frozen.md`. **N-batch change: the
§4.3 triangulation verdict is downgraded from 「区间不重叠 → supports 'nobody
noticed'」 to 「directionally consistent, not established」 — the comparison
depends on an unmeasured defect composition (sensitivity table in §4.3), and
no commensurable matched population exists.**

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
truth sources that ask orthogonal questions: **consequence labelling** by LLM
(15% defect), maintainer **spontaneous behaviour** (13/478 = 2.7% of tracked
family sites ever fixed), and maintainer **reaction when told** (16/43 = 37.2%
of the author's family fix PRs accepted). The three are directionally
consistent with the "nobody noticed" reading, but the comparison does not
prove it and cannot support a verdict: the arms count incommensurable
populations, the interval disjointness flips within the unmeasured defect
composition of the tracked sites (§4.3), and no matched-population substitute
exists. We report this as a quantified impossibility result and name the
datum that would close it.

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
4. **A tri-source triangulation for defect families where standard validation
   fails structurally — and a quantified impossibility result** (§4.3): its
   arms count incommensurable populations, the headline interval comparison
   flips within an unmeasured composition, and no matched-population
   substitute exists; we specify the datum that would settle the question.
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
| **Total (scanned)** | | | **2,124** | **524,229** |

The eight pinned sdists contain **2,354** .py files / **563,270** lines in
total; the per-package counts above are within each scan root (the subtree
actually scanned).

*Rationale:* pinned sdists make the artifact reproducible by anyone with
network access and no git history; a reviewer re-running
`tools/fetch_corpus.py` gets byte-identical inputs (version + SHA-256 pinned
in `paper/corpus-manifest.json`, verified against `corpus-lock.json`).

### 4.1 RQ1 — Prevalence and cross-tool coverage

`failroute` (v0.8.0) reports **621 findings**. Baselines were run on the
*same* pinned trees:

| Tool | Version | Rules | Findings | Co-located with a failroute finding (±1 line) |
|---|---|---|---|---|
| **failroute** | 0.8.0 | all six | **621** | — |
| ruff | 0.16.0 | S110, S112 | 76 | 72 |
| bandit | 1.9.4 | B110, B112 | 67 | 63 |
| pylint | 4.0.8 | W0702/3/5/6 | 529 | 245 |
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
   novelty by roughly 3.4× (72 vs 245 co-located findings). Any paper in this
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
precision-fix deletions were all labelled **CONTRACT** — **zero labelled DEFECT
was lost**. The
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
unfalsifiable. We triangulate three truth sources that ask **orthogonal
questions** — of, as it turns out, **non-commensurable populations**, which is
what bounds the conclusion below:

| Arm | Measures | Value | Wilson95 |
|---|---|---|---|
| **Arm 1 · consequence labelling** (§4.2) | "if triggered, how bad is it?" | 12/80 = 15.0% defect, all in one package | [8.8%, 24.4%] |
| **Arm 2 · maintainer spontaneous behaviour** | "did anyone notice without prompting?" | 13/478 = 2.7% of family sites ever fixed by maintainers | [1.6%, 4.6%] |
| **Arm 3 · maintainer reaction when told** | "when surfaced, do they accept?" | 16/43 = 37.2% of our family fix PRs merged | [24.4%, 52.1%] |

Arm 2 ground truth is a maintainer-behaviour dataset we built over the same
eight pinned packages: every family site classified as FIXED or SURVIVED by
reading the package's own history (478 sites, 13 FIXED; none of the 13 FIXED
attributions coincides with an author PR — spontaneous in the strict sense).
The 12 arm-1 defects in `deepteam` sit in sites whose history shows **no**
maintainer action.

Arm 3 ground truth is the merged/closed record of fix PRs in this family
authored by the present author: of 75 merged PRs across these ecosystems,
**16** are family fixes (every one adjudicated by reading the diff, not the
title; itemised in `paper/merged-pr-recall.csv`), **8 of the 16 are in
packages outside the tracked eight**, and the **27 closed-unmerged** family
PRs are counted in the denominator but are **not itemised in any committed
artifact** — a provenance gap we flag in §6. Of those, the maintainer-closed
subset (n=8) contains **no** case where a maintainer disputed the defect's
existence. Excluding PRs the author closed himself, acceptance is 16/24 =
66.7% [46.7%, 82.0%].

**Verdict: directionally consistent, not established.** The natural headline
reading is arithmetic: arm 3's interval lower bound (24.4%) lies above arm 2's
upper bound (4.6%), the intervals are disjoint, and disjointness is read as
supporting *"nobody noticed"* over *"false positive"*. The arithmetic is right
and the reading is not: what the two denominators count is different, and
neither count is warranted.

🔴 **The arms are not commensurable.** Arm 2's denominator is all 478 tracked
family sites; arm 3's is 43 defect candidates pre-screened by the author, of
whose 16 merged members 8 lie in packages outside the tracked eight. A
site-level rate and a self-selected-candidate rate answer different questions
about different populations; no interval comparison between them can support a
population-level verdict.

🔴 **The disjointness depends on an unmeasured composition.** Whether the
intervals are disjoint depends on two quantities that were never measured:
**n**, the number of the 478 tracked sites that are genuine defects, and
**k ≤ 13**, the number of the 13 spontaneous fixes that landed on defect
sites:

| k | n | k/n | Wilson95 | Disjoint from arm 3? | Composition reading |
|---|---|---|---|---|---|
| 13 | 478 | 2.7% | [1.6, 4.6] | yes | all tracked sites as risk set |
| 13 | 144 | 9.0% | [5.4, 14.8] | yes | 30% defect share |
| 13 | 86 | 15.1% | [9.1, 24.2] | yes | **boundary** |
| 13 | 85 | 15.3% | [9.2, 24.4] | **no** | just below boundary |
| 13 | 72 | 18.1% | [10.9, 28.5] | **no** | **this paper's own 15% base rate** |
| 6 | 72 | 8.3% | [3.9, 17.0] | yes | half the fixes were defect fixes |
| 2 | 72 | 2.8% | [0.8, 9.6] | yes | fixes ∝ defect share (13×0.15) |

Taking all 478 sites as the risk set — which counts the ~85% of findings our
own labelling calls deliberate contracts as if they were opportunities to fix
a defect — yields disjointness. But under this paper's own 15% base rate
(n ≈ 72) with fixes concentrated on defects (k = 13) — arguably the natural
composition, since maintainers fix bugs rather than contracts — arm 2 becomes
13/72 = 18.1% [10.9, 28.5], which **overlaps** arm 3 on [24.4, 28.5].
Disjointness survives only if n ≥ 86, i.e. only if the defect share among
tracked sites is at least 18.0% — **strictly above this paper's own precision
estimate**. And the 15% is itself LLM-labelled (Limitation 1): if it cannot be
trusted, there is equally no independent warrant for the n=478 denominator.
**Neither corner is selectable on evidence**, and Limitation 2 says n cannot
be measured from spontaneous behaviour at all — that is precisely the family's
defining problem.

🔴 **No commensurable substitute exists.** The natural repair — compare only
sites that are both tracked and PR-reported — is empty: none of the 16 merged
family fixes maps to any of the 478 tracked sites (**zero exact file
matches**; the tracked population and the author-reported population are
near-disjoint, a consequence of the 3/16 recall and of the 8 out-of-corpus
fixes). The closest available approximation is package-level: in `uqlm`, 0 of
12 tracked family sites were spontaneously fixed through the tracked window
(0.0–23.4%) while 5 of 5 author-reported `uqlm` family fixes were merged
(56.6–100.0%). Same maintainer team — but different site sets,
author-selected, and n too small to exclude almost anything. We report it as
context, not as a test.

**What survives.** Three things, each weaker than a verdict. (i) Directly:
across the 24 maintainer-adjudicated outcomes in the author's PR record (16
merged, 8 maintainer-closed), no closure disputed the defect's existence —
evidence against the *strong* false-positive reading, but only for the
author-selected subset. (ii) Spontaneous repair of tracked family sites is
rare (2.7%) whatever their composition — but by Limitation 2 that rarity is
equally consistent with "mostly contracts". (iii) The datum that would settle
"nobody noticed" against "false positive" — maintainer reaction to a *random*
sample of findings — **does not exist and cannot be retro-constructed**. The
triangulation is directionally consistent with the "nobody noticed" reading;
it **does not prove** it. We state the question as open and record that datum
as a design requirement for future work.

**The four limitations, stated with the result:**
1. **Arm 1 is LLM-judged** (two rounds, same model family, 80/80 agreement =
   shared bias, not quality).
2. **Arm 2's SURVIVED label is only readable as "nobody acted", never as
   "deliberate contract"** — for this family the two are indistinguishable,
   which is precisely why spontaneous behaviour cannot validate the detector.
3. **Arm 3's selection bias is irreducible**: acceptance applies only to the
   self-selected reports, not to the detector's findings at large.
4. **The arms are not commensurable**: arm 2 counts tracked sites, arm 3
   counts author-selected defect candidates, and 8 of the 16 merged candidates
   lie outside the tracked packages. No interval comparison between them
   yields a population-level verdict (Verdict, above).

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
to reach ~93 genuine defects — a cross-frame extrapolation (the 15%
LLM-labelled share is measured on the v0.7.0 sample frame; the 621 count is
v0.8.0), not a measurement; see §6 — of which the vast majority are three
copy-paste families in a single package. As an *alarm*, that is unusable. As a
*search-space reducer* over 563k lines, it is a different proposition: it
narrowed the space by roughly three orders of magnitude (from 563k lines to 621
findings, a factor of 907), and a reading of 80 sampled handlers found
a systematic fail-open security verdict in a red-teaming tool.

**The triangulation reframes the negative precision result — as an
impossibility result.** 15% defects is
bad for an alarm and unremarkable for a search tool; the interesting fact is
that the family's defining property — silence — also disables the usual
external check on the number. Spontaneous repair of tracked family sites was
2.7%; when the author surfaced adjudicated defect candidates, acceptance was
37.2%. 🔴 These numbers measure different populations and cannot be combined
into a verdict (§4.3): rebased under this paper's own defect share, the
intervals overlap. What the triangulation establishes is narrower and, we
believe, more useful: for this family neither spontaneous behaviour nor
triangulation around it can validate a detector; the reason is quantifiable
(an unmeasured two-dimensional composition, §4.3 table); and the missing datum
is nameable — maintainer reaction to a random sample of findings.

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
  Reporting only merged PRs would have made this worse; the 27 closed-unmerged
  family PRs are counted in the denominator, and none of the eight
  maintainer-closed ones disputed the defect's existence. Two provenance
  caveats: the closed-unmerged members are **not itemised in any committed
  artifact** (the 16 merged ones are, in `paper/merged-pr-recall.csv`), and 8
  of the 16 lie in packages outside the tracked eight — arm 3's population is
  not arm 2's.
- 🔴 **Limitation 4 — the triangulation's arms are not commensurable.** Arm 2
  counts tracked sites; arm 3 counts author-selected defect candidates. The
  headline interval comparison depends on an unmeasured composition (§4.3) and
  supports no population-level verdict; we report directional consistency
  only.
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
  family fixes were written and submitted by the author; a maintainer merge
  records that the change was acceptable to the project — it is not a
  maintainer finding that the pre-fix behaviour was a defect, and it says
  nothing about representativeness. The
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

The methodological contribution is a quantified impossibility result. For a
defect family whose defining property is silence, "did maintainers fix it?" is
a broken validation instrument — spontaneous repair of tracked family sites
was 2.7% — and the natural workaround fails too: triangulating against
maintainer reaction when told (37.2% acceptance of author-reported candidates)
compares incommensurable populations, and the interval disjointness that
appears to support the "nobody noticed" reading flips to overlap under this
paper's own defect share, with no matched-population substitute and no
independent warrant for either denominator. What remains is honest but
narrower: directionally consistent observations, no maintainer-adjudicated
dispute of defect existence among 24 outcomes, and an open question whose
missing datum we name — maintainer reaction to a random sample of findings.
And the recall audit supplies the honest boundary: 3 of 14 ground-truth
defects detected, and 64.3% of them route the failure outside any handler —
the phenomenon is larger than the subfamily we, and every handler-shaped
detector, can see.

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
| Verdict (N batch): **directionally consistent, not established** — sensitivity over unmeasured (k, n); boundary n ≥ 86 ⇔ defect share ≥ 18.0%; rebase 13/72 = 18.1% [10.9, 28.5] overlaps arm 3; matched population empty (0 exact site matches, 16 PRs × 478 sites); uqlm 0/12 [0.0, 23.4] vs 5/5 [56.6, 100.0]; arm-2 numerator uncontaminated (13 FIXED attributions ∩ 16 author PRs = ∅); 27 closed-unmerged not itemised; 8/16 merged outside tracked eight | `N1.*` — 🔴 **取代 `H3.verdict` 的判决口径**（H3 的 disjoint=True 算术仍真、claim 仍绿，但论文不再据此下「supports」结论；H3 stmt 待主规划者标注） |
| ~93 defects = 621 × 15.0%（跨 frame 外推，已就地标注）; 563,270 → 621 = 907× ≈ 三个数量级; 3.4× 仅指 245/72 co-located 之比 | `N2.text_fixes_landed` · `M4.three_four_orders_unreconstructible`（旧「3.4 orders」措辞已删） |
| Recall 3/14 = 21.4% [7.6, 47.6]; handler ceiling 5/14; non-handler 9/14 = 64.3% | `J1.recall_superseded`（J1 更新；原 `H1.recall_audit` 2/11 被取代）|
| Ground truth 16 family fixes / 75 merged PRs, all diff-read | `J1.ledger_recompute`, `J1.zero_title_screened`, `J1.three_flips` |
| Truth coverage of findings by maintainer data 171/621 = 27.5% | `H2.*` (not cited in body; available for reviewers) |
| Adoption: 1 star / 0 fork | 冻结表「采用度」行 — never written as adoption |

---

## Reproduction

```bash
cd 新项目-failroute
.venv/bin/python -m pip install '.[test,paper]'   # pytest + matplotlib + ruff/bandit/pylint/flake8(+bugbear)
.venv/bin/python tools/fetch_corpus.py            # pinned sdists → paper/corpus/
    # version+sha256 pinned in paper/corpus-manifest.json; fetch verifies each
    # archive against paper/corpus-lock.json and exits non-zero on mismatch
PYTHONPATH=src .venv/bin/python tools/rescan_corpus.py --out bench/rescan-v0.8
    # rescan with the current detector (total 621). Writes to bench/; do NOT
    # re-export over paper/scan/, which is the frozen v0.7.0 baseline
.venv/bin/python tools/coverage_union.py --findings-dir bench/rescan-f2
    # → bench/corpus-coverage-union.json ; union 250/621 = 40.3%
.venv/bin/python tools/j1_adjudicate.py           # J1 diff-read adjudication (idempotent)
.venv/bin/python tools/compute_intervals.py       # → paper/intervals.json
.venv/bin/python -m pytest                        # 158 tests
cd ../新项目-contractlens
python3 tools/h1_stats.py j1                      # recall 3/14, acceptance 16/43 recomputed
python3 tools/verify_claims.py --slow             # every claim recomputes from raw data
```

🔴 Three pipeline commands are deliberately **not** part of the reproduction
path, because each overwrites a hand-curated artifact without regenerating it
faithfully: `draw_sample.py` (the committed `paper/sample.jsonl` was drawn
from the pre-fix 659 frame; re-drawing changes which 80 findings the published
labels describe), `merged_pr_recall.py` (drops the hand-written `note`
column), and `compare_linters_corpus.py` (drops the merged semgrep results).
See ARTIFACT §0.2、§5.5–5.6.

Artifacts: `paper/corpus-lock.json` (inputs) · `paper/sample.jsonl` (sample) ·
`paper/annotations.csv` (labels + rationale) · `paper/merged-pr-recall.csv`
(recall ledger, all rows diff-read) · `paper/j1-trulens2653-prefix.py`
(pre-fix evidence for the trulens#2653 detection) ·
`bench/corpus-coverage-union-5tool.json` (coverage).

---

## Remaining work before submission

| # | Item | Blocking? |
|---|---|---|
| 1 | ~~Related work with verifiable DOIs / arXiv IDs~~ **done** (K batch: 23/23 entries re-verified 09-02 against Crossref/DBLP/OpenAlex/proceedings pages; 0 unverifiable, 0 miscited) | no |
| 2 | ~~Author block and affiliations~~ **done**（作者本人 2026-09-02 填入 `main.tex`：姓名、Sun Yat-sen University、邮箱，外加 `\thanks` 利益冲突声明脚注；DRAFT 按设计不携任何个人信息） | no |
| 3 | ~~Figures regenerated for the J1 recall values (fig3 cell 2/11 → 3/14)~~ **done** (K batch, commit `d40a772`) | no |
| 4 | Merge `fix/v0.8-precision` and publish 0.8.0 before submission (artifact honesty) | **yes** |

🔴 **Materials discipline:** until this is on arXiv it is *a draft*, not *a
preprint*. Application materials may say **"a preprint describing the tool
and the study"** only after an arXiv ID exists — never "published",
"peer-reviewed", or "accepted".

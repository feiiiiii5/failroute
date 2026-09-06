# Changelog

All notable changes to failroute. Format follows [Keep a Changelog](https://keepachangelog.com/).

## [0.9.0] - 2026-09-06

The predicate rewrite. Findings on the pinned eight-package corpus go 621 → 476.

### Changed

- **The core predicate.** "The handler returned a constant from a fixed set" is
  replaced by two ordered questions: is the value inside the function's success
  domain (`-> Optional[X]` returning `None` is a declared outcome; `-> float`
  returning `0.0` is not), and is the caught exception the answer to the question
  the function asks. The second is what separates `_is_serializable()` returning
  `False` (a contract) from `is_vulnerable()` returning `False` (a claim that a
  scan completed).
- **Logging no longer exempts.** It is a severity modifier, one level down. A
  logged `return 0.0` still hands the caller an indistinguishable score; the log
  makes the failure auditable, not the value distinguishable. What does clear a
  finding is the exception reaching the caller.
- **Handler bodies are walked path-sensitively.** `except: if c: return 0.0 else:
  return 1.0` was invisible to 0.8.0, which only inspected top-level statements.
- **`covered_by` is verified, not inferred.** It read the handler's body shape and
  never the caught type, so every narrow `except X: pass` was credited to
  `S110`/`B110` — rules that only fire on broad handlers. 146 findings were
  over-attributed; the novel share moves from 18.3% to 47.1%. The mapping is now
  checked by running all four linters over a 68-cell probe matrix.
- `silent-suppress` reports only broad suppressions; a specific type is the
  explicit contract `SIM105` asks for.

### Added

- `severity`, `isomorphism`, `covered_by` and a plain-language `verdict` on every
  finding, in text, JSON and SARIF.
- `--only-novel`, `--fail-on`, `--exit-zero`. Exit codes are now 0 / 1 / 2 rather
  than "any finding is 1", which in CI made success look like failure.
- `bench/realworld/` — 87 cases anchored to real coordinates in the pinned corpus.
- `tools/lint_mapping_probe.py`, `tools/pinned_rescan.py`, `tools/refix_replay.py`.

### Fixed

- `except*` (PEP 654) handlers were entirely invisible: the walk matched only
  `ast.Try`.
- Non-deterministic key order in `tools/rq5_refactor_delta.py` (a set fed into a
  `Counter`), which made "byte-reproducible" untrue for that artifact.

### Note on the paper

The accompanying preprint freezes the **v0.8.0** frame at 621 findings on
purpose, and pins its claims to a v0.8.0 worktree. Its numbers and this
README's are expected to differ.

> Not yet released: the version stays at 0.8.0 because a release moves five
> pointers at once (`pyproject.toml`, `__init__.py`, `action/action.yml`,
> `README.md` pre-commit rev, `SECURITY.md` support table) and
> `tests/test_release_consistency.py` fails unless all five agree. Only
> `src/failroute/**`, `tests/**`, `bench/realworld/`, `CHANGELOG.md` and
> `ROADMAP.md` were in scope for this batch, so the pointers were deliberately
> left alone rather than half-moved.

### Changed — the predicate itself

The detector's question was *"did a handler's top-level statement return or
assign a generic constant?"*. It is now *"was the failure converted into a value
the caller cannot tell apart from success, and is that conversion outside the
function's contract?"*, decided in three layers:

1. **Value range.** An explicitly declared `-> None` / `Optional[X]` return
   range, or a local whose own annotation admits `None`, makes the routed value
   contractual rather than a substitute for a result.
2. **Exception/predicate isomorphism.** Is the caught exception *the answer* to
   the question the function exists to answer? `_is_serializable` guarding
   `json.dumps(x)` and catching `(TypeError, ValueError)` is isomorphic — being
   unserializable *is* the negative answer. `is_vulnerable` guarding a loop over
   test cases is not: an exception aborts a partial computation that is then
   reported as a complete, clean "not vulnerable". Decided from three structural
   signals only — catch-all-ness, whether the guarded block loops, whether it
   can produce a value at all — and **never from the function's name**. A
   polarity regex over names was measured first: it hit 3 of 8 confirmed defects
   and judged `is_private_ip`, the one fail-closed positive example in the
   paper, backwards.
3. **Consequence.** Recording the failure now moves a finding **down one level**
   instead of exempting it; a value that outlives the call (object state, result
   constructor) moves it **up one**. Only the exception itself reaching the
   caller — in the return value or a collection the caller reads — makes an
   outcome genuinely distinguishable.

### Added

- **Per-finding severity** (`high`/`medium`/`low`/`info`) on every finding, in
  text, JSON and SARIF output. A per-*rule* SARIF level could not express two
  `silent-fallback` findings three levels apart, which is precisely why the old
  model had to exempt logged handlers instead of downgrading them.
- **`covered_by`** on every finding: the trivial-lint rules that already point
  at the same handler. Empty means nothing else flags this line. Every mapping
  was established by running the four tools over a synthetic file carrying one
  instance of each shape — 68 probes: 11 caught-type forms × 6 body forms plus
  two `contextlib.suppress` cases — and `tools/lint_mapping_probe.py
  --check-parity` re-runs that measurement against the production code path
  rather than trusting the table in `_shared.py`. What the tools actually do:
  - bare `except:` → `flake8:E722`, `ruff:E722`, `bugbear:B001`, `pylint:W0702`
  - a catch-all typed handler (`Exception` / `BaseException`, including inside
    a tuple, dotted, or an unresolvable call) → `ruff:BLE001`, `pylint:W0718`
  - an inert body → `ruff:S110` on any broad handler but `bandit:B110` only on
    bare or plain `except Exception:`; `ruff:S112` / `bandit:B112` split the
    same way over `continue`. `S110`/`B110` need a literal `pass` — `...` does
    not trigger them.
  - a discarded comparison in the guarded block → `ruff:B015`, `bugbear:B015`
  Three results are counter-intuitive and were each measured twice: **`BLE001`
  does not fire on a bare `except:`** (it covered 0 of the 12 confirmed defects
  in the pinned corpus); **bandit is strictly narrower than ruff** — B110/B112
  fire on bare and plain `except Exception:` only, not on `except
  BaseException:` nor on a tuple containing either; and **no tool in the set
  flags `contextlib.suppress(...)` at all**. `ruff:SIM105` does fire on an
  inert body at every caught type, and is deliberately *not* credited: it
  suggests rewriting to `suppress`, which is a style preference, not a report
  that the failure was discarded.
- **`--only-novel`** to report just the findings whose `covered_by` is empty,
  and **`--fail-on {high,medium,low,info}`** (default `high`) plus
  **`--exit-zero`**.
- **`bench/realworld/`** — an external regression bench built *before* the
  predicate was touched, from the 80 human-labelled coordinates in the
  SHA256-locked paper corpus plus the seven probe shapes. 87 cases, five gates.
  Run with `PYTHONPATH=src python3 bench/realworld/run.py`.

### Fixed

- **`covered_by` over-credited the linters.** Found and fixed inside this same
  unreleased build; the account is kept because the *direction* of the error is
  the point. The first implementation inferred `S110`/`B110`/`S112`/`B112` from
  the handler's body alone, never looking at what it catches. Those four rules
  fire only on broad handlers, so every narrow-typed `except X: pass` was
  credited with lint coverage it does not have: **146 findings** on the pinned
  corpus (93 `info`, 48 `medium`, 5 `high`), of which 137 are genuinely novel
  rather than covered. Static novelty consequently read 87/476 (18.3%) where the
  corrected figure is **224/476 (47.1%)**, and HIGH findings with no lint
  coverage read 20 where the corrected figure is **25**. The total finding count
  is unchanged at 476 — this was a mislabelled field, not a detection change.
  It had to be fixed rather than disclosed as a caveat because the error ran in
  the direction of *flattering* the linters, and the paper's central negative
  result is precisely that trivial lint already absorbs the increment: a field
  known to overstate lint coverage cannot be allowed to drive that claim. The
  same audit found a second error running the other way — a tuple catch bailed
  out of the broadness test entirely, so `except (CancelledError, Exception):`
  was credited with nothing and 3 findings were under-credited.
  `tools/refix_replay.py` now replays the 36 mapping tests against the pre-fix
  predicate (21 of them fail) so the gate cannot silently go vacuous.
- **Path-sensitive handler exits.** `for stmt in handler.body` could not see
  `if strict: return 0.0 else: return 1.0`, so a handler routing the failure on
  *every* path reported nothing. Replaced by an enumerator covering
  `if`/`else`, `with`, `try`/`except`/`else`/`finally`, `match`/`case` and
  loops (approximated conservatively), never entering nested `def`/`class`/
  `lambda`. Each block is expanded exactly once.
- **`except*` (PEP 654) was invisible.** The traversal matched `ast.Try` only,
  so every `except*` handler in a scanned tree was silently skipped. `ast.TryStar`
  is now handled wherever `ast.Try` is.
- **Null-byte sources raised.** `ast.parse` reports those as `ValueError`, not
  `SyntaxError`; the skip path now catches both.
- **Skipped files could print to stderr.** An unreadable file logged at
  `WARNING`, which reaches stderr through logging's last-resort handler — one
  line per unreadable file during a whole-tree scan. Now `DEBUG`.
- **An unexpected exception during a scan escaped as a traceback** and, worse,
  would have been indistinguishable from "findings above threshold". It is now
  caught at the CLI boundary and reported as exit 2.
- **Exit 1 no longer means "any finding at all".** The old contract made a
  clean scan of a typical repository look like a failure in CI, since almost
  every codebase has at least one low-severity finding.

### Removed / narrowed

- `silent-suppress` now reports **broad** suppression only
  (`suppress(Exception)` / `suppress(BaseException)` / unresolvable arguments).
  On the pinned corpus the split measured 23 broad to 4 specific, so this drops
  4 findings and keeps every shape that discards an unbounded exception set.
- `name-shadowing` still ships, but at `info`, with the reason recorded in the
  rule: its consequence is a *loud* failure (`UnboundLocalError` on the next
  read), which is the opposite of failure-routing, so it must not count toward
  any precision or recall claim about this family. The rejected justification
  for deleting it — "CPython is safe about rebinding the exception name" — is
  **false** and was measured; the conclusion survives, that reason does not.

### Measured effect on the pinned corpus

2,124 files / 524,229 lines across eight SHA256-locked packages:

| | v0.8.0 | this build |
|---|---|---|
| findings | 617 coordinates | 472 coordinates (476 findings) |
| high | — (no per-finding severity) | 208 |
| high ∧ `covered_by` empty | not expressible | 25 |

All 12 confirmed defects are still reported, all at `high`. On the 16 labelled
`-> bool` coordinates the isomorphism verdict is 8:8 correct, including not
reporting `is_private_ip`.

The 25 was 20 until the `covered_by` fix above; the five that joined are all
specific-typed handlers — two `except SyntaxError: pass`, one
`except FileNotFoundError: pass`, one `except (OSError, _7Z_ARCHIVE_ERROR):
pass`, one `except anyio.get_cancelled_exc_class(): pass` — which is exactly the
shape the old inference wrongly credited `S110`/`B110` for. The authoritative
stratification of the confirmed defects by handler form is the paper's RQ2
crosstab, not this table.

### Known red, by design

- `tools/closure_check.py` reports `git_clean FAIL` — but **no longer for the
  reason originally written here.** That reason was that the `covered_by` fix
  was deliberately held uncommitted until the paper's numbers were final, so a
  field known to have been wrong was never the tip of a branch; the V4 seal
  commit discharged it. The check still fails, for a much smaller one:
  `paper/arxiv/main.out`, a hyperref build intermediate, is untracked and is
  not in `.gitignore`, which already covers its three siblings `main.aux`,
  `main.log` and `main.blg`. Measured 2026-09-05 after the seal: **7 checks
  PASS, `git_clean` FAIL, "1 uncommitted path(s)"** — and that path is
  `main.out`. Adding one line to `.gitignore` closes it. The V4 batch did not,
  because `.gitignore` was not among the paths it was authorised to touch.
  🔴 Note for `paper/ARTIFACT.md` §6.4, which tells a reviewer to expect
  `CLOSURE: CLOSED (8/8)`: as of this commit the honest output is `1 FAIL`.
- One bench case disagrees with a human label and is left disagreeing:
  `pydantic_ai/models/fallback.py:478`, `with suppress(Exception):` inside a
  telemetry method declared `-> None`, labelled CONTRACT. The label rests on
  "telemetry is best-effort", which is domain knowledge the structure does not
  encode. Reporting it is the conservative direction; see
  `bench/realworld/README.md`.

### No longer red (this section used to list them)

The V1 batch left two claims-ledger entries stale on purpose, its own scope
being the detector rather than the tooling. Both are closed:

- `F1.f2_consistency` asserted that `warnings.warn` exempts a handler, which
  layer 3 overturns — recording the failure now downgrades a finding one level
  instead of suppressing it. Replaced in V1 by a **paired probe**: the same
  handler with and without `warnings.warn` must both be reported and must sit
  one severity level apart. That is strictly stronger than the original, since
  it fails both if the exemption comes back and if the downgrade is removed.
- `F1.no_regression` pinned a test count that moved 158 → 185 in V1 and
  185 → 221 in V3 when the mapping tests landed. Each move turned the claim red
  and each fix meant editing a gate, which is the one thing the ledger's rules
  exist to prevent. V4 removed the incentive instead of re-freezing a fourth
  time: the expect is now a **floor** — at least 221 passed, *and* no `failed`
  or `error` anywhere on the summary line — so deleting a test still goes red
  while adding one no longer requires touching the gate. 🔴 This is not a
  one-way loosening. The old exact form also matched `1 failed, 221 passed`, so
  a suite of 222 with one failure passed the gate; the new form is strictly
  tighter on failures and looser only on count. Both halves are demonstrated by
  real pytest runs recorded in the claim's `stmt`, not by argument.

The eleven `slow` claims that the V1 refactor turned red were **re-pinned, not
rewritten**: `tools/pinned_rescan.py` rescans the locked corpus inside a v0.8.0
worktree using that revision's own source and exporter, so each claim still
asserts the historical scan it was written about, with its expected numbers
untouched. `F3.truth_f3_154` needed a second pin on the truth side — it reads
`dataset.jsonl` from the neighbouring contractlens repository, whose coverage
was extended three hours after the claim was frozen, so the cmd now takes that
file at the commit which was in force at the time. `verify_claims.py` **without**
`--skip-slow` is the acceptance gate; with it, all eleven are invisible.

## [0.8.0] - 2026-09-01

### Changed
- **Baseline re-freeze**: the eight-package corpus baseline is now the v0.8.0
  finding set (621 findings); README benchmark tables updated to the re-run
  union numbers (four-linter union 250/621 = 40.3%; + hand-written semgrep
  269/621 = 43.3%), and the 80-sample annotation section carries a
  provenance caveat (LLM-labelled, v0.7.0 frame).
- **Recall-gap adjudication (I0)**: the two known in-scope recall misses
  (inspect_ai#5068 state-mutation routing, inspect_ai#4906 tenacity
  RetryError masking) are adjudicated NEW CANDIDATE PATTERNS, not rule bugs;
  both fail the ROADMAP candidate gate (no independent hand-labelled
  fixtures; the second needs library semantics the tool refuses to guess),
  so neither ships. Rationale recorded in `docs/f-batch-report.md` §I0 and
  `paper/merged-pr-recall.csv` notes.

### Fixed
- **Precision round (F batch)**: three deterministic false-positive classes
  closed. `except (A, B)` tuple handlers are now matched against the
  control-flow ignore list when every member is ignored; `warnings.warn()` /
  `warnings.warn_explicit()` count as an error signal in typed and catch-all
  handlers alike; `StopAsyncIteration` joins `IGNORED_EXC_NAMES` (async twin
  of `StopIteration`).
- **Two precision adjudications** (see `docs/f-batch-report.md` ADR-0001 /
  ADR-0002): optional-dependency probes (`try: import x / except ImportError:`
  with a pure import/setup body and a minimal capability fallback) are
  contracts, not findings; `with suppress(...)` inside a handler that
  re-raises at top level is best-effort cleanup, not failure routing. Both
  exemptions are deliberately narrow — mixed tuples, non-import guarded
  bodies, non-minimal fallbacks, and branch-conditional raises all stay
  reported.
- **CI on Python 3.9**: `tests/corpus/v06_shapes.py` carried a PEP 634
  `match`/`case` handler, which made the *whole corpus file* unparseable on the
  oldest supported interpreter. Every label in that file was scored as a miss,
  so the corpus gate failed on the 3.9 leg. The `match`/`case` shapes now live
  in their own file (`tests/corpus/match_case_cases.py`), and
  `tools/benchmark.py` reports corpus files the running interpreter cannot
  parse as **skipped** (their labels excluded from that run) instead of
  counting them as false negatives. `pytest` asserts that nothing is skipped on
  Python 3.10+, so those labels remain enforced in the 3.10-3.13 legs of the
  matrix. The version-specific unit test is `skipif`-gated for the same reason.
- README benchmark and corpus figures were restated from the checked-in
  `bench/` artifacts; they had silently drifted behind v0.6/v0.7. Measured
  numbers are now maintained in one place, and `docs/writeup.md` links to them
  instead of carrying a copy that goes stale.

### Added
- `.github/CODE_OF_CONDUCT.md` (Contributor Covenant 2.1) and
  `.github/PULL_REQUEST_TEMPLATE.md` (the four deterministic gates).
- `tests/test_release_consistency.py`: the package version, the composite
  Action's default pin, the README pre-commit `rev`, the SECURITY.md supported
  series and the CHANGELOG entry must all name the same release. Three of
  those five had drifted (the Action was installing a two-releases-old engine,
  SECURITY.md advertised 0.4.x support, and the README rev lagged a release);
  drift is now a CI failure rather than something a reader discovers.
- README `## License` section (the MIT `LICENSE` file was never referenced).

### Fixed
- `.pre-commit-hooks.yaml` description named 2 of the 6 detection modes.

### Chores
- Stopped tracking build/test artifacts in the repository: `.coverage` and a
  local issue draft (both now covered by `.gitignore`).

## [0.7.0] - 2026-08-29

### Added
- **Dotted-name sentinels**: `[tool.failroute] fallback_names = ["Status.UNKNOWN", "Signal.NAN"]`
  extends the failure vocabulary to Enum members and qualified constants,
  matched on attribute chains only. Bare (unqualified) names are rejected by
  design — `return result`-style code must never match a config token.
  `NaN` via `float("nan")` and indirect fallbacks through helper calls
  remain explicitly out of scope (see ROADMAP "Considered and declined").

### Fixed
- **`implicit-fallback` false-positive class**: handlers whose body is
  `continue` (skip-and-continue over a result loop) or `break` (retry
  exhaustion) were reported as fall-throughs to the enclosing function's
  implicit `None`. Both are control-flow terminators — deliberate routing,
  not silent corruption. Found by the refreshed 8-repository ruff-comparison
  benchmark (garak alone carried thousands of such loop-skip handlers);
  labelled corpus negatives added before the fix.
- **README example/implementation mismatch**: the headline `data =
  {"items": []}` example never produced a finding — non-empty error-shaped
  containers are deliberately exempt (an explicit error object is the
  remediation the tool recommends). The example now uses a shape the scanner
  actually reports, and the "not flagged by design" section states the
  exemption explicitly.

### Fixed (audit round)
- **`implicit-fallback` tail-position gate**: a handler inside a loop, or a
  `try` followed by a trailing `return`, does not fall through to the
  function's implicit `None` (fall-through re-enters control flow or reaches
  the trailing return). Both shapes were false positives; labelled corpus
  negatives added before the fix, and the rule now only reports handlers
  whose fall-through actually reaches the end of the function body.
- **Scan-cache isolation**: the cache payload now carries the engine version
  and a fingerprint of the scan options (disabled rules, sentinel
  vocabulary); any mismatch downgrades to a cold scan. Previously, findings
  scanned under a configured sentinel vocabulary could be served to an
  unconfigured scan (cache poisoning), and caches survived engine upgrades.
- Configured-sentinel findings now say "configured sentinel" instead of
  "constant", so the message states why the token matched.

### Changed
- ROADMAP: inter-procedural/dataflow tracking (and the indirect
  helper-call fallback shape) moved into "Considered and declined" with the
  reasoning, alongside `return`-in-`finally`.

## [0.6.0] - 2026-08-29

### Added
- **`implicit-fallback` detector**: a handler that neither re-raises, returns
  explicitly, nor records the failure falls through — and inside a
  value-returning function the caller observes exactly the outcome of
  `except: pass` (the implicit `return None`). The v0.5 visitor only
  examined raise/return/assignment statements, so bare-statement handlers
  (`print(...)`, conditional raises, docstring-only bodies) slipped through
  every gate. Precision gates: the enclosing function must return a real
  value on its success path; procedures, generators, logged handlers,
  bare-`return`-only functions, and process-terminating handlers are exempt.
- **Rule registry + plugin architecture** (`failroute.rules`): one module
  per anti-pattern with declarative metadata (`RuleSpec`); adding a rule is
  one module + one registry line. SARIF rule metadata is now generated from
  the registry, closing the output-drift class of bugs.
- **Unified finding IR** (`failroute.ir`): `Finding` carries `rule_id`;
  `FailureMode`, `RuleSpec`, `ScanContext` and the `Rule` contract live in
  one place.
- **Configurable fallback sentinels**: `[tool.failroute] fallback_values =
  [-1, "N/A"]` teaches the scanner a project's failure vocabulary; the
  detector matches the canonical rendering and refuses to guess unconfigured
  semantics.
- **Per-rule policy**: `[tool.failroute.rules.<id>] enabled / severity`
  tables and a `--ignore RULE` CLI flag.
- **Performance**: `--jobs N` (0 = per-core) fans repo scans across worker
  processes; `--cache` keeps an mtime+size-keyed cache in the system temp
  dir. Measured on the vLLM core tree (2,032 files / ~758 kLOC): 10.3 s
  serial -> 2.0 s parallel (~377 kLOC/s) -> 0.1 s cache-warm, findings
  byte-identical across all three paths.
- Corpus v3: 36 hand-labelled positives + 27 labelled negatives (63 total)
  across all six modes, including the implicit-fallback family and
  configurable-sentinel boundary cases.
- `docs/architecture.md` (five-layer pipeline) and `docs/triage.md` (the
  human adjudication workflow behind the precision claim).

### Fixed
- **Logger-name heuristic**: the exact five-name whitelist (`logger`,
  `logging`, `log`, `_logger`, `sentry_sdk`) misjudged conventional names
  (`LOG`, `audit_logger`, `self._log`), so recording handlers were falsely
  reported as silent fallbacks. Names are now matched case-insensitively
  with the conventional `_log`/`_logger`/`logger`/`logging` suffixes.
- **`match`/`case` conditional raises** are recognised as branches
  (`masked-exception` classification, not the lower-level
  `silent-fallback`).
- **Handlers nested two or more levels deep were reported twice** — the
  v0.5 walker re-visited its own subtree for nested handlers. Every handler
  is now visited exactly once (regression test in `test_boundaries.py`).
- Numeric fallback tokens `1` / `1.0` were dead whitelist entries (the
  renderer never produced them); the renderer now canonicalises every
  numeric constant, so `return 1` is flagged as the documented ambiguous
  hint. Augmented assignments (`failed += 1`) are excluded on purpose:
  the constant is an increment, never the assigned fallback value.
- The v0.6 rules found 2 latent silent-fallback shapes in failroute's own
  cache code during self-scan; both restructured (propagate or log) per the
  tool's own discipline.

### Changed
- Engine internals moved to the registry architecture with identical
  detection behaviour on the existing corpus; public API
  (`scan_source`/`scan_path`/`scan_repo`/`main`/`Finding`/`FailureMode`)
  is unchanged, with `Finding.to_dict()` gaining a `rule_id` field.

## [0.5.1] - 2026-08-28

### Fixed
- Ignore-list consistency between syntaxes: `contextlib.suppress(KeyboardInterrupt)` /
  `suppress(StopIteration)` / `suppress(CancelledError)` (and friends) are
  idiomatic control-flow absorption and are no longer flagged — matching the
  handler-level exemption that already existed. One real error type in the
  same call (e.g. `suppress(CancelledError, OSError)`) still flags: mixing an
  idiomatic suppression with a real failure type does not make the failure
  routable. Corpus extended with labelled fixtures for the exemption, both
  dotted and bare forms, and the mixed case.
- `failroute --repo file.py` silently reported zero findings (repository
  traversal over a file path yields nothing); a single-file path now falls
  back to a direct file scan.

### Added
- Tag-triggered release workflow now creates the GitHub Release
  automatically, with notes extracted from the CHANGELOG section matching the
  released version (`tools/release_notes.py`).
- PyPI project links (`Homepage` / `Changelog` / `Issues`) and the
  `Typing :: Typed` classifier.

## [0.5.0] - 2026-08-28

### Added
- `silent-suppress` detector: `with contextlib.suppress(...)` is semantically
  identical to `try` / `except` + discard, but no shipped linter flags it —
  and ruff's SIM105 actively recommends rewriting `try-except-pass` into this
  form, migrating the silence out of every existing detector's view.
  Resolution is import-aware (direct import, `contextlib.` attribute access,
  and aliases are all recognized; a same-name import from another module is
  not). `# failroute: ignore` / `# pragma: no cover` markers are honored on
  the `with` line. Benchmark re-run: 77 suppress blocks across 8 real
  AI/eval repositories, all invisible to ruff S110/S112.
- Corpus v2: 27 hand-labelled samples (15 positives across all four modes,
  12 negatives), labels written from fixture semantics independently of tool
  output; precision 1.0 / recall 1.0 enforced by `pytest` and
  `tools/benchmark.py`.
- `tools/compare_ruff.py` now reports the `silent-suppress` column and
  records the exact scanned path per repository.

### Fixed
- SARIF rule metadata was missing `name-shadowing` (shipped in 0.3.0 but
  absent from the rules dictionary, so code scanning showed it without a
  description). `silent-suppress` metadata added alongside.
- `_handler_logs_error` was not scope-aware: a log call inside a callback
  *defined* in the handler exempted the handler even though the callback may
  never run. It now uses the same scope-aware walk as the rest of the
  analyzer.
- Module docstring claimed unconditional re-raise counts as `no-action`; the
  implementation (and README) never flagged it.

### Not adopted, deliberately
- `return` inside `finally`: a real failure-routing form, but already covered
  by syntactic rules (ruff/bugbear `B012`, `SIM107`). Adding it would dilute
  the differentiator — failroute targets the class syntactic rules cannot
  express.

## [0.4.0] - 2026-08-27

### Added
- Project-level configuration: `[tool.failroute]` in the nearest
  `pyproject.toml` (searched upward from the scan path) with `exclude`
  (list of paths) and `threshold` (int). CLI flags always override config;
  malformed config is ignored, never fatal.
- `py.typed` marker (PEP 561) — the package ships inline type annotations.
- Pre-commit hook manifest (`.pre-commit-hooks.yaml`).
- PyPI Trusted Publishing release workflow (OIDC, tag-triggered, no long-lived
  token), bug-report issue template, and Dependabot for action versions.
- CI: 3 OS × 5 Python versions test matrix plus a dedicated quality job
  (`ruff`, `mypy --strict` on `src/`, coverage gate ≥ 88%, self-scan,
  corpus benchmark).

### Changed
- `--threshold` default resolution order is now: CLI flag >
  `[tool.failroute]` config > `0`.
- SARIF tool version is read from installed distribution metadata instead of
  a hardcoded constant that had drifted (v0.3.0 shipped labelled 0.2.0).

## [0.3.0] - 2026-08-27

### Added
- `name-shadowing` detector: rebinding the caught exception variable, whose
  binding Python deletes at handler exit (later uses raise `NameError`).
- Labelled benchmark corpus (`tests/corpus/` + `tests/corpus/manifest.json`):
  19 hand-labelled exception handlers with independently written ground truth;
  current corpus score is precision 1.0 / recall 1.0, enforced by `pytest` and
  `tools/benchmark.py`.
- `tools/compare_ruff.py`: quantifies the detection gap against ruff's
  syntactic exception rules (S110/S112) on real repositories.
- `--exclude PATH` (repeatable): skip repo-relative paths such as intentional
  fixture directories; implies repository-style traversal.
- `python -m failroute` module invocation (`src/failroute/__main__.py`).
- Composite GitHub Action under `action/` for SARIF uploads to code scanning.
- CI now runs the benchmark and a self-scan with corpus exclusion.
- `[project.optional-dependencies] test` so `pip install -e ".[test]"` works.

### Changed
- Two-tier logging exemption: catch-all handlers need a readable severity
  (`warning`+) to count as informational; typed handlers accept any level.
- Scope-aware scans: returns inside callbacks defined within a handler belong
  to the callback, not the handler's control flow.
- `masked-exception` is now gated to catch-all handlers; typed handlers with
  conditional re-raise + early return are treated as deliberate retry logic.
- `sys.exit` terminates control flow like `raise`; `StopIteration` and
  `CancelledError` joined the ignore list. Deterministic finding order.
- `scan_path` skips files whose AST nesting exceeds the interpreter's
  recursion budget instead of crashing (real-world red-team payload resources
  trigger this); covered by a regression test.
- CLI tests invoke the tool via `python -m failroute`, making the suite work
  from a bare source checkout.

### Removed
- README's previous "validation on real codebases" table: its numbers were not
  reproducible from the checkout. Replaced by the benchmark section, whose
  every number is re-runnable.

## [0.2.0] - 2026-08-25

### Added
- SARIF 2.1.0 output, `# failroute: ignore` opt-out markers, text/json/sarif
  output formats, `--threshold`, `--quiet`, `--output`.

## [0.1.0] - 2026-08-25

### Added
- Initial scanner: `no-action`, `silent-fallback`, `masked-exception`
  detection over Python ASTs with CLI.

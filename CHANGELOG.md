# Changelog

All notable changes to failroute. Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

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

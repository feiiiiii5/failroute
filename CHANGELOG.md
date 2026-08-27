# Changelog

All notable changes to failroute. Format follows [Keep a Changelog](https://keepachangelog.com/).

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

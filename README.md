# failroute

[![CI](https://github.com/feiiiiii5/failroute/actions/workflows/ci.yml/badge.svg)](https://github.com/feiiiiii5/failroute/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/failroute)](https://pypi.org/project/failroute/)
[![Python](https://img.shields.io/pypi/pyversions/failroute)](https://pypi.org/project/failroute/)

Static detection of **failure-routing** anti-patterns in Python: the practice of
converting an underlying failure into a success-like outcome at the wrong layer.

## Why this exists

While fixing correctness bugs across mainstream AI/ML open source, one defect
family kept recurring: an LLM judge outage becoming a legitimate-looking `0.0`
score, a network error becoming "no results", a red-team metric reporting
success from a judge that never ran. Existing linters reason about the *shape*
of an exception handler; the defect lives in what the handler *returns*.
`failroute` is a detector for that semantic gap, built around three principles:

- **Precision over volume** — every rule is validated against a hand-labelled
  corpus whose ground truth was written independently of tool output.
- **Honest triage** — findings without a production consequence chain are
  benchmark material, not issues (see `docs/process.md` for a worked example).
- **Everything reproducible** — every number in this README can be re-run from
  this checkout with one command.

Failure-routing is the root cause behind some of the most insidious correctness
bugs in real LLM/eval/agent codebases:

```python
# Before — a judge API outage becomes a perfect "0.0 score" with no way to tell
try:
    score = await llm_judge(prompt)
except Exception:
    return 0.0  # ← silent fallback: failure looks like a legitimate low score

# After — the failure propagates; callers can route it to the right outcome
return await llm_judge(prompt)
```

## What it detects

| Mode | Pattern |
| --- | --- |
| `no-action` | `except ...: pass` — the exception is discarded, callers never learn |
| `silent-fallback` | handler returns/assigns a constant (`None`, `0`, `0.0`, `False`, `[]`, …) without re-raising |
| `masked-exception` | **catch-all** handler re-raises conditionally yet also falls through to a success-looking return |
| `name-shadowing` | `except E as e:` whose body rebinds `e` — Python deletes the binding at handler exit, so later uses raise `NameError` |

Findings are emitted as `file:line: mode: message`, or as JSON for CI.

### Logging exemption (two tiers)

A handler that *records* the failure is informational, not silent — but what
counts as a record depends on how wide the handler is:

- **Catch-all handlers** (`except:` / `except Exception:`) must log at a
  severity worth reading (`warning`+). A `debug` line or a bare `print(...)`
  does not survive production triage, so it does not exempt.
- **Typed handlers** name an anticipated failure mode; recording it at *any*
  level (even `logger.info`) is enough.

## Usage

```console
$ failroute path/to/file.py
$ failroute path/to/dir      # recursive
$ failroute --repo .         # skip .git/.venv/build/...
$ failroute --repo . --exclude tests/corpus   # repeatable path exclusions
$ failroute --json --repo .  | jq 'select(.mode=="silent-fallback")'
$ failroute --format sarif --output results.sarif --repo .   # code scanning
$ failroute --threshold 5    # exit 1 when more than 5 findings
$ python -m failroute .      # module form (no console script needed)
```

Exit codes: `0` clean, `1` findings above threshold, `2` usage error.

### Project configuration

Repositories can commit their policy instead of repeating CLI flags; the
nearest `pyproject.toml` at or above the scan path is consulted:

```toml
[tool.failroute]
exclude = ["tests/corpus", "vendor"]
threshold = 0
```

CLI flags always override config. Malformed config is ignored, never fatal.

### pre-commit

```yaml
repos:
  - repo: https://github.com/feiiiiii5/failroute
    rev: v0.4.0
    hooks:
      - id: failroute
```

### Output formats

```console
$ failroute --format text   path/       # default: file:line: mode: message
$ failroute --format json   path/       # one JSON object per finding
$ failroute --format sarif  --output scan.sarif path/   # SARIF 2.1.0
```

SARIF output plugs straight into [GitHub code scanning](
https://docs.github.com/en/code-security/code-scanning) via the
`upload-sarif` action, so findings appear inline on pull requests:

```yaml
- run: failroute --format sarif --output results.sarif --repo .
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: results.sarif
```

Or use the bundled composite action, which installs failroute, scans, and
uploads SARIF in one step:

```yaml
- uses: feiiiiii5/failroute/action@main
  with:
    path: src
    exclude: tests/corpus fixtures
    threshold: "0"
```

Severity mapping: `silent-fallback` → `error`, `no-action` and
`masked-exception` → `warning`.

### Suppressing findings

Reviewed-and-accepted handlers can be opted out with a line marker (the
scanner honors both):

```python
try:
    return best_effort()
except Exception:  # failroute: ignore - documented fallback semantics
    return None
```

`# pragma: no cover` markers are honored as well (explicitly defensive code).

## Examples that trip it

```python
def classify(text):                       # no-action
    try:
        return model.predict(text)
    except Exception:
        pass                                # 💥 swallowed

def score(prompt):                          # silent-fallback
    try:
        return judge(prompt)
    except Exception:
        return 0.0                          # 💥 outage == "0.0 score"

def fetch(url):                             # silent-fallback (assign)
    data = None
    try:
        data = download(url)
    except Exception:
        data = {"items": []}                # 💥 error looks like an empty result
    return data
```

## What it does *not* flag (by design)

* `except KeyboardInterrupt` / `except SystemExit` — normally intentional.
* Handlers that re-raise unconditionally without a fallback.
* `except` bodies that log at `warning`/`error` **and** re-raise — the failure
  still propagates; we only flag the success-looking path.

Run `failroute` on its own checkout as a smoke test:

```console
$ pip install -e .
$ failroute --repo .     # expected: zero findings (self-hosting)
```

## Benchmarks & validation

All numbers below are reproducible from this checkout; nothing here is
copy-pasted from a run that cannot be re-executed.

### Labelled corpus (precision / recall)

`tests/corpus/` holds 19 hand-labelled exception handlers (10 positives across
all three modes, 9 negatives covering re-raise, log-and-raise, derived values,
dead code, opt-out markers, and non-fallback constants). Ground truth lives in
`tests/corpus/manifest.json` and was written from the *semantics* of each
fixture, independently of tool output.

```
corpus v1   TP=10  FP=0  FN=0  TN=9
precision=1.0  recall=1.0
```

Re-run: `python tools/benchmark.py` (also enforced by `pytest`).

### What syntactic linters miss

Against the source packages of 8 real AI/eval repositories (garak,
inspect_ai, pydantic-ai, uqlm, trl, smolagents, deepteam, fickling),
failroute reported **647 findings**; ruff's exception-handling rules
(`S110` try-except-pass, `S112` try-except-continue) reported **80**, of which
70 overlap failroute's `no-action` mode. The remaining **390 findings are
silent-fallback / masked-exception handlers** -- failures converted into
success-looking values -- a class syntactic rules cannot express by
construction.

Re-run: `python tools/compare_ruff.py <repo> [<repo> ...]`.
Results are checked into `bench/`.

### Throughput

Measured 2026-08-27 on `microsoft/PyRIT` (656 files, 148,241 lines):
**78 kLOC/s** single-core (1.91 s wall time, 107 findings). Re-run:
`time failroute --repo <checkout> --quiet`.

## Development

```console
$ pip install -e ".[test]"
$ pytest
$ ruff check .
```

## How this project is built

`failroute` is developed with an **AI-assisted, human-audited workflow**:
LLM tooling proposes code and analyses, but nothing lands without passing
deterministic gates — a 70+ test suite, a hand-labelled precision/recall
corpus, `mypy --strict`, and a self-scan of the repository with the tool
itself. Humans own every judgment call: rule semantics, corpus labels,
upstream triage, and all external communication. A worked example of that
triage discipline (including a case where we deliberately filed *nothing*)
is in [`docs/process.md`](docs/process.md).
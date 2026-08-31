# failroute

[![CI](https://github.com/feiiiiii5/failroute/actions/workflows/ci.yml/badge.svg)](https://github.com/feiiiiii5/failroute/actions/workflows/ci.yml)
[![self-scan](https://github.com/feiiiiii5/failroute/actions/workflows/self-scan.yml/badge.svg)](https://github.com/feiiiiii5/failroute/actions/workflows/self-scan.yml)
[![PyPI version](https://img.shields.io/pypi/v/failroute)](https://pypi.org/project/failroute/)
[![Python](https://img.shields.io/pypi/pyversions/failroute)](https://pypi.org/project/failroute/)

Static detection of **failure-routing** anti-patterns in Python: the practice of
converting an underlying failure into a success-like outcome at the wrong layer.

## Quickstart

```console
$ pip install failroute
$ failroute judge.py
judge.py:4: silent-suppress: contextlib.suppress(Exception) silently discards every failure inside the block; callers can never learn the operation failed
1 finding(s)
```

The flagged code — the exact pattern ruff's SIM105 rule *recommends* as a fix:

```python
import contextlib

def score_answer(prompt: str, answer: str) -> float:
    with contextlib.suppress(Exception):   # judge outage == silence
        return judge(prompt, answer)
    return 0.0
```

## How it differs from the linters you already run

| | ruff `S110`/`S112`, Bandit `B110`/`B112` | failroute |
|---|---|---|
| What it sees | the *shape* of a handler (`except: pass`, `except: continue`) | what the failure is *routed to* (constants returned, values assigned, suppress blocks) |
| `return 0.0` after a judge outage | invisible | flagged (`silent-fallback`) |
| `contextlib.suppress(Exception)` | invisible — SIM105 actively *recommends* migrating into it | flagged (`silent-suppress`) |
| Branch-dependent outcomes (conditional re-raise + fallback) | invisible | flagged (`masked-exception`) |
| Precision target | low-noise, syntactic by design | **findings are not a defect list** — see "How often is a finding a bug?" below; they are meant to be triaged by a human |

failroute is not a replacement: it runs alongside your linter as a separate,
higher-scrutiny pass over eval, judge, and agent code paths.

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
| `implicit-fallback` | handler body neither re-raises, returns explicitly, nor records — it falls through, and a value-returning function hands the caller its implicit `None` (bare `print(...)`, conditional raise, docstring-only bodies) |
| `silent-suppress` | `with contextlib.suppress(...)`: semantically identical to `except` + discard, but invisible to every shipped syntactic linter — and ruff's SIM105 actively *recommends* rewriting `try-except-pass` into this form |

Findings are emitted as `file:line: mode: message`, or as JSON for CI.

### Logging exemption (two tiers)

A handler that *records* the failure is informational, not silent — but what
counts as a record depends on how wide the handler is:

- **Catch-all handlers** (`except:` / `except Exception:`) must log at a
  severity worth reading (`warning`+). A `debug` line or a bare `print(...)`
  does not survive production triage, so it does not exempt.
- **Typed handlers** name an anticipated failure mode; recording it at *any*
  level (even `logger.info`) is enough.

Logger objects are recognised by a name heuristic (``logger``, ``LOG``,
``audit_logger``, ``err_log``, ``self._log``, …), not a fixed five-name
whitelist — exact-name matching silently misjudged every unconventional
logger name into a false positive.

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
ignore = ["name-shadowing"]            # disable rules by id
fallback_values = [-1, "N/A"]           # project-specific fallback sentinels

[tool.failroute.rules.implicit-fallback]
enabled = false                          # same as adding to `ignore`
severity = "warning"                     # override the SARIF level
```

Sentinel canonicalisation: a TOML int/float is its decimal token (`-1`), a
TOML string its Python `repr` form (`"N/A"` -> `"'N/A'"`). The tool matches
what you write against the same canonical rendering the detector produces —
and without configuration it refuses to guess project-specific sentinels.

CLI flags always override config (`--ignore RULE`, `--exclude PATH`).
Malformed config is ignored, never fatal. Large trees: `--jobs 0` fans the
scan across cores and `--cache` keeps an mtime-keyed result cache in the
system temp dir; both produce findings identical to the serial scan.

### pre-commit

```yaml
repos:
  - repo: https://github.com/feiiiiii5/failroute
    rev: v0.7.0
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
        data = {}                           # 💥 error looks like an empty result
    return data

def evaluate(prompt):                       # silent-suppress
    with contextlib.suppress(Exception):    # 💥 outage == silence, no trace at all
        score = judge(prompt)
    return score
```

## What it does *not* flag (by design)

* `except KeyboardInterrupt` / `except SystemExit` — normally intentional.
* Non-empty "error-shaped" containers (`return {"items": [], "error": True}`)
  — an explicit error object is the remediation the tool itself recommends,
  so it refuses to second-guess one. Loop skip-and-continue / retry-break
  handlers (`continue` / `break`) are deliberate control flow, not
  fall-throughs.
* The same control-flow exception types under `contextlib.suppress`
  (`KeyboardInterrupt`, `SystemExit`, `StopIteration`, `CancelledError`,
  `GeneratorExit`) — absorbing cancellation or iterator termination is
  idiomatic, not failure routing. One real error type in the same call
  (e.g. `suppress(CancelledError, OSError)`) still flags.
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

`tests/corpus/` holds **68 hand-labelled samples** (36 positives across all six
modes, 32 negatives covering re-raise, log-and-raise, derived values, dead
code, opt-out markers, non-fallback constants, non-suppress context managers,
same-name-different-origin imports, idiomatic control-flow suppression, enum
and named sentinels, and terminal `os._exit` handlers). Ground truth lives in
`tests/corpus/manifest.json` and was written from the *semantics* of each
fixture, independently of tool output.

```
corpus v6   TP=36  FP=0  FN=0  TN=32
precision=1.0  recall=1.0
```

`tests/corpus/match_case_cases.py` uses PEP 634 (`match`/`case`) syntax, so it
is only parseable on Python 3.10+. `tools/benchmark.py` reports it as a
*skipped* corpus file on older interpreters instead of scoring its labels as
misses, and `pytest` asserts that nothing is skipped on 3.10+ — CI covers
3.9–3.13, so every label is enforced somewhere in the matrix.

Re-run: `python tools/benchmark.py` (also enforced by `pytest`).

### What syntactic linters miss

Measured against **eight pinned PyPI releases** (garak, inspect_ai, pydantic-ai,
uqlm, trl, smolagents, deepteam, fickling — 2,354 files, 563,270 lines), locked by
URL, SHA-256 and tree hash in `paper/corpus-lock.json` so the corpus is
byte-reproducible. failroute reports **649 findings**.

Compared against **four standard linters** at their default configurations
(ruff, bandit, pylint, flake8 + bugbear), matching on ±1 line:

| | Findings co-located | Share |
| --- | --- | --- |
| Union of all four linters | **253** | 39.0% |
| **failroute only** | **396** | **61.0%** |

Per mode, and which tool (if any) reaches it:

| Mode | Total | Covered by the four | Notes |
| --- | --- | --- | --- |
| `silent-fallback` | 400 | 179 (pylint 178) | the defect is what the handler *returns*, not its shape |
| `no-action` | 219 | 72 (ruff 72 / pylint 67 / bandit 63) | the one family syntactic rules do reach |
| `silent-suppress` | 27 | **0** | `contextlib.suppress` is a call expression, not an `ExceptHandler`; ruff's SIM105 actively *recommends* rewriting `try-except-pass` into it |
| `masked-exception` | 3 | 3 (pylint) | branch-dependent outcome |

> **A note on baselines.** Earlier versions of this README compared only against
> ruff's `S110`/`S112`. That is not a fair baseline: **pylint is much stronger**
> (178 + 67 on its own), and a ruff-only comparison overstates the gap by roughly
> 3.4×. The numbers above use the union of four linters. A hand-written semgrep
> ruleset targeting these patterns raises the union to 279 (43.0%) — mostly by
> covering 25 of the 27 `silent-suppress` findings — so "no shipped linter reaches
> this" is a statement about *default configurations*, not about what is expressible.

Re-run: see `paper/ARTIFACT.md`. Results are checked into `bench/`.

### How often is a finding a bug?

**Mostly, it is not — and that is the most useful thing this project measured.**

On a stratified random sample of **80** of the 649 findings (by rule × package,
fixed seed, reproducible), independently labelled twice:

| Verdict | Count | Share |
| --- | --- | --- |
| **Deliberate design contract** | 64 | **80%** |
| Genuine defect | 12 | 15% |
| False positive | 4 | 5% |

Every one of the 12 defects fell inside a **single, young package**; the other
seven mature packages contributed **0 defects out of 66 sampled findings**.

The conclusion is not flattering to this tool, and it is the point: **a syntactic
detector cannot distinguish an intentional fallback from a bug.** failroute
narrows where to look; a person still has to argue the failure chain. Treat its
output as a review queue, not a defect list.

The internal `tests/corpus/` fixtures (68 samples, precision = recall = 1.0 in CI)
are a **regression gate on the rules themselves** — construct validity. They say
nothing about how the tool behaves on code it has never seen; the table above does.

Full study, including the recall measurement against upstream-merged fixes
(1 of 10 in-family fixes detected): `paper/DRAFT.md`.


### Throughput

Measured 2026-08-29 on the vLLM core tree (`vllm/vllm`, 2,032 files,
~758 kLOC) with the six-rule v0.6 engine: **~74 kLOC/s** serial (10.3 s,
388 findings), **~377 kLOC/s** with `--jobs 0` (2.0 s, 10 workers,
identical findings), and **~0.1 s** warm with `--cache`. The v0.6 serial
number is lower than v0.5.1's single-rule figure because findings now come
from six independent rules re-walking each handler; the parallel path is
the intended operating point for large trees. Re-run:
`time failroute <path> --repo --jobs 0 --quiet`.

## Development

```console
$ pip install -e ".[test]"
$ pytest
$ ruff check .
```

## How this project is built

`failroute` is developed with an **AI-assisted, human-audited workflow**:
LLM tooling proposes code and analyses, but nothing lands without passing
deterministic gates — a 118-test suite, a hand-labelled precision/recall
corpus, `mypy --strict`, and a self-scan of the repository with the tool
itself. Humans own every judgment call: rule semantics, corpus labels,
upstream triage, and all external communication. A worked example of that
triage discipline (including a case where we deliberately filed *nothing*)
is in [`docs/process.md`](docs/process.md).

## License

MIT — see [LICENSE](LICENSE).

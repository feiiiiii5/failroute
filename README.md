# failroute

Static detection of **failure-routing** anti-patterns in Python: the practice of
converting an underlying failure into a success-like outcome at the wrong layer.

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
$ failroute --json --repo .  | jq 'select(.mode=="silent-fallback")'
$ failroute --format sarif --output results.sarif --repo .   # code scanning
$ failroute --threshold 5    # exit 1 when more than 5 findings
```

Exit codes: `0` clean, `1` findings above threshold, `2` usage error.

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

## Validation on real codebases

`failroute` was developed against (and validated on) production AI/eval
repositories where the same anti-patterns caused real, fixed bugs:

| Repo | v0.1 | v0.2 | Notes |
| --- | --- | --- | --- |
| `microsoft/PyRIT` | 70 | **85** | +15: catch-all handlers with `debug`-only traces / stdout `print` + `return False` (CLI family) |
| `browser-use/browser-use` | 174 | **179** | +5: `except Exception` → `logger.debug(...)` → fallback (`return False`) |
| `confident-ai/deepeval` (metrics) | 20 | **14** | −6 precision: typed handlers with deliberate conditional re-raise are no longer reported as masked |

v0.2 changes vs v0.1:

* **New detector**: `name-shadowing` — rebinding the caught exception variable
  (Python deletes the binding at handler exit; later uses raise `NameError`).
* **Two-tier logging exemption** — catch-all handlers need a readable severity
  (`warning`+); typed handlers accept any level. A bare `print()` or
  `debug` line no longer hides a silent fallback.
* **Scope-aware scans** — `return None` inside a callback *defined in the
  handler* belongs to the callback, not to the handler's control flow.
* **Masked-exception is a catch-all contract** — typed handlers with
  conditional re-raise + early return are deliberate retry/skip logic.
* **Process exit terminates like raise** — `sys.exit(1)` after an assignment
  means the fallback value is never observable.
* **Ignore list** adds `StopIteration` and `CancelledError` (idiomatic
  control-flow absorption).
* **CLI**: deterministic finding order, `--version`.
* **Performance**: source lines split once per file instead of once per handler.

The `silent-fallback` hits on `deepeval`'s metric modules fall in the same
failure-routing family as the *verdict/score disagreement* defect fixed
upstream in `HallucinationMetric` — the class of bug `failroute` is built to
surface. See `tests/` for the pattern catalog.

## Development

```console
$ pip install -e ".[test]"
$ pytest
$ ruff check .
```
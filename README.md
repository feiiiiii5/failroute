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
| `masked-exception` | catch-all re-raises yet later falls through to a success-looking return |

Findings are emitted as `file:line: mode: message`, or as JSON for CI.

## Usage

```console
$ failroute path/to/file.py
$ failroute path/to/dir      # recursive
$ failroute --repo .         # skip .git/.venv/build/...
$ failroute --json --repo .  | jq 'select(.mode=="silent-fallback")'
$ failroute --threshold 5    # exit 1 when more than 5 findings
```

Exit codes: `0` clean, `1` findings above threshold, `2` usage error.

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

| Repo | Findings | Notes |
| --- | --- | --- |
| `microsoft/PyRIT` | 70 | ~55 silent-fallbacks, 17 no-actions |
| `browser-use/browser-use` | 174 | includes masked-exception branch outcomes |
| `confident-ai/deepeval` (metrics) | 20 | scoring failure silently converted to `False` |

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
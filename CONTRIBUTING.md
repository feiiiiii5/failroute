# Contributing to failroute

Thanks for considering a contribution. This project is deliberately small;
the bar is "correctness + tests", not volume.

## Setup

```console
python3 -m venv .venv
.venv/bin/pip install -e ".[test]" ruff
```

> **macOS troubleshooting**: if `import failroute` fails with
> `ModuleNotFoundError` despite an editable install, check
> `ls -lO .venv/lib/*/site-packages/*.pth`. Files carrying the `hidden`
> flag are silently skipped by CPython's `.pth` processing. Fix with
> `chflags -R nohidden .venv`.

## Running the gates

Every PR must pass all four:

```console
.venv/bin/python -m pytest -q                                # unit + benchmark gate
.venv/bin/ruff check .                                       # lint
.venv/bin/python -m failroute --repo . --exclude tests/corpus   # self-scan is expected clean
.venv/bin/python tools/benchmark.py                          # corpus precision/recall
```

## Changing detection semantics

1. Add or adjust fixtures in `tests/corpus/` (keep line numbers aligned).
2. Update `tests/corpus/manifest.json` — ground truth is written from the
   *semantics* of the fixture, not from what the tool currently emits. If the
   tool disagrees with your label, decide explicitly which one is wrong and
   say so in the PR description.
3. Known, deliberately-accepted gaps are recorded in the manifest's
   `labelled_true_negatives` notes (e.g. handlers that log are treated as
   informational even when they also fall back).

## Adding new repositories to the comparison

Run `python tools/compare_ruff.py <repo>` and commit the updated `bench/`
artifacts. Do not hand-edit benchmark numbers.

## Code of conduct

Be concrete in issues: a finding report without a failure-consequence chain
("what wrong outcome does this produce in production?") will be closed.

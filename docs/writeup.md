# Failure-Routing: A Taxonomy of Silent Correctness Bugs in LLM/Eval Systems

*Technical write-up for `failroute`. Measured numbers are maintained in one
place -- the "Benchmarks & validation" section of the README and the artifacts
in `bench/` -- so this document does not carry its own copy that can drift.
Every figure is reproducible from this checkout.*

## 1. Where the taxonomy comes from

Across merged fixes in 20+ open-source AI/ML projects (UK AISI inspect_ai,
NVIDIA garak, Microsoft PyRIT, pydantic-ai, Trail of Bits fickling, uqlm,
llama_index, and others), one defect family kept recurring: **a failure being
converted into a success-looking outcome at the wrong layer**. Three concrete
shapes:

1. **`no-action`** — `except ...: pass`. The caller can never learn the
   operation failed.
2. **`silent-fallback`** — the handler returns/assigns a constant
   (`0.0`, `None`, `[]`, `False`) without re-raising. An LLM-judge outage
   becomes a legitimate-looking `0.0` score; a network error becomes "no
   results".
3. **`masked-exception`** — a catch-all that conditionally re-raises but also
   falls back to a constant: the outcome depends on which branch ran.

The danger is not the crash that didn't happen — it is the **evaluation
conclusion that was computed from a failure while looking like a result**.
In red-teaming and eval frameworks this produces false-clean reports and
flipped vulnerability verdicts, with nothing in the logs to explain them.

## 2. Why existing linters don't see it

Syntactic rules reason about the *shape of the handler*, not about what the
handler *returns*. ruff `S110` (try-except-pass) and `S112`
(try-except-continue), Bandit `B110`/`B112`, flake8-bugbear `B001`, and
pylint's bare/broad-except warnings all stop at the handler boundary.
`except Exception: return 0.0` is invisible to every one of them — and it is
the shape that corrupts scores.

Measured on the source packages of 8 real AI/eval repositories (garak,
inspect_ai, pydantic-ai, uqlm, trl, smolagents, deepteam, fickling), failroute
reports an order of magnitude more findings than ruff's exception rules, and
the gap is not noise: the overwhelming majority of failroute-only findings are
`silent-fallback`, `silent-suppress`, `implicit-fallback` and
`masked-exception` — the classes syntactic rules cannot express by
construction.

The current dated totals and per-mode breakdown live in
[`README.md` — "What syntactic linters miss"](../README.md#what-syntactic-linters-miss);
raw per-repository results are checked into `bench/ruff-comparison.json` with
the exact scanned paths, and re-run with `python tools/compare_ruff.py <repo>`.
Keeping the numbers in one place is deliberate: an earlier revision of this
document carried its own copy of the table and silently went stale.

## 3. Precision discipline

`tests/corpus/` holds the hand-labelled corpus; ground truth was written from
fixture *semantics*, independently of tool output. The corpus is versioned in
`tests/corpus/manifest.json`, its current size and score are printed by
`python tools/benchmark.py`, and **precision = recall = 1.0** is enforced by
CI on every push. Known,
documented gaps are recorded in the manifest rather than hidden (e.g.
handlers that log are treated as informational even when they also fall
back — a deliberate precision-over-recall choice for triage workflows).

## 4. Honest triage is part of the method

Scanning Microsoft PyRIT produced 65 semantic findings. Manual review of a
12-finding sample found **all of them intentional contracts**: malformed-cursor
decoders returning `None` to restart pagination, capability probes,
existence checks. Only one finding touched user-visible behaviour, and it was
cosmetic (a skipped log line). Conclusion recorded as *not worth filing*.

Conversely, scanning confident-ai/deepteam surfaced a systemic pattern across
~40 metric classes: bare-except initialization that silently degrades the
judge's system prompt, and an `is_successful` whose `try: self.score == 1`
comparison can never raise — so a failed evaluation may be reported with a
stale success value. Those findings carry an explicit failure-consequence
chain and are queued upstream through the project's normal issue process.

The asymmetry is the point: **a finding without a production consequence
chain is benchmark material, not an issue**. Volume is cheap; calibrated
findings are the asset.

## 5. Limitations

- AST-level only: no interprocedural tracking of where a fallback value flows.
- "Logging handler = informational" is a deliberate false-negative class.
- Non-empty container returns are not treated as fallback shapes.
- Precision on real repositories depends on human triage (see §4); the tool
  reports, humans decide.

## 6. Reproduce

```console
pip install -e ".[test]"
pytest                          # unit + corpus benchmark gate
python tools/benchmark.py       # precision/recall on labelled corpus
python tools/compare_ruff.py .. # detection-gap measurement
failroute --repo <any-python-repo> --exclude tests/corpus
```

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

## 2. Comparison with existing linters

Some syntactic rules identify handlers that failroute also reports. Broad-except
warnings can flag a handler containing a fallback return even if they do not
explain the return's consequence. The paper therefore measures co-location
with four tools, rather than interpreting a ruff-only comparison as a detection
advantage. The extra candidates are mostly contracts under the recorded LLM
labels; a larger candidate list is not evidence of better bug detection.

The current comparison and its limitations are in
[the README](../README.md#what-syntactic-linters-miss) and the
[current paper](../paper/arxiv/main.pdf). Use
[ARTIFACT.md](../paper/ARTIFACT.md) to reproduce the versioned comparisons.

## 3. Precision discipline

`tests/corpus/` holds explicit fixture expectations used as a regression gate.
They do not establish independent annotation or real-world accuracy. The corpus is versioned in
`tests/corpus/manifest.json`, its current size and score are printed by
`python tools/benchmark.py`, and **precision = recall = 1.0** is enforced by
CI on every push. Known,
documented gaps are recorded in the manifest rather than hidden (e.g.
handlers that log are treated as informational even when they also fall
back — a deliberate precision-over-recall choice for triage workflows).

## 4. Honest triage is part of the method

Scanning Microsoft PyRIT produced dozens of semantic findings. Manual review of a
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

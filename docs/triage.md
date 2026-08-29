# Triage: the human half of the detector

failroute finds *shapes*. A finding becomes a defect only when a human can
articulate the **failure consequence chain** — what the caller observes, and
what goes wrong downstream because of it. The tool is responsible for
recall at the shape level; this document is the process that keeps the
precision claim honest.

## The three-outcome verdict

For every finding, write down one of:

1. **Defect** — the failure consequence chain is articulable:
   *what* fails → *where* the fallback surfaces → *what* downstream
   consumer cannot distinguish it. Fix the code (route the failure).
2. **Documented fallback** — the constant is the module's deliberate
   contract, stated in a docstring/README. Mark the handler with
   `# failroute: ignore` and link the justification.
3. **False positive** — the shape reasoning failed (e.g. the "constant"
   is only reachable after a real error was recorded). Fix the *rule*
   or add a corpus negative so the same miss cannot recur.

Case studies of all three outcomes live in `scan-ledger.md`.

## Corpus feedback loop

Every triage verdict feeds back into `tests/corpus/`:

* Defects become positive fixtures (the shape that caught a real bug).
* False positives become labelled negatives with a note explaining why
  the shape is legitimate.

The `manifest.json` labels are written **from the semantics of the
fixture, not from tool output**, and `tests/test_benchmark.py` fails the
build if precision or recall drops below 1.0. This is what makes "P=R=1.0
on hand-labelled data" a claim about the tool rather than a tautology.

## Rule-change discipline

A detector change (new rule, widened shape, new gate) ships only when:

* the corpus gate still holds at 1.0 after the change,
* new positives *and* new negatives for the change are in the same commit,
* the CHANGELOG entry names the behaviour change explicitly.

## Known, accepted limitations

* Handlers that log the failure at a readable severity (catch-all:
  `warning`+; typed: any level) are treated as informational and never
  reported — the failure has a trace, even if the value still lies.
* Constant fallback shapes are a closed vocabulary (`None`, `0`, `[]`,
  `''`, …). Project-specific sentinels belong in
  `[tool.failroute] fallback_values`; the tool refuses to guess
  semantics it cannot see (`-1`, enum members, `float("nan")`).
* Single-file AST scope: no dataflow (see `ROADMAP.md` non-goals).

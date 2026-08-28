# How failroute is built: an AI-assisted, human-audited workflow

This document describes the development process behind `failroute` — because
the process is part of the claim: *what does it mean to use AI tooling well
on a correctness-critical tool?*

## The short answer

AI proposes; deterministic gates verify; humans own judgment.

Concretely, every change to this repository passes four gates before it is
merged — locally and again in CI:

1. **Test suite** (80+ tests, 3 OS x 5 Python versions in CI).
2. **Labelled corpus benchmark** — 30 hand-labelled samples where
   the ground truth was written from the *semantics* of each fixture,
   independently of tool output. Precision and recall must stay at 1.0.
3. **Static checks** — `mypy --strict` and `ruff`.
4. **Self-scan** — the repository is scanned with `failroute` itself, and the
   expected result is zero findings. The gate has caught real regressions
   introduced by new code (including its own author's), which were then
   either fixed or explicitly registered with `# failroute: ignore` markers
   documenting why the pattern is accepted.

## Where AI helps, and where it deliberately does not

**AI-assisted**: drafting detector logic, generating test skeletons, refactors,
documentation, and broad codebase reading during triage.

**Human-owned**:

- **Rule semantics.** What counts as a finding is a judgment about production
  consequences, not pattern popularity. Known limitations are recorded in the
  corpus manifest instead of being hidden.
- **Corpus labels.** Ground truth is never derived from tool output; when the
  tool disagrees with a label, the disagreement is resolved explicitly and the
  resolution is documented.
- **Upstream triage.** Every externally reported finding carries a written
  failure-consequence chain ("what wrong outcome does this produce in
  production?") and a minimal reproduction verified against the upstream
  release.

## A worked example of triage discipline

Scanning a major, well-maintained red-teaming framework produced 65
semantic-mode findings. Manual review of a 12-finding sample found **all
twelve were intentional contracts**: malformed-input decoders returning `None`
to restart pagination, capability probes, existence checks. The one finding
touching user-visible behaviour was cosmetic (a skipped log line).

Conclusion recorded: *not worth filing*. No issue was opened.

By contrast, scanning an evaluation framework surfaced the same bare-except
pattern replicated across ~40 metric classes, with a concrete consequence
chain (a failed judge silently degrading every subsequent score). That one
was filed — as a single consolidated issue, with reproduction steps, not as
forty separate reports.

The asymmetry is the point: volume is cheap; calibrated findings are the
asset. The same standard applies to this repository's own code — the
self-scan gate treats the author's code exactly like anyone else's.

## A worked example of the full loop: shipping the `silent-suppress` detector

v0.5.0 followed the same discipline end to end, and is worth recording as a
concrete instance of the process — including what the tooling got *wrong*
before it shipped:

1. **Human identifies the gap.** `with contextlib.suppress(...)` is
   semantically identical to `try` / `except` + discard, but the analyzer
   only walked `ExceptHandler` nodes. Research confirmed no shipped linter
   detects it — and ruff's SIM105 actively *recommends* rewriting
   `try-except-pass` into this form, migrating the silence out of every
   existing detector's view.
2. **Corpus first, red by design.** Eight suppress fixtures were hand-labelled
   (positives and negatives: aliased imports, a same-name import from another
   module, marker opt-outs, non-suppress context managers) and added to the
   manifest *before any implementation existed*. Running the benchmark then
   reported exactly the five expected false negatives — recall 0.667, exit 1.
   The failing gate is the point: it proves the labels were independent of
   the tool, not reverse-engineered from its output.
3. **Implement, then the gate turns green.** The detector resolves imports
   (direct import, attribute access, aliases), honors the opt-out markers,
   and the benchmark returned to precision 1.0 / recall 1.0 with zero false
   positives.
4. **The corpus then caught a design mistake pre-release.** An early draft
   flagged `contextlib.suppress(asyncio.CancelledError)` — but absorbing
   cancellation is idiomatic control flow, and the handler-level rules
   already exempt `except asyncio.CancelledError`. The inconsistency (one
   semantic decision, two syntaxes, two answers) was a bug. v0.5.1 unified
   the ignore list across both syntaxes, with labelled fixtures for the
   exemption *and* for the mixed case (`suppress(CancelledError, OSError)`
   still flags, because one real error means real failures are silenced).
5. **Release.** Tag push → OIDC publish → GitHub Release generated from the
   CHANGELOG by `tools/release_notes.py`. Every gate re-runs in CI on 15
   Python/OS combinations.

The loop is the methodology: a semantic claim (this idiom routes failures to
silence), reduced to labelled data, enforced by a gate that must first fail
and then pass — with the corpus independent enough to catch the tool's own
design errors on the way.

## Verifiability

Every quantitative claim in the README is reproducible from a fresh checkout:

```console
pytest                                        # suite + corpus gate
python tools/benchmark.py                     # precision / recall
python tools/compare_ruff.py <repos...>       # detection-gap measurement
time failroute --repo <checkout> --quiet      # throughput
```

If a number here cannot be regenerated by one of these commands, it does not
belong in this README.

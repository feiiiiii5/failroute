## What does this change?

<!-- One or two sentences. If it fixes an issue, link it: `Fixes #NNN`. -->

## Before you submit — the four gates

Every change to this repository is verified by deterministic gates, locally
and in CI. Please confirm what you have run:

- [ ] `pytest` — full suite passes
- [ ] `python tools/benchmark.py` — hand-labelled corpus still at
      precision = recall = 1.0 (**if you changed a detector's behaviour, this
      is the gate that matters most**)
- [ ] `ruff check .` and `mypy --strict src/failroute` — clean
- [ ] `failroute --repo . --exclude tests/corpus` — self-scan still reports
      zero findings (or every new finding is registered with a
      `# failroute: ignore` marker explaining why the pattern is accepted)

## Rule changes

If this PR adds or changes what counts as a finding:

- [ ] Corpus labels were written **from the semantics of the fixture, before
      the detector change** — labels are never derived from tool output
- [ ] The benchmark was red (missing labels) before it was green
- [ ] `README.md` and `docs/process.md` describe the new behaviour honestly,
      including what it does *not* flag

## Notes

Findings produced by this tool are meant to be triaged by a human with a
written failure-consequence chain before they are reported upstream. See
[`docs/process.md`](../docs/process.md).

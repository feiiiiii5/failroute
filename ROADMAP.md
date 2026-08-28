# Roadmap

Where failroute goes next — and, as importantly, where it deliberately does not.

## Now (adoption & evidence)

- **Dogfooding is visible**: this repository scans itself in CI and uploads
  SARIF to GitHub code scanning (`self-scan` workflow). Expected result: zero
  alerts. A non-zero result is a bug in either the code or the rule.
- **Upstream evidence**: findings reported to evaluation/red-teaming projects
  are tracked in `scan-ledger.md` with explicit states; one polite follow-up
  per submission, no pressure, no duplication.
- **Distribution channels already in place**: PyPI install, composite GitHub
  Action, pre-commit hook manifest, `[tool.failroute]` project config.

## Candidates (each requires evidence before it ships)

Any candidate must first earn corpus entries: hand-labelled fixtures whose
ground truth is written independently of tool output, with the precision /
recall gate still at 1.0 afterwards.

| Candidate | What it would add | Gate to attempt it |
|---|---|---|
| Baseline / diff mode | Report only findings introduced since a baseline file — the CI-adoption unlock for existing large codebases | 3 real repositories where maintainers asked for it |
| Inter-procedural fallback-flow tracking | Follow a fallback value to where it is consumed (score aggregation, reports) | A labelled corpus slice of >= 10 flow-through cases |
| Additional modes (e.g. logged-but-swallowed) | The known limitation where logging handlers are treated as informational | Corpus evidence that reviewers want it flagged |

## Shipped from this list (with the evidence that unlocked it)

- **`silent-suppress` (v0.5.0)** — shipped without waiting for a maintainer
  request because the gate it needed was corpus evidence, and corpus is ours
  to produce: v2 added hand-labelled suppress fixtures, and the 8-repository
  benchmark found 77 `contextlib.suppress` blocks invisible to every shipped
  syntactic linter (ruff's SIM105 actively recommends migrating into this
  form). Same failure-routing family, same precision gate held at 1.0.

## Considered and declined

- **`return` inside `finally`** — a real failure-routing form, but already
  covered by syntactic rules (ruff/bugbear `B012`, `SIM107`). Adding it would
  duplicate shipped linters and dilute the differentiator: failroute targets
  the class syntactic rules cannot express.

## Non-goals

- No rule additions without hand-labelled corpus validation.
- No download-count or adoption-count targets; the metric that matters is
  calibrated findings, not volume.
- No upstream issue volume: one consolidated, evidence-backed report per
  defect family is the ceiling, not the floor.
- No dependency growth beyond the single conditional `tomli` for py<3.11.

## Decision rule

Every feature request against this repository is answered with the same
question used for its findings: *what wrong outcome does this prevent, and
can we label the evidence for it?*

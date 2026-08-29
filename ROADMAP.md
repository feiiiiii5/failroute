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

- **Inter-procedural fallback tracking / dataflow** (incl. the indirect
  shape `except Exception: return default_score()`, where the constant hides
  behind one function call) — judging it requires knowing what
  `default_score` returns, i.e. whole-program analysis. As a single-file AST
  layer this is architecturally out of reach, and a partial dataflow engine
  would be neither sound nor cheap. The capability exists in adjacent
  infrastructure (GitHub CodeQL's queries) at distribution scale failroute
  cannot match; the durable lane is the high-precision hint layer plus human
  triage (`docs/triage.md`). Revisit only as an upstream-contribution
 载体, never as in-tree scope.
- **`return` inside `finally`** — a real failure-routing form, but already
  covered by syntactic rules (ruff/bugbear `B012`, `SIM107`). Adding it would
  duplicate shipped linters and dilute the differentiator: failroute targets
  the class syntactic rules cannot express.

## Non-goals (detection scope)

The engine is a single-file AST layer with human curation. It deliberately
does **not** try to be a dataflow engine. Out of detection scope, with the
reason:

- **Indirect fallback through a call** — `except Exception: return
  default_score()` wraps the constant in one function call. Judging it
  requires knowing what `default_score` returns (cross-function), and
  guessing produces either false positives or a half-dataflow engine.
- **Custom `__exit__` swallowers** — any context manager whose `__exit__`
  returns a truthy value is semantically `contextlib.suppress`. Recognising
  arbitrary classes needs whole-program type resolution; the tool only
  knows the stdlib form by name.
- **Call-form and attribute sentinels** — `float("nan")`, `Status.UNKNOWN`.
  These are matched only if a project spells them as constants in
  `[tool.failroute] fallback_values`; the tool refuses to guess semantics
  it cannot see.
- **Cross-function / cross-module consumption analysis** — "does this
  fallback value eventually get consumed as a success value" is a
  call-graph question (CodeQL-shaped). failroute's lane is the
  high-precision hint layer plus human triage (`docs/triage.md`); the
  remaining ~20-30% of shapes belong in the dataflow tier, documented here
  rather than feigned.

## Non-goals (project)

- No rule additions without hand-labelled corpus validation.
- No download-count or adoption-count targets; the metric that matters is
  calibrated findings, not volume.
- No upstream issue volume: one consolidated, evidence-backed report per
  defect family is the ceiling, not the floor.
- No dependency growth beyond the single conditional `tomli` for py<3.11.

## High-risk track: upstream the detection idea

The distribution ceiling for a solo-maintained PyPI linter is structural:
ruff and CodeQL ship for free by default. The higher-value form of this
project may be the *detection idea* landing upstream:

- **ruff** — a `silent-fallback` rule would sit beside S110/S112, but
  ruff's bar for new heuristic (non-syntactic) rules is very high, and
  **astral-sh repositories enforce an AI-assistance policy that
  auto-closes AI-assisted PRs** (observed on prior attempts): an ruff rule
  contribution must be written and argued entirely by a human, without AI
  assistance. High rejection risk; plan accordingly.
- **tryceratops** — friendlier to new `TRY` rules, smaller audience.
- **CodeQL query pack** — the dataflow tier failroute deliberately does
  not build exists there for free; a contributed query would be the
  natural home for the cross-function half of this problem.

Track separately from the standalone tool; a merge upstream outranks any
number of downloads.

## Decision rule

Every feature request against this repository is answered with the same
question used for its findings: *what wrong outcome does this prevent, and
can we label the evidence for it?*

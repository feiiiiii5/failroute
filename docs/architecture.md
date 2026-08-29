# failroute architecture

failroute is a five-layer pipeline: **CLI/config → dispatcher → rules → IR →
outputs**. Each layer only knows the one below it, so adding a rule never
touches the engine, and outputs can never disagree with what rules claim
about themselves.

```
┌──────────────────────────────────────────────────────────────┐
│ cli.py        argparse + [tool.failroute] + exit codes        │
│ config.py     exclude / threshold / ignore /                  │
│               fallback_values / rules.<id>.enabled+severity   │
├──────────────────────────────────────────────────────────────┤
│ analyzer.py   the dispatcher (the only traversal):            │
│               • walks the AST once                            │
│               • gates: opt-out markers, ignore-list           │
│               • hands each ExceptHandler to handler rules     │
│                 in registry order, then file rules            │
│               • dedups handlers (one visit each), line-sorts  │
│               scan_repo: serial | --jobs N | --cache          │
├──────────────────────────────────────────────────────────────┤
│ rules/        one module per anti-pattern, each carrying a    │
│               RuleSpec (id, severity, descriptions):          │
│                 no-action · name-shadowing ·                  │
│                 masked-exception · silent-fallback ·          │
│                 implicit-fallback · silent-suppress           │
│               rules/_shared.py holds the predicates every     │
│               rule shares (constant shapes, catch-all test,   │
│               scope walk, logger heuristic, markers)          │
├──────────────────────────────────────────────────────────────┤
│ ir.py         Finding + FailureMode + RuleSpec + ScanContext  │
│               single source of truth for what a finding is    │
│               and what every rule claims about itself         │
├──────────────────────────────────────────────────────────────┤
│ sarif.py      SARIF 2.1.0 — rule metadata GENERATED from the  │
│               registry (a rule cannot ship findings whose     │
│               metadata the output does not know)              │
│               json / text renderers in cli.py                 │
└──────────────────────────────────────────────────────────────┘
```

## Why the dispatcher owns the gates

Opt-out markers (`# pragma: no cover`, `# failroute: ignore`), the
handler-level ignore list (`KeyboardInterrupt`, `StopIteration`,
`CancelledError`, …), handler dedup, and result ordering live in
`analyzer.scan_tree`, not in the rules. A rule author cannot forget them,
and a rule cannot apply them differently from its neighbours.

## Adding a rule

1. Create `src/failroute/rules/your_rule.py`:
   a `RuleSpec` + a `Rule` subclass overriding `check_handler` (per
   `except` handler) and/or `check_file` (whole module).
2. Append one line to `HANDLER_RULES` or `FILE_RULES` in
   `src/failroute/rules/__init__.py`.

The dispatcher, SARIF output, `[tool.failroute.rules.<id>]` config tables,
`--ignore`, and the text/JSON renderers pick the rule up automatically.
Registry order is emission order for same-line findings.

## Evidence gates

Every detector must first earn corpus entries
(`tests/corpus/` + `manifest.json`), hand-labelled independently of tool
output, with the precision/recall gate still at 1.0
(`tests/test_benchmark.py`). v0.7 corpus: 36 positives + 31 labelled
negatives across six modes. See `docs/triage.md` for how labels are judged.

## Performance model

Per-file scanning is embarrassingly parallel, so `scan_repo` fans out by
file (`--jobs N`, `0` = one worker per core) and `--cache` keeps an
mtime+size-keyed result cache in the system temp dir (no in-repo
pollution). Both paths produce byte-identical findings to the serial scan —
`tests/test_boundaries.py` pins that equivalence. Measured on the vLLM core
tree (2,032 files / ~758 kLOC, M-series laptop): serial ≈ 10.3 s, parallel
≈ 2.0 s (≈ 377 kLOC/s), cache-warm ≈ 0.1 s.

## Design boundary (honest scope)

failroute is a single-file AST layer with human curation — deliberately
**not** a dataflow engine. It cannot see through function calls (a constant
wrapped in `return default_score()`), custom `__exit__` swallowers, or
cross-module consumption of fallback values. These are documented
non-goals in `ROADMAP.md`, not gaps we pretend do not exist.

# Cross-linter comparison — self-scan + corpus scope (NOT the 8-repo scope)

Generated: 2026-08-30T16:00:10Z · Python 3.11.15 · macOS-27.0-arm64-arm-64bit

> 🔴 Scope: failroute's own source (`src/failroute`) + labelled corpus (`tests/corpus`).
> The corpus is intentionally invalid Python; tools that reject unparseable files will under-report there.
> This table does not replace `bench/ruff-comparison.md` (8-repo scope, clones removed 2026-08-30).

| tool | version | findings | per-code | failroute findings matched (±1 line) |
|---|---|---|---|---|
| failroute | (this repo, see bench/paper-baseline.json) | 36 | implicit-fallback:7, masked-exception:3, name-shadowing:2, no-action:5, silent-fallback:9, silent-suppress:10 | 36 |
| ruff | ruff 0.16.0 | 7 | S110:4, S112:1, invalid-syntax:2 | 4 |
| bandit | bandit 1.9.4 | 5 | B110:4, B112:1 | 3 |
| pylint | pylint 4.0.8 | 3 | W0702:1, W0706:2 | 1 |
| flake8+bugbear | flake8 7.3.0 (flake8-bugbear: 25.11.29, mccabe: 0.7.0, pycodestyle: 2.14.0, pyflakes: | 2 | B001:1, E722:1 | 1 |
| semgrep | not installed | 0 | — | 0 |

## Full commands

**failroute** ((this repo, see bench/paper-baseline.json)):
```
PYTHONPATH=src -m failroute --format json /Users/fei/Desktop/申请季/新项目-failroute/src/failroute
```
```
PYTHONPATH=src -m failroute --format json /Users/fei/Desktop/申请季/新项目-failroute/tests/corpus
```

**ruff** (ruff 0.16.0):
```
ruff check --select S110,S112 --output-format json /Users/fei/Desktop/申请季/新项目-failroute/src/failroute
```
```
ruff check --select S110,S112 --output-format json /Users/fei/Desktop/申请季/新项目-failroute/tests/corpus
```

**bandit** (bandit 1.9.4):
```
/Users/fei/Desktop/申请季/新项目-failroute/.venv/bin/python -m bandit -r /Users/fei/Desktop/申请季/新项目-failroute/src/failroute -f json -q -t B110,B112
```
```
/Users/fei/Desktop/申请季/新项目-failroute/.venv/bin/python -m bandit -r /Users/fei/Desktop/申请季/新项目-failroute/tests/corpus -f json -q -t B110,B112
```

**pylint** (pylint 4.0.8):
```
python -m pylint --disable=all --enable=W0702,W0703,W0705,W0706 --output-format=json --score=no <src/failroute/*.py>
```
```
python -m pylint --disable=all --enable=W0702,W0703,W0705,W0706 --output-format=json --score=no <tests/corpus/*.py>
```

**flake8+bugbear** (flake8 7.3.0 (flake8-bugbear: 25.11.29, mccabe: 0.7.0, pycodestyle: 2.14.0, pyflakes:):
```
-m flake8 --select=E722,B001,B017 /Users/fei/Desktop/申请季/新项目-failroute/src/failroute
```
```
-m flake8 --select=E722,B001,B017 /Users/fei/Desktop/申请季/新项目-failroute/tests/corpus
```

**semgrep** (not installed):

## Reproducing the full 8-repo comparison (if clones are restored later)

1. Restore the eight checkouts at the exact paths recorded in `bench/ruff-comparison.md` / `bench/paper-baseline.json` (git clone at the commit that produced the 2026-08-29 numbers is NOT pinned — re-run against the same paths and re-freeze).
2. For each repo: `PYTHONPATH=src python -m failroute --export-findings <out.jsonl> --repo-name <name> <scanned_path>` and `ruff check --select S110,S112 --output-format json <scanned_path>` (plus the bandit/pylint/flake8 commands above, one directory per repo).
3. Compute overlap by file+line (±1 line tolerance) and regenerate the table; record new totals in a NEW file, never overwrite `bench/ruff-comparison.md` (frozen baseline).

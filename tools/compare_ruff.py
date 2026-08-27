#!/usr/bin/env python3
"""Compare failroute against ruff's syntactic exception-handling rules (S110/S112).

Hypothesis: ruff S110 (try-except-pass) and S112 (try-except-continue) only see
*syntactic* swallow patterns.  The failure-routing family that corrupts eval
results -- a handler that converts a failure into a success-looking constant
(``return 0.0`` after a judge outage) -- is invisible to them.

Usage:
    python tools/compare_ruff.py REPO [REPO ...] [--json]

Writes bench/ruff-comparison.{md,json} with per-repo counts and the set of
failroute-only findings (the semantic gap).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from failroute.analyzer import scan_repo  # noqa: E402


def ruff_findings(repo: Path) -> list[tuple[str, int, str]]:
    exe = shutil.which("ruff") or str(REPO_ROOT / ".venv" / "bin" / "ruff")
    proc = subprocess.run(
        [exe, "check", "--select", "S110,S112", "--output-format", "json", "--no-cache", str(repo)],
        capture_output=True,
        text=True,
    )
    # ruff exits 1 when findings exist; 2 = error
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"ruff failed on {repo}: {proc.stderr[:400]}")
    if not proc.stdout.strip():
        return []
    out = []
    for item in json.loads(proc.stdout):
        rel = str(Path(item["filename"]).relative_to(repo))
        out.append((rel, item["location"]["row"], item["code"]))
    return out


def compare(repo: Path) -> dict:
    fr = scan_repo(repo)
    rf = ruff_findings(repo)

    def rel(p: str) -> str:
        try:
            return str(Path(p).resolve().relative_to(repo))
        except ValueError:
            return p

    fr_no_action = {(rel(f.file), f.lineno) for f in fr if f.mode.value == "no-action"}
    fr_semantic = {(rel(f.file), f.lineno, f.mode.value) for f in fr if f.mode.value != "no-action"}
    rf_set = {(f, line) for f, line, _ in rf}

    overlap = fr_no_action & rf_set
    return {
        "repo": repo.name,
        "failroute_total": len(fr),
        "failroute_no_action": len(fr_no_action),
        "failroute_semantic": len(fr_semantic),
        "ruff_S110_S112": len(rf),
        "overlap_no_action": len(overlap),
        "failroute_only": len(fr) - len(overlap),
        "semantic_breakdown": {
            mode: sum(1 for f in fr if f.mode.value == mode)
            for mode in ("silent-fallback", "masked-exception")
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repos", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    rows = []
    for repo in args.repos:
        repo = repo.resolve()
        if not repo.is_dir():
            print(f"skip {repo}: not a directory", file=sys.stderr)
            continue
        print(f"scanning {repo.name} ...", file=sys.stderr)
        rows.append(compare(repo))

    totals = {k: sum(r[k] for r in rows) for k in (
        "failroute_total", "failroute_no_action", "failroute_semantic",
        "ruff_S110_S112", "overlap_no_action", "failroute_only",
    )}

    md = []
    md.append("# failroute vs ruff S110/S112 -- real AI/eval repositories")
    md.append("")
    md.append(f"Run: {_dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    md.append("")
    md.append(
        "| Repo | failroute total | no-action | semantic (fallback+masked) "
        "| ruff S110/S112 | overlap | failroute-only |"
    )
    md.append("|---|---|---|---|---|---|---|")
    for r in rows:
        md.append(
            f"| {r['repo']} | {r['failroute_total']} | {r['failroute_no_action']} "
            f"| {r['failroute_semantic']} | {r['ruff_S110_S112']} | {r['overlap_no_action']} "
            f"| {r['failroute_only']} |"
        )
    md.append(
        f"| **total** | {totals['failroute_total']} | {totals['failroute_no_action']} "
        f"| {totals['failroute_semantic']} | {totals['ruff_S110_S112']} "
        f"| {totals['overlap_no_action']} | {totals['failroute_only']} |"
    )
    md.append("")
    md.append(
        "`semantic` = silent-fallback + masked-exception: the failure-to-success "
        "conversion class that ruff S110/S112 cannot express by construction."
    )
    md.append("")

    bench = REPO_ROOT / "bench"
    bench.mkdir(exist_ok=True)
    (bench / "ruff-comparison.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    if args.json:
        payload = {"run_at": _dt.datetime.now(_dt.timezone.utc).isoformat(), "repos": rows, "totals": totals}
        (bench / "ruff-comparison.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

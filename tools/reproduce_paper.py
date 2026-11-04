#!/usr/bin/env python3
"""Current-audit reproduction of the manuscript's executable measurements.

Every output goes to a NEW directory given by --out-dir; committed files under
bench/ and paper/ are only read, then compared with the recomputation. The
historical v0.8.0 scan runs from a disposable git worktree inside --out-dir.

Steps (each prints PASS or FAIL, and the script exits non-zero on any FAIL):

  corpus       tools/fetch_corpus.py --verify: 8 trees and archive SHA-256 vs the lock
  scan-v080    v0.8.0 detector from a worktree at tag v0.8.0  == bench/rescan-f2 (621);
               exported without context windows, as the frozen export was
  scan-current current detector, with context windows       == bench/rescan-v2 (476)
  coverage     four selected lint baselines on both frozen frames; per-finding rows
               == bench/corpus-coverage-per-finding-{621,v2}.jsonl

Comparison scope: scans and coverage rows are compared as whole JSON rows (every
field, order-independent); each step also reports whether the files are
byte-identical. The delta, E722 and probe outputs are compared as JSON with only
their timestamp (and, for the probe matrix, interpreter path) ignored.
  delta        tools/rq5_refactor_delta.py on the fresh exports == bench/rq5-refactor-delta.json
  e722         tools/e722_baseline.py                       == bench/e722-baseline.json
  probes       tools/lint_mapping_probe.py --check-parity   == bench/lint-rule-mapping.json
  refix        tools/refix_replay.py: the 36 mapping tests fail 21 on the pre-fix predicate
  semgrep      (only with --with-semgrep) tools/semgrep_diagnostic.py; reported as
               PARTIAL, not PASS, when Semgrep records analysis errors

Usage:
    python tools/fetch_corpus.py                  # once; leaves the lock untouched if it matches
    python tools/reproduce_paper.py --out-dir /tmp/failroute-audit [--with-semgrep]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
RESULTS: list[tuple[str, str, str]] = []


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["FAILROUTE_PY"] = PY
    env["PATH"] = str(Path(PY).parent) + os.pathsep + env.get("PATH", "")
    return subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, **kw)


def record(step: str, ok: bool | None, detail: str) -> None:
    status = "PASS" if ok else ("PARTIAL" if ok is None else "FAIL")
    RESULTS.append((step, status, detail))
    print(f"[{status:7}] {step:12} {detail}", flush=True)


def rows_of(paths: list[Path]) -> list[str]:
    """Every row of every file, as canonical JSON, order-independent."""
    out = []
    for f in paths:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(f"{f.name}\t" + json.dumps(json.loads(line), sort_keys=True))
    return sorted(out)


def compare_files(fresh: list[Path], frozen: list[Path]) -> tuple[bool, bool, int]:
    """(whole rows equal, files byte-identical, number of rows)."""
    names_ok = [p.name for p in fresh] == [p.name for p in frozen]
    a, b = rows_of(fresh), rows_of(frozen)
    same_bytes = names_ok and all(x.read_bytes() == y.read_bytes() for x, y in zip(fresh, frozen))
    return names_ok and a == b, same_bytes, len(a)


def jsonl_dir(directory: Path) -> list[Path]:
    return sorted(Path(p) for p in glob.glob(str(directory / "*.jsonl")))


def same_json(a: Path, b: Path, ignore: tuple[str, ...]) -> list[str]:
    x, y = json.loads(a.read_text(encoding="utf-8")), json.loads(b.read_text(encoding="utf-8"))
    return [k for k in sorted(set(x) | set(y)) if k not in ignore and x.get(k) != y.get(k)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--with-semgrep", action="store_true")
    args = ap.parse_args()
    out = args.out_dir.resolve()
    if out.exists():
        sys.exit(f"error: output directory already exists: {out}")
    out.mkdir(parents=True)

    p = run([PY, "tools/fetch_corpus.py", "--verify"])
    record("corpus", p.returncode == 0, (p.stdout.strip().splitlines() or ["no output"])[-1])
    if p.returncode != 0:
        print(p.stdout + p.stderr)
        return 1

    # bench/rescan-f2 was exported without context windows and bench/rescan-v2 with
    # them; each recomputation uses the same export options as its frozen file.
    p = run([PY, "tools/pinned_rescan.py", "--ref", "v0.8.0", "--out", str(out / "scan-v080"),
             "--worktree", str(out / "worktree-v080")], timeout=7200)
    rows_ok, bytes_ok, n = compare_files(jsonl_dir(out / "scan-v080"), jsonl_dir(ROOT / "bench/rescan-f2"))
    record("scan-v080", p.returncode == 0 and rows_ok,
           f"{n} findings vs bench/rescan-f2; whole rows equal={rows_ok}, bytes identical={bytes_ok}")

    p = run([PY, "tools/rescan_corpus.py", "--out", str(out / "scan-current"), "--with-context"], timeout=7200)
    rows_ok, bytes_ok, n = compare_files(jsonl_dir(out / "scan-current"), jsonl_dir(ROOT / "bench/rescan-v2"))
    record("scan-current", p.returncode == 0 and rows_ok,
           f"{n} findings vs bench/rescan-v2; whole rows equal={rows_ok}, bytes identical={bytes_ok}")

    p = run([PY, "tools/reproduce_warning_coverage.py", "--out-dir", str(out / "coverage")], timeout=7200)
    if p.returncode != 0:
        record("coverage", False, (p.stderr or p.stdout)[-300:])
    else:
        for name, frozen in (("baseline", "621"), ("refined", "v2")):
            fresh = out / "coverage" / f"{name}-per-finding.jsonl"
            stored = ROOT / f"bench/corpus-coverage-per-finding-{frozen}.jsonl"
            rows_ok = rows_of([fresh]) == rows_of([stored]) if fresh.name == stored.name else (
                sorted(r.split("\t", 1)[1] for r in rows_of([fresh]))
                == sorted(r.split("\t", 1)[1] for r in rows_of([stored])))
            bytes_ok = fresh.read_bytes() == stored.read_bytes()
            rows = [json.loads(x) for x in fresh.read_text(encoding="utf-8").splitlines() if x.strip()]
            covered = sum(not r["failroute_only"] for r in rows)
            record("coverage", rows_ok, f"{name}: {covered}/{len(rows)} co-located; whole rows "
                                        f"equal={rows_ok}, bytes identical={bytes_ok}")

    p = run([PY, "tools/rq5_refactor_delta.py", "--old", str(out / "coverage/baseline-per-finding.jsonl"),
             "--new", str(out / "coverage/refined-per-finding.jsonl"), "--out", str(out / "rq5.json")])
    diff = same_json(out / "rq5.json", ROOT / "bench/rq5-refactor-delta.json",
                     ("generated_at_utc", "generated_at_utc8", "inputs")) if p.returncode == 0 else ["run failed"]
    record("delta", not diff, f"differing keys: {diff or 'none'}")

    p = run([PY, "tools/e722_baseline.py", "--out", str(out / "e722.json")], timeout=3600)
    diff = same_json(out / "e722.json", ROOT / "bench/e722-baseline.json",
                     ("generated_at_utc", "generated_at_utc8")) if p.returncode == 0 else ["run failed"]
    record("e722", not diff, f"differing keys: {diff or 'none'}")

    p = run([PY, "tools/lint_mapping_probe.py", "--check-parity", "--out", str(out / "lint-map.json")],
            timeout=3600)
    diff = same_json(out / "lint-map.json", ROOT / "bench/lint-rule-mapping.json",
                     ("generated_at_utc8", "interpreter")) if p.returncode == 0 else ["run failed"]
    record("probes", not diff, f"68-probe matrix and parity; differing keys: {diff or 'none'}")

    p = run([PY, "tools/refix_replay.py"], timeout=1800)
    line = next((x for x in p.stdout.splitlines() if "failed" in x and "REFIX_REPLAY" in x), "no summary")
    record("refix", "21 failed, 15 passed" in line, line)

    if args.with_semgrep:
        p = run([PY, "tools/semgrep_diagnostic.py", "--out-dir", str(out / "semgrep"),
                 "--frame", f"baseline={out / 'coverage/baseline-per-finding.jsonl'}",
                 "--frame", f"refined={out / 'coverage/refined-per-finding.jsonl'}"], timeout=7200)
        if p.returncode != 0:
            record("semgrep", False, (p.stderr or p.stdout)[-300:])
        else:
            rep = json.loads((out / "semgrep/semgrep-diagnostic.json").read_text(encoding="utf-8"))
            frames = "; ".join(f"{n}: {f['five_tool_covered_observed']}/{f['findings']} "
                               f"(upper bound {f['five_tool_covered_upper_bound']})"
                               for n, f in rep["frames"].items())
            record("semgrep", True if rep["status"].startswith("complete") else None,
                   f"{rep['semgrep_version']}: {rep['status']}; {frames}")

    (out / "summary.json").write_text(json.dumps(
        [{"step": s, "status": st, "detail": d} for s, st, d in RESULTS], indent=2), encoding="utf-8")
    run(["git", "worktree", "remove", "--force", str(out / "worktree-v080")])
    failed = [s for s, st, _ in RESULTS if st == "FAIL"]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} steps without FAIL; summary in {out / 'summary.json'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

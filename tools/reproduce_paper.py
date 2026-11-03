#!/usr/bin/env python3
"""Current-audit reproduction of the manuscript's executable measurements.

Every output goes to a NEW directory given by --out-dir; committed files under
bench/ and paper/ are only read, then compared with the recomputation. The
historical v0.8.0 scan runs from a disposable git worktree inside --out-dir.

Steps (each prints PASS or FAIL, and the script exits non-zero on any FAIL):

  corpus       tools/fetch_corpus.py --verify: 8 trees and archive SHA-256 vs the lock
  scan-v080    v0.8.0 detector from a worktree at tag v0.8.0  == bench/rescan-f2 (621)
  scan-current current detector                                == bench/rescan-v2 (476)
  coverage     four selected lint baselines on both frozen frames; per-finding rows
               == bench/corpus-coverage-per-finding-{621,v2}.jsonl
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


def scan_keys(directory: Path) -> list[tuple]:
    keys = []
    for f in sorted(glob.glob(str(directory / "*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                path = (r.get("file") or "").replace("\\", "/")
                keys.append((Path(f).name, path, r.get("lineno"), r.get("rule") or r.get("rule_id")))
    return sorted(keys)


def coverage_keys(path: Path) -> list[tuple]:
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return sorted((r["repo"], r["file"].replace("\\", "/"), r["lineno"], r["rule"], r["failroute_only"],
                   tuple(sorted(r["baseline_tools_colocated"])), json.dumps(r.get("covered_by_static")))
                  for r in rows)


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

    p = run([PY, "tools/pinned_rescan.py", "--ref", "v0.8.0", "--out", str(out / "scan-v080"),
             "--worktree", str(out / "worktree-v080"), "--with-context"], timeout=7200)
    ok = p.returncode == 0 and scan_keys(out / "scan-v080") == scan_keys(ROOT / "bench/rescan-f2")
    record("scan-v080", ok, f"{len(scan_keys(out / 'scan-v080'))} findings vs bench/rescan-f2")

    p = run([PY, "tools/rescan_corpus.py", "--out", str(out / "scan-current"), "--with-context"], timeout=7200)
    ok = p.returncode == 0 and scan_keys(out / "scan-current") == scan_keys(ROOT / "bench/rescan-v2")
    record("scan-current", ok, f"{len(scan_keys(out / 'scan-current'))} findings vs bench/rescan-v2")

    p = run([PY, "tools/reproduce_warning_coverage.py", "--out-dir", str(out / "coverage")], timeout=7200)
    if p.returncode != 0:
        record("coverage", False, (p.stderr or p.stdout)[-300:])
    else:
        for name, frozen in (("baseline", "621"), ("refined", "v2")):
            fresh = out / "coverage" / f"{name}-per-finding.jsonl"
            a, b = coverage_keys(fresh), coverage_keys(ROOT / f"bench/corpus-coverage-per-finding-{frozen}.jsonl")
            covered = sum(not k[4] for k in a)
            record("coverage", a == b, f"{name}: {covered}/{len(a)} co-located, rows identical={a == b}")

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

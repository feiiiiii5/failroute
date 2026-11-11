#!/usr/bin/env python3
"""Diagnose what the supplementary Semgrep baseline actually analysed.

tools/coverage_union.py --with-semgrep is deliberately strict: any entry in
Semgrep's ``errors`` array aborts the run, so a partial scan is never recorded
as complete coverage. That strictness also means it cannot say *how* partial a
failing run is. This script answers that question without relaxing the strict
harness and without touching any committed file.

For each pinned scan root it runs the pinned Semgrep rules once and records:

* every Semgrep error (type, level, path), and which detector findings lie in a
  file Semgrep reported as only partially analysed;
* every ``.py`` file under the scan root that Semgrep did not scan (for
  example through its default ``.semgrepignore``), and the detector findings in
  those files;
* the five-tool union that the retained Semgrep matches give when added to a
  four-tool per-finding export, together with the bound implied by findings in
  partially analysed or unscanned files.

The output is a diagnostic, not a clean reproduction: when ``errors`` is
non-empty the report says so in its ``status`` field.

Usage (output directory must not exist):
    .venv/bin/python tools/semgrep_diagnostic.py --out-dir /tmp/sg-diag \\
        --frame baseline=bench/corpus-coverage-per-finding-621.jsonl \\
        --frame refined=bench/corpus-coverage-per-finding-v2.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "tools/semgrep-rules/exception-handling.yaml"
TOL = 1


def run_semgrep(executable: str, scan_root: Path) -> dict:
    rel = os.path.relpath(scan_root, ROOT)
    proc = subprocess.run(
        [executable, "--metrics=off", "--disable-version-check", "--no-git-ignore",
         "--json", "-f", str(RULES), rel],
        cwd=ROOT, capture_output=True, text=True, timeout=3600,
    )
    try:
        doc = json.loads(proc.stdout)
    except ValueError:
        sys.exit(f"error: Semgrep produced no JSON for {rel} (rc={proc.returncode}): "
                 f"{proc.stderr[-500:]}")
    if proc.returncode not in (0, 1):
        sys.exit(f"error: Semgrep exited {proc.returncode} for {rel}")
    doc["_returncode"] = proc.returncode
    return doc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--frame", action="append", default=[], metavar="NAME=PER_FINDING_JSONL",
                    help="four-tool per-finding export(s) to extend with Semgrep matches")
    args = ap.parse_args()
    out_dir = args.out_dir.resolve()
    if out_dir.exists():
        sys.exit(f"error: output directory already exists: {out_dir}")
    executable = os.environ.get("SEMGREP") or shutil.which("semgrep")
    if not executable:
        sys.exit("error: Semgrep missing; install the pinned [paper-semgrep] extra")
    frames = []
    for spec in args.frame or ["baseline=bench/corpus-coverage-per-finding-621.jsonl"]:
        name, _, path = spec.partition("=")
        frames.append((name, Path(path)))

    version = subprocess.run([executable, "--version"], capture_output=True, text=True).stdout.strip()
    lock = json.loads((ROOT / "paper/corpus-lock.json").read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True)

    hits: set[tuple[str, int]] = set()
    partial: set[str] = set()
    unscanned: set[str] = set()
    packages = {}
    for pkg in lock["packages"]:
        scan_root = ROOT / "paper/corpus" / pkg["extracted_to"] / pkg["scan_root"]
        if not scan_root.is_dir():
            sys.exit(f"error: scan root missing: {scan_root}; run tools/fetch_corpus.py first")
        doc = run_semgrep(executable, scan_root)
        (out_dir / f"semgrep-{pkg['name']}.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
        scanned = {os.path.normpath(p) for p in doc["paths"]["scanned"]}
        py_files = {os.path.normpath(os.path.relpath(p, ROOT)) for p in scan_root.rglob("*.py")}
        not_scanned = sorted(py_files - scanned)
        unscanned.update(not_scanned)
        errs = []
        for e in doc.get("errors", []):
            path = e.get("path") or ""
            errs.append({"type": e.get("type"), "level": e.get("level"), "path": path,
                         "message": (e.get("message") or "").splitlines()[0]})
            if path:
                partial.add(os.path.normpath(path))
        for r in doc["results"]:
            hits.add((os.path.normpath(r["path"]), int(r["start"]["line"])))
        packages[pkg["name"]] = {"results": len(doc["results"]), "errors": errs,
                                 "py_files": len(py_files), "py_files_scanned": len(py_files & scanned),
                                 "py_files_not_scanned": not_scanned}

    report = {"semgrep_version": version, "rules": os.path.relpath(RULES, ROOT),
              "line_tolerance": TOL, "packages": packages, "frames": {}}
    for name, path in frames:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        four = sum(not r["failroute_only"] for r in rows)
        newly: Counter[str] = Counter()
        sg_coloc = 0
        undecided = []
        for r in rows:
            f = os.path.normpath(r["file"])
            near = any((f, r["lineno"] + d) in hits for d in range(-TOL, TOL + 1))
            sg_coloc += near
            if near and r["failroute_only"]:
                newly[r["rule"]] += 1
            if not near and r["failroute_only"] and (f in partial or f in unscanned):
                undecided.append(f"{r['file']}:{r['lineno']} ({r['rule']})")
        five = four + sum(newly.values())
        report["frames"][name] = {
            "per_finding_export": str(path), "findings": len(rows), "four_tool_covered": four,
            "semgrep_colocated": sg_coloc, "newly_covered_by_semgrep": dict(sorted(newly.items())),
            "five_tool_covered_observed": five,
            "uncovered_findings_in_partial_or_unscanned_files": undecided,
            "five_tool_covered_upper_bound": five + len(undecided),
        }
    clean = all(not p["errors"] for p in packages.values())
    report["status"] = ("complete: no Semgrep errors" if clean else
                        "PARTIAL: Semgrep reported errors; five-tool counts are bounded, not reproduced")
    (out_dir / "semgrep-diagnostic.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Semgrep {version}: {report['status']}")
    for name, p in packages.items():
        if p["errors"] or p["py_files_not_scanned"]:
            print(f"  {name}: errors={[(e['type'], e['path']) for e in p['errors']]} "
                  f"py_not_scanned={p['py_files_not_scanned']}")
    for name, fr in report["frames"].items():
        print(f"  frame {name}: {fr['findings']} findings, four-tool {fr['four_tool_covered']}, "
              f"+semgrep {fr['five_tool_covered_observed']} "
              f"(upper bound {fr['five_tool_covered_upper_bound']}); newly {fr['newly_covered_by_semgrep']}; "
              f"undecided {fr['uncovered_findings_in_partial_or_unscanned_files']}")
    print(f"wrote {out_dir / 'semgrep-diagnostic.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

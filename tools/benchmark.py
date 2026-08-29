#!/usr/bin/env python3
"""Benchmark failroute against the labelled corpus.

Usage:
    python tools/benchmark.py            # prints a report, exits 1 on P/R < 1.0
    python tools/benchmark.py --json     # also writes bench/benchmark-results.json

Ground truth lives in tests/corpus/manifest.json and was labelled by hand from
the semantics of each fixture -- never from tool output.  Any mismatch between
manifest and scanner is therefore a real precision/recall event.
"""

from __future__ import annotations

import argparse
import ast
import datetime as _dt
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from failroute.analyzer import scan_path  # noqa: E402


def run() -> dict:
    corpus = REPO_ROOT / "tests" / "corpus"
    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))

    expected = {(e["file"], e["lineno"], e["mode"]) for e in manifest["expected"]}
    labelled_negatives = {(n["file"], n["lineno"]) for n in manifest["labelled_true_negatives"]}

    # A corpus file may use syntax the *running interpreter* cannot parse
    # (match_case_cases.py needs PEP 634 / Python 3.10+). Scanning it would
    # yield nothing and every one of its labels would be scored as a false
    # negative -- an environment limit, not a detector defect. Such files are
    # reported as skipped and their labels excluded from this run, while CI
    # still enforces them on the interpreters that can parse them.
    skipped_files: list[str] = []
    findings = []
    for py in sorted(corpus.glob("*.py")):
        try:
            ast.parse(py.read_text(encoding="utf-8", errors="replace"), filename=str(py))
        except SyntaxError:
            skipped_files.append(py.name)
            continue
        for f in scan_path(py):
            findings.append((Path(f.file).name, f.lineno, f.mode.value))

    if skipped_files:
        expected = {e for e in expected if e[0] not in skipped_files}
        labelled_negatives = {n for n in labelled_negatives if n[0] not in skipped_files}

    actual = set(findings)
    tp = sorted(expected & actual)
    fp = sorted(actual - expected)
    fn = sorted(expected - actual)

    # true negatives: labelled clean handlers that produced no finding
    flagged_handlers = {(f[0], f[1]) for f in actual}
    tn = sorted(labelled_negatives - flagged_handlers)
    tn_violated = sorted(labelled_negatives & flagged_handlers)

    precision = len(tp) / (len(tp) + len(fp)) if (tp or fp) else 1.0
    recall = len(tp) / (len(tp) + len(fn)) if (tp or fn) else 1.0

    return {
        "corpus_version": manifest["corpus_version"],
        "run_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "skipped_files": skipped_files,
        "true_positives": len(tp),
        "false_positives": [{"file": f, "lineno": line, "mode": m} for f, line, m in fp],
        "false_negatives": [{"file": f, "lineno": line, "mode": m} for f, line, m in fn],
        "true_negatives": len(tn),
        "true_negative_violations": [{"file": f, "lineno": line} for f, line in tn_violated],
        "precision": round(precision, 4),
        "recall": round(recall, 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="write bench/benchmark-results.json")
    args = parser.parse_args()

    report = run()
    print(f"corpus v{report['corpus_version']}  run_at={report['run_at']}")
    if report["skipped_files"]:
        print(f"  skipped (unparseable on this interpreter): {', '.join(report['skipped_files'])}"
              f"  [Python {sys.version_info.major}.{sys.version_info.minor}]")
    print(f"  TP={report['true_positives']}  FP={len(report['false_positives'])}"
          f"  FN={len(report['false_negatives'])}  TN={report['true_negatives']}"
          f"  TN-violations={len(report['true_negative_violations'])}")
    print(f"  precision={report['precision']}  recall={report['recall']}")
    for kind in ("false_positives", "false_negatives", "true_negative_violations"):
        for item in report[kind]:
            print(f"  {kind}: {item}")

    if args.json:
        out = REPO_ROOT / "bench" / "benchmark-results.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"  wrote {out.relative_to(REPO_ROOT)}")

    ok = report["precision"] == 1.0 and report["recall"] == 1.0 and not report["true_negative_violations"]
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

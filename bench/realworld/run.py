#!/usr/bin/env python3
"""External regression bench for the failroute predicate refactor (V1 batch).

Runs the detector against ``cases.jsonl`` — 80 real-world coordinates carrying
human labels that were written for the arXiv paper, plus the seven probe shapes
from 委外任务清单.md §V1.0-A — and reports each acceptance gate as pass/fail.

Why this exists before the predicate was touched
------------------------------------------------
The paper's own RQ4 records that a hand-written fixture corpus failed to catch
the detector's blind spot, because the fixtures and the detector came from the
same author with the same blind spot. This bench is built from coordinates in
``paper/annotations.csv`` (read-only, SHA256-locked corpus), so the expectations
come from labels that were written against real third-party code.

Usage (from the repo root)::

    PYTHONPATH=src python3 bench/realworld/run.py            # gate report
    PYTHONPATH=src python3 bench/realworld/run.py --verbose  # every case
    PYTHONPATH=src python3 bench/realworld/run.py --json     # machine-readable

Exit code is 0 only when every gate passes.

Runs against both the pre-refactor detector (findings carry no per-finding
severity) and the refactored one. For the pre-refactor detector the rule's
declared SARIF severity stands in (``error`` -> HIGH, ``warning`` -> MEDIUM),
which is exactly why the pre-refactor baseline cannot express "downgrade to
INFO": there is no per-finding severity to downgrade.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_DIR = Path(__file__).resolve().parent
CASES = BENCH_DIR / "cases.jsonl"

#: Severity lattice, ascending. "NONE" means "not reported at all".
SEV_ORDER = ["NONE", "INFO", "LOW", "MEDIUM", "HIGH"]
SEV_RANK = {name: i for i, name in enumerate(SEV_ORDER)}

#: Stand-in severities for the pre-refactor detector, which had no per-finding
#: severity — only a per-rule SARIF level.
LEGACY_RULE_SEVERITY = {"error": "HIGH", "warning": "MEDIUM"}


def sev_rank(name: str | None) -> int:
    return SEV_RANK.get((name or "NONE").upper(), -1)


def load_cases() -> list[dict]:
    if not CASES.is_file():
        sys.exit(f"error: missing bench cases: {CASES}")
    with CASES.open(encoding="utf-8") as fh:
        cases = [json.loads(line) for line in fh if line.strip()]
    if not cases:
        sys.exit(f"error: bench cases file is empty: {CASES}")
    return cases


def find_findings_at(findings: list, lineno: int) -> list:
    """Findings whose handler starts on ``lineno`` (or spans it)."""
    hits = []
    for f in findings:
        end = getattr(f, "end_lineno", None) or f.lineno
        if f.lineno == lineno or f.lineno <= lineno <= end:
            hits.append(f)
    return [f for f in hits if f.lineno == lineno] or hits


def finding_severity(f) -> str:
    sev = getattr(f, "severity", None)
    if sev is None:
        from failroute.rules import rule_by_id

        rule = rule_by_id(getattr(f, "rule_id", "") or "")
        declared = rule.spec.severity if rule is not None else "warning"
        return LEGACY_RULE_SEVERITY.get(declared, "MEDIUM")
    return getattr(sev, "value", str(sev)).upper()


def finding_isomorphism(f):
    iso = getattr(f, "isomorphism", None)
    if iso is None:
        return None
    return getattr(iso, "value", str(iso))


def finding_covered_by(f) -> tuple:
    return tuple(getattr(f, "covered_by", ()) or ())


def scan_case(case: dict):
    """Return (findings, error_string) for one case."""
    from failroute.analyzer import scan_path, scan_source

    try:
        if case["kind"] == "probe":
            return scan_source(case["source"], file=f"<probe {case['case_id']}>"), None
        path = REPO_ROOT / case["file"]
        if not path.is_file():
            return [], f"corpus file missing: {path}"
        return scan_path(path), None
    except SyntaxError as exc:
        return [], f"SyntaxError: {exc}"
    except Exception as exc:  # a crash here is itself the finding
        return [], f"{type(exc).__name__}: {exc}"


def evaluate(case: dict, findings: list, error: str | None) -> dict:
    """Judge one case; return a result record."""
    out = {
        "case_id": case["case_id"],
        "kind": case["kind"],
        "gate": case.get("gate"),
        "label": case.get("label"),
        "expect_isomorphism": case.get("expect_isomorphism"),
        "error": error,
        "pass": True,
        "detail": "",
    }
    lineno = case.get("lineno")
    hits = find_findings_at(findings, lineno) if lineno is not None else list(findings)
    actual_max = max((finding_severity(f) for f in hits), key=sev_rank, default="NONE")
    out["n_findings"] = len(hits)
    out["actual_max_severity"] = actual_max
    out["rules"] = sorted({getattr(f, "rule_id", "") or "" for f in hits})
    out["covered_by"] = sorted({c for f in hits for c in finding_covered_by(f)})
    isos = {finding_isomorphism(f) for f in hits} - {None}
    out["actual_isomorphism"] = sorted(isos)[0] if len(isos) == 1 else (sorted(isos) if isos else None)

    want_min = case.get("expect_min_severity")
    want_max = case.get("expect_max_severity")
    if error is not None:
        out["pass"] = False
        out["detail"] = error
        return out
    if want_min is not None:
        if sev_rank(actual_max) < sev_rank(want_min):
            out["pass"] = False
            out["detail"] = f"expected >= {want_min}, got {actual_max} ({len(hits)} finding(s))"
        else:
            out["detail"] = f"{actual_max} >= {want_min}"
    if want_max is not None:
        if want_max == "NONE":
            if hits:
                out["pass"] = False
                out["detail"] = f"expected no finding, got {len(hits)} at {actual_max} ({out['rules']})"
            else:
                out["detail"] = "not reported"
        elif sev_rank(actual_max) > sev_rank(want_max):
            out["pass"] = False
            out["detail"] = f"expected <= {want_max}, got {actual_max}"
        else:
            out["detail"] = f"{actual_max} <= {want_max}"
    if case.get("expect") == "report" and not hits:
        out["pass"] = False
        out["detail"] = "expected a finding, got none"
    return out


def signal_confusion(cases: list[dict], results: dict) -> dict:
    """Confusion matrix of each candidate isomorphism signal on the -> bool cases.

    Positive class = NON_ISOMORPHIC (i.e. "report as a defect").
    """
    bools = [c for c in cases if c.get("expect_isomorphism")]
    signals = {
        "S-A catch-all handler (bare / except Exception)": lambda c: bool(c.get("is_catchall")),
        "S-B try body contains a loop or comprehension": lambda c: bool(c.get("try_has_loop")),
        "S-C try body is a single statement": lambda c: c.get("try_body_stmts") == 1,
        "S-A OR S-B": lambda c: bool(c.get("is_catchall")) or bool(c.get("try_has_loop")),
        "NOT S-C (multi-statement try body)": lambda c: c.get("try_body_stmts") != 1,
    }
    matrices = {}
    for name, pred in signals.items():
        tp = fp = tn = fn = 0
        for c in bools:
            truth = c["expect_isomorphism"] == "NON_ISOMORPHIC"
            said = bool(pred(c))
            if truth and said:
                tp += 1
            elif truth and not said:
                fn += 1
            elif said and not truth:
                fp += 1
            else:
                tn += 1
        n = len(bools)
        matrices[name] = {
            "tp": tp, "fp": fp, "tn": tn, "fn": fn, "n": n,
            "sensitivity": f"{tp}/{tp + fn}" if (tp + fn) else "-",
            "specificity": f"{tn}/{tn + fp}" if (tn + fp) else "-",
            "precision": f"{tp}/{tp + fp}" if (tp + fp) else "-",
        }
    return matrices


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verbose", action="store_true", help="print every case, not just failures")
    ap.add_argument("--json", action="store_true", help="print machine-readable results")
    ap.add_argument("--gate", default=None, help="only evaluate cases carrying this gate")
    args = ap.parse_args()

    cases = load_cases()
    if args.gate:
        cases = [c for c in cases if c.get("gate") == args.gate]

    import failroute

    results = []
    for case in cases:
        findings, error = scan_case(case)
        results.append(evaluate(case, findings, error))
    by_id = {r["case_id"]: r for r in results}

    gates = defaultdict(lambda: {"pass": 0, "fail": 0, "failures": []})
    for case, res in zip(cases, results):
        g = case.get("gate") or "(no gate)"
        gates[g]["pass" if res["pass"] else "fail"] += 1
        if not res["pass"]:
            where = case["file"].split("/")[-1] if case.get("file") else case.get("shape", "")
            gates[g]["failures"].append(
                f"{case['case_id']} [{case.get('label')}] {where}"
                f":{case.get('lineno', '')} — {res['detail']}"
            )

    if args.json:
        print(json.dumps({"failroute_version": getattr(failroute, "__version__", "?"),
                          "results": results,
                          "gates": {k: dict(v) for k, v in gates.items()},
                          "signals": signal_confusion(cases, by_id)},
                         ensure_ascii=False, indent=2))
        return 0 if all(v["fail"] == 0 for v in gates.values()) else 1

    print(f"failroute {getattr(failroute, '__version__', '?')} · bench cases={len(cases)}")
    print(f"per-finding severity supported: "
          f"{'yes' if _detector_has_severity() else 'NO (pre-refactor: rule SARIF level stands in)'}")
    print()
    for g in sorted(gates):
        v = gates[g]
        mark = "PASS" if v["fail"] == 0 else "FAIL"
        print(f"[{mark}] {g:<32} {v['pass']} pass / {v['fail']} fail")
        if v["fail"]:
            for line in v["failures"][:60]:
                print(f"        - {line}")
            if len(v["failures"]) > 60:
                print(f"        ... and {len(v['failures']) - 60} more")
    print()
    print("=== isomorphism signal confusion matrices (-> bool cases, positive = NON_ISOMORPHIC) ===")
    for name, m in signal_confusion(cases, by_id).items():
        print(f"  {name}")
        print(f"      TP={m['tp']} FP={m['fp']} TN={m['tn']} FN={m['fn']}  n={m['n']}  "
              f"sens={m['sensitivity']} spec={m['specificity']} prec={m['precision']}")
    print()
    print("=== detector isomorphism verdict vs label (-> bool cases) ===")
    for c in cases:
        if not c.get("expect_isomorphism"):
            continue
        r = by_id[c["case_id"]]
        verdict = r["actual_isomorphism"]
        sev = r["actual_max_severity"]
        if c["expect_isomorphism"] == "ISOMORPHIC":
            agrees = verdict == "isomorphic" or sev in ("NONE", "INFO")
        else:
            agrees = verdict == "non-isomorphic" or sev_rank(sev) >= sev_rank("MEDIUM")
        mark = "ok " if agrees else "MISS"
        if args.verbose or not agrees:
            where = c["file"].split("/")[-1] if c.get("file") else ""
            print(
                f"  [{mark}] {c['case_id']} {c['label']:<15} {str(c['func']):<26} "
                f"{where}:{c.get('lineno', '')} expect={c['expect_isomorphism']:<16} "
                f"actual={str(verdict):<16} sev={sev:<7} covered_by={r['covered_by']}"
            )
    if args.verbose:
        print()
        print("=== all cases ===")
        for case, res in zip(cases, results):
            print(f"  [{'ok ' if res['pass'] else 'FAIL'}] {case['case_id']:<10} "
                  f"{str(case.get('label')):<15} {str(case.get('gate')):<28} {res['detail']}")
    total_fail = sum(v["fail"] for v in gates.values())
    print()
    print(f"RESULT: {'ALL GATES PASS' if total_fail == 0 else f'{total_fail} CASE(S) FAILING'}")
    return 0 if total_fail == 0 else 1


def _detector_has_severity() -> bool:
    from failroute.analyzer import scan_source

    for f in scan_source("try:\n    pass\nexcept ValueError:\n    pass\n"):
        if hasattr(f, "severity"):
            return True
    try:
        from failroute.ir import Finding  # noqa: F401
        return "severity" in Finding.__dataclass_fields__
    except Exception:
        return False


if __name__ == "__main__":
    raise SystemExit(main())

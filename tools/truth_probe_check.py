#!/usr/bin/env python3
"""Validate failroute findings/suppressions against contractlens's
maintainer-behaviour ground truth (the N1 dataset).

Ground truth = what upstream maintainers actually did to a flagged site
(``dataset.jsonl`` labels: SURVIVED / FIXED / MUTATED / VANISHED / TOO_YOUNG),
**not** anyone's opinion. Join key: package + file suffix + enclosing-function
qualname, restricted to dataset rows whose observed version range covers the
pinned corpus version of that package.

Modes
-----
f2  One-line audit of the findings suppressed by the F2 decisions:
    ``SUPPRESSED=n SURVIVED=s FIXED=f MUTATED=m VANISHED=v NO_TRUTH=u``
    plus a per-site table. Fails (exit 1) unless SURVIVED share among
    truth-joined sites is >= --min-survived (default 0.95) AND no FIXED site
    lost a detection entirely.
f3  v0.7.0 (frozen ``paper/scan``) vs new findings on the 154 decisive sites
    (SURVIVED+FIXED rows in scope): per-mode totals and the 9-FIXED recall
    table. Fails (exit 1) if the new findings detect fewer FIXED sites than
    the frozen baseline (the one "must not fail" gate of the F batch).

Every input path is mandatory; a missing file aborts loudly (a silent skip
here would fake a validation).

Usage (repo root):
    PYTHONPATH=src .venv/bin/python tools/truth_probe_check.py --mode f2 \
        --dataset ../新项目-contractlens/data/dataset.jsonl \
        --base bench/rescan-f1 --new bench/rescan-f2
    PYTHONPATH=src .venv/bin/python tools/truth_probe_check.py --mode f3 \
        --dataset ../新项目-contractlens/data/dataset.jsonl \
        --base paper/scan --new bench/rescan-f2
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DECISIVE = ("SURVIVED", "FIXED", "MUTATED", "VANISHED")


def _vt(version: str) -> tuple[int, ...]:
    # Keep every component: garak's 4-part "0.9.0.12" must sort correctly
    # against the 3-part pins. Tuple comparison handles mixed lengths.
    return tuple(int(part) for part in version.split("."))


def load_lock() -> tuple[dict[str, str], dict[str, Path]]:
    """pkg -> pinned version and pkg -> corpus scan root."""
    lock_path = ROOT / "paper" / "corpus-lock.json"
    if not lock_path.is_file():
        sys.exit(f"error: missing {lock_path}")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    versions: dict[str, str] = {}
    roots: dict[str, Path] = {}
    for pkg in lock["packages"]:
        extracted = pkg["extracted_to"]
        # extracted_to is "<name>-<version>"; the version is the tail.
        versions[pkg["name"]] = extracted.rsplit("-", 1)[-1]
        root = ROOT / "paper" / "corpus" / extracted / pkg["scan_root"]
        if not root.is_dir():
            sys.exit(f"error: corpus scan root missing: {root}")
        roots[pkg["name"]] = root
    return versions, roots


def load_rows(dataset_path: Path, versions: dict[str, str]) -> list[dict]:
    """Dataset rows for overlap packages whose version range covers the pin."""
    if not dataset_path.is_file():
        sys.exit(f"error: missing dataset: {dataset_path}")
    rows: list[dict] = []
    with dataset_path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            d = json.loads(line)
            pkg = d.get("pkg")
            if pkg not in versions:
                continue
            try:
                lo = _vt(d["ver_first"])
                hi = _vt(d["ver_last"])
            except Exception:  # unparseable version strings cannot be scoped
                continue
            pinned = _vt(versions[pkg])
            if lo <= pinned <= hi:
                d["_pinned_ok"] = True
                rows.append(d)
    if not rows:
        sys.exit("error: no in-scope ground-truth rows -- join would be vacuous")
    return rows


def load_rows_all(dataset_path: Path, versions: dict[str, str]) -> list[dict]:
    """All rows for overlap packages, unscoped (for the FIXED recall gate)."""
    if not dataset_path.is_file():
        sys.exit(f"error: missing dataset: {dataset_path}")
    rows: list[dict] = []
    with dataset_path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            d = json.loads(line)
            if d.get("pkg") in versions:
                rows.append(d)
    return rows


def function_spans(root: Path) -> dict[str, list[tuple[str, int, int]]]:
    """relpath suffix -> [(qualname, start, end)] for every function."""
    spans: dict[str, list[tuple[str, int, int]]] = {}
    for path in sorted(root.rglob("*.py")):
        if path.name.endswith((" 2.py", " 3.py")):  # Finder duplicates, see rescan tool
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        rel = path.relative_to(ROOT)
        entries: list[tuple[str, int, int]] = []

        def walk(body, prefix):
            for node in body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qn = f"{prefix}{node.name}" if not prefix else f"{prefix}.{node.name}"
                    entries.append((qn, node.lineno, node.end_lineno or node.lineno))
                    walk(node.body, qn)
                elif isinstance(node, ast.ClassDef):
                    cp = f"{prefix}.{node.name}" if prefix else node.name
                    walk(node.body, cp)
                elif isinstance(node, (ast.If,)):
                    walk(node.body, prefix)
                    walk(node.orelse, prefix)
                elif isinstance(node, (ast.Try,)):
                    walk(node.body, prefix)
                    for h in node.handlers:
                        walk(h.body, prefix)
                    walk(node.orelse, prefix)
                    walk(node.finalbody, prefix)
                elif isinstance(node, (ast.With, ast.AsyncWith, ast.For, ast.AsyncFor, ast.While)):
                    walk(node.body, prefix)

        walk(tree.body, "")
        spans[str(rel)] = entries
    return spans


def find_qualname(spans: dict[str, list], file: str, lineno: int) -> str | None:
    """Innermost enclosing function qualname; ``<module>`` for module-level
    sites (the dataset uses the same token); None when the file is unknown."""
    for path_key, entries in spans.items():
        if path_key == file or path_key.endswith(file) or file.endswith(path_key):
            best = None
            for qn, start, end in entries:
                if start <= lineno <= end:
                    if best is None or start >= best[1]:
                        best = (qn, start, end)
            return best[0] if best is not None else "<module>"
    return None


def load_findings(dirpath: Path) -> list[dict]:
    dirpath = dirpath if dirpath.is_absolute() else ROOT / dirpath
    jsonls = sorted(dirpath.glob("*.jsonl"))
    if not jsonls:
        sys.exit(f"error: no .jsonl findings under {dirpath}")
    rows = []
    for p in jsonls:
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def match_row(row: dict, pkg: str, qualname: str | None, file: str) -> bool:
    """Truth row <-> finding site: same package, file suffix, function."""
    if qualname is None:
        return False
    row_file = row["file"]
    if not (file.endswith(row_file) or row_file.endswith(Path(file).name)):
        return False
    return row["qualname"] == qualname


def ablation_report(dataset: Path, versions: dict[str, str], rows: list[dict],
                    roots: dict[str, Path]) -> int:
    """Test each ADR-0001 predicate condition against ground truth.

    For every ImportError-family handler in the six overlap packages, classify
    it under the shipped predicate and under variants with one condition
    dropped, then join the sites to maintainer labels. Reports, per variant:
    number of matching handlers, and how many join to SURVIVED / FIXED /
    other labels. A variant is only defensible if it suppresses no FIXED
    site and keeps the SURVIVED share high.
    """
    from failroute.rules._shared import (
        IMPORT_EXC_NAMES,
        _handler_body_is_minimal_fallback,
        _handler_exc_member_names,
        _try_body_is_import_probe,
    )

    overlap = {"fickling", "garak", "inspect_ai", "smolagents", "trl", "uqlm"}
    spans_by_pkg = {pkg: function_spans(roots[pkg]) for pkg in overlap}

    variants = {
        "shipped (all three)": lambda exc_ok, body_ok, handler_ok: exc_ok and body_ok and handler_ok,
        "drop cond-1 (any exc type)": lambda exc_ok, body_ok, handler_ok: body_ok and handler_ok,
        "drop cond-2 (any guarded body)": lambda exc_ok, body_ok, handler_ok: exc_ok and handler_ok,
        "drop cond-3 (any handler body)": lambda exc_ok, body_ok, handler_ok: exc_ok and body_ok,
    }
    stats = {name: {"n": 0, "SURVIVED": 0, "FIXED": 0, "MUTATED": 0, "VANISHED": 0,
                    "TOO_YOUNG": 0, "NO_TRUTH": 0}
             for name in variants}

    for pkg in overlap:
        for path in sorted(roots[pkg].rglob("*.py")):
            if path.name.endswith((" 2.py", " 3.py")):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            rel = str(path.relative_to(ROOT))
            for try_node in (n for n in ast.walk(tree) if isinstance(n, ast.Try)):
                for handler in try_node.handlers:
                    names = _handler_exc_member_names(handler) or []
                    # Candidate population: the ImportError family appears
                    # somewhere in the caught types. Condition 1 (shipped)
                    # additionally requires *every* member to be family-only;
                    # dropping it admits mixed tuples like (ImportError, ValueError).
                    if not names or not any(n in IMPORT_EXC_NAMES for n in names):
                        continue
                    exc_ok = all(n in IMPORT_EXC_NAMES for n in names)
                    body_ok = _try_body_is_import_probe(try_node.body)
                    handler_ok = _handler_body_is_minimal_fallback(handler)
                    qn = find_qualname(spans_by_pkg[pkg], rel, handler.lineno)
                    label = None
                    for row in rows:
                        if row["pkg"] == pkg and match_row(row, pkg, qn, rel):
                            label = row["label"]
                            break
                    for name, fn in variants.items():
                        if fn(exc_ok, body_ok, handler_ok):
                            stats[name]["n"] += 1
                            stats[name][label or "NO_TRUTH"] += 1

    print(f"{'variant':<34} {'n':>4} {'SURV':>5} {'FIXED':>6} {'MUT':>4} {'VAN':>4} {'YOUNG':>6} {'NO_TRUTH':>9}")
    for name, s in stats.items():
        print(f"{name:<34} {s['n']:>4} {s['SURVIVED']:>5} {s['FIXED']:>6} {s['MUTATED']:>4} "
              f"{s['VANISHED']:>4} {s['TOO_YOUNG']:>6} {s['NO_TRUTH']:>9}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=("f2", "f3", "ablation"), required=True)
    ap.add_argument("--dataset", required=True, help="contractlens data/dataset.jsonl")
    ap.add_argument("--base", help="findings dir before the change under test (f2/f3)")
    ap.add_argument("--new", help="findings dir after the change under test (f2/f3)")
    ap.add_argument("--min-survived", type=float, default=0.95)
    args = ap.parse_args()
    if args.mode != "ablation" and (not args.base or not args.new):
        ap.error(f"--base and --new are required for mode {args.mode}")

    versions, roots = load_lock()
    dataset = Path(args.dataset)
    if not dataset.is_absolute():
        dataset = ROOT / dataset
    rows = load_rows(dataset, versions)

    if args.mode == "ablation":
        return ablation_report(dataset, versions, rows, roots)

    # Build function spans for the six overlap packages.
    overlap = {"fickling", "garak", "inspect_ai", "smolagents", "trl", "uqlm"}
    spans_by_pkg = {pkg: function_spans(roots[pkg]) for pkg in overlap}

    base = load_findings(Path(args.base))
    new = load_findings(Path(args.new))

    def site_key(d):
        pkg = d["repo"]
        qn = find_qualname(spans_by_pkg.get(pkg, {}), d["file"], d["lineno"])
        return (pkg, d["file"], d["lineno"], qn)

    if args.mode == "f2":
        base_keys = {(k[0], k[1], k[2]) for k in map(site_key, base)}
        suppressed = [d for d in base if (d["repo"], d["file"], d["lineno"]) in base_keys
                      and not any(n["repo"] == d["repo"] and n["file"] == d["file"]
                                  and n["lineno"] == d["lineno"] for n in new)]
        # de-dup by (repo,file,lineno) keeping first
        seen = set()
        uniq = []
        for d in suppressed:
            k = (d["repo"], d["file"], d["lineno"])
            if k not in seen:
                seen.add(k)
                uniq.append(d)
        counts = {lab: 0 for lab in DECISIVE}
        no_truth = 0
        print(f"{'site':<70} {'label':<10}")
        for d in uniq:
            qn = find_qualname(spans_by_pkg.get(d["repo"], {}), d["file"], d["lineno"])
            label = None
            for row in rows:
                if row["pkg"] == d["repo"] and match_row(row, d["repo"], qn, d["file"]):
                    label = row["label"]
                    break
            if label in counts:
                counts[label] += 1
            else:
                no_truth += 1
                label = label or "NO_TRUTH"
            print(f"{d['repo']}:{d['file'].split('/')[-1]}:{d['lineno']} qn={qn!s:<32} {label}")
        joined = sum(counts.values())
        share = counts["SURVIVED"] / joined if joined else 0.0
        print(
            f"\nSUPPRESSED={len(uniq)} SURVIVED={counts['SURVIVED']} FIXED={counts['FIXED']} "
            f"MUTATED={counts['MUTATED']} VANISHED={counts['VANISHED']} NO_TRUTH={no_truth} "
            f"survived_share_of_joined={share:.3f}"
        )
        ok = joined > 0 and share >= args.min_survived and counts["FIXED"] == 0
        print("PASS" if ok else "FAIL", "(criterion: share >= %.2f and zero FIXED)" % args.min_survived)
        return 0 if ok else 1

    # mode f3: 154 decisive sites, old vs new detection + FIXED recall gate.
    # SURVIVED rows are evaluated in version scope; the FIXED recall gate
    # uses ALL FIXED rows of the six packages regardless of version scope
    # (the pinned tree may still contain the flagged function even when the
    # row's observed range ended earlier -- recall must not silently drop).
    all_rows = load_rows_all(dataset, versions)
    fixed_all = [r for r in all_rows if r["label"] == "FIXED"]
    decisive = [r for r in rows if r["label"] == "SURVIVED"] + fixed_all

    def detected(row, findings):
        for d in findings:
            if d["repo"] != row["pkg"]:
                continue
            qn = find_qualname(spans_by_pkg.get(row["pkg"], {}), d["file"], d["lineno"])
            if match_row(row, row["pkg"], qn, d["file"]):
                return True
        return False

    old_hits = {r["id"]: detected(r, base) for r in decisive}
    new_hits = {r["id"]: detected(r, new) for r in decisive}
    print(f"{'id':<72} {'label':<9} old new")
    for r in decisive:
        o, n = old_hits[r["id"]], new_hits[r["id"]]
        mark = "" if (o == n or not (o and not n)) else "  <-- lost"
        print(f"{r['id'][-60:]:<72} {r['label']:<9} {int(o)}   {int(n)}{mark}")
    for lab in ("SURVIVED", "FIXED"):
        sub = [r for r in decisive if r["label"] == lab]
        o = sum(1 for r in sub if old_hits[r["id"]])
        n = sum(1 for r in sub if new_hits[r["id"]])
        print(f"SUMMARY {lab}: sites={len(sub)} detected_old={o} detected_new={n}")
    fixed = [r for r in decisive if r["label"] == "FIXED"]
    lost = [r for r in fixed if old_hits[r["id"]] and not new_hits[r["id"]]]
    print("RECALL_GATE " + ("PASS (new >= old on FIXED)" if not lost else f"FAIL lost={[r['id'] for r in lost]}"))
    return 0 if not lost else 1


if __name__ == "__main__":
    raise SystemExit(main())

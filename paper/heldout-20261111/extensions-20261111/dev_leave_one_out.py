#!/usr/bin/env python3
"""Development-corpus leave-one-package-out robustness check.

Symmetric counterpart to the held-out leave-one-out in comparison.json. Reads
only the committed per-package aggregates of the two development frames; runs
no detector and no linter.

  old frame: bench/corpus-coverage-union.json      (621 findings, 255 covered)
  new frame: bench/corpus-coverage-union-v2.json   (476 findings, 252 covered)

Usage:  python3 dev_leave_one_out.py [--repo ROOT] [--out JSON]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def decomposition(n0: int, c0: int, n1: int, c1: int) -> dict:
    den = (c0 / n1 - c0 / n0) * 100
    cov = (c1 / n1 - c0 / n1) * 100
    return {
        "n0": n0, "c0": c0, "n1": n1, "c1": c1,
        "share0_pct": round(c0 / n0 * 100, 2),
        "share1_pct": round(c1 / n1 * 100, 2),
        "delta_pp": round(c1 / n1 * 100 - c0 / n0 * 100, 2),
        "denominator_term_pp": round(den, 2),
        "covered_count_term_pp": round(cov, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    old = json.loads((args.repo / "bench/corpus-coverage-union.json").read_text())
    new = json.loads((args.repo / "bench/corpus-coverage-union-v2.json").read_text())

    o = {p["name"]: p for p in old["per_package"]}
    n = {p["name"]: p for p in new["per_package"]}
    if set(o) != set(n):
        raise SystemExit("package sets differ between frames")

    T0 = sum(p["failroute"] for p in o.values())
    C0 = sum(p["covered"] for p in o.values())
    T1 = sum(p["failroute"] for p in n.values())
    C1 = sum(p["covered"] for p in n.values())
    for got, want, label in (
        (T0, old["failroute_total"], "old total"),
        (C0, old["union_covered"], "old covered"),
        (T1, new["failroute_total"], "new total"),
        (C1, new["union_covered"], "new covered"),
    ):
        if got != want:
            raise SystemExit(f"{label}: per-package sum {got} != headline {want}")

    rows = []
    for name in sorted(o):
        d = decomposition(
            T0 - o[name]["failroute"], C0 - o[name]["covered"],
            T1 - n[name]["failroute"], C1 - n[name]["covered"],
        )
        d["excluded"] = name
        d["share_change_pp"] = d["delta_pp"]
        d["covered_change"] = d["c1"] - d["c0"]
        rows.append(d)

    result = {
        "source_old": "bench/corpus-coverage-union.json",
        "source_new": "bench/corpus-coverage-union-v2.json",
        "note": "post-hoc symmetric robustness check; no detector or linter was run",
        "primary": decomposition(T0, C0, T1, C1),
        "leave_one_out": rows,
        "all_share_changes_positive": all(r["share_change_pp"] > 0 for r in rows),
        "share_change_range_pp": [min(r["share_change_pp"] for r in rows),
                                  max(r["share_change_pp"] for r in rows)],
        "covered_count_reversals": [r["excluded"] for r in rows if r["covered_change"] > 0],
    }

    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)

    p = result["primary"]
    print(f"\nprimary: {p['c0']}/{p['n0']} -> {p['c1']}/{p['n1']}  "
          f"share {p['share0_pct']}% -> {p['share1_pct']}%  "
          f"covered change {p['c1'] - p['c0']:+d}")
    print(f"share rises in all {len(rows)}: {result['all_share_changes_positive']}  "
          f"range {result['share_change_range_pp']}")
    print(f"covered-count sign reverses when excluding: {result['covered_count_reversals']}")
    for r in rows:
        print(f"  {r['excluded']:20s} {r['n0']:3d}/{r['c0']:3d} -> {r['n1']:3d}/{r['c1']:3d}  "
              f"share {r['share0_pct']:5.2f} -> {r['share1_pct']:5.2f} "
              f"({r['share_change_pp']:+5.2f})  covered {r['covered_change']:+3d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
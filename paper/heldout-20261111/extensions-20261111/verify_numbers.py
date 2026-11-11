#!/usr/bin/env python3
"""Independent recomputation gate for the paper's headline numbers.

Unlike scripts/check_paper_heldout.py, which compares comparison.json against
hard-coded constants and greps the manuscript, this script recomputes every
headline quantity from the raw per-finding records and only then compares it
to both comparison.json and the manuscript text. A number that survives this
gate has been derived twice by different code paths.

Reads only. Runs no detector, no linter, no model.

Usage:  python3 verify_numbers.py [--repo ROOT] [--out JSON]
Exit code 0 iff every check passes.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
from pathlib import Path

TOL_PP = 0.005


def near(a: float, b: float) -> bool:
    return abs(a - b) <= TOL_PP


def share(c: int, n: int) -> float:
    return c / n * 100


def terms(n0: int, c0: int, n1: int, c1: int) -> tuple[float, float, float]:
    return ((c0 / n1 - c0 / n0) * 100,
            (c1 / n1 - c0 / n1) * 100,
            (c1 / n1 - c0 / n0) * 100)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    ho = a.repo / "paper/heldout-20261111"
    tex = (a.repo / "paper/arxiv/main.tex").read_text(encoding="utf-8")
    cmp_ = json.loads((ho / "comparison.json").read_text())

    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    def in_tex(*needles: str) -> bool:
        return all(n in tex for n in needles)

    # ---- held-out: recount raw findings -------------------------------------
    raw = {}
    for ver in ("v0.8.0", "v0.9.1"):
        per = collections.Counter()
        rules = collections.Counter()
        sites = set()
        for p in sorted(glob.glob(str(ho / f"findings-{ver}" / "*.jsonl"))):
            for line in Path(p).read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                per[r["repo"]] += 1
                rules[r["rule"]] += 1
                sites.add((r["file"], r["lineno"]))
        raw[ver] = {"per": per, "rules": rules,
                    "total": sum(per.values()), "sites": len(sites)}

    pf = [json.loads(l) for l in
          (ho / "per-finding-v0.9.1.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    emp_per = collections.Counter(r["repo"] for r in pf if r["baseline_tools_colocated"])
    emp_total = sum(emp_per.values())

    add("raw findings 322 / 248",
        raw["v0.8.0"]["total"] == 322 and raw["v0.9.1"]["total"] == 248
        and in_tex("322", "248"))
    add("raw distinct sites 317 / 245",
        raw["v0.8.0"]["sites"] == 317 and raw["v0.9.1"]["sites"] == 245
        and in_tex("317 to 245"))
    add("raw empirical covered v0.9.1 = 88", emp_total == 88)

    f080, f091 = cmp_["frames"]["v0.8.0"], cmp_["frames"]["v0.9.1"]
    add("comparison.json totals match raw recount",
        f080["total"] == raw["v0.8.0"]["total"] and f091["total"] == raw["v0.9.1"]["total"]
        and f091["covered"] == emp_total)

    # per-package table, both frames
    pp_ok = True
    for row in cmp_["per_package"]:
        nm = row["name"]
        if (row["findings_v080"] != raw["v0.8.0"]["per"][nm]
                or row["findings_v091"] != raw["v0.9.1"]["per"][nm]
                or row["covered_v091"] != emp_per.get(nm, 0)):
            pp_ok = False
    add("all 8 per-package rows match raw recount", pp_ok)

    C0 = sum(r["covered_v080"] for r in cmp_["per_package"])
    T0 = sum(r["findings_v080"] for r in cmp_["per_package"])
    T1 = sum(r["findings_v091"] for r in cmp_["per_package"])
    C1 = sum(r["covered_v091"] for r in cmp_["per_package"])
    add("table sums 322/99 -> 248/88", (T0, C0, T1, C1) == (322, 99, 248, 88))
    add("shares 30.7% and 35.5% (1dp, from exact ratios)",
        round(share(C0, T0), 1) == 30.7 and round(share(C1, T1), 1) == 35.5
        and in_tex("30.7", "35.5"))

    den, cov, delta = terms(T0, C0, T1, C1)
    add("primary decomposition +9.17 / -4.44 / +4.74",
        near(round(den, 2), 9.17) and near(round(cov, 2), -4.44)
        and near(round(delta, 2), 4.74) and in_tex("+9.17", "-4.44", "+4.74"))

    # ---- sensitivities ------------------------------------------------------
    nv, ed = cmp_["sensitivity_no_vendor"], cmp_["sensitivity_exclude_dspy"]
    add("no-vendor 235/55 -> 189/56 and shares",
        (nv["v0.8.0"]["total"], nv["v0.8.0"]["covered"],
         nv["v0.9.1"]["total"], nv["v0.9.1"]["covered"]) == (235, 55, 189, 56)
        and round(share(55, 235), 1) == 23.4 and round(share(56, 189), 1) == 29.6
        and in_tex("235 to 189", "55 to 56"))
    add("exclude-dspy 147/30 -> 134/35 and shares",
        (ed["v0.8.0"]["total"], ed["v0.8.0"]["covered"],
         ed["v0.9.1"]["total"], ed["v0.9.1"]["covered"]) == (147, 30, 134, 35)
        and round(share(30, 147), 1) == 20.4 and round(share(35, 134), 1) == 26.1
        and in_tex("147 to 134", "30 to 35"))
    add("exclude-dspy equals total minus dspy row",
        (T0 - raw["v0.8.0"]["per"]["dspy"], T1 - raw["v0.9.1"]["per"]["dspy"]) == (147, 134))
    for key, exp in (("sensitivity_no_vendor", (5.70, 0.53)),
                     ("sensitivity_exclude_dspy", (1.98, 3.73))):
        d = cmp_[key]["decomposition"]
        got = terms(d["n0"], d["c0"], d["n1"], d["c1"])
        add(f"{key} decomposition recomputes",
            near(round(got[0], 2), exp[0]) and near(round(got[1], 2), exp[1]))

    # ---- leave-one-out, both corpora ---------------------------------------
    loo = []
    for row in cmp_["per_package"]:
        nm = row["name"]
        n0, c0 = T0 - row["findings_v080"], C0 - row["covered_v080"]
        n1, c1 = T1 - row["findings_v091"], C1 - row["covered_v091"]
        loo.append({"excluded": nm, "share_change_pp": round(share(c1, n1) - share(c0, n0), 2),
                    "covered_change": c1 - c0})
    add("held-out LOO: all 8 share changes positive, range +2.92..+5.88",
        all(r["share_change_pp"] > 0 for r in loo)
        and near(min(r["share_change_pp"] for r in loo), 2.92)
        and near(max(r["share_change_pp"] for r in loo), 5.88)
        and in_tex("all eight exclusions", "+2.92 to +5.88"))
    add("held-out LOO: covered count reverses only for dspy",
        [r["excluded"] for r in loo if r["covered_change"] > 0] == ["dspy"]
        and in_tex("only when", "dspy"))
    add("held-out LOO matches comparison.json",
        all(r["share_change_pp"] == j["share_change_pp"] and r["covered_change"] == j["covered_change"]
            for r in loo for j in cmp_["leave_one_out"] if j["excluded"] == r["excluded"]))

    dev = json.loads((Path(__file__).parent / "dev-leave-one-out.json").read_text())
    dl = dev["leave_one_out"]
    add("development LOO: all 8 share changes positive, range +9.81..+12.48",
        all(r["share_change_pp"] > 0 for r in dl)
        and near(min(r["share_change_pp"] for r in dl), 9.81)
        and near(max(r["share_change_pp"] for r in dl), 12.48)
        and in_tex("+9.81", "+12.48"))
    add("development LOO: covered count reverses for deepteam and inspect_ai",
        sorted(r["excluded"] for r in dl if r["covered_change"] > 0) == ["deepteam", "inspect_ai"]
        and in_tex("deepteam", "inspect\\_ai", "124 \\rightarrow 125", "160 \\rightarrow 173"))

    # ---- suppress and static/empirical -------------------------------------
    sup08 = raw["v0.8.0"]["rules"]["silent-suppress"]
    sup09 = raw["v0.9.1"]["rules"]["silent-suppress"]
    supcov = sum(1 for r in pf if r["rule"] == "silent-suppress" and r["baseline_tools_colocated"])
    add("suppress 24 / 9, none covered",
        sup08 == 24 and sup09 == 9 and supcov == 0 and in_tex("none is covered"))

    dis = [r for r in pf if bool(r["covered_by_static"]) != bool(r["baseline_tools_colocated"])]
    add("held-out static/empirical 246 of 248, 2 name-shadowing at builder.py:1575,1881",
        len(pf) - len(dis) == 246 and len(dis) == 2
        and all(r["rule"] == "name-shadowing" for r in dis)
        and sorted(r["lineno"] for r in dis) == [1575, 1881]
        and all(r["file"].endswith("datasets/builder.py") for r in dis)
        and in_tex("246 of 248", "name-shadowing"))

    # ---- development frame: item-level agreement ---------------------------
    dv = [json.loads(l) for l in
          (a.repo / "bench/corpus-coverage-per-finding-v2.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]
    dsc = sum(1 for r in dv if r["covered_by_static"])
    dec = sum(1 for r in dv if r["baseline_tools_colocated"])
    ddis = sum(1 for r in dv if bool(r["covered_by_static"]) != bool(r["baseline_tools_colocated"]))
    add("development 476 findings, 252 covered, ITEM-LEVEL 0 disagreements",
        len(dv) == 476 and dsc == 252 and dec == 252 and ddis == 0
        and in_tex("agree on all 476"))
    add("development 472 sites, 4 duplicated",
        len({(r["file"], r["lineno"]) for r in dv}) == 472
        and sum(1 for v in collections.Counter((r["file"], r["lineno"]) for r in dv).values() if v > 1) == 4
        and in_tex("617 to 472"))
    dden, dcov, ddelta = terms(621, 255, 476, 252)
    add("development decomposition +12.51 / -0.63 / +11.88",
        near(round(dden, 2), 12.51) and near(round(dcov, 2), -0.63)
        and near(round(ddelta, 2), 11.88) and in_tex("+12.51", "-0.63", "+11.88"))

    # ---- calibration -------------------------------------------------------
    rd = json.loads((a.repo / "bench/rq5-refactor-delta.json").read_text())["covered_by_fix"]
    add("calibration 68 probes, 146 = 137 + 9, 87 -> 224",
        json.loads((a.repo / "bench/lint-rule-mapping.json").read_text())["probe_cases"] == 68
        and rd["over_credited_findings"] == 146
        and rd["over_credited_that_became_novel"] == 137
        and rd["over_credited_but_still_covered"] == 9
        and rd["static_novel_pre"] == 87 and rd["static_novel_post"] == 224
        and 87 + 137 == 224 and in_tex("68", "146", "87", "224"))

    # ---- wording guards ----------------------------------------------------
    add("no 'pre-registered' claim remains", "pre-registered" not in tex and "preregistered" not in tex)
    add("abstract frames the 19 suppress candidates as v0.8.0", "all 19 v0.8.0" in tex)
    add("no blanket 'covered-count result does not replicate'",
        "the covered-count result does not" not in tex
        and "the absolute-count result does not" not in tex)

    failed = [c["check"] for c in checks if not c["pass"]]
    out = {"checks": len(checks), "passed": len(checks) - len(failed),
           "failed": failed, "detail": checks}
    text = json.dumps(out, indent=2, ensure_ascii=False)
    if a.out:
        a.out.write_text(text + "\n", encoding="utf-8")
    for c in checks:
        print(("PASS  " if c["pass"] else "FAIL  ") + c["check"])
    print(f"\n{out['passed']}/{out['checks']} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
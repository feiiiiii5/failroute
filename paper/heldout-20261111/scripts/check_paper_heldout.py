#!/usr/bin/env python3
"""Check the held-out numbers printed in paper/arxiv/main.tex against comparison.json.

This is a narrow text/number gate for the new held-out section and abstract. It
does not re-run the detector or linters, and it does not check every number in
the development study.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # repo root
TEX = ROOT / "paper" / "arxiv" / "main.tex"
DATA = ROOT / "paper" / "heldout-20261111" / "comparison.json"


def main() -> int:
    text = TEX.read_text(encoding="utf-8")
    d = json.loads(DATA.read_text(encoding="utf-8"))
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    def has(*needles: str) -> bool:
        return all(n in text for n in needles)

    f080 = d["frames"]["v0.8.0"]
    f091 = d["frames"]["v0.9.1"]
    dp = d["decomposition_primary"]
    dn = d["sensitivity_no_vendor"]["decomposition"]
    de = d["sensitivity_exclude_dspy"]["decomposition"]
    nv = d["sensitivity_no_vendor"]
    ed = d["sensitivity_exclude_dspy"]

    add("corpus: 8 packages, 1,564 files, 415,101 lines",
        d["corpus"]["packages"] == 8 and d["corpus"]["py_files"] == 1564 and d["corpus"]["lines"] == 415101
        and has("1{,}564", "415{,}101"))
    add("v0.8.0 total 322 / v0.9.1 total 248",
        f080["total"] == 322 and f091["total"] == 248 and has("322", "248"))
    add("shares 30.7% and 35.5%",
        abs(f080["share_pct"] - 30.7) < 0.06 and abs(f091["share_pct"] - 35.5) < 0.06
        and has("30.7", "35.5"))
    add("covered count 99 to 88",
        f080["covered"] == 99 and f091["covered"] == 88 and has("99 to 88"))
    add("primary decomposition +9.17, -4.44, +4.74",
        dp["denominator_term_pp"] == 9.17 and dp["covered_count_term_pp"] == -4.44 and dp["delta_pp"] == 4.74
        and has("+9.17", "-4.44", "+4.74"))
    add("no-vendor sensitivity 235/189, 55/56, 23.4/29.6",
        nv["v0.8.0"]["total"] == 235 and nv["v0.9.1"]["total"] == 189
        and nv["v0.8.0"]["covered"] == 55 and nv["v0.9.1"]["covered"] == 56
        and nv["v0.8.0"]["share_pct"] == 23.4 and nv["v0.9.1"]["share_pct"] == 29.63
        and has("235 to 189", "55 to 56", "23.4", "29.6"))
    add("exclude-dspy sensitivity 147/134, 30/35, 20.4/26.1",
        ed["v0.8.0"]["total"] == 147 and ed["v0.9.1"]["total"] == 134
        and ed["v0.8.0"]["covered"] == 30 and ed["v0.9.1"]["covered"] == 35
        and ed["v0.8.0"]["share_pct"] == 20.41 and ed["v0.9.1"]["share_pct"] == 26.12
        and has("147 to 134", "30 to 35", "20.4", "26.1"))
    add("no-vendor decomposition +5.70 / +0.53",
        dn["denominator_term_pp"] == 5.7 and dn["covered_count_term_pp"] == 0.53
        and has("+0.53"))
    add("exclude-dspy decomposition +3.73",
        de["covered_count_term_pp"] == 3.73 and has("+3.73"))
    add("dspy dominance 175 of 322 and 114 of 248",
        bool(re.search(r"175 of\s+the\s+322", text)) and bool(re.search(r"114 of\s+the\s+248", text)))
    add("dspy covered 69 to 53",
        has("69 to 53"))
    add("suppress 24 and 9, 0 covered",
        d["suppress"]["v0.8.0"]["total"] == 24 and d["suppress"]["v0.9.1"]["total"] == 9
        and d["suppress"]["v0.8.0"]["covered"] == 0 and d["suppress"]["v0.9.1"]["covered"] == 0
        and has("24", "9", "none is covered"))
    loo = d["leave_one_out"]
    add("leave-one-out: all eight share changes positive; only dspy reverses covered count",
        len(loo) == 8 and all(x["share_change_pp"] > 0 for x in loo)
        and [x["excluded"] for x in loo if x["covered_change"] > 0] == ["dspy"]
        and has("all eight exclusions", "only when", "dspy"))
    add("static/empirical 246 of 248, two name-shadowing",
        d["static_vs_empirical_v091"]["disagreements"] == 2
        and d["static_vs_empirical_v091"]["main_rules"]["rows"] == 246
        and has("246 of 248", "name-shadowing"))
    add("five of eight packages gain share",
        has("Five of eight packages gain share"))
    add("abstract contains held-out result and checklist",
        has("eight held-out", "30.7\\% to 35.5\\%", "checklist"))

    failed = [c for c in checks if not c[1]]
    print(json.dumps({"checks": len(checks), "failed": [c[0] for c in failed],
                      "detail": [{"check": c[0], "pass": c[1], "detail": c[2]} for c in checks]},
                     ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

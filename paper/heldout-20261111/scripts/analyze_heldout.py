#!/usr/bin/env python3
"""Analyze the held-out corpus run and write comparison.json / RESULTS.md.

Reads only committed-or-copied local records:
  heldout-lock.json
  findings-v0.8.0/*.jsonl
  findings-v0.9.1/*.jsonl
  coverage-v0.8.0.json
  coverage-v0.9.1.json
  coverage-v0.8.0-novendor.json
  coverage-v0.9.1-novendor.json
  per-finding-v0.9.1.jsonl

No detector, linter or model is run here. This is the analysis/reporting step.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT


def load_json(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def load_jsonl(name: str) -> list[dict]:
    path = DATA / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def all_findings(version: str) -> list[dict]:
    rows: list[dict] = []
    for path in sorted((DATA / f"findings-{version}").glob("*.jsonl")):
        rows.extend(
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return rows


def site_key(row: dict) -> tuple[str, int]:
    return (row["file"], row["lineno"])


def decomp(c0: int, n0: int, c1: int, n1: int) -> dict:
    o0, o1 = c0 / n0, c1 / n1
    covered_pp = (c1 - c0) / n1 * 100.0
    denom_pp = c0 * (1.0 / n1 - 1.0 / n0) * 100.0
    return {
        "n0": n0, "c0": c0, "share0_pct": round(o0 * 100, 2),
        "n1": n1, "c1": c1, "share1_pct": round(o1 * 100, 2),
        "delta_pp": round((o1 - o0) * 100, 2),
        "covered_count_term_pp": round(covered_pp, 2),
        "denominator_term_pp": round(denom_pp, 2),
        "sum_pp": round(covered_pp + denom_pp, 2),
    }


def cov_summary(cov: dict) -> dict:
    return {
        "total": cov["failroute_total"],
        "covered": cov["union_covered"],
        "only": cov["failroute_only"],
        "share_pct": round(cov["union_covered"] / cov["failroute_total"] * 100, 2),
    }


lock = load_json("heldout-lock.json")
packages = {p["name"]: p for p in lock["packages"]}
f080 = all_findings("v0.8.0")
f091 = all_findings("v0.9.1")
cov080 = load_json("coverage-v0.8.0.json")
cov091 = load_json("coverage-v0.9.1.json")
cov080n = load_json("coverage-v0.8.0-novendor.json")
cov091n = load_json("coverage-v0.9.1-novendor.json")
pf = load_jsonl("per-finding-v0.9.1.jsonl")

per_pkg_080 = {p["name"]: p for p in cov080["per_package"]}
per_pkg_091 = {p["name"]: p for p in cov091["per_package"]}
per_pkg_080n = {p["name"]: p for p in cov080n["per_package"]}
per_pkg_091n = {p["name"]: p for p in cov091n["per_package"]}

# Distinct handler sites (file, line), irrespective of rule.
sites_080 = {site_key(r) for r in f080}
sites_091 = {site_key(r) for r in f091}

# Per-package table, primary frame (including dspy's vendored subtree).
per_package = []
for name, p in packages.items():
    a = per_pkg_080[name]
    b = per_pkg_091[name]
    s0 = {site_key(r) for r in f080 if r["repo"] == name}
    s1 = {site_key(r) for r in f091 if r["repo"] == name}
    per_package.append({
        "name": name,
        "version": p["version"],
        "py_files": p["scan_root_py_files"],
        "lines": p["scan_root_total_lines"],
        "findings_v080": a["failroute"],
        "covered_v080": a["covered"],
        "share_v080_pct": round(a["covered"] / a["failroute"] * 100, 2) if a["failroute"] else None,
        "sites_v080": len(s0),
        "findings_v091": b["failroute"],
        "covered_v091": b["covered"],
        "share_v091_pct": round(b["covered"] / b["failroute"] * 100, 2) if b["failroute"] else None,
        "sites_v091": len(s1),
    })

# Sensitivity: exclude dspy's vendored subtree from both frames.
per_package_novendor = []
for name, p in packages.items():
    a = per_pkg_080n[name]
    b = per_pkg_091n[name]
    per_package_novendor.append({
        "name": name,
        "findings_v080": a["failroute"],
        "covered_v080": a["covered"],
        "findings_v091": b["failroute"],
        "covered_v091": b["covered"],
    })

# Leave-one-package-out aggregates from the same per-package table.
leave_one_out = []
for ex in per_package:
    rest = [r for r in per_package if r["name"] != ex["name"]]
    n0 = sum(r["findings_v080"] for r in rest)
    c0 = sum(r["covered_v080"] for r in rest)
    n1 = sum(r["findings_v091"] for r in rest)
    c1 = sum(r["covered_v091"] for r in rest)
    leave_one_out.append({
        "excluded": ex["name"],
        "v080": {"total": n0, "covered": c0, "share_pct": round(c0 / n0 * 100, 2)},
        "v091": {"total": n1, "covered": c1, "share_pct": round(c1 / n1 * 100, 2)},
        "share_change_pp": round((c1 / n1 - c0 / n0) * 100, 2),
        "covered_change": c1 - c0,
    })

# Static vs empirical agreement for v0.9.1.
disagreements = []
for r in pf:
    static = bool(r.get("covered_by_static"))
    emp = bool(r.get("baseline_tools_colocated"))
    if static != emp:
        disagreements.append({
            "repo": r["repo"],
            "file": r["file"].replace("paper/corpus/", "paper/heldout-20261111/corpus/"),
            "lineno": r["lineno"],
            "rule": r["rule"],
            "covered_by_static": r.get("covered_by_static"),
            "baseline_tools_colocated": r.get("baseline_tools_colocated"),
        })

# Suppress coverage.
sup080 = [r for r in f080 if r["rule"] == "silent-suppress"]
sup091 = [r for r in f091 if r["rule"] == "silent-suppress"]
# Coverage by_rule is the same empirical count as the per-finding rows.
sup_cov_080 = cov080["by_rule"].get("silent-suppress", {})
sup_cov_091 = cov091["by_rule"].get("silent-suppress", {})

# By-rule counts for both frames.
def rule_counts(rows: list[dict]) -> dict[str, int]:
    return dict(sorted(Counter(r["rule"] for r in rows).items()))

# Severity / isomorphism for v0.9.1.
severity = dict(sorted(Counter(r.get("severity") for r in f091).items(), key=lambda x: str(x[0])))
isomorphism = dict(sorted(Counter(r.get("isomorphism") for r in f091).items(), key=lambda x: str(x[0])))

# Hypothesis verdicts.
h1 = len(f091) < len(f080)
h2 = (cov091["union_covered"] / cov091["failroute_total"]) > (cov080["union_covered"] / cov080["failroute_total"])
h3 = cov091["union_covered"] < cov080["union_covered"]
d_primary = decomp(cov080["union_covered"], cov080["failroute_total"],
                   cov091["union_covered"], cov091["failroute_total"])
h4 = d_primary["denominator_term_pp"] > 0 and d_primary["covered_count_term_pp"] < 0
h5 = (sup_cov_080.get("covered", 0) == 0 and sup_cov_091.get("covered", 0) == 0)
h6 = len(disagreements) == 0
d_novendor = decomp(cov080n["union_covered"], cov080n["failroute_total"],
                    cov091n["union_covered"], cov091n["failroute_total"])
d_excl_dspy = decomp(
    cov080["union_covered"] - per_pkg_080["dspy"]["covered"],
    cov080["failroute_total"] - per_pkg_080["dspy"]["failroute"],
    cov091["union_covered"] - per_pkg_091["dspy"]["covered"],
    cov091["failroute_total"] - per_pkg_091["dspy"]["failroute"],
)

result = {
    "protocol_sha256": (DATA / "PROTOCOL.sha256").read_text(encoding="utf-8").strip(),
    "generated_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "environment": {
        "python": "3.11.15",
        "failroute": "0.9.1",
        "failroute_head": "15dffaaf3550aa3903a534b45c33d1a8b605d1d8",
        "v080_tag_commit": "a73158b8b69f94f21f77b57840d8e56df8275c16",
        "v091_tag_commit": "1b4a56268be16828701b048f4446d4ac0de945c0",
        "ruff": "0.16.4",
        "bandit": "1.9.4",
        "pylint": "4.0.8",
        "flake8": "7.3.0",
        "flake8_bugbear": "25.11.29",
    },
    "corpus": {
        "packages": len(packages),
        "py_files": sum(p["scan_root_py_files"] for p in packages.values()),
        "lines": sum(p["scan_root_total_lines"] for p in packages.values()),
        "sdist_py_files": lock["totals"]["py_files"],
        "sdist_lines": lock["totals"]["total_lines"],
    },
    "frames": {
        "v0.8.0": {
            **cov_summary(cov080),
            "distinct_sites": len(sites_080),
            "by_rule": rule_counts(f080),
        },
        "v0.9.1": {
            **cov_summary(cov091),
            "distinct_sites": len(sites_091),
            "by_rule": rule_counts(f091),
            "severity": severity,
            "isomorphism": isomorphism,
        },
    },
    "per_package": per_package,
    "decomposition_primary": d_primary,
    "sensitivity_no_vendor": {
        "note": "post-hoc structural sensitivity: drop dspy/_vendor from both frames",
        "v0.8.0": {**cov_summary(cov080n), "distinct_sites": len({site_key(r) for r in f080 if "/_vendor/" not in r["file"]})},
        "v0.9.1": {**cov_summary(cov091n), "distinct_sites": len({site_key(r) for r in f091 if "/_vendor/" not in r["file"]})},
        "decomposition": d_novendor,
        "per_package": per_package_novendor,
    },
    "sensitivity_exclude_dspy": {
        "note": "post-hoc structural sensitivity: drop the dspy package entirely",
        "v0.8.0": cov_summary({
            "failroute_total": cov080["failroute_total"] - per_pkg_080["dspy"]["failroute"],
            "union_covered": cov080["union_covered"] - per_pkg_080["dspy"]["covered"],
            "failroute_only": cov080["failroute_only"] - per_pkg_080["dspy"]["only"],
        }),
        "v0.9.1": cov_summary({
            "failroute_total": cov091["failroute_total"] - per_pkg_091["dspy"]["failroute"],
            "union_covered": cov091["union_covered"] - per_pkg_091["dspy"]["covered"],
            "failroute_only": cov091["failroute_only"] - per_pkg_091["dspy"]["only"],
        }),
        "decomposition": d_excl_dspy,
    },
    "leave_one_out": leave_one_out,
    "static_vs_empirical_v091": {
        "rows": len(pf),
        "disagreements": len(disagreements),
        "disagreement_rate_pct": round(len(disagreements) / len(pf) * 100, 2),
        "by_rule": dict(Counter(d["rule"] for d in disagreements)),
        "main_rules": {
            "rows": len([r for r in pf if r["rule"] != "name-shadowing"]),
            "disagreements": len([d for d in disagreements if d["rule"] != "name-shadowing"]),
        },
        "items": disagreements,
    },
    "suppress": {
        "v0.8.0": {"total": len(sup080), "covered": sup_cov_080.get("covered", 0)},
        "v0.9.1": {"total": len(sup091), "covered": sup_cov_091.get("covered", 0)},
        "note": "four selected linters, ±1 line; no semgrep",
    },
    "hypotheses": {
        "H1_pruning": {"pass": h1, "v080": len(f080), "v091": len(f091)},
        "H2_share_rises": {"pass": h2, "v080_pct": round(cov080["union_covered"] / cov080["failroute_total"] * 100, 2),
                            "v091_pct": round(cov091["union_covered"] / cov091["failroute_total"] * 100, 2)},
        "H3_covered_count_falls": {"pass": h3, "v080": cov080["union_covered"], "v091": cov091["union_covered"],
                                    "novendor_v080": cov080n["union_covered"], "novendor_v091": cov091n["union_covered"]},
        "H4_decomposition_signs": {"pass": h4, **d_primary, "novendor": d_novendor},
        "H5_suppress_uncovered": {"pass": h5, "v080": f"{sup_cov_080.get('covered', 0)}/{len(sup080)}",
                                   "v091": f"{sup_cov_091.get('covered', 0)}/{len(sup091)}"},
        "H6_static_empirical_agreement": {"pass": h6, "disagreements": len(disagreements), "rows": len(pf)},
    },
}

(DATA / "comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# Markdown table for the paper / README.
lines = []
lines.append("| Package | Version | .py | Lines | v0.8.0 findings | v0.8.0 covered | v0.8.0 share | v0.9.1 findings | v0.9.1 covered | v0.9.1 share |")
lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
for row in per_package:
    lines.append("| {name} | {version} | {py_files:,} | {lines:,} | {findings_v080} | {covered_v080} | {share_v080_pct:.1f}% | {findings_v091} | {covered_v091} | {share_v091_pct:.1f}% |".format(**row))
lines.append("| **total** | | **{:,}** | **{:,}** | **{}** | **{}** | **{:.1f}%** | **{}** | **{}** | **{:.1f}%** |".format(
    result["corpus"]["py_files"], result["corpus"]["lines"],
    cov080["failroute_total"], cov080["union_covered"], cov080["union_covered"] / cov080["failroute_total"] * 100,
    cov091["failroute_total"], cov091["union_covered"], cov091["union_covered"] / cov091["failroute_total"] * 100))
lines.append("")
lines.append("## Leave-one-package-out")
lines.append("")
lines.append("| Excluded | v0.8.0 findings/covered/share | v0.9.1 findings/covered/share | share change | covered change |")
lines.append("|---|---:|---:|---:|---:|")
for row in leave_one_out:
    lines.append("| {excluded} | {v080[total]}/{v080[covered]}/{v080[share_pct]:.1f}% | {v091[total]}/{v091[covered]}/{v091[share_pct]:.1f}% | {share_change_pp:+.2f} pp | {covered_change:+d} |".format(**row))
(DATA / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

print(json.dumps(result, ensure_ascii=False, indent=2))

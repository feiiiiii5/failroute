"""Stratified random sampling of exported failroute findings.

Reads a JSONL produced by ``failroute --export-findings`` (one object
per finding; if several exports are concatenated, records may span
multiple repositories) and draws a fixed-seed stratified sample over
(rule, repo) strata. The same seed reproduces the same sample.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fixed-seed stratified random sample of exported failroute findings."
    )
    parser.add_argument("findings", type=Path, help="JSONL produced by failroute --export-findings")
    parser.add_argument("--per-stratum", type=int, default=10, help="max findings per (rule, repo) stratum (default 10)")
    parser.add_argument("--seed", type=int, default=20260830, help="random seed (default 20260830)")
    parser.add_argument("--out", type=Path, required=True, help="output JSON (sample + per-stratum distribution)")
    args = parser.parse_args()

    records = [json.loads(line) for line in args.findings.read_text(encoding="utf-8").splitlines() if line.strip()]
    strata: dict[tuple[str, str], list[dict]] = {}
    for rec in records:
        strata.setdefault((rec["rule"], rec["repo"]), []).append(rec)

    rng = random.Random(args.seed)
    sample: list[dict] = []
    distribution: dict[str, dict[str, int]] = {}
    for key in sorted(strata):
        bucket = strata[key]
        ordered = sorted(bucket, key=lambda r: (r["file"], r["lineno"], r["id"]))
        picked = rng.sample(ordered, min(args.per_stratum, len(ordered)))
        sample.extend(picked)
        rule, repo = key
        label = f"{rule}@{repo or '(unlabelled)'}"
        distribution[label] = {"population": len(bucket), "sampled": len(picked)}

    out = {
        "seed": args.seed,
        "per_stratum": args.per_stratum,
        "source": str(args.findings),
        "total_findings": len(records),
        "strata": len(strata),
        "sampled_total": len(sample),
        "distribution": distribution,
        "sample": sample,
    }
    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    counts = Counter(rec["rule"] for rec in sample)
    print(f"wrote {args.out}: {len(sample)} sampled from {len(records)} across {len(strata)} strata")
    for rule in sorted(counts):
        print(f"  {rule}: {counts[rule]}")


if __name__ == "__main__":
    main()

"""Freeze the paper baseline record into bench/paper-baseline.json.

Captures the exact tool/corpus/environment state that produced the
8-repo comparison in bench/ruff-comparison.md. The eight upstream
clones were removed on 2026-08-30; this record preserves the scanned
paths and numbers as published, marked local_clones_removed=true.
"""

from __future__ import annotations

import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "bench" / "paper-baseline.json"


def load_repo_rows(md_text: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in md_text.splitlines():
        if not line.startswith("|") or line.startswith("| Repo") or line.startswith("|--"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 9:
            continue
        name, scanned_path = cells[0], cells[1]
        if name == "**total**":
            continue
        rows.append(
            {
                "name": name,
                "scanned_path": scanned_path.strip("`"),
                "failroute_total": int(cells[2]),
                "no_action": int(cells[3]),
                "semantic_fallback_masked": int(cells[4]),
                "silent_suppress": int(cells[5]),
                "ruff_s110_s112": int(cells[6]),
                "overlap": int(cells[7]),
                "failroute_only": int(cells[8]),
            }
        )
    return rows


def main() -> None:
    commit = (
        subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        .stdout.strip()
    )
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE).group(1)
    manifest = json.loads((ROOT / "tests/corpus/manifest.json").read_text(encoding="utf-8"))
    md = (ROOT / "bench/ruff-comparison.md").read_text(encoding="utf-8")
    repos = load_repo_rows(md)

    def col(key: str) -> int:
        return sum(int(r[key]) for r in repos)  # type: ignore[arg-type]

    record = {
        "frozen_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "failroute": {
            "commit": commit,
            "version": version,
        },
        "corpus": {
            "version": manifest["corpus_version"],
            "labelled": manifest["labelled"],
            "expected_true_positives": len(manifest["expected"]),
            "labelled_true_negatives": len(manifest["labelled_true_negatives"]),
        },
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "benchmark": {
            "source": "bench/ruff-comparison.md",
            "run": "2026-08-29 05:34 UTC",
            "totals": {
                "failroute": col("failroute_total"),
                "no_action": col("no_action"),
                "semantic_fallback_masked": col("semantic_fallback_masked"),
                "silent_suppress": col("silent_suppress"),
                "ruff_s110_s112": col("ruff_s110_s112"),
                "overlap": col("overlap"),
                "failroute_only": col("failroute_only"),
            },
            "local_clones_removed": True,
            "note": "Upstream clones under 'Open source/' were removed on 2026-08-30; "
            "paths and counts below are preserved verbatim from bench/ruff-comparison.md "
            "and cannot be reproduced without restoring those checkouts. Totals are column "
            "sums of the per-repo rows (the md total row omits the silent-suppress and "
            "scanned-path columns); the sums match the md total row on all shared columns "
            "(670/217/449/79/70/600).",
            "repos": repos,
        },
    }
    OUT.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

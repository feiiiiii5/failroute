#!/usr/bin/env python3
"""J1: fetch the diffs of the 52 title-screened merged PRs for diff-read re-adjudication.

Recall denominator integrity: merged-pr-recall.csv marks 52 merged PRs as
`belongs_to_family=no` with note "(title-screened)" — judged by title only.
Any misjudgement invalidates the recall denominator. This script fetches each
PR's diff and merge-commit sha (traceability) via gh, one subprocess per call
with a hard timeout (shell loops hung on gh in the previous batch).

Outputs (under /tmp/j1 by default):
  meta.json               repo/pr -> {title, merge_commit_sha, diff_lines, bytes}
  diffs/<repo>_<num>.diff raw diff

Exit non-zero if any fetch fails; nothing is silently skipped.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def gh(args: list[str], accept: str | None = None, timeout: int = 30) -> str:
    cmd = ["gh", "api", *args]
    if accept:
        cmd += ["-H", f"Accept: {accept}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"gh api {' '.join(args[:3])} rc={r.returncode}: {r.stderr.strip()[:200]}")
    return r.stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/j1")
    ap.add_argument("--sleep", type=float, default=2.0)
    args = ap.parse_args()

    out = Path(args.out)
    (out / "diffs").mkdir(parents=True, exist_ok=True)
    csv_path = ROOT / "paper" / "merged-pr-recall.csv"
    if not csv_path.is_file():
        sys.exit(f"error: missing {csv_path}")
    rows = [r for r in csv.DictReader(open(csv_path)) if "title-screened" in r["note"]]
    if not rows:
        sys.exit("error: no title-screened rows found")
    print(f"title-screened rows: {len(rows)}")

    meta: dict[str, dict] = {}
    failures = []
    for i, r in enumerate(rows, 1):
        repo, num = r["repo"], r["pr_number"]
        key = f"{repo}#{num}"
        diff_path = out / "diffs" / f"{repo.replace('/', '_')}_{num}.diff"
        if diff_path.is_file() and diff_path.stat().st_size > 0 and key in meta:
            continue
        try:
            info = json.loads(gh([f"repos/{repo}/pulls/{num}"]))
            diff = gh([f"repos/{repo}/pulls/{num}"], accept="application/vnd.github.diff")
            diff_path.write_text(diff, encoding="utf-8")
            meta[key] = {
                "title": info.get("title", ""),
                "merge_commit_sha": info.get("merge_commit_sha"),
                "merged_at": info.get("merged_at"),
                "diff_lines": len(diff.splitlines()),
                "bytes": len(diff),
            }
            print(f"[{i}/{len(rows)}] {key}: {len(diff.splitlines())} lines")
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            failures.append((key, str(e)[:160]))
            print(f"[{i}/{len(rows)}] {key}: FAILED {str(e)[:120]}")
        time.sleep(args.sleep)

    (out / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nfetched {len(meta)}/{len(rows)}; failures={len(failures)}")
    for k, e in failures:
        print(f"  FAIL {k}: {e}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

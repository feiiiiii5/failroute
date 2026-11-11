"""Exploratory merged-PR location matching, not semantic defect detection.

Scan base-side Python files at the merge commit's first parent. Match findings
within +/-3 lines of removed lines or pure-insertion anchors. This revised
protocol does not regenerate or validate the manuscript's historical ratios.
See docs/merged-pr-matching-protocol.md for definitions and limitations.
Read-only against upstreams. Pass --out to a fresh CSV for a new run.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = Path("/tmp/a3")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+")


def gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def get_diff(repo: str, pr: str) -> str:
    cached = OUT_DIR / f"diff_{repo.replace('/', '_')}_{pr}.diff"
    if cached.exists() and cached.stat().st_size > 0:
        return cached.read_text(encoding="utf-8")
    proc = gh("api", f"repos/{repo}/pulls/{pr}", "-H", "Accept: application/vnd.github.diff")
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"Cannot fetch diff for {repo}#{pr}: {proc.stderr.strip()}")
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(proc.stdout, encoding="utf-8")
    return proc.stdout


def base_sites(diff_text: str) -> tuple[dict[str, set[int]], dict[str, set[int]]]:
    """Return removed lines and pure-insertion anchors, keyed by OLD Python path.

    An insertion anchor is the preceding base line, clamped to line 1 at BOF.
    Consecutive +/- lines form one edit block: replacements contribute removed
    lines only. New files have no base-side site and are excluded.
    """
    removed: dict[str, set[int]] = {}
    insertions: dict[str, set[int]] = {}
    cur_file: str | None = None
    pre_line = 0
    in_hunk = False
    block_removed = False
    insertion_anchor: int | None = None

    def flush() -> None:
        nonlocal block_removed, insertion_anchor
        if cur_file and insertion_anchor is not None and not block_removed:
            insertions.setdefault(cur_file, set()).add(insertion_anchor)
        block_removed = False
        insertion_anchor = None

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            flush()
            cur_file = None
            in_hunk = False
        elif not in_hunk and line.startswith("--- "):
            path = line[4:].split("\t", 1)[0]
            if path.startswith('"'):
                # Git quotes paths with spaces/control or non-ASCII bytes using
                # C escapes; JSON handles the common quoted ASCII path case.
                try:
                    path = json.loads(path)
                except ValueError:
                    raise ValueError("Unsupported quoted diff path; use git -c core.quotePath=false diff") from None
            cur_file = path[2:] if path.startswith("a/") and path.endswith(".py") else None
        elif line.startswith("@@"):
            flush()
            match = HUNK.match(line)
            in_hunk = match is not None
            if match:
                pre_line = int(match.group(1))
                # A zero-length old range names the line BEFORE the insertion.
                if match.group(2) == "0":
                    pre_line += 1
        elif in_hunk:
            if line.startswith("-"):
                if cur_file:
                    removed.setdefault(cur_file, set()).add(pre_line)
                block_removed = True
                pre_line += 1
            elif line.startswith("+"):
                if insertion_anchor is None:
                    insertion_anchor = max(1, pre_line - 1)
            elif line.startswith(" "):
                flush()
                pre_line += 1
            elif line.startswith("\\ No newline"):
                pass
            else:
                flush()
                in_hunk = False
    flush()
    return removed, insertions


def removed_sites(diff_text: str) -> dict[str, set[int]]:
    """Base-side removed lines only (legacy selection, corrected rename paths)."""
    return base_sites(diff_text)[0]


def changed_sites(diff_text: str) -> dict[str, set[int]]:
    """Union of removed lines and pure-insertion anchors for proximity matching."""
    removed, insertions = base_sites(diff_text)
    return {path: removed.get(path, set()) | insertions.get(path, set())
            for path in removed.keys() | insertions.keys()}


def nearby_findings(findings: list[dict], lines: set[int], tolerance: int = 3) -> list[dict]:
    """Location proximity only; does not establish semantic correspondence."""
    if tolerance < 0:
        raise ValueError("tolerance must be nonnegative")
    return [finding for finding in findings
            if any(abs(finding["lineno"] - line) <= tolerance for line in lines)]


def pre_fix_sha(repo: str, pr: str) -> tuple[str, str]:
    proc = gh("api", f"repos/{repo}/pulls/{pr}", "--jq", ".merge_commit_sha")
    if proc.returncode != 0 or not proc.stdout.strip() or proc.stdout.strip() == "null":
        raise RuntimeError(f"Cannot resolve merge commit for {repo}#{pr}")
    merge_sha = proc.stdout.strip()
    proc = gh("api", f"repos/{repo}/commits/{merge_sha}", "--jq", ".parents[0].sha")
    if proc.returncode != 0 or not proc.stdout.strip() or proc.stdout.strip() == "null":
        raise RuntimeError(f"Cannot resolve first parent for {repo}#{pr}")
    return merge_sha, proc.stdout.strip()


def fetch_file(repo: str, path: str, ref: str) -> str | None:
    from urllib.parse import quote

    proc = gh(
        "api", f"repos/{repo}/contents/{quote(path)}?ref={ref}",
        "--jq", ".content",
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return base64.b64decode(proc.stdout.strip()).decode("utf-8", errors="replace")
    except Exception:  # failroute: ignore
        # Intentional: None means "file not retrievable at this ref" and every caller
        # branches on it; the row is then written with location_match="n/a" rather than
        # counted as a miss. Same contract as the returncode check three lines up.
        return None


def run_failroute(path: Path) -> list[dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "failroute", "--format", "json", str(path)],
        capture_output=True, text=True, cwd=ROOT,
    )
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"failroute failed for {path}: {proc.stderr.strip()}")
    return [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "paper" / "merged-pr-recall.csv")
    parser.add_argument("--allow-overwrite-frozen", action="store_true")
    args = parser.parse_args(argv)
    from _frozen_guard import guard_output

    guard_output(args.out, args.allow_overwrite_frozen)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Manual notes where the automated pipeline cannot express the verdict.
    notes_override = {
        ("microsoft/PyRIT", "2460"): "TypeScript (web UI); failroute is Python-only -> out of language scope",
        ("cvs-health/uqlm", "418"): "pure-additive fix; pre-fix defect is a non-handler implicit-None "
        "(function violates -> float contract) which the six detectors do not cover by design",
    }
    candidates = Path(__file__).resolve().parent / "a3_candidates.tsv"
    prs = [line.split("\t") for line in candidates.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = []
    for repo, pr, family, title in prs:
        override = notes_override.get((repo, pr))
        diff = get_diff(repo, pr)
        sites = changed_sites(diff)
        if not sites:
            rows.append({"repo": repo, "pr_number": pr, "pr_title": title,
                         "belongs_to_family": family, "pre_fix_sha": "",
                         "file": "", "line": "", "location_match": "n/a",
                         "rule_matched": "", "note": override or "no base-side Python sites (new files and non-Python files excluded)"})
            continue
        merge_sha, prefix_sha = pre_fix_sha(repo, pr)
        matched_rules: set[str] = set()
        matched_sites: list[str] = []
        scanned: list[str] = []
        for fpath, lines in sorted(sites.items()):
            content = fetch_file(repo, fpath, prefix_sha)
            if content is None:
                continue
            local = OUT_DIR / ("prefix_" + fpath.replace("/", "__"))
            local.write_text(content, encoding="utf-8")
            scanned.append(fpath)
            hits = nearby_findings(run_failroute(local), lines)
            for h in hits:
                matched_rules.add(h["mode"])
                matched_sites.append(f"{fpath}:{h['lineno']}({h['mode']})")
        location_match = "yes" if matched_sites else ("no" if len(scanned) == len(sites) else "n/a")
        rows.append({
            "repo": repo, "pr_number": pr, "pr_title": title,
            "belongs_to_family": family,
            "pre_fix_sha": prefix_sha,
            "file": ";".join(scanned),
            "line": ";".join(f"{f}:{sorted(sites[f])[0]}" for f in scanned),
            "location_match": location_match,
            "rule_matched": ";".join(sorted(matched_rules)),
            "note": (("location proximity only: " + "; ".join(matched_sites)) if matched_sites else "")
            + ("; incomplete base-file retrieval" if len(scanned) != len(sites) else "")
            + (("; " + override) if override else ""),
        })
        print(f"{repo}#{pr}: prefix={prefix_sha[:12]} files={len(scanned)} "
              f"location_match={location_match} rules={sorted(matched_rules)}")
    out_csv = args.out
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out_csv}")


if __name__ == "__main__":
    main()

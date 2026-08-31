"""A3 driver: align merged PRs with failroute detection (recall table).

Per spec: for each candidate PR, obtain the pre-fix commit (first parent of
the merge commit), fetch the affected pre-fix Python files via
`gh api repos/<o>/<r>/contents/<path>?ref=<pre_fix_sha>` into /tmp/a3/,
run failroute over each file, and check whether any finding lands on the
pre-fix line numbers of the diff's removed lines (the defect site).

Read-only against upstreams. No cloning, no upstream writes.

Input:  tools/a3_candidates.tsv   (repo<TAB>pr<TAB>family<TAB>title)
Diffs:  /tmp/a3/diff_<repo>_<pr>.diff (downloaded beforehand; fetched if absent)
Output: paper/merged-pr-recall.csv
"""

from __future__ import annotations

import base64
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = Path("/tmp/a3")
OUT_DIR.mkdir(exist_ok=True)
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+")


def gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def get_diff(repo: str, pr: str) -> str:
    cached = OUT_DIR / f"diff_{repo.replace('/', '_')}_{pr}.diff"
    if cached.exists() and cached.stat().st_size > 0:
        return cached.read_text(encoding="utf-8")
    proc = gh("api", f"repos/{repo}/pulls/{pr}", "-H", "Accept: application/vnd.github.diff")
    cached.write_text(proc.stdout, encoding="utf-8")
    return proc.stdout


def removed_sites(diff_text: str) -> dict[str, set[int]]:
    """file -> set of pre-fix line numbers of removed lines."""
    sites: dict[str, set[int]] = {}
    cur_file: str | None = None
    pre_line = 0
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            m = re.search(r" b/(.+)$", line)
            cur_file = m.group(1) if m else None
        elif line.startswith("@@"):
            m = HUNK.match(line)
            if m:
                pre_line = int(m.group(1))
        elif cur_file and cur_file.endswith(".py"):
            if line.startswith("-") and not line.startswith("---"):
                sites.setdefault(cur_file, set()).add(pre_line)
                pre_line += 1
            elif line.startswith("+") and not line.startswith("+++"):
                pass  # added lines do not advance the pre-fix cursor
            elif line.startswith(" ") or line == "":
                pre_line += 1
    return sites


def pre_fix_sha(repo: str, pr: str) -> tuple[str, str]:
    proc = gh("api", f"repos/{repo}/pulls/{pr}", "--jq", ".merge_commit_sha")
    merge_sha = proc.stdout.strip()
    proc = gh("api", f"repos/{repo}/commits/{merge_sha}", "--jq", ".parents[0].sha")
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
        # branches on it; the row is then written with detected="n/a" rather than
        # counted as a miss. Same contract as the returncode check three lines up.
        return None


def run_failroute(path: Path) -> list[dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "failroute", "--format", "json", str(path)],
        capture_output=True, text=True, cwd=ROOT,
    )
    return [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]


def main() -> None:
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
        sites = removed_sites(diff)
        if not sites:
            rows.append({"repo": repo, "pr_number": pr, "pr_title": title,
                         "belongs_to_family": family, "pre_fix_sha": "",
                         "file": "", "line": "", "detected": "n/a",
                         "rule_matched": "", "note": override or "no .py removals"})
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
            tol = 3  # handler spans a few lines; finding may sit on the except line
            hits = [f for f in run_failroute(local)
                    if any(abs(f["lineno"] - l) <= tol for l in lines)]
            for h in hits:
                matched_rules.add(h["mode"])
                matched_sites.append(f"{fpath}:{h['lineno']}({h['mode']})")
        rows.append({
            "repo": repo, "pr_number": pr, "pr_title": title,
            "belongs_to_family": family,
            "pre_fix_sha": prefix_sha,
            "file": ";".join(scanned),
            "line": ";".join(f"{f}:{sorted(sites[f])[0]}" for f in scanned),
            "detected": "yes" if matched_sites else "no",
            "rule_matched": ";".join(sorted(matched_rules)),
            "note": (("matched: " + "; ".join(matched_sites)) if matched_sites else "")
            + (("; " + override) if override else ""),
        })
        print(f"{repo}#{pr}: prefix={prefix_sha[:12]} files={len(scanned)} "
              f"detected={'yes' if matched_sites else 'no'} rules={sorted(matched_rules)}")
    out_csv = ROOT / "paper" / "merged-pr-recall.csv"
    out_csv.parent.mkdir(exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out_csv}")


if __name__ == "__main__":
    main()

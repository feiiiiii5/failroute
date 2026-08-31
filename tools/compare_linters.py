"""Cross-linter comparison for the failroute paper (self-scan + corpus scope).

The eight upstream benchmark clones were removed on 2026-08-30, so this
script compares failroute against ruff / Bandit / pylint / flake8(+bugbear)
/ semgrep *only* over failroute's own source tree (``src/failroute``) and
the labelled benchmark corpus (``tests/corpus``).

This is the "self-scan + corpus" scope. It is NOT the 8-repo scope of
bench/ruff-comparison.md and must not be mixed with or substituted for it.

Outputs: bench/linter-comparison.json and bench/linter-comparison.md.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
TARGETS = {"src/failroute": ROOT / "src" / "failroute", "tests/corpus": ROOT / "tests" / "corpus"}

FLAKE8_LINE = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+):\d+: (?P<code>[A-Z]\d+) (?P<msg>.*)$")


def _run(cmd: list[str], extra_env: dict[str, str] | None = None) -> tuple[int, str, str]:
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, env=env)
    return proc.returncode, proc.stdout, proc.stderr


def _version(cmd: list[str]) -> str:
    code, out, err = _run(cmd)
    return (out or err).strip().splitlines()[0] if (out or err).strip() else "unknown"


def run_failroute() -> tuple[list[dict], list[str]]:
    findings: list[dict] = []
    cmds = []
    for label, path in TARGETS.items():
        cmd = [
            PY, "-m", "failroute", "--format", "json", str(path),
        ]
        cmds.append(f"PYTHONPATH=src {' '.join(cmd[1:])}")
        code, out, _ = _run(cmd, {"PYTHONPATH": str(ROOT / "src")})
        for line in out.splitlines():
            if line.strip():
                rec = json.loads(line)
                rec["target"] = label
                findings.append(rec)
    return findings, cmds


def run_ruff() -> tuple[list[dict], list[str], str]:
    version = _version(["ruff", "--version"])
    rows: list[dict] = []
    cmds = []
    for label, path in TARGETS.items():
        cmd = ["ruff", "check", "--select", "S110,S112", "--output-format", "json", str(path)]
        cmds.append(" ".join(cmd))
        code, out, err = _run(cmd)
        if code not in (0, 1):
            continue
        for item in json.loads(out or "[]"):
            rows.append({
                "file": item["filename"], "line": item["location"]["row"],
                "code": item["code"], "target": label,
            })
    return rows, cmds, version


def run_bandit() -> tuple[list[dict], list[str], str]:
    raw = _version([PY, "-m", "bandit", "--version"])
    version = "bandit " + raw.split()[-1] if raw else "unknown"
    rows: list[dict] = []
    cmds = []
    for label, path in TARGETS.items():
        cmd = [PY, "-m", "bandit", "-r", str(path), "-f", "json", "-q",
               "-t", "B110,B112"]
        cmds.append(" ".join(cmd))
        code, out, _ = _run(cmd)
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            continue
        for item in data.get("results", []):
            rows.append({
                "file": item["filename"], "line": item["line_number"],
                "code": item["test_id"], "target": label,
            })
    return rows, cmds, version


def run_pylint() -> tuple[list[dict], list[str], str]:
    version = _version([PY, "-m", "pylint", "--version"])
    rows: list[dict] = []
    cmds = []
    for label, path in TARGETS.items():
        files = sorted(path.rglob("*.py"))
        cmd = [PY, "-m", "pylint", "--disable=all",
               "--enable=W0702,W0703,W0705,W0706",
               "--output-format=json", "--score=no", *map(str, files)]
        cmds.append(f"python -m pylint --disable=all --enable=W0702,W0703,W0705,W0706 --output-format=json --score=no <{label}/*.py>")
        code, out, _ = _run(cmd)
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            continue
        for item in data:
            if item["message-id"] not in {"W0702", "W0703", "W0705", "W0706"}:
                continue
            rows.append({
                "file": item["path"], "line": item["line"],
                "code": item["message-id"], "target": label,
            })
    return rows, cmds, version


def run_flake8() -> tuple[list[dict], list[str], str]:
    raw = _version([PY, "-m", "flake8", "--version"])
    version = "flake8 " + raw if raw else "unknown"
    rows: list[dict] = []
    cmds = []
    for label, path in TARGETS.items():
        cmd = [PY, "-m", "flake8", "--select=E722,B001,B017", str(path)]
        cmds.append(" ".join(cmd[1:]))
        code, out, _ = _run(cmd)
        for line in out.splitlines():
            m = FLAKE8_LINE.match(line)
            if m:
                rows.append({
                    "file": m.group("file"), "line": int(m.group("line")),
                    "code": m.group("code"), "target": label,
                })
    return rows, cmds, version


def run_semgrep() -> tuple[list[dict], list[str], str]:
    if shutil.which("semgrep") is None and _run([PY, "-m", "semgrep", "--version"])[0] != 0:
        return [], [], "not installed"
    version = _version([PY, "-m", "semgrep", "--version"])
    rule = ROOT / "bench" / "semgrep-failure-routing.yml"
    rule.write_text(
        """rules:
  - id: try-except-pass
    pattern: |
      try:
        ...
      except ...:
        pass
    message: exception swallowed with pass
    languages: [python]
    severity: WARNING
  - id: try-except-continue
    pattern: |
      try:
        ...
      except ...:
        continue
    message: exception swallowed with continue
    languages: [python]
    severity: WARNING
""",
        encoding="utf-8",
    )
    rows: list[dict] = []
    cmds = []
    for label, path in TARGETS.items():
        cmd = [PY, "-m", "semgrep", "--config", str(rule), "--json", "--quiet", str(path)]
        cmds.append("python -m semgrep --config bench/semgrep-failure-routing.yml --json --quiet " + str(path))
        code, out, _ = _run(cmd)
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            continue
        for item in data.get("results", []):
            rows.append({
                "file": item["path"], "line": item["start"]["line"],
                "code": item["check_id"], "target": label,
            })
    return rows, cmds, version


def main() -> None:
    failroute_findings, failroute_cmds = run_failroute()
    ruff_rows, ruff_cmds, ruff_version = run_ruff()
    bandit_rows, bandit_cmds, bandit_version = run_bandit()
    pylint_rows, pylint_cmds, pylint_version = run_pylint()
    flake8_rows, flake8_cmds, flake8_version = run_flake8()
    semgrep_rows, semgrep_cmds, semgrep_version = run_semgrep()

    tools = {
        "failroute": {"version": "(this repo, see bench/paper-baseline.json)", "rows": failroute_findings, "cmds": failroute_cmds, "line_key": "lineno"},
        "ruff": {"version": ruff_version, "rows": ruff_rows, "cmds": ruff_cmds, "line_key": "line"},
        "bandit": {"version": bandit_version, "rows": bandit_rows, "cmds": bandit_cmds, "line_key": "line"},
        "pylint": {"version": pylint_version, "rows": pylint_rows, "cmds": pylint_cmds, "line_key": "line"},
        "flake8+bugbear": {"version": flake8_version, "rows": flake8_rows, "cmds": flake8_cmds, "line_key": "line"},
        "semgrep": {"version": semgrep_version, "rows": semgrep_rows, "cmds": semgrep_cmds, "line_key": "line"},
    }

    # Per-tool counts, then overlap with failroute findings (same file, |dline| <= 1).
    def index(rows: list[dict], key: str) -> dict[tuple[str, str], set[int]]:
        idx: dict[tuple[str, str], set[int]] = {}
        for r in rows:
            idx.setdefault((str(Path(r["file"]).name), r["target"]), set()).add(int(r[key]))
        return idx

    fr_idx = index(failroute_findings, "lineno")
    summary: dict[str, dict[str, object]] = {}
    for name, info in tools.items():
        rows = info["rows"]
        key = info["line_key"]
        per_code: dict[str, int] = {}
        for r in rows:
            per_code[r["code"] if name != "failroute" else r["mode"]] = (
                per_code.get(r["code"] if name != "failroute" else r["mode"], 0) + 1
            )
        if name == "failroute":
            matched = len(rows)
        else:
            idx = index(rows, key)
            matched = 0
            for f in failroute_findings:
                fname = (Path(f["file"]).name, f["target"])
                lines = idx.get(fname, set())
                if any(abs(f["lineno"] - l) <= 1 for l in lines):
                    matched += 1
        summary[name] = {
            "version": info["version"],
            "total_rows": len(rows),
            "per_code": per_code,
            "failroute_findings_matched_within_1_line": matched,
            "commands": info["cmds"],
        }

    out = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": "self-scan + corpus ONLY (src/failroute and tests/corpus). "
        "NOT the 8-repo scope of bench/ruff-comparison.md; the upstream clones "
        "were removed on 2026-08-30 and must not be re-cloned for this task.",
        "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
        "failroute_findings_total": len(failroute_findings),
        "tools": summary,
    }
    (ROOT / "bench" / "linter-comparison.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    md = ["# Cross-linter comparison — self-scan + corpus scope (NOT the 8-repo scope)", ""]
    md.append(f"Generated: {out['generated_at_utc']} · Python {out['environment']['python']} · {out['environment']['platform']}")
    md.append("")
    md.append("> 🔴 Scope: failroute's own source (`src/failroute`) + labelled corpus (`tests/corpus`).")
    md.append("> The corpus is intentionally invalid Python; tools that reject unparseable files will under-report there.")
    md.append("> This table does not replace `bench/ruff-comparison.md` (8-repo scope, clones removed 2026-08-30).")
    md.append("")
    md.append("| tool | version | findings | per-code | failroute findings matched (±1 line) |")
    md.append("|---|---|---|---|---|")
    for name, s in summary.items():
        per = ", ".join(f"{k}:{v}" for k, v in sorted(s["per_code"].items())) or "—"
        md.append(f"| {name} | {s['version']} | {s['total_rows']} | {per} | {s['failroute_findings_matched_within_1_line']} |")
    md.append("")
    md.append("## Full commands")
    md.append("")
    for name, s in summary.items():
        md.append(f"**{name}** ({s['version']}):")
        for c in s["commands"]:
            md.append(f"```\n{c}\n```")
        md.append("")
    md.append("## Reproducing the full 8-repo comparison (if clones are restored later)")
    md.append("")
    md.append("1. Restore the eight checkouts at the exact paths recorded in `bench/ruff-comparison.md` / `bench/paper-baseline.json` (git clone at the commit that produced the 2026-08-29 numbers is NOT pinned — re-run against the same paths and re-freeze).")
    md.append("2. For each repo: `PYTHONPATH=src python -m failroute --export-findings <out.jsonl> --repo-name <name> <scanned_path>` and `ruff check --select S110,S112 --output-format json <scanned_path>` (plus the bandit/pylint/flake8 commands above, one directory per repo).")
    md.append("3. Compute overlap by file+line (±1 line tolerance) and regenerate the table; record new totals in a NEW file, never overwrite `bench/ruff-comparison.md` (frozen baseline).")
    (ROOT / "bench" / "linter-comparison.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"wrote bench/linter-comparison.json and bench/linter-comparison.md")
    for name, s in summary.items():
        print(f"  {name}: {s['total_rows']} rows, matched {s['failroute_findings_matched_within_1_line']}/{len(failroute_findings)}")


if __name__ == "__main__":
    main()

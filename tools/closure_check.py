#!/usr/bin/env python3
"""I4 closure check — the single gate that proves failroute has no loose ends.

Runs eight independent checks and prints one line per check:
PASS / KNOWN-OPEN / FAIL. Exit code = number of FAIL lines.

Honesty rule: a check that cannot be satisfied is reported as-is. Items may
be registered KNOWN-OPEN *with a reason*; a KNOWN-OPEN entry whose check
starts passing is flagged STALE so the registry cannot hide a closed item.
Loosening a check to force green invalidates the whole batch.

Usage:  PYTHONPATH=src .venv/bin/python tools/closure_check.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (check id, why it cannot be closed yet, what would close it).
# Deliberately empty at delivery time: every check is PASS. If a future
# change makes one unsatisfiable, add it here WITH a reason — never relax
# the check itself.
KNOWN_OPEN: dict[str, tuple[str, str]] = {}


def version_locations() -> dict[str, str]:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    init = (ROOT / "src" / "failroute" / "__init__.py").read_text(encoding="utf-8")
    action = (ROOT / "action" / "action.yml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    cli = subprocess.run(
        [sys.executable, "-m", "failroute", "--version"],
        capture_output=True, text=True, cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"},
    ).stdout.strip().split()[-1]
    return {
        "--version": cli,
        "pyproject": re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1),
        "__init__": re.search(r'__version__ = "([^"]+)"', init).group(1),
        "action.yml": re.search(r'failroute-version:.*?default: "([^"]+)"', action, re.S).group(1),
        "README rev": re.search(r"rev: v([\d.]+)", readme).group(1),
    }


def check_versions() -> tuple[bool, str]:
    locs = version_locations()
    uniq = set(locs.values())
    detail = " ".join(f"{k}={v}" for k, v in locs.items())
    return (len(uniq) == 1, detail)


def check_tests() -> tuple[bool, str]:
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header"],
        capture_output=True, text=True, cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin:/usr/local/bin"},
    )
    last = (r.stdout + r.stderr).strip().splitlines()[-1] if (r.stdout + r.stderr).strip() else "no output"
    ok = r.returncode == 0 and "failed" not in last and "error" not in last.lower()
    skipped = re.search(r"(\d+) skipped", last)
    if skipped and int(skipped.group(1)) > 0:
        ok = ok and "skipif" in (r.stdout + r.stderr)  # unexpected skips would need review
    return (ok, last.strip())


def check_self_scan() -> tuple[bool, str]:
    sys.path.insert(0, str(ROOT / "src"))
    from failroute.analyzer import scan_repo  # noqa: PLC0415

    findings = scan_repo(ROOT / "src")
    return (len(findings) == 0, f"self-scan findings={len(findings)}")


def check_readme_numbers() -> tuple[bool, str]:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    stale = []
    for token in ("649", "253", "39.0%", "61.0%", "43.0%", "396", "279"):
        if token in readme:
            stale.append(token)
    required = ["621 findings", "**250**", "40.3%", "**269**", "43.3%", "**371**", "59.7%"]
    missing = [t for t in required if t not in readme]
    ok = not stale and not missing
    return (ok, f"stale={stale or 'none'} missing={missing or 'none'}")


def check_artifact() -> tuple[bool, str]:
    art = (ROOT / "paper" / "ARTIFACT.md").read_text(encoding="utf-8")
    bad = [m for m in re.findall(r".{0,60}could not re-derive.{0,60}", art, re.I)]
    return (not bad, bad[0].strip() if bad else "no 'could not re-derive' open items")


def check_roadmap() -> tuple[bool, str]:
    rm = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    bad = re.findall(r".{0,60}~?\d+-\d+%.{0,60}", rm)
    return (not bad, bad[0].strip() if bad else "no unmeasured percentage estimates")


def check_source_todos() -> tuple[bool, str]:
    hits = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\b(TODO|FIXME|XXX)\b", line):
                hits.append(f"{path.relative_to(ROOT)}:{i}")
    return (not hits, ", ".join(hits[:5]) if hits else "no TODO/FIXME/XXX in src/")


def check_git_clean() -> tuple[bool, str]:
    r = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=ROOT)
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    return (not lines, f"{len(lines)} uncommitted path(s)")


CHECKS = [
    ("versions", check_versions),
    ("tests", check_tests),
    ("self_scan", check_self_scan),
    ("readme_numbers", check_readme_numbers),
    ("artifact", check_artifact),
    ("roadmap", check_roadmap),
    ("source_todos", check_source_todos),
    ("git_clean", check_git_clean),
]


def main() -> int:
    fails = 0
    print(f"{'check':<16} {'status':<12} detail")
    for name, fn in CHECKS:
        ok, detail = fn()
        if ok:
            if name in KNOWN_OPEN:
                print(f"{name:<16} {'STALE':<12} registered KNOWN-OPEN but now passes: {KNOWN_OPEN[name][0]}")
                fails += 1
            else:
                print(f"{name:<16} {'PASS':<12} {detail}")
        else:
            if name in KNOWN_OPEN:
                why, closes = KNOWN_OPEN[name]
                print(f"{name:<16} {'KNOWN-OPEN':<12} {detail} | why: {why} | closes when: {closes}")
            else:
                print(f"{name:<16} {'FAIL':<12} {detail}")
                fails += 1
    print(f"\nCLOSURE: {'CLOSED' if fails == 0 else f'{fails} FAIL'}")
    return fails


if __name__ == "__main__":
    raise SystemExit(main())

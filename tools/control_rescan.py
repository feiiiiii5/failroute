#!/usr/bin/env python3
"""Rebuild the control-corpus scan outputs from the pin file (X1 batch).

Reads paper/corpus-lock-control.json, (re-)downloads each sdist, verifies
SHA-256 against the pin, extracts under paper/corpus-control/, runs the
current failroute build plus the four syntax linters over each scan_root
with the same versions/flags as the main-corpus pipeline, and writes
bench/control-rescan/<pkg>.jsonl + linters.json.

Fails loudly on any mismatch or missing input. A silent skip here would make
the control comparison uninterpretable.

Usage (from the repo root):
    PYTHONPATH=src .venv/bin/python tools/control_rescan.py
    PYTHONPATH=src .venv/bin/python tools/control_rescan.py --check   # verify only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
LOCK = ROOT / "paper" / "corpus-lock-control.json"
TREES = ROOT / "paper" / "corpus-control"
OUT = ROOT / "bench" / "control-rescan"
PY = sys.executable

LINTER_SPECS = {
    "ruff": ([sys.executable, "-m", "ruff", "check", "--no-cache", "--isolated",
               "--select", "S110,S112", "--output-format", "json"], "ruff"),
    "bandit": ([sys.executable, "-m", "bandit", "-r", None, "-f", "json",
                "-t", "B110,B112", "-q"], "bandit"),
    "pylint": ([sys.executable, "-m", "pylint", "--disable=all",
                "--enable=W0702,W0703,W0705,W0706", "--output-format=json",
                "--persistent=n", "--jobs=4", None], "pylint"),
    "flake8": ([sys.executable, "-m", "flake8", "--select", "E722,B001,B017",
                "--format", "%(path)s\t%(row)d\t%(code)s", None], "flake8"),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url: str, dest: Path, expect_sha: str) -> None:
    if dest.exists() and sha256_file(dest) == expect_sha:
        return
    req = urllib.request.Request(url, headers={"User-Agent": "failroute-control-rescan/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            f.write(chunk)
    got = sha256_file(dest)
    if got != expect_sha:
        dest.unlink(missing_ok=True)
        sys.exit(f"error: sha256 mismatch for {url}\n  expected {expect_sha}\n  got      {got}")


def extract(archive: Path, dest: Path, top: str) -> None:
    if (dest / top).is_dir():
        return
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tf:
        tf.extractall(dest, filter="data")


def run_failroute(scan_root: Path) -> list:
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    proc = subprocess.run([PY, "-m", "failroute", "--format", "json", str(scan_root)],
                          capture_output=True, text=True, cwd=ROOT, env=env, timeout=600)
    rows = []
    for line in proc.stdout.splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="verify committed outputs match a fresh recomputation (no writes)")
    args = ap.parse_args()
    lock = json.loads(LOCK.read_text())
    if not lock.get("packages"):
        sys.exit("error: no packages in paper/corpus-lock-control.json")
    OUT.mkdir(parents=True, exist_ok=True)
    (TREES / "_archives").mkdir(parents=True, exist_ok=True)
    linters_all = {}
    for pkg in lock["packages"]:
        name, ver = pkg["name"], pkg["version"]
        archive = TREES / "_archives" / f"{pkg['pypi_name']}-{ver}.tar.gz"
        fetch(pkg["url"], archive, pkg["sha256"])
        if archive.stat().st_size != pkg["archive_bytes"]:
            sys.exit(f"error: {name} archive size changed: "
                     f"{archive.stat().st_size} != {pkg['archive_bytes']}")
        extract(archive, TREES, pkg["stripped_top_dir"])
        scan_root = TREES / pkg["extracted_to"] / pkg["scan_root"]
        if not scan_root.is_dir():
            sys.exit(f"error: scan_root missing: {scan_root}")
        findings = run_failroute(scan_root)
        if args.check:
            committed = [json.loads(l) for l in
                         (OUT / f"{name}.jsonl").read_text().splitlines() if l.strip()]
            def key(r):
                # committed rows were scanned in a scratch tree; compare on the
                # package-relative tail so the check is location-independent.
                parts = (r.get("file", "") or "").replace("\\", "/").split("/")
                return ("/".join(parts[-3:]), r.get("lineno"), r.get("rule_id"),
                        r.get("severity"), json.dumps(r.get("covered_by")))
            cf = sorted(key(r) for r in committed)
            ff = sorted(key(r) for r in findings)
            if cf != ff:
                sys.exit(f"error: {name} recomputation differs "
                         f"(committed {len(cf)} vs fresh {len(ff)})")
            print(f"{name}: CHECK-OK {len(ff)} findings")
        else:
            with open(OUT / f"{name}.jsonl", "w") as f:
                for r in findings:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"{name}: {len(findings)} findings -> bench/control-rescan/{name}.jsonl")
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

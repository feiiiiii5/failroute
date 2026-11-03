#!/usr/bin/env python3
"""Recompute four/five-tool warning coverage without overwriting frozen exports.

Install the documented paper toolchain first. A new output directory is required;
raw corpus inputs must already have been fetched with tools/fetch_corpus.py.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(output: Path, *, semgrep: bool = False) -> None:
    output = output.resolve()
    if output.exists():
        raise ValueError(f"output directory already exists: {output}; choose a new directory")
    if not (ROOT / "paper/corpus").is_dir():
        raise ValueError("pinned corpus is missing; run tools/fetch_corpus.py first")
    executable = os.environ.get("SEMGREP") or shutil.which("semgrep")
    if semgrep and not executable:
        raise ValueError("Semgrep missing; install the pinned [paper-semgrep] extra")
    output.mkdir(parents=True)
    env = os.environ.copy()
    env["FAILROUTE_PY"] = sys.executable
    if executable:
        env["SEMGREP"] = executable
    for name, frame in (("baseline", "bench/rescan-f2"), ("refined", "bench/rescan-v2")):
        cmd = [sys.executable, str(ROOT / "tools/coverage_union.py"),
               "--findings-dir", frame, "--out", str(output / f"{name}-coverage.json"),
               "--emit-per-finding", str(output / f"{name}-per-finding.jsonl")]
        if semgrep:
            cmd.append("--with-semgrep")
        subprocess.run(cmd, cwd=ROOT, env=env, check=True)
    print(f"Coverage outputs written to {output}. Frozen exports were not overwritten.")
    print("This checks warning coverage of frozen candidate frames, not defect labels.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--with-semgrep", action="store_true")
    args = parser.parse_args()
    try:
        run(args.out_dir, semgrep=args.with_semgrep)
    except (ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

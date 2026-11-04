#!/usr/bin/env python3
"""Run every claim in claims/*.json and print a PASS/FAIL table.

Each claim is ``{id, stmt, value, cmd, expect[, slow]}``. ``cmd`` runs from
the repository root through the shell; it must exit 0 and its combined
output must match ``expect`` (Python regex, searched not anchored).

Design rules inherited from the N1-batch postmortem:

* a claim's cmd must RECOMPUTE from raw data -- reading back a JSON this
  batch wrote is not verification;
* missing inputs must fail loudly: every tool invoked here exits non-zero
  on missing input, and this runner exits with the number of failed claims.

Historical claims. A claim may carry
``"historical": {"reason": ..., "requires_git_objects": [...], "requires_env_paths": [...]}``.
When every listed git object and path exists, the claim runs like any other. When one
is missing (for example a commit that never reached the public history), the claim is
reported as HIST -- never PASS -- with the reason and the missing inputs, and its
expectation is left untouched. HIST claims are listed separately from the checks the
current version must pass; --strict-historical counts them as failures.

Usage:  .venv/bin/python tools/verify_claims.py            # everything
        .venv/bin/python tools/verify_claims.py --only f1  # one file
        .venv/bin/python tools/verify_claims.py --skip-slow
        .venv/bin/python tools/verify_claims.py --strict-historical
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def claim_environment(root: Path) -> dict[str, str]:
    """Resolve checkout paths before commands enter historical worktrees.

    CONTRACTLENS_ROOT may point to a separate clone; the default is its sibling
    directory. Commands must quote these variables, including paths with spaces.
    No fixed developer home directory is part of the reproduction contract.
    """
    env = os.environ.copy()
    env["FAILROUTE_ROOT"] = str(root.resolve())
    env["CONTRACTLENS_ROOT"] = str(Path(
        env.get("CONTRACTLENS_ROOT", root.parent / "新项目-contractlens")
    ).resolve())
    return env


def missing_historical_inputs(claim: dict, root: Path, env: dict[str, str]) -> list[str]:
    """Inputs a historical claim needs that this checkout cannot provide."""
    spec = claim.get("historical") or {}
    missing = []
    for obj in spec.get("requires_git_objects", []):
        probe = subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{obj}^{{commit}}"],
                               capture_output=True, text=True)
        if probe.returncode != 0:
            missing.append(f"git object {obj}")
    for var in spec.get("requires_env_paths", []):
        value = env.get(var, "")
        if not value or not Path(value).exists():
            missing.append(f"${var} ({value or 'unset'})")
    return missing


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="run only claims/<only>.json")
    ap.add_argument("--skip-slow", action="store_true", help="skip claims marked slow")
    ap.add_argument("--strict-historical", action="store_true",
                    help="count historical claims whose inputs are missing as failures")
    args = ap.parse_args()

    claims_dir = ROOT / "claims"
    if args.only:
        paths = [claims_dir / f"{args.only}.json"]
    else:
        paths = sorted(claims_dir.glob("*.json"))
    paths = [p for p in paths if p.is_file()]
    if not paths:
        sys.exit("error: no claims files found under claims/")

    failures = 0
    historical: list[str] = []
    env = claim_environment(ROOT)
    for path in paths:
        claims = json.loads(path.read_text(encoding="utf-8"))
        print(f"\n=== {path.name} ({len(claims)} claims) ===")
        print(f"{'id':<28} {'result':<6} {'secs':>6}  stmt")
        for claim in claims:
            if args.skip_slow and claim.get("slow"):
                print(f"{claim['id']:<28} {'SKIP':<6} {'':>6}  {claim['stmt']}")
                continue
            missing = missing_historical_inputs(claim, ROOT, env)
            if missing:
                historical.append(claim["id"])
                if args.strict_historical:
                    failures += 1
                print(f"{claim['id']:<28} {'HIST':<6} {'':>6}  not independently reproducible here")
                print(f"    | missing: {', '.join(missing)}")
                print(f"    | reason: {claim['historical'].get('reason', '')}")
                print(f"    | expectation kept unchanged: {claim['expect']!r}")
                continue
            t0 = time.time()
            try:
                proc = subprocess.run(
                    claim["cmd"],
                    shell=True,
                    cwd=ROOT,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=2400,
                )
                output = (proc.stdout or "") + (proc.stderr or "")
                ok = proc.returncode == 0 and re.search(claim["expect"], output) is not None
            except subprocess.TimeoutExpired:
                output, ok = "", False
            secs = round(time.time() - t0, 1)
            result = "PASS" if ok else "FAIL"
            if not ok:
                failures += 1
            print(f"{claim['id']:<28} {result:<6} {secs:>6}  {claim['stmt']}")
            if not ok:
                tail = output.strip().splitlines()[-4:]
                for line in tail:
                    print(f"    | {line[:160]}")
                print(f"    | expected regex: {claim['expect']!r}")

    if historical:
        print(f"\n{len(historical)} HISTORICAL CLAIM(S) NOT INDEPENDENTLY REPRODUCIBLE "
              f"(not counted as PASS): {', '.join(historical)}")
    if failures == 0:
        print(f"\n{'ALL CURRENT CLAIMS PASS' if historical else 'ALL CLAIMS PASS'}")
    else:
        print(f"\n{failures} CLAIM(S) FAILED")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())

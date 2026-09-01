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

Usage:  .venv/bin/python tools/verify_claims.py            # everything
        .venv/bin/python tools/verify_claims.py --only f1  # one file
        .venv/bin/python tools/verify_claims.py --skip-slow
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="run only claims/<only>.json")
    ap.add_argument("--skip-slow", action="store_true", help="skip claims marked slow")
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
    for path in paths:
        claims = json.loads(path.read_text(encoding="utf-8"))
        print(f"\n=== {path.name} ({len(claims)} claims) ===")
        print(f"{'id':<28} {'result':<6} {'secs':>6}  stmt")
        for claim in claims:
            if args.skip_slow and claim.get("slow"):
                print(f"{claim['id']:<28} {'SKIP':<6} {'':>6}  {claim['stmt']}")
                continue
            t0 = time.time()
            try:
                proc = subprocess.run(
                    claim["cmd"],
                    shell=True,
                    cwd=ROOT,
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

    print(f"\n{'ALL CLAIMS PASS' if failures == 0 else f'{failures} CLAIM(S) FAILED'}")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())

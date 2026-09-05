#!/usr/bin/env python3
"""The trivial-baseline measurement the paper was missing: `flake8 --select E722`.

Why this tool exists
--------------------
Every cross-tool number in the paper compared ``failroute`` against *lines of
code* (524,229) or against a four-linter union. Neither is the comparison a
reviewer reaches for first. The obvious baseline for a detector whose headline
finding is "handlers that swallow failures" is the one lint rule that has flagged
bare ``except:`` since the 1990s::

    flake8 --select E722

Run over the eight pinned scan roots this yields a candidate set, and the
question that decides whether ``failroute`` earns its keep is not "how many lines
did you save me from reading" but **"does that candidate set already contain
every confirmed defect?"** If it does, the search-space-reduction claim has to be
stated against 134 candidates, not against half a million lines.

Measured 2026-09-05 (V2 batch): 134 candidates, containing all 12 confirmed
defects in ``paper/annotations.csv``. This tool recomputes that from the corpus
and the annotations every run; it never reads back a number another tool wrote.

Also measured here, because it is the mirror image and equally load-bearing:
``ruff --select BLE001`` (blind-except). BLE001 fires on ``except Exception:``
but **not** on a bare ``except:``, so it covers none of the 12 defects. Anyone
assuming "BLE001 is the ruff equivalent of E722" will get the coverage matrix
wrong in the opposite direction.

Usage::

    cd 新项目-failroute
    PYTHONPATH=src .venv/bin/python tools/e722_baseline.py
    PYTHONPATH=src .venv/bin/python tools/e722_baseline.py --out bench/e722-baseline.json

Exits non-zero if a linter cannot run, if a scan root is missing, or if the
annotations cannot be read. A silent zero here would read as "E722 finds
nothing", which is the exact failure mode ``coverage_union.py`` was hardened
against in the L2 batch.

🔴 Invocation note (learned the hard way on 2026-09-04): do **not** pass
``--exclude="* 2.py,* 3.py"`` to flake8. An exclude pattern containing a space
makes flake8 emit *nothing at all* while still exiting 0 — measured as 0 hits on
a directory that has 131. Finder duplicates are handled by filtering the
reported paths in Python instead, where the behaviour is visible.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

#: macOS Finder duplicates ("name 2.py"). Excluded from the *count*, never from
#: the corpus itself, and never by a flake8 --exclude pattern (see module
#: docstring). The pinned corpus currently carries none under any scan root, so
#: this is a guard rather than a correction; it is reported so a future run on a
#: dirtier tree cannot silently change the denominator.
DUPLICATE_SUFFIXES = (" 2.py", " 3.py")


def _resolve_python() -> str:
    env = os.environ.get("FAILROUTE_PY")
    if env:
        if not os.path.exists(env):
            sys.exit(f"error: FAILROUTE_PY points at a missing interpreter: {env}")
        return env
    venv_py = os.path.abspath(".venv/bin/python")
    return venv_py if os.path.exists(venv_py) else sys.executable


PY = _resolve_python()


def _preflight(module: str) -> None:
    """Fail loudly when a linter is unusable, rather than reporting zero hits."""
    r = subprocess.run([PY, "-m", module, "--version"], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(
            f"error: `{PY} -m {module}` is unusable (rc={r.returncode}); refusing to run "
            f"because an empty result would read as 'this linter finds nothing'.\n"
            f"stderr: {(r.stderr or '').strip()[:400]}\n"
            "Install the pinned paper toolchain with:  pip install '.[paper]'"
        )


def _corpus_rel(path: str) -> str:
    """Repo-relative corpus path, immune to symlink resolution and to cwd."""
    marker = "/paper/corpus/"
    absolute = os.path.abspath(path)
    idx = absolute.find(marker)
    if idx == -1:
        sys.exit(f"error: linter reported a path outside the pinned corpus: {path}")
    return "paper/corpus/" + absolute[idx + len(marker):]


def _run(select: str, tool: str, root: str) -> list[tuple[str, int]]:
    """Run one linter over one scan root; return [(corpus-relative file, line)]."""
    if tool == "flake8":
        cmd = [PY, "-m", "flake8", "--select", select, "--format", "%(path)s\t%(row)d", root]
    elif tool == "ruff":
        cmd = [
            PY, "-m", "ruff", "check", "--no-cache", "--isolated", "--select", select,
            "--output-format", "concise", root,
        ]
    else:  # pragma: no cover - guarded by the caller
        sys.exit(f"error: unknown tool {tool!r}")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    out = r.stdout or ""
    if r.returncode != 0 and not out.strip():
        sys.exit(
            f"error: {tool} --select {select} failed with empty stdout (rc={r.returncode}) "
            f"on {root}\nstderr: {(r.stderr or '').strip()[:400]}"
        )
    hits: list[tuple[str, int]] = []
    dropped = 0
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        # ruff's concise format ends with a "Found N errors." summary line that is
        # not a hit. Skipping it silently is correct; warning about it would make
        # a reviewer read one dropped row per package as lost data.
        if tool == "ruff" and line.startswith(("Found ", "warning:")):
            continue
        if tool == "flake8":
            parts = line.split("\t")
        else:
            # ruff concise: "path:line:col: CODE message"
            parts = line.split(":")[:2]
        if len(parts) != 2:
            dropped += 1
            continue
        try:
            hits.append((_corpus_rel(parts[0]), int(parts[1])))
        except ValueError:
            # A row that looked like a hit but did not parse IS worth warning
            # about: it means the count is short by one and nobody would know.
            dropped += 1
    if dropped:
        print(f"  [warn] {tool}: {dropped} hit-shaped row(s) failed to parse", file=sys.stderr)
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="bench/e722-baseline.json")
    ap.add_argument(
        "--annotations", default="paper/annotations.csv",
        help="labelled sample used to check defect coverage (read-only truth)",
    )
    args = ap.parse_args()

    lock_path = "paper/corpus-lock.json"
    if not os.path.isfile(lock_path):
        sys.exit(f"error: missing corpus lock: {lock_path}")
    lock = json.load(open(lock_path, encoding="utf-8"))
    if not os.path.isfile(args.annotations):
        sys.exit(f"error: missing annotations: {args.annotations}")

    _preflight("flake8")
    _preflight("ruff")

    e722: set[tuple[str, int]] = set()
    ble001: set[tuple[str, int]] = set()
    per_pkg: dict[str, dict[str, int]] = {}
    duplicates_seen = 0

    for pkg in lock["packages"]:
        root = os.path.normpath(
            os.path.join("paper/corpus", pkg["extracted_to"], pkg["scan_root"])
        )
        if not os.path.isdir(root):
            sys.exit(
                f"error: corpus scan root missing for {pkg['name']}: {root}\n"
                "The extracted corpus is not committed; run `python tools/fetch_corpus.py`."
            )
        raw_e = _run("E722", "flake8", root)
        raw_b = _run("BLE001", "ruff", root)
        keep_e = [h for h in raw_e if not h[0].endswith(DUPLICATE_SUFFIXES)]
        keep_b = [h for h in raw_b if not h[0].endswith(DUPLICATE_SUFFIXES)]
        duplicates_seen += (len(raw_e) - len(keep_e)) + (len(raw_b) - len(keep_b))
        e722.update(keep_e)
        ble001.update(keep_b)
        per_pkg[pkg["name"]] = {"e722": len(keep_e), "ble001": len(keep_b)}
        print(f"  {pkg['name']:<20} E722={len(keep_e):>4}   BLE001={len(keep_b):>4}")

    # ---- defect coverage: join against the labelled sample, do not trust prose
    with open(args.annotations, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    defects = [(r["file"], int(r["lineno"])) for r in rows if r["label"] == "DEFECT"]
    if not defects:
        sys.exit(f"error: no DEFECT rows in {args.annotations}; refusing to report 0/0 coverage")
    e_hit = [d for d in defects if d in e722]
    b_hit = [d for d in defects if d in ble001]
    labels = Counter(r["label"] for r in rows)

    print(f"\n  E722 candidates      = {len(e722)}")
    print(f"  BLE001 candidates    = {len(ble001)}")
    print(f"  DEFECT covered by E722   = {len(e_hit)}/{len(defects)}")
    print(f"  DEFECT covered by BLE001 = {len(b_hit)}/{len(defects)}")
    missing = [d for d in defects if d not in e722]
    if missing:
        print("  🔴 DEFECT coordinates NOT covered by E722:")
        for d in missing:
            print(f"      {d[0]}:{d[1]}")

    payload = {
        "generated_at_utc8": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "corpus_lock": lock.get("lock_version"),
        "annotations_file": args.annotations,
        "annotation_labels": dict(labels),
        "flake8_select": "E722",
        "ruff_select": "BLE001",
        "finder_duplicates_excluded": duplicates_seen,
        "e722_candidates": len(e722),
        "ble001_candidates": len(ble001),
        "e722_by_package": {k: v["e722"] for k, v in per_pkg.items()},
        "ble001_by_package": {k: v["ble001"] for k, v in per_pkg.items()},
        "defects_total": len(defects),
        "defects_covered_by_e722": len(e_hit),
        "defects_covered_by_ble001": len(b_hit),
        "defects_not_covered_by_e722": [f"{f}:{l}" for f, l in missing],
        "e722_coordinates": sorted(f"{f}:{l}" for f, l in e722),
    }
    out = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Check the protected study inputs and the derived artefacts by content.

Replaces the modification-time test that V2.frozen_truth_untouched used to run.
A modification time says when a file was last written, not what it contains, and
a checkout, a copy or `touch` changes it freely; the old test also named figure
files that had since been renamed. This tool checks content instead:

protected   every file in paper/frozen-truth-sha256.json must have exactly the
            recorded SHA-256; with --corpus the fetched corpus tree is also
            verified against paper/corpus-lock.json (tools/fetch_corpus.py --verify).
derived     paper/intervals.json and the three paper figures are REBUILT into a
            temporary directory from their committed inputs and compared with the
            committed files: intervals.json as JSON with only its generation
            timestamp ignored; each figure PDF by the multiset of its text tokens
            (labels, counts and percentages), because PDF bytes also encode the
            matplotlib version, creation date and glyph placement.

Prints `protected=<n changed> derived_rebuilt_match=<True|False>` and exits
non-zero when either check fails. Requires matplotlib and `pdftotext`
(poppler-utils) for the figure comparison; a missing tool is an error, never a pass.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "paper/frozen-truth-sha256.json"
FIGURES = ("fig1_llm_label_share_by_package", "fig2_cross_tool_coverage",
           "fig3_reference_matches_by_family")
TIMESTAMP_KEYS = ("generated_at_utc8", "generated_at_utc")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def changed_protected(root: Path) -> list[str]:
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    changed = []
    for rel, entry in manifest["files"].items():
        path = root / rel
        if not path.is_file() or sha256(path) != entry["sha256"]:
            changed.append(rel)
    return changed


def same_intervals(committed: Path, rebuilt: Path) -> bool:
    a = json.loads(committed.read_text(encoding="utf-8"))
    b = json.loads(rebuilt.read_text(encoding="utf-8"))
    for key in TIMESTAMP_KEYS:
        a.pop(key, None)
        b.pop(key, None)
    return a == b


def pdf_tokens(pdf: Path) -> collections.Counter[str]:
    exe = shutil.which("pdftotext")
    if exe is None:
        sys.exit("error: pdftotext (poppler-utils) is required to compare figure content")
    out = subprocess.run([exe, "-layout", str(pdf), "-"], capture_output=True, text=True, check=True)
    return collections.Counter(out.stdout.split())


def derived_mismatches(root: Path, python: str = sys.executable) -> list[str]:
    bad = []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        proc = subprocess.run([python, str(root / "tools/compute_intervals.py"),
                               "--out", str(work / "intervals.json")],
                              cwd=root, capture_output=True, text=True)
        if proc.returncode != 0 or not same_intervals(root / "paper/intervals.json",
                                                      work / "intervals.json"):
            bad.append("paper/intervals.json")
        proc = subprocess.run([python, str(root / "tools/make_figures.py"),
                               "--out-dir", str(work / "figures")],
                              cwd=root, capture_output=True, text=True)
        if proc.returncode != 0:
            sys.exit(f"error: figure rebuild failed: {(proc.stderr or proc.stdout)[-400:]}")
        for name in FIGURES:
            committed = root / "paper/figures" / f"{name}.pdf"
            rebuilt = work / "figures" / f"{name}.pdf"
            if not committed.is_file() or pdf_tokens(committed) != pdf_tokens(rebuilt):
                bad.append(f"paper/figures/{name}.pdf")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", action="store_true",
                    help="also verify the fetched corpus tree against paper/corpus-lock.json")
    args = ap.parse_args()
    changed = changed_protected(ROOT)
    if args.corpus:
        proc = subprocess.run([sys.executable, str(ROOT / "tools/fetch_corpus.py"), "--verify"],
                              cwd=ROOT, capture_output=True, text=True)
        if proc.returncode != 0:
            changed.append("paper/corpus (tree or archive hash)")
    mismatched = derived_mismatches(ROOT)
    for rel in changed:
        print(f"  changed protected input: {rel}")
    for rel in mismatched:
        print(f"  rebuilt artefact differs: {rel}")
    print(f"protected={len(changed)} derived_rebuilt_match={not mismatched}")
    return 1 if changed or mismatched else 0


if __name__ == "__main__":
    raise SystemExit(main())

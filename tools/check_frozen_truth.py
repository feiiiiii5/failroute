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
            timestamp ignored; each figure PDF on two independent axes:
              text      the multiset of its text tokens (labels, counts, percentages);
              geometry  the drawn vector marks (paths, scatter markers) and embedded
                        images (heatmap cells, colour bar), read from the PDF content
                        stream by tools/pdf_geometry.py and expressed relative to the
                        axes area (see that module for the method and tolerances).
            A figure matches only when both agree. Text alone cannot see a point,
            cell or bar that moved while its label stayed the same.

Why not compare bytes or rendered pixels: PDF bytes encode the matplotlib version,
creation date and glyph placement, and rasterised pixels add font, hinting and
renderer differences. The geometry comparison reads coordinates the plotting code
wrote, so it does not depend on a renderer or on installed fonts. It does depend on
matplotlib's PDF output: the committed figures were written by matplotlib 3.11.0
(figures 1-2) and 3.11.1 (figure 3), and the rebuild uses the pinned 3.11.1. The
residual differences this causes are measured and printed, never ignored silently.

Prints one line per figure and then
`protected=<n changed> derived_rebuilt_match=<True|False>`, and exits non-zero when
either check fails. Requires matplotlib and `pdftotext` (poppler-utils); a missing
tool is an error, never a pass. Only a temporary directory is written.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
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


def _producer(pdf: Path) -> str:
    m = re.search(rb"/Producer\s*\(([^)]*)\)", pdf.read_bytes())
    return m.group(1).decode("latin-1") if m else "unknown producer"


def figure_match(committed: Path, rebuilt: Path) -> tuple[bool, bool, str]:
    """(text tokens equal, geometry within tolerance, human-readable detail)."""
    import pdf_geometry  # local module in tools/

    text_ok = pdf_tokens(committed) == pdf_tokens(rebuilt)
    comparison = pdf_geometry.compare(pdf_geometry.extract(committed),
                                      pdf_geometry.extract(rebuilt))
    return text_ok, comparison.within(), comparison.detail


def derived_mismatches(root: Path, python: str = sys.executable,
                       report: list[str] | None = None) -> list[str]:
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
            if not committed.is_file():
                bad.append(f"paper/figures/{name}.pdf")
                continue
            text_ok, geometry_ok, detail = figure_match(committed, rebuilt)
            if report is not None:
                report.append(f"  {name}: text={'same' if text_ok else 'DIFFERENT'} "
                              f"geometry={'within tolerance' if geometry_ok else 'DIFFERENT'} "
                              f"[{detail}; committed by {_producer(committed)}, rebuilt by "
                              f"{_producer(rebuilt)}]")
            if not (text_ok and geometry_ok):
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
    report: list[str] = []
    mismatched = derived_mismatches(ROOT, report=report)
    for line in report:
        print(line)
    for rel in changed:
        print(f"  changed protected input: {rel}")
    for rel in mismatched:
        print(f"  rebuilt artefact differs: {rel}")
    print(f"protected={len(changed)} derived_rebuilt_match={not mismatched}")
    return 1 if changed or mismatched else 0


if __name__ == "__main__":
    raise SystemExit(main())

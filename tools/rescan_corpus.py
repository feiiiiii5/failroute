#!/usr/bin/env python3
"""Rescan the eight pinned corpus packages with the *current* failroute code.

The frozen baseline in ``paper/scan/*.jsonl`` was produced by the CLI's
``--export-findings`` path under v0.7.0.  This tool reruns the same scan with
whatever detector code is on ``PYTHONPATH`` right now, so precision fixes can
be diffed against the frozen baseline finding-for-finding.

Records carry the same identity fields as the frozen jsonl (id / repo / file /
lineno / end_lineno / rule / mode / message); annotation context windows are
omitted because delta analysis never reads them.

🔴 Corpus hygiene note (measured 2026-09-01): the extracted trees under
``paper/corpus/`` have since accumulated 624 macOS Finder duplicates
(``name 2.py``, ``name 2.md``...); the frozen ``paper/scan`` baseline was
produced on a clean tree. The corpus itself may not be modified, so this
tool excludes Finder duplicates from the scan by default (``--keep-dup``
disables that). The frozen 649 findings reproduce byte-exact with the
exclusion on (measured: extra=0, missing=0).

Usage (from the repo root):
    PYTHONPATH=src .venv/bin/python tools/rescan_corpus.py --out bench/rescan-v0.8

Fails loudly on missing inputs: a silent skip here would make a later delta
uninterpretable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# 🔴 No Path.resolve() anywhere in this tool: macOS rewrites /tmp to
# /private/tmp and symlinked corpus mounts (worktree replays) resolve to
# their target, either of which breaks the relative_to(ROOT) bookkeeping.
ROOT = Path(__file__).parent.parent

# 🔴 Finder duplicates, NOT the corpus contents, differ from the frozen scan's
# tree (see module docstring). The lock's sha256/tree-hash covers the original
# archives; this list is an exclusion-only hygiene measure and must never be
# used to alter paper/corpus/ itself.
DUPLICATE_SUFFIXES = (" 2.py", " 3.py")


def _stable_id(file: str, lineno: int, rule: str) -> str:
    # Same derivation as failroute.cli._stable_id so ids compare across runs.
    return hashlib.sha256(f"{file}\n{lineno}\n{rule}".encode()).hexdigest()[:16]


def _corpus_rel(file: str) -> str:
    """Repo-relative corpus path, immune to symlink resolution.

    Worktree replays mount the corpus through a symlink; depending on the
    interpreter version the walked paths come back lexical *or* resolved to
    the link target. Both spellings contain the ``/paper/corpus/`` marker,
    so normalising on the marker keeps finding identities comparable with
    the frozen ``paper/scan`` records.
    """
    marker = "/paper/corpus/"
    idx = file.find(marker)
    if idx == -1:
        sys.exit(f"error: finding outside the pinned corpus: {file}")
    return "paper/corpus/" + file[idx + len(marker):]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        required=True,
        help="output directory for the per-package jsonl files (must not pre-exist as a file)",
    )
    parser.add_argument(
        "--keep-dup",
        action="store_true",
        help="also scan macOS Finder duplicates ('name 2.py'); off by default, see module docstring",
    )
    parser.add_argument(
        "--with-context",
        action="store_true",
        help="attach the same context_before/context_after/function_signature "
        "windows the CLI's --export-findings writes (needed for annotation)",
    )
    args = parser.parse_args()

    lock_path = ROOT / "paper" / "corpus-lock.json"
    if not lock_path.is_file():
        sys.exit(f"error: missing corpus lock file: {lock_path}")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))

    try:
        from failroute.analyzer import scan_path, scan_repo
    except ImportError as exc:  # missing PYTHONPATH=src is a user error, not a skip
        sys.exit(f"error: cannot import failroute ({exc}); run with PYTHONPATH=src")
    finding_context = None
    if args.with_context:
        from failroute.cli import _finding_context as finding_context  # noqa: PLC0415

    def scan_one(root: Path):
        if args.keep_dup:
            return scan_repo(root)
        # scan_repo has no per-file exclude hook; walk the same deterministic
        # file list and scan file-by-file, dropping Finder duplicates.
        from failroute.analyzer import _collect_repo_files

        findings = []
        for path in _collect_repo_files(root, None, None):
            if path.name.endswith(DUPLICATE_SUFFIXES):
                continue
            findings.extend(scan_path(path))
        return findings

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    for pkg in lock["packages"]:
        root = ROOT / "paper" / "corpus" / pkg["extracted_to"] / pkg["scan_root"]
        if not root.is_dir():
            sys.exit(f"error: corpus scan root missing for {pkg['name']}: {root}")
        findings = scan_one(root)
        out_path = out_dir / f"{pkg['name']}.jsonl"
        with out_path.open("w", encoding="utf-8") as fh:
            for f in sorted(findings, key=lambda x: (x.file, x.lineno, x.rule_id)):
                rel = _corpus_rel(f.file)
                rule = f.rule_id or f.mode.value
                record = {
                    "id": _stable_id(str(rel), f.lineno, rule),
                    "repo": pkg["name"],
                    "file": str(rel),
                    "lineno": f.lineno,
                    "end_lineno": f.end_lineno,
                    "rule": rule,
                    "mode": f.mode.value,
                    "message": f.message,
                }
                if finding_context is not None:
                    record.update(finding_context(ROOT, str(rel), f.lineno))
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"{pkg['name']:<20} {len(findings):>4}")
        total += len(findings)
    print(f"{'total':<20} {total:>4}")
    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

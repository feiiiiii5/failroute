"""Command-line interface for failroute."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from failroute.analyzer import scan_path, scan_repo

_EPILOG = """\
exit status:
  0  scan completed, no findings
  1  scan completed, findings above threshold
  2  usage or input error
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="failroute",
        description="Detect failure-routing anti-patterns (silently swallowed exceptions, "
        "silent fallback returns) in Python source.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="file or directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--repo",
        action="store_true",
        help="treat PATH as a repository checkout and skip conventional junk dirs (.git, .venv, build, ...)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit findings as JSON (one object per line)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=0,
        help="exit 1 when more findings than this are emitted (default: 0)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="only print the finding count summary",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    path = Path(args.path)
    if not path.exists():
        print(f"failroute: error: no such path: {path}", file=sys.stderr)
        return 2

    if args.repo:
        findings = scan_repo(path)
    else:
        findings = scan_path(path)

    if args.json:
        for finding in findings:
            print(json.dumps(finding.to_dict(), ensure_ascii=False))
    elif not args.quiet:
        for finding in findings:
            print(f"{finding.file}:{finding.lineno}: {finding.mode.value}: {finding.message}")

    print(f"\n{len(findings)} finding(s)", file=sys.stderr if not args.json else sys.stderr)
    return 0 if len(findings) <= args.threshold else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

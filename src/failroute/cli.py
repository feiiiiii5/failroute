"""Command-line interface for failroute."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from failroute.analyzer import Finding, scan_path, scan_repo
from failroute.sarif import to_sarif_json


def _version() -> str:
    from importlib import metadata

    return metadata.version("failroute")


def _load_project_config(start: Path) -> dict[str, Any]:
    """Read ``[tool.failroute]`` from the nearest pyproject.toml at/above ``start``.

    Recognised keys: ``exclude`` (list of repo-relative paths) and ``threshold``
    (int). Malformed files or wrong value types are ignored silently -- a config
    problem must never turn a scan into a crash.
    """
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - py<3.11 path
        try:
            import tomli as tomllib  # type: ignore[import-not-found,no-redef]
        except ModuleNotFoundError:  # failroute: ignore - no TOML parser, no project config
            return {}
    for base in (start, *start.parents):
        candidate = base / "pyproject.toml"
        if not candidate.is_file():
            continue
        try:
            with candidate.open("rb") as fh:
                data = tomllib.load(fh)
        except (OSError, ValueError):  # failroute: ignore - documented: bad config = no config
            return {}
        cfg = data.get("tool", {}).get("failroute", {})
        return cfg if isinstance(cfg, dict) else {}
    return {}


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
        "--format",
        choices=("text", "json", "sarif"),
        default="text",
        help="output format (default: text)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="alias for --format json (one object per line; kept for backwards compatibility)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="write results to FILE instead of stdout (implies --format unless --format given)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=None,
        help="exit 1 when more findings than this are emitted "
        "(default: [tool.failroute] threshold in pyproject.toml, else 0)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="only print the finding count summary",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATH",
        help="repo-relative path to skip, repeatable (e.g. --exclude tests/corpus); "
        "implies repository-style traversal",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_version()}",
    )
    return parser


def _sort_key(finding: Finding) -> tuple[str, int, str]:
    return (finding.file, finding.lineno, finding.mode.value)


def _render(findings: list[Finding], fmt: str) -> str:
    if fmt == "json":
        return "\n".join(json.dumps(f.to_dict(), ensure_ascii=False) for f in findings)
    if fmt == "sarif":
        return to_sarif_json(findings)
    return "\n".join(f"{f.file}:{f.lineno}: {f.mode.value}: {f.message}" for f in findings)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    path = Path(args.path)
    if not path.exists():
        print(f"failroute: error: no such path: {path}", file=sys.stderr)
        return 2

    # Project-level config; CLI flags always win.
    cfg = _load_project_config(path.resolve())
    cfg_exclude = cfg.get("exclude")
    cfg_excludes = {e for e in cfg_exclude if isinstance(e, str)} if isinstance(cfg_exclude, list) else set()
    excludes = set(args.exclude) | cfg_excludes
    cfg_threshold = cfg.get("threshold")
    threshold = (
        args.threshold
        if args.threshold is not None
        else cfg_threshold
        if isinstance(cfg_threshold, int) and not isinstance(cfg_threshold, bool)
        else 0
    )

    # --json is a legacy alias; --format wins when both are supplied.
    fmt = args.format
    if args.json and args.format == "text":
        fmt = "json"

    # --repo/-exclude only make sense over a directory tree; a single file is
    # scanned directly (previously `--repo file.py` silently reported zero).
    if path.is_dir() and (args.repo or excludes):
        findings = scan_repo(path, exclude=excludes)
    else:
        findings = scan_path(path)

    # Deterministic order regardless of filesystem enumeration.
    findings.sort(key=_sort_key)

    rendered = _render(findings, fmt)

    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    elif not args.quiet and rendered:
        print(rendered)

    # Quiet mode suppresses findings but still reports the count on stderr,
    # so scripts can rely on the summary line for logging.
    if args.output is not None:
        print(f"{len(findings)} finding(s) written to {args.output}", file=sys.stderr)
    else:
        print(f"{len(findings)} finding(s)", file=sys.stderr)
    return 0 if len(findings) <= threshold else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

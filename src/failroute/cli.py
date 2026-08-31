"""Command-line interface for failroute."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path

from failroute.analyzer import Finding, scan_path, scan_repo
from failroute.config import load_config
from failroute.sarif import to_sarif_json


def _version() -> str:
    from importlib import metadata

    return metadata.version("failroute")


_EPILOG = """\
exit status:
  0  scan completed, no findings
  1  scan completed, findings above threshold
  2  usage or input error

project configuration lives in [tool.failroute] (pyproject.toml):
  exclude, threshold, ignore, fallback_values, rules.<id>.enabled/severity

--export-findings writes one JSON object per finding (stable id, +/-15 lines
of source context, enclosing function signature) for offline labelling.
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
        "--ignore",
        action="append",
        default=[],
        metavar="RULE",
        help="disable a rule by id (e.g. --ignore name-shadowing); repeatable; "
        "merges with [tool.failroute] ignore / rules.<id>.enabled = false",
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
        "--jobs",
        type=int,
        default=1,
        metavar="N",
        help="worker processes for repository scans (0 = one per core; default 1)",
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        help="cache per-file results (mtime+size keyed) so re-runs scan only changed files",
    )
    parser.add_argument(
        "--export-findings",
        type=Path,
        default=None,
        metavar="OUT_JSONL",
        help="write one JSON object per finding (stable id, +/-15 lines of "
        "context, enclosing function signature) to OUT_JSONL and exit",
    )
    parser.add_argument(
        "--repo-name",
        default="",
        metavar="NAME",
        help="repository label recorded in each --export-findings record (default: empty)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="only print the finding count summary",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_version()}",
    )
    return parser


def _sort_key(finding: Finding) -> tuple[str, int, str]:
    return (finding.file, finding.lineno, finding.mode.value)


def _stable_id(file: str, lineno: int, rule: str) -> str:
    return hashlib.sha256(f"{file}\n{lineno}\n{rule}".encode("utf-8")).hexdigest()[:16]


def _enclosing_signature(tree: ast.Module, lineno: int) -> str | None:
    innermost: ast.AST | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.lineno <= lineno <= (
            node.end_lineno or node.lineno
        ):
            if innermost is None or node.lineno >= innermost.lineno:  # type: ignore[union-attr]
                innermost = node
    if innermost is None:
        return None
    prefix = "async def " if isinstance(innermost, ast.AsyncFunctionDef) else "def "
    args = ast.unparse(innermost.args)
    returns = f" -> {ast.unparse(innermost.returns)}" if innermost.returns else ""
    return f"{prefix}{innermost.name}({args}){returns}"


def _finding_context(root: Path, file: str, lineno: int) -> dict[str, object]:
    empty = {
        "context_before": [],
        "context_after": [],
        "function_signature": None,
    }
    candidate = Path(file)
    targets = [candidate] if candidate.is_absolute() else [root / candidate, candidate]
    source = None
    for target in targets:
        try:
            source = target.read_text(encoding="utf-8", errors="replace")
            break
        except OSError:
            continue
    if source is None:
        return dict(empty)
    lines = source.splitlines()
    context = {
        "context_before": lines[max(0, lineno - 16) : lineno - 1],
        "context_after": lines[lineno : lineno + 15],
    }
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {**empty, **context}
    return {**context, "function_signature": _enclosing_signature(tree, lineno)}


def _export_findings(
    findings: list[Finding], out: Path, scan_root: Path, repo_name: str
) -> None:
    with out.open("w", encoding="utf-8") as fh:
        for f in findings:
            rule = f.rule_id or f.mode.value
            record = {
                "id": _stable_id(f.file, f.lineno, rule),
                "repo": repo_name,
                "file": f.file,
                "lineno": f.lineno,
                "end_lineno": f.end_lineno,
                "rule": rule,
                "mode": f.mode.value,
                "message": f.message,
                **_finding_context(scan_root, f.file, f.lineno),
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _render(findings: list[Finding], fmt: str, severity_overrides: dict[str, str]) -> str:
    if fmt == "json":
        return "\n".join(json.dumps(f.to_dict(), ensure_ascii=False) for f in findings)
    if fmt == "sarif":
        return to_sarif_json(findings, severity_overrides=severity_overrides)
    return "\n".join(f"{f.file}:{f.lineno}: {f.mode.value}: {f.message}" for f in findings)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    path = Path(args.path)
    if not path.exists():
        print(f"failroute: error: no such path: {path}", file=sys.stderr)
        return 2

    # Project-level config; CLI flags always win.
    cfg = load_config(path.resolve())
    excludes = set(args.exclude) | set(cfg.exclude)
    disabled_rules = set(cfg.disabled_rules) | {r for r in args.ignore if r}
    threshold = args.threshold if args.threshold is not None else cfg.threshold

    # --json is a legacy alias; --format wins when both are supplied.
    fmt = args.format
    if args.json and args.format == "text":
        fmt = "json"

    # --repo/-exclude only make sense over a directory tree; a single file is
    # scanned directly (previously `--repo file.py` silently reported zero).
    if path.is_dir() and (args.repo or excludes):
        findings = scan_repo(
            path,
            exclude=excludes,
            disabled_rules=disabled_rules,
            extra_fallback_values=cfg.fallback_values,
            extra_fallback_names=cfg.fallback_names,
            jobs=args.jobs,
            use_cache=args.cache,
        )
    else:
        findings = scan_path(
            path,
            disabled_rules=disabled_rules,
            extra_fallback_values=cfg.fallback_values,
            extra_fallback_names=cfg.fallback_names,
        )

    # Deterministic order regardless of filesystem enumeration.
    findings.sort(key=_sort_key)

    if args.export_findings is not None:
        _export_findings(findings, args.export_findings, path.resolve(), args.repo_name)
        print(
            f"{len(findings)} finding(s) exported to {args.export_findings}", file=sys.stderr
        )
        return 0 if len(findings) <= threshold else 1

    rendered = _render(findings, fmt, cfg.severity_overrides)

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

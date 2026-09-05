"""Command-line interface for failroute."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path
from typing import Union

from failroute.analyzer import Finding, scan_path, scan_repo
from failroute.config import load_config
from failroute.ir import Severity
from failroute.sarif import to_sarif_json


def _version() -> str:
    from importlib import metadata

    return metadata.version("failroute")


_EPILOG = """\
exit status:
  0  scan completed, and nothing reached --fail-on (or --exit-zero was given)
  1  scan completed, more findings at or above --fail-on than --threshold allows
  2  usage or input error, or the scan itself failed

🔴 Exit 1 is gated on *severity*, not on the raw finding count. The previous
contract ("any finding at all exits 1") made a clean scan of a typical
repository indistinguishable from a failed one, because almost every codebase
has at least one INFO-level finding. Default --fail-on high means CI fails on
defects, not on observations.

every finding carries:
  severity    high | medium | low | info  (the consequence level)
  covered_by  trivial-lint rules that already flag the same handler; empty
              means nothing else points at this line (--only-novel shows just
              those)
  verdict     why that severity, in one line

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
        "--fail-on",
        choices=("high", "medium", "low", "info"),
        default="high",
        metavar="LEVEL",
        help="exit 1 when a finding reaches this severity or above (default: high). "
        "Findings below it are still reported; they just do not fail the run.",
    )
    parser.add_argument(
        "--exit-zero",
        action="store_true",
        help="always exit 0, even when findings reach --fail-on (report-only mode)",
    )
    parser.add_argument(
        "--only-novel",
        action="store_true",
        help="report only findings whose covered_by is empty, i.e. the ones no "
        "trivial lint rule (E722 / BLE001 / S110 / B015 / ...) already flags",
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
    return hashlib.sha256(f"{file}\n{lineno}\n{rule}".encode()).hexdigest()[:16]


_FuncDef = Union[ast.FunctionDef, ast.AsyncFunctionDef]


def _enclosing_signature(tree: ast.Module, lineno: int) -> str | None:
    innermost: _FuncDef | None = None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.lineno <= lineno <= (node.end_lineno or node.lineno):
            if innermost is None or node.lineno >= innermost.lineno:
                innermost = node
    if innermost is None:
        return None
    prefix = "async def " if isinstance(innermost, ast.AsyncFunctionDef) else "def "
    args = ast.unparse(innermost.args)
    returns = f" -> {ast.unparse(innermost.returns)}" if innermost.returns else ""
    return f"{prefix}{innermost.name}({args}){returns}"


def _finding_context(root: Path, file: str, lineno: int) -> dict[str, object]:
    empty: dict[str, object] = {
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
                # The four V1 verdict fields, so an offline labeller sees the
                # same record the JSON/SARIF outputs carry. Without them the
                # export is the only format that loses the severity, which is
                # how a hand-transcribed number sneaks into a paper.
                "severity": f.severity.value,
                "isomorphism": f.isomorphism.value if f.isomorphism is not None else None,
                "covered_by": list(f.covered_by),
                "verdict": f.verdict,
                **_finding_context(scan_root, f.file, f.lineno),
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _render(findings: list[Finding], fmt: str, severity_overrides: dict[str, str]) -> str:
    if fmt == "json":
        return "\n".join(json.dumps(f.to_dict(), ensure_ascii=False) for f in findings)
    if fmt == "sarif":
        return to_sarif_json(findings, severity_overrides=severity_overrides)
    lines = []
    for f in findings:
        novel = "" if f.covered_by else " [novel]"
        lines.append(f"{f.file}:{f.lineno}: {f.severity.value}: {f.mode.value}{novel}: {f.message}")
    return "\n".join(lines)


def _gate_count(findings: list[Finding], fail_on: Severity) -> int:
    """How many findings reach ``fail_on``; this, not the total, decides exit 1."""
    return sum(1 for f in findings if f.severity.at_least(fail_on))


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

    fail_on = Severity(args.fail_on)

    # --repo/-exclude only make sense over a directory tree; a single file is
    # scanned directly (previously `--repo file.py` silently reported zero).
    #
    # 🔴 An unexpected exception here is a *run failure*, not a clean scan. It
    # must not be allowed to escape as a traceback (a CI log full of stack
    # frames from someone else's source tree is the worst possible output for a
    # linter), and it must not be reported as exit 1, which would read as
    # "findings above threshold". Exit 2 says "the tool did not complete".
    try:
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
    except Exception as exc:  # noqa: BLE001 - the CLI boundary is exactly where a
        # catch-all belongs: nothing useful can be done with the type, and the
        # alternative is a traceback in someone else's CI log.
        print(f"failroute: error: scan failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    # Deterministic order regardless of filesystem enumeration.
    findings.sort(key=_sort_key)

    if args.only_novel:
        findings = [f for f in findings if not f.covered_by]

    gated = _gate_count(findings, fail_on)
    failed = gated > threshold and not args.exit_zero

    if args.export_findings is not None:
        _export_findings(findings, args.export_findings, path.resolve(), args.repo_name)
        print(
            f"{len(findings)} finding(s) exported to {args.export_findings}", file=sys.stderr
        )
        return 1 if failed else 0

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
    # Spell out why a run with findings still exited 0, so "no gate reached"
    # never has to be inferred from silence.
    if findings and not failed:
        print(
            f"gate: {gated} of {len(findings)} at or above {fail_on.value}"
            f" (threshold {threshold})"
            + ("; --exit-zero" if args.exit_zero else ""),
            file=sys.stderr,
        )
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

"""AST-based scanner for failure-routing anti-patterns.

Design notes (v0.6)
-------------------
Detection lives in the :mod:`failroute.rules` package: one rule per
anti-pattern, each carrying declarative metadata
(:class:`failroute.ir.RuleSpec`). This module is the **dispatcher**: it walks
the AST once, hands every ``except`` handler to the registered handler rules
in registry order, runs the whole-file rules, and applies the gates rules
should not re-implement:

* **Opt-out markers** — ``# pragma: no cover`` (defensive code) and
  ``# failroute: ignore`` (reviewed-and-accepted) anywhere in a handler's
  lines suppress its findings; the same marker check gates ``suppress``
  statements.
* **Handler-level ignore list** — swallowing ``KeyboardInterrupt`` /
  ``SystemExit`` / ``GeneratorExit`` / ``StopIteration`` /
  ``StopAsyncIteration`` / ``CancelledError`` is idiomatic control flow,
  not failure routing; tuple handlers qualify only when every member is
  ignored.
* **Deterministic order** — findings are line-sorted; the stable sort keeps
  per-handler registry order for same-line findings.

The heuristics deliberately err on the side of *reporting*: reviewers
(and CI gates) can triage quickly, and a finding is always worth a look at
the surrounding lines.

The failure modes themselves are documented in :mod:`failroute.ir`:

* **No action** — the handler body is ``pass``/``...``: the caller can never
  learn the operation failed.
* **Silent fallback** — the handler returns/assigns a constant fallback
  (``None``, ``0``, ``[]``...) without re-raising: failure becomes a
  default-looking value at the wrong layer.
* **Masked exception** — a catch-all that conditionally re-raises *and*
  falls back: the outcome depends on the branch.
* **Name shadowing** — ``except E as e:`` whose body rebinds ``e``.
* **Silent suppress** — ``with contextlib.suppress(...):``, the
  context-manager form of ``except: pass`` that ruff's SIM105 actively
  recommends rewriting into.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

from failroute.ir import FailureMode, Finding, Rule, ScanContext
from failroute.rules import FILE_RULES, HANDLER_RULES
from failroute.rules._shared import (
    collect_import_bindings,
    handler_marked_off,
    import_probe_handler_ids,
    is_ignored_handler,
)

logger = logging.getLogger(__name__)

__all__ = [
    "FailureMode",
    "Finding",
    "Rule",
    "ScanContext",
    "scan_tree",
    "scan_source",
    "scan_path",
    "scan_repo",
]


def scan_tree(
    tree: ast.AST,
    *,
    file: str = "<source>",
    source: str | None = None,
    disabled_rules: frozenset[str] | set[str] = frozenset(),
    extra_fallback_values: frozenset[str] | set[str] = frozenset(),
    extra_fallback_names: frozenset[str] | set[str] = frozenset(),
) -> list[Finding]:
    """Scan a parsed AST for failure-routing anti-patterns.

    ``source`` (the original file text) is used to detect explicit
    opt-out markers: ``# pragma: no cover`` (defensive code) and
    ``# failroute: ignore`` (reviewed-and-accepted in a code review).

    ``disabled_rules`` skips rules by id (``[tool.failroute] ignore`` /
    ``rules.<id>.enabled = false``); ``extra_fallback_values`` carries
    project-specific fallback sentinels (``[tool.failroute]
    fallback_values``).
    """
    ctx = ScanContext(
        file=file,
        source_lines=source.splitlines() if source is not None else None,
        bindings=collect_import_bindings(tree),
        extra_fallback_values=frozenset(extra_fallback_values),
        extra_fallback_names=frozenset(extra_fallback_names),
        probe_handlers=import_probe_handler_ids(tree),
    )

    findings: list[Finding] = []
    # The v0.5 walker re-visited handlers nested two or more levels deep
    # (each visit walked its own subtree for more handlers), double-reporting
    # innermost handlers. Visit every handler exactly once instead.
    visited: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or id(node) in visited:
            continue
        visited.add(id(node))
        if is_ignored_handler(node) or handler_marked_off(node, ctx.source_lines):
            continue
        exc_name: str | None = node.name or None
        for rule in HANDLER_RULES:
            if rule.spec.rule_id in disabled_rules:
                continue
            findings.extend(rule.check_handler(node, exc_name, ctx))

    for rule in FILE_RULES:
        if rule.spec.rule_id in disabled_rules:
            continue
        findings.extend(rule.check_file(tree, ctx))

    # Deterministic order: line-sorted; the stable sort keeps per-handler
    # registry order for same-line findings.
    findings.sort(key=lambda f: f.lineno)
    return findings


def scan_source(
    source: str,
    *,
    file: str = "<source>",
    disabled_rules: frozenset[str] | set[str] = frozenset(),
    extra_fallback_values: frozenset[str] | set[str] = frozenset(),
    extra_fallback_names: frozenset[str] | set[str] = frozenset(),
) -> list[Finding]:
    """Scan a source string and return findings."""
    tree = ast.parse(source, filename=file)
    return scan_tree(
        tree,
        file=file,
        source=source,
        disabled_rules=disabled_rules,
        extra_fallback_values=extra_fallback_values,
        extra_fallback_names=extra_fallback_names,
    )


def scan_path(
    path: Path,
    *,
    follow_links: bool = False,
    disabled_rules: frozenset[str] | set[str] = frozenset(),
    extra_fallback_values: frozenset[str] | set[str] = frozenset(),
    extra_fallback_names: frozenset[str] | set[str] = frozenset(),
) -> list[Finding]:
    """Scan a single file (or a directory tree) for findings."""
    path = Path(path)
    findings: list[Finding] = []
    if path.is_file():
        if path.suffix != ".py":
            return findings
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:  # pragma: no cover - read errors are environment-specific
            logger.warning("skipping %s: %s", path, exc)
            return findings
        try:
            findings.extend(
                scan_source(
                    source,
                    file=str(path),
                    disabled_rules=disabled_rules,
                    extra_fallback_values=extra_fallback_values,
                    extra_fallback_names=extra_fallback_names,
                )
            )
        except SyntaxError:
            logger.debug("skipping %s: not parseable as Python", path)
        except RecursionError:  # pragma: no cover - depends on interpreter recursion budget
            # Deeply nested generated files (payload resources, vendored
            # schemas) can exceed the interpreter's recursion budget during
            # the AST walk.  A scanner must never crash on hostile input.
            logger.debug("skipping %s: AST nesting exceeds recursion budget", path)
        return findings

    for sub in sorted(path.rglob("*.py")):
        if sub.is_dir():
            continue
        findings.extend(
            scan_path(
                sub,
                disabled_rules=disabled_rules,
                extra_fallback_values=extra_fallback_values,
                extra_fallback_names=extra_fallback_names,
            )
        )
    return findings


def _collect_repo_files(
    root: Path,
    skip_dirs: set[str] | None,
    exclude: set[str] | None,
) -> list[Path]:
    """Deterministic list of Python files a repo scan covers."""
    skip_dirs = skip_dirs or {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "build",
        "dist",
        ".tox",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
    exclude = {e.strip("/") for e in (exclude or set())}
    files: list[Path] = []
    root = Path(root)
    for sub in sorted(root.rglob("*.py")):
        rel = sub.relative_to(root)
        if any(part in skip_dirs for part in rel.parts):
            continue
        rel_str = str(rel).replace("\\", "/")
        if any(rel_str == ex or rel_str.startswith(ex + "/") for ex in exclude):
            continue
        files.append(sub)
    return files


def _scan_file_worker(
    path_str: str,
    disabled_rules: frozenset[str],
    extra_fallback_values: frozenset[str],
    extra_fallback_names: frozenset[str],
) -> list[Finding]:
    """Process-pool entry point: scan one file, return picklable findings."""
    return scan_path(
        Path(path_str),
        disabled_rules=disabled_rules,
        extra_fallback_values=extra_fallback_values,
        extra_fallback_names=extra_fallback_names,
    )


def _scan_parallel(
    files: list[Path],
    jobs: int,
    disabled_rules: frozenset[str],
    extra_fallback_values: frozenset[str],
    extra_fallback_names: frozenset[str],
) -> list[Finding]:
    """Scan files across worker processes; degrade to serial on any failure."""
    import itertools
    from concurrent.futures import ProcessPoolExecutor

    try:
        findings: list[Finding] = []
        with ProcessPoolExecutor(max_workers=jobs) as executor:
            for result in executor.map(
                _scan_file_worker,
                [str(p) for p in files],
                itertools.repeat(frozenset(disabled_rules)),
                itertools.repeat(frozenset(extra_fallback_values)),
                itertools.repeat(frozenset(extra_fallback_names)),
                chunksize=4,
            ):
                findings.extend(result)
        return findings
    except Exception:  # pragma: no cover - environment-dependent (spawn/fork limits)
        logger.debug("parallel scan unavailable; falling back to serial", exc_info=True)
        return [
            f
            for p in files
            for f in scan_path(
                p,
                disabled_rules=disabled_rules,
                extra_fallback_values=extra_fallback_values,
                extra_fallback_names=extra_fallback_names,
            )
        ]


def _engine_version() -> str:
    from importlib import metadata

    try:
        return metadata.version("failroute")
    except Exception:  # pragma: no cover - not installed as a distribution
        return "0"


def _cache_options(
    disabled_rules: frozenset[str],
    extra_fallback_values: frozenset[str],
    extra_fallback_names: frozenset[str],
) -> str:
    """Stable fingerprint of every scan option that changes findings.

    The cache must never serve findings scanned under a different rule set
    or sentinel vocabulary, nor findings computed by an older engine.
    """
    import hashlib
    import json as _json

    payload = _json.dumps(
        {
            "engine": _engine_version(),
            "disabled": sorted(disabled_rules),
            "values": sorted(extra_fallback_values),
            "names": sorted(extra_fallback_names),
        },
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _cache_file(root: Path) -> Path:
    """Per-repo cache location in the system temp dir (no in-repo pollution)."""
    import hashlib
    import tempfile

    key = hashlib.sha1(str(root.resolve()).encode("utf-8", "replace")).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"failroute-cache-{key}.json"


def _finding_from_dict(data: dict[str, Any]) -> Finding:
    """Rebuild a Finding from its cached dict form.

    Raises ``KeyError``/``ValueError`` on schema drift; the caller decides
    what a corrupt entry means (re-scan the file) instead of this helper
    silently returning ``None``.
    """
    return Finding(
        file=data["file"],
        lineno=data["lineno"],
        end_lineno=data["end_lineno"],
        mode=FailureMode(data["mode"]),
        exc_name=data.get("exc_name"),
        handler_text=data.get("handler_text", ""),
        message=data.get("message", ""),
        rule_id=data.get("rule_id", ""),
    )


def _scan_with_cache(
    files: list[Path],
    root: Path,
    disabled_rules: frozenset[str],
    extra_fallback_values: frozenset[str],
    extra_fallback_names: frozenset[str],
) -> list[Finding]:
    """Scan with an mtime+size keyed cache; re-scan only changed files.

    The cache payload carries the engine version and a fingerprint of the
    scan options; any mismatch downgrades to a cold scan so findings are
    never served from a different rule set, sentinel vocabulary, or engine.
    """
    import json

    opts = _cache_options(disabled_rules, extra_fallback_values, extra_fallback_names)
    cache_path = _cache_file(root)
    cache: dict[str, Any] = {}
    if cache_path.is_file():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):  # failroute: ignore - documented: corrupt cache = cold cache
            cache = {}
    if not isinstance(cache, dict) or cache.get("engine") != _engine_version() or cache.get("opts") != opts:
        cache = {}

    findings: list[Finding] = []
    fresh: dict[str, Any] = {"engine": _engine_version(), "opts": opts, "files": {}}
    file_entries: dict[str, Any] = fresh["files"]
    dirty = False
    for path in files:
        try:
            stat = path.stat()
            sig = [stat.st_mtime_ns, stat.st_size]
        except OSError:  # pragma: no cover - racing deletion
            sig = None
        entry = cache.get("files", {}).get(str(path)) if isinstance(cache.get("files"), dict) else None
        if sig is not None and isinstance(entry, dict) and entry.get("sig") == sig:
            try:
                rebuilt = [_finding_from_dict(d) for d in entry.get("findings", [])]
            except (KeyError, ValueError, TypeError):
                # Cache schema drifted: treat the entry as a miss and re-scan.
                logger.debug("cache entry for %s unreadable; re-scanning", path)
            else:
                findings.extend(rebuilt)
                file_entries[str(path)] = entry
                continue
        result = scan_path(
            path,
            disabled_rules=disabled_rules,
            extra_fallback_values=extra_fallback_values,
            extra_fallback_names=extra_fallback_names,
        )
        findings.extend(result)
        if sig is not None:
            file_entries[str(path)] = {"sig": sig, "findings": [f.to_dict() for f in result]}
            dirty = True

    if dirty or set(cache.get("files", {}) if isinstance(cache.get("files"), dict) else {}) != set(
        file_entries
    ):
        try:
            tmp = cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(fresh), encoding="utf-8")
            tmp.replace(cache_path)
        except OSError:  # pragma: no cover - read-only temp dir etc.
            logger.debug("could not persist scan cache", exc_info=True)
    return findings


def scan_repo(
    root: Path,
    *,
    skip_dirs: set[str] | None = None,
    exclude: set[str] | None = None,
    disabled_rules: frozenset[str] | set[str] = frozenset(),
    extra_fallback_values: frozenset[str] | set[str] = frozenset(),
    extra_fallback_names: frozenset[str] | set[str] = frozenset(),
    jobs: int = 1,
    use_cache: bool = False,
) -> list[Finding]:
    """Scan a repository checkout, skipping conventional junk directories.

    ``exclude`` holds repo-relative paths (``tests/corpus``) that are skipped
    even though they are valid Python -- used to keep intentional fixtures out
    of self-scans. ``jobs`` > 1 fans the per-file scans out to worker
    processes (``jobs == 0`` means one worker per core); ``use_cache``
    persists per-file results keyed by mtime+size so re-runs only re-scan
    changed files. Both keep the output deterministic (callers line-sort).
    """
    import os

    root = Path(root)
    if root.is_file():
        # A single-file path has no tree to traverse; scan it directly.
        return scan_path(
            root,
            disabled_rules=frozenset(disabled_rules),
            extra_fallback_values=frozenset(extra_fallback_values),
        )
    files = _collect_repo_files(root, skip_dirs, exclude)
    rules = frozenset(disabled_rules)
    values = frozenset(extra_fallback_values)
    names = frozenset(extra_fallback_names)

    if use_cache:
        return _scan_with_cache(files, root, rules, values, names)

    workers = jobs if jobs > 0 else (os.cpu_count() or 1)
    if workers > 1 and len(files) > 1:
        return _scan_parallel(files, workers, rules, values, names)

    return [
        finding
        for path in files
        for finding in scan_path(
            path, disabled_rules=rules, extra_fallback_values=values, extra_fallback_names=names
        )
    ]

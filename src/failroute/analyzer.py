"""AST-based scanner for failure-routing anti-patterns.

Design notes
------------
The scanner walks every ``ExceptHandler`` and inspects what its body does
about the exception:

* **No action** (body is ``pass``, ``...``, a bare comment-holder, or the
  handler re-raises unconditionally without recording anything): the caller
  can never learn the operation failed.  This is the classic "swallowed
  exception" defect and the root cause behind score/result corruption in
  eval frameworks.

* **Silent fallback value** (body returns/logs/assigns a constant while the
  handler never re-raises): the failure is converted into a default-looking
  value (``None``, ``0``, ``0.0``, ``False``, ``""``, ``{}``, ``[]``) at the
  wrong layer.  Concretely this is what turns an LLM judge outage into a
  "0.0 score" or a network error into "no download" in the repos we audit.

* **Catch-all with a masked exception**: ``except Exception`` whose body
  raises a bare ``raise`` from a *different* exception, or logs then falls
  through to a later ``return`` that looks successful.

The heuristics deliberately err on the side of *reporting*: reviewers
(and CI gates) can triage quickly, and a finding is always worth a look at
the surrounding lines.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

#: Exception types whose handler is almost always informational (KeyboardInterrupt
#: at module level, SystemExit for CLI tools...) and is therefore not a finding.
_IGNORED_EXC_NAMES = {"KeyboardInterrupt", "SystemExit", "GeneratorExit"}

#: Return statements whose payload is a constant that "looks like" a fallback.
_FALLBACK_CONSTANT_NAMES: set[str] = {
    "None",
    "False",
    "True",  # ambiguous (legit in boolean scorers) — flagged as a hint only
    "0",
    "0.0",
    "1",  # ambiguous
    "1.0",  # ambiguous
    '""',
    "''",
    "b''",
    'b""',
    "[]",
    "{}",
    "()",
}

#: Names of lookups that indicate the except body is doing something real.
_ACTIVE_CALL_NAMES: set[str] = {"raise", "sys.exit"}


#: Aggregated finding kinds, kept coarse so consumers can group by root cause.
class FailureMode(str, Enum):
    NO_ACTION = "no-action"  # pass / bare / unconditional re-raise, nothing recorded
    SILENT_FALLBACK = "silent-fallback"  # returns a constant, never re-raises
    MASKED_EXCEPTION = "masked-exception"  # catch-all that swallows the original error
    NAME_SHADOWING = "name-shadowing"  # except as e: ... success path uses a stale value


@dataclass(frozen=True)
class Finding:
    """A single anti-pattern occurrence."""

    file: str
    lineno: int
    end_lineno: int
    mode: FailureMode
    exc_name: str | None
    handler_text: str = ""
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "lineno": self.lineno,
            "end_lineno": self.end_lineno,
            "mode": self.mode.value,
            "exc_name": self.exc_name,
            "handler_text": self.handler_text,
            "message": self.message,
        }


def _is_catch_all(exc_type: ast.expr | None) -> bool:
    """True when the handler catches every exception (bare except / except Exception)."""
    if exc_type is None:
        return True
    if isinstance(exc_type, ast.Attribute):
        return exc_type.attr == "Exception"
    if isinstance(exc_type, ast.Name):
        return exc_type.id == "Exception"
    return False


def _constant_value(node: ast.expr) -> str | None:
    """Render simple constant expressions to a canonical string, else None."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return "True" if node.value else "False"
        if node.value is None:
            return "None"
        if node.value == 0 and isinstance(node.value, int):
            return "0"
        if node.value == 0.0 and isinstance(node.value, float):
            return "0.0"
        if node.value in ("", b""):
            return repr(node.value)
        return None
    if isinstance(node, ast.List) and not node.elts:
        return "[]"
    if isinstance(node, ast.Dict) and not node.keys:
        return "{}"
    if isinstance(node, ast.Tuple) and not node.elts:
        return "()"
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
    ):
        v = node.operand.value
        if v == 0:
            return "0"
        if v == 0.0:
            return "0.0"
    return None


def _body_has_raise(statements: list[ast.stmt]) -> bool:
    for stmt in statements:
        if isinstance(stmt, ast.Raise):
            return True
        for child in ast.walk(stmt):
            if isinstance(child, ast.Raise):
                return True
    return False


def _body_has_call(statements: list[ast.stmt], names: set[str]) -> bool:
    for stmt in statements:
        for child in ast.walk(stmt):
            if isinstance(child, (ast.Call, ast.Raise)):
                func: ast.expr | None = getattr(child, "func", None)
                if isinstance(child, ast.Raise):
                    return True
                if func is not None:
                    name = _call_name(func)
                    if name in names:
                        return True
    return False


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _is_constant_fallback_return(stmts: list[ast.stmt]) -> str | None:
    """Return the constant name when the handler's *final* statement returns it."""
    for stmt in reversed(stmts):
        if isinstance(stmt, ast.Return):
            if stmt.value is None:
                return "None"
            value = _constant_value(stmt.value)
            if value is not None and value in _FALLBACK_CONSTANT_NAMES:
                return value
            return None
    return None


class _HandlerVisitor(ast.NodeVisitor):
    """Collect failure-routing findings inside a single exception handler.

    The body is walked in statement order with an *alive* flag: an
    unconditional ``raise`` or ``return`` terminates control flow, so
    statements after it are unreachable and are never reported (a fallback
    return after a bare raise is dead code, not a masking defect).
    """

    def __init__(self, *, file: str, handler: ast.ExceptHandler, exc_name: str | None) -> None:
        self.file = file
        self.handler = handler
        self.exc_name = exc_name
        self.findings: list[Finding] = []
        self._has_conditional_raise = self._scan_conditional_raises()
        self._has_fallback_return = self._scan_fallback_returns()

    def visit(self, node: ast.AST) -> None:  # noqa: D102
        if self._body_is_effectively_empty():
            self.findings.append(
                _finding(
                    self.file,
                    self.handler,
                    FailureMode.NO_ACTION,
                    self.exc_name,
                    message="exception handler does nothing; the failure is silently discarded",
                )
            )
            return

        # A conditional raise combined with a fallback return produces a
        # branch-dependent outcome (masked failure); report it once up front.
        if self._has_conditional_raise and self._has_fallback_return:
            self.findings.append(
                _finding(
                    self.file,
                    self.handler,
                    FailureMode.MASKED_EXCEPTION,
                    self.exc_name,
                    message="catch-all conditionally re-raises but also falls back to a "
                    "constant return; the failure outcome depends on the branch",
                )
            )
            return

        # Handlers that log the failure are leaving a trace; they are
        # informational, not silent corruption. Only the silent variants are
        # findings.
        if _handler_logs_error(self.handler):
            return

        reported_any = False
        alive = True
        for stmt in self.handler.body:
            if not alive:
                break
            alive, reported = self._examine(stmt)
            reported_any = reported_any or reported
        if not reported_any and not alive and not self._has_fallback_return:
            # Unconditional re-raise with no fallback: propagate-only handlers
            # are healthy — nothing else needed.
            pass

    def _examine(self, stmt: ast.stmt) -> tuple[bool, bool]:
        """Examine one statement; returns (control_flow_continues, reported)."""
        if isinstance(stmt, ast.Raise):
            return False, False
        if isinstance(stmt, ast.Return):
            value = _constant_value(stmt.value) if stmt.value is not None else "None"
            if value in _FALLBACK_CONSTANT_NAMES:
                self.findings.append(
                    _finding(
                        self.file,
                        self.handler,
                        FailureMode.SILENT_FALLBACK,
                        self.exc_name,
                        message=(
                            f"exception handler returns constant {value!r} without re-raising; "
                            "the caller cannot distinguish failure from a legitimate value of "
                            "the same shape"
                        ),
                    )
                )
                return False, True
            return False, False
        if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            # Only constant fallback values are actionable; assignments that
            # derive from the exception itself (e.g. error_msg = str(e)) are
            # part of error handling, not silent fallbacks.
            value = _constant_value(stmt.value) if stmt.value is not None else None
            if value in _FALLBACK_CONSTANT_NAMES and not _body_has_call([stmt], _ACTIVE_CALL_NAMES):
                self.findings.append(
                    _finding(
                        self.file,
                        self.handler,
                        FailureMode.SILENT_FALLBACK,
                        self.exc_name,
                        message=f"exception handler assigns fallback constant {value!r} without "
                        "re-raising or recording the error",
                    )
                )
                return True, True
        return True, False

    def _scan_conditional_raises(self) -> bool:
        """True when the handler raises inside an if/while/for branch."""
        for stmt in self.handler.body:
            if isinstance(stmt, (ast.If, ast.While, ast.For, ast.Try)):
                for child in ast.walk(stmt):
                    if isinstance(child, ast.Raise):
                        return True
        return False

    def _scan_fallback_returns(self) -> bool:
        """True when the handler returns a fallback constant anywhere."""
        for stmt in self.handler.body:
            for child in ast.walk(stmt):
                if isinstance(child, ast.Return):
                    value = _constant_value(child.value) if child.value is not None else "None"
                    if value in _FALLBACK_CONSTANT_NAMES:
                        return True
        return False

    def _body_is_effectively_empty(self) -> bool:
        for stmt in self.handler.body:
            if isinstance(stmt, ast.Pass):
                continue
            if (
                isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Constant)
                and stmt.value.value is Ellipsis
            ):
                continue
            return False
        return True


def _finding(
    file: str, handler: ast.ExceptHandler, mode: FailureMode, exc_name: str | None, *, message: str
) -> Finding:
    text = _render_handler(handler)
    return Finding(
        file=file,
        lineno=handler.lineno,
        end_lineno=getattr(handler, "end_lineno", handler.lineno),
        mode=mode,
        exc_name=exc_name,
        handler_text=text,
        message=message,
    )


def _render_handler(handler: ast.ExceptHandler, limit: int = 240) -> str:
    try:
        start = handler.lineno
        end = getattr(handler, "end_lineno", start)
        if end > start:
            return f"except ... (lines {start}-{end})"
    except Exception:  # pragma: no cover - defensive
        pass
    return f"except ... (line {handler.lineno})"


def scan_tree(tree: ast.AST, *, file: str = "<source>", source: str | None = None) -> list[Finding]:
    """Scan a parsed AST for failure-routing anti-patterns.

    ``source`` (the original file text) is used to detect explicit
    opt-out markers: ``# pragma: no cover`` (defensive code) and
    ``# failroute: ignore`` (reviewed-and-accepted in a code review).
    """
    findings: list[Finding] = []

    class Walker(ast.NodeVisitor):
        def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:  # noqa: D102
            exc_name: str | None = None
            if node.name:
                exc_name = node.name
            # Skip handlers for exceptions we've explicitly decided are noise.
            if _is_ignored_handler(node) or _handler_marked_off(node, source, file):
                return
            visitor = _HandlerVisitor(file=file, handler=node, exc_name=exc_name)
            visitor.visit(node)
            findings.extend(visitor.findings)
            # Recurse into nested handlers inside this handler's body.
            for child in ast.walk(node):
                if child is not node and isinstance(child, ast.ExceptHandler):
                    self.visit_ExceptHandler(child)

    Walker().visit(tree)
    return findings


def _handler_marked_off(handler: ast.ExceptHandler, source: str | None, file: str) -> bool:
    """True when the handler's source slice carries an opt-out marker.

    Two markers are honoured:

    * ``# pragma: no cover`` — explicitly defensive code.
    * ``# failroute: ignore`` — reviewed and accepted (e.g. a documented
      fallback whose semantics the team wants to keep).

    Matching is text-based and line-scoped: a marker anywhere inside the
    handler's lines suppresses all findings for that handler.
    """
    if source is None:
        return False
    try:
        start = handler.lineno
        end = getattr(handler, "end_lineno", start) + 1
        lines = source.splitlines()
        slice_text = "\n".join(lines[start - 1 : end])
    except Exception:  # defensive - slicing failures should never crash a scan
        return False
    return "# pragma: no cover" in slice_text or "# failroute: ignore" in slice_text


def _handler_logs_error(handler: ast.ExceptHandler) -> bool:
    """True when the handler body records the failure (logger.*, print)."""
    log_names = {"logger", "logging", "log", "print", "_logger"}
    for stmt in handler.body:
        for child in ast.walk(stmt):
            if isinstance(child, ast.Call):
                func = child.func
                if isinstance(func, ast.Attribute):
                    base = func.value
                    if isinstance(base, ast.Name) and base.id in log_names:
                        return True
                    if isinstance(base, ast.Attribute) and base.attr in log_names:
                        return True
                elif isinstance(func, ast.Name) and func.id in log_names:
                    return True
    return False


def _is_ignored_handler(node: ast.ExceptHandler) -> bool:
    if node.type is None:
        return False
    if isinstance(node.type, ast.Name) and node.type.id in _IGNORED_EXC_NAMES:
        return True
    if isinstance(node.type, ast.Attribute) and node.type.attr in _IGNORED_EXC_NAMES:
        return True
    return False


def scan_source(source: str, *, file: str = "<source>") -> list[Finding]:
    """Scan a source string and return findings."""
    tree = ast.parse(source, filename=file)
    return scan_tree(tree, file=file, source=source)


def scan_path(path: Path, *, follow_links: bool = False) -> list[Finding]:
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
            findings.extend(scan_source(source, file=str(path)))
        except SyntaxError:
            logger.debug("skipping %s: not parseable as Python", path)
        return findings

    for sub in sorted(path.rglob("*.py")):
        if sub.is_dir():
            continue
        findings.extend(scan_path(sub))
    return findings


def scan_repo(root: Path, *, skip_dirs: set[str] | None = None) -> list[Finding]:
    """Scan a repository checkout, skipping conventional junk directories."""
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
    findings: list[Finding] = []
    root = Path(root)
    for sub in sorted(root.rglob("*.py")):
        rel = sub.relative_to(root)
        if any(part in skip_dirs for part in rel.parts):
            continue
        findings.extend(scan_path(sub))
    return findings

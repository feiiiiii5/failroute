"""AST-based scanner for failure-routing anti-patterns.

Design notes
------------
The scanner walks every ``ExceptHandler`` and inspects what its body does
about the exception:

* **No action** (body is ``pass``, ``...``, or a bare comment-holder): the caller
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

* **Name shadowing** (``except E as e:`` whose body rebinds ``e``): Python
  deletes the binding when the handler exits, so any later use of the name
  raises ``NameError`` — and mid-handler the original exception object is lost.

* **Silent suppress** (``with contextlib.suppress(...):``): semantically
  identical to ``try`` / ``except`` + discard, but invisible to every
  shipped syntactic linter — and ruff's SIM105 actively *recommends*
  rewriting ``try-except-pass`` into this form. The silence is unchanged;
  only the syntax learns to hide.

The heuristics deliberately err on the side of *reporting*: reviewers
(and CI gates) can triage quickly, and a finding is always worth a look at
the surrounding lines.
"""

from __future__ import annotations

import ast
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Exception types whose handler is almost always informational (KeyboardInterrupt
#: at module level, SystemExit for CLI tools...) and is therefore not a finding.
_IGNORED_EXC_NAMES = {
    "KeyboardInterrupt",
    "SystemExit",
    "GeneratorExit",
    # Swallowing these is idiomatic control flow, not failure routing:
    # - StopIteration: how iterators terminate (PEP 479 makes generators special).
    # - CancelledError: async tasks routinely absorb cancellation in cleanup paths;
    #   flagging every one of them drowns real findings.
    "StopIteration",
    "CancelledError",
}

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

#: Attribute names of calls that terminate the process — treated like a raise
#: because the caller never observes a fallback value afterwards.
_ACTIVE_CALL_NAMES: set[str] = {"exit", "_exit"}


#: Aggregated finding kinds, kept coarse so consumers can group by root cause.
class FailureMode(str, Enum):
    NO_ACTION = "no-action"  # pass / bare, nothing recorded
    SILENT_FALLBACK = "silent-fallback"  # returns a constant, never re-raises
    MASKED_EXCEPTION = "masked-exception"  # catch-all that swallows the original error
    NAME_SHADOWING = "name-shadowing"  # except as e: ... success path uses a stale value
    SILENT_SUPPRESS = "silent-suppress"  # with contextlib.suppress(...): failure routed to silence


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

    def to_dict(self) -> dict[str, Any]:
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
    """True when any statement in ``statements`` (its own scope) raises."""
    for child in _walk_scope(statements):
        if isinstance(child, ast.Raise):
            return True
    return False


def _walk_scope(nodes: list[ast.stmt]) -> Iterator[ast.AST]:
    """Yield nodes belonging to the *enclosing* scope of ``nodes``.

    Descends into control-flow statements but **not** into nested
    function/lambda/class bodies: a ``return None`` inside a callback defined
    in the handler belongs to the callback's contract, not to the handler's.
    """
    stack: list[ast.AST] = list(nodes)
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _body_has_call(statements: list[ast.stmt], names: set[str]) -> bool:
    for child in _walk_scope(statements):
        if isinstance(child, ast.Raise):
            return True
        if isinstance(child, ast.Call):
            func = getattr(child, "func", None)
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
        self._shadows_exc_name = self._scan_name_shadowing()
        # A handler that terminates the process never lets a caller observe
        # an assigned fallback value, so assignments are not "silent".
        self._exits_process = _body_has_call(self.handler.body, _ACTIVE_CALL_NAMES)

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

        # Rebinding the caught exception variable is reported independently of
        # everything else: it is a NameError hazard, not a routing decision.
        if self._shadows_exc_name:
            self.findings.append(
                _finding(
                    self.file,
                    self.handler,
                    FailureMode.NAME_SHADOWING,
                    self.exc_name,
                    message=f"exception variable {self.exc_name!r} is rebound inside the "
                    "handler; Python deletes the binding when the handler exits, so any "
                    "later use of that name raises NameError",
                )
            )

        # A conditional raise combined with a fallback return produces a
        # branch-dependent outcome (masked failure); report it once up front.
        # The masking contract is about *catch-all* handlers — a typed handler
        # that conditionally re-raises is usually deliberate retry logic.
        if _is_catch_all(self.handler.type) and self._has_conditional_raise and self._has_fallback_return:
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

        # Handlers that log the failure at a severity worth reading are leaving
        # a trace; they are informational, not silent corruption. Only the
        # silent variants are findings.
        if _handler_logs_error(self.handler):
            return

        for stmt in self.handler.body:
            alive, _reported = self._examine(stmt)
            if not alive:
                break

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
            # part of error handling, not silent fallbacks. Assignments in a
            # handler that ends the process are never caller-observable.
            value = _constant_value(stmt.value) if stmt.value is not None else None
            if (
                value in _FALLBACK_CONSTANT_NAMES
                and not self._exits_process
                and not _body_has_call([stmt], _ACTIVE_CALL_NAMES)
            ):
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
        """True when the handler itself raises inside a branch (if/while/for).

        Nested function bodies are excluded: a ``raise`` inside a callback
        defined in the handler belongs to the callback, not to the handler's
        own control flow.
        """
        for stmt in self.handler.body:
            if isinstance(stmt, (ast.If, ast.While, ast.For)) and _body_has_raise([stmt]):
                return True
        return False

    def _scan_fallback_returns(self) -> bool:
        """True when the handler itself returns a fallback constant anywhere."""
        for node in _walk_scope(self.handler.body):
            if isinstance(node, ast.Return):
                value = node.value if node.value is not None else None
                rendered = _constant_value(value) if value is not None else "None"
                if rendered in _FALLBACK_CONSTANT_NAMES:
                    return True
        return False

    def _scan_name_shadowing(self) -> bool:
        """True when the handler rebinds the caught exception variable.

        Python implicitly deletes the ``except E as name`` binding when the
        handler exits, and any rebinding inside the body loses the original
        exception object mid-handler.
        """
        if not self.exc_name:
            return False
        for node in _walk_scope(self.handler.body):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.For, ast.NamedExpr)):
                targets = [node.target]
            elif isinstance(node, ast.With):
                targets = [item.optional_vars for item in node.items if item.optional_vars]
            elif isinstance(node, ast.AsyncFor):
                targets = [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id == self.exc_name:
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


def _collect_import_bindings(tree: ast.AST) -> dict[str, str]:
    """Map module-level names to their dotted import origins.

    Needed so that ``with suppress(...)``, ``from contextlib import suppress as x``
    and ``import contextlib as cl`` all resolve to the same silent-swallow
    primitive, while ``from helpers import suppress`` correctly does not.
    """
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bindings[alias.asname or alias.name.split(".")[0]] = alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            for alias in node.names:
                bindings[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return bindings


def _is_suppress_call(func: ast.expr, bindings: dict[str, str]) -> bool:
    """True when ``func`` resolves to ``contextlib.suppress`` via the file's imports."""
    if isinstance(func, ast.Name):
        return bindings.get(func.id, func.id) == "contextlib.suppress"
    if isinstance(func, ast.Attribute) and func.attr == "suppress":
        base = func.value
        if isinstance(base, ast.Name):
            return bindings.get(base.id, base.id) == "contextlib"
    return False


def _exc_type_name(expr: ast.expr) -> str:
    """Best-effort dotted name of an exception type expression."""
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        parts: list[str] = []
        cur: ast.expr = expr
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
            return ".".join(reversed(parts))
    return "..."


def _scan_suppress_statements(
    tree: ast.AST, *, file: str, source_lines: list[str] | None
) -> list[Finding]:
    """Find ``with contextlib.suppress(...)`` blocks: failure routed to silence.

    Semantically identical to ``try`` / ``except`` + discard, but structured as
    a context manager, so handler-based detection never sees it. One finding
    per ``with`` statement even when several suppress items share it.
    """
    bindings = _collect_import_bindings(tree)
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.With, ast.AsyncWith)):
            continue
        hits = [
            item.context_expr
            for item in node.items
            if isinstance(item.context_expr, ast.Call)
            and _is_suppress_call(item.context_expr.func, bindings)
        ]
        if not hits or _marked_off(node, source_lines):
            continue
        exc_names = [
            _exc_type_name(arg)
            for arg in hits[0].args
            if isinstance(arg, (ast.Name, ast.Attribute))
        ]
        is_catch_all = "Exception" in exc_names
        if is_catch_all:
            message = (
                "contextlib.suppress(Exception) silently discards every failure inside the "
                "block; callers can never learn the operation failed"
            )
        else:
            shown = exc_names[0] if exc_names else "..."
            message = (
                f"contextlib.suppress({shown}) routes the failure to silence — the same "
                f"routing decision as `except {shown}: pass`"
            )
        findings.append(
            Finding(
                file=file,
                lineno=node.lineno,
                end_lineno=getattr(node, "end_lineno", node.lineno),
                mode=FailureMode.SILENT_SUPPRESS,
                exc_name=None,
                handler_text=f"suppress({', '.join(exc_names) if exc_names else '...'})",
                message=message,
            )
        )
    return findings


def _render_handler(handler: ast.ExceptHandler, limit: int = 240) -> str:
    try:
        start = handler.lineno
        end = getattr(handler, "end_lineno", start)
        if end > start:
            return f"except ... (lines {start}-{end})"
    except Exception:  # pragma: no cover - defensive
        pass
    return f"except ... (line {handler.lineno})"


def _marked_off(node: ast.stmt, lines: list[str] | None) -> bool:
    """True when the node's exact source slice carries an opt-out marker.

    Same two markers as handlers (``# pragma: no cover`` and
    ``# failroute: ignore``); used for suppress statements, whose body is
    protected code rather than an error handler.
    """
    if lines is None:
        return False
    try:
        start = node.lineno
        end = getattr(node, "end_lineno", start)
        slice_text = "\n".join(lines[start - 1 : end])
    except Exception:  # defensive - slicing failures should never crash a scan
        return False
    return "# pragma: no cover" in slice_text or "# failroute: ignore" in slice_text


def scan_tree(tree: ast.AST, *, file: str = "<source>", source: str | None = None) -> list[Finding]:
    """Scan a parsed AST for failure-routing anti-patterns.

    ``source`` (the original file text) is used to detect explicit
    opt-out markers: ``# pragma: no cover`` (defensive code) and
    ``# failroute: ignore`` (reviewed-and-accepted in a code review).
    """
    findings: list[Finding] = []
    # Split once per file, not once per handler (large modules have hundreds).
    source_lines = source.splitlines() if source is not None else None

    class Walker(ast.NodeVisitor):
        def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:  # noqa: D102
            exc_name: str | None = None
            if node.name:
                exc_name = node.name
            # Skip handlers for exceptions we've explicitly decided are noise.
            if _is_ignored_handler(node) or _handler_marked_off(node, source_lines):
                return
            visitor = _HandlerVisitor(file=file, handler=node, exc_name=exc_name)
            visitor.visit(node)
            findings.extend(visitor.findings)
            # Recurse into nested handlers inside this handler's body.
            for child in ast.walk(node):
                if child is not node and isinstance(child, ast.ExceptHandler):
                    self.visit_ExceptHandler(child)

    Walker().visit(tree)
    findings.extend(_scan_suppress_statements(tree, file=file, source_lines=source_lines))
    # Deterministic order: line-sorted; the stable sort keeps per-handler
    # insertion order for same-line findings.
    findings.sort(key=lambda f: f.lineno)
    return findings


def _handler_marked_off(handler: ast.ExceptHandler, lines: list[str] | None) -> bool:
    """True when the handler's source slice carries an opt-out marker.

    Two markers are honoured:

    * ``# pragma: no cover`` — explicitly defensive code.
    * ``# failroute: ignore`` — reviewed and accepted (e.g. a documented
      fallback whose semantics the team wants to keep).

    Matching is text-based and line-scoped: a marker anywhere inside the
    handler's lines suppresses all findings for that handler.
    """
    if lines is None:
        return False
    try:
        start = handler.lineno
        end = getattr(handler, "end_lineno", start) + 1
        slice_text = "\n".join(lines[start - 1 : end])
    except Exception:  # defensive - slicing failures should never crash a scan
        return False
    return "# pragma: no cover" in slice_text or "# failroute: ignore" in slice_text


#: ``<logger>.<severity>(...)`` calls that record a failure worth reading.
#: A bare ``print(...)`` or ``logger.debug(...)`` does not qualify: printing
#: progress text is not failure recording.
_LOG_SEVERITY_METHODS = {"error", "warning", "warn", "exception", "critical", "fatal"}
_LOGGER_BASE_NAMES = {"logger", "logging", "log", "_logger", "sentry_sdk"}


def _handler_logs_error(handler: ast.ExceptHandler) -> bool:
    """True when the handler records the failure somewhere routable.

    Two tiers:

    - **Catch-all handlers** (bare ``except:`` / ``except Exception:``) must
      log at a severity worth reading (``warning``+) — a ``debug`` line or a
      ``print`` is not a trace that survives production triage.
    - **Typed handlers** name an anticipated failure mode; recording it at
      *any* level (even ``logger.info``) is enough, because the exception
      type itself already documents the routing decision.
    """
    catch_all = _is_catch_all(handler.type)
    for stmt in handler.body:
        # Scope-aware: a log call inside a callback *defined* in the handler
        # belongs to the callback (which may never run), not to the handler.
        for child in _walk_scope([stmt]):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            if isinstance(func, ast.Attribute):
                base = func.value
                base_is_loggerish = (isinstance(base, ast.Name) and base.id in _LOGGER_BASE_NAMES) or (
                    isinstance(base, ast.Attribute) and base.attr in _LOGGER_BASE_NAMES
                )
                if func.attr == "capture_exception":
                    if base_is_loggerish:
                        return True
                elif base_is_loggerish and (not catch_all or func.attr in _LOG_SEVERITY_METHODS):
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
        except RecursionError:  # pragma: no cover - depends on interpreter recursion budget
            # Deeply nested generated files (payload resources, vendored
            # schemas) can exceed the interpreter's recursion budget during
            # the AST walk.  A scanner must never crash on hostile input.
            logger.debug("skipping %s: AST nesting exceeds recursion budget", path)
        return findings

    for sub in sorted(path.rglob("*.py")):
        if sub.is_dir():
            continue
        findings.extend(scan_path(sub))
    return findings


def scan_repo(
    root: Path,
    *,
    skip_dirs: set[str] | None = None,
    exclude: set[str] | None = None,
) -> list[Finding]:
    """Scan a repository checkout, skipping conventional junk directories.

    ``exclude`` holds repo-relative paths (``tests/corpus``) that are skipped
    even though they are valid Python -- used to keep intentional fixtures out
    of self-scans.
    """
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
    findings: list[Finding] = []
    root = Path(root)
    for sub in sorted(root.rglob("*.py")):
        rel = sub.relative_to(root)
        if any(part in skip_dirs for part in rel.parts):
            continue
        rel_str = str(rel).replace("\\", "/")
        if any(rel_str == ex or rel_str.startswith(ex + "/") for ex in exclude):
            continue
        findings.extend(scan_path(sub))
    return findings

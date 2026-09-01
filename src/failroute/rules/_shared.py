"""Shared predicates and helpers used by the detection rules.

Moved verbatim from the v0.5 analyzer monolith so the rules package has one
home for them; :mod:`failroute.analyzer` re-exports the handful the public
API and tests relied on.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator

from failroute.ir import FailureMode, Finding, ScanContext

#: Exception types whose handler is almost always informational (KeyboardInterrupt
#: at module level, SystemExit for CLI tools...) and is therefore not a finding.
IGNORED_EXC_NAMES = {
    "KeyboardInterrupt",
    "SystemExit",
    "GeneratorExit",
    # Swallowing these is idiomatic control flow, not failure routing:
    # - StopIteration: how iterators terminate (PEP 479 makes generators special).
    # - StopAsyncIteration: the async twin -- how async iterators terminate
    #   (PEP 525); absorbing it in drain/copy loops is the documented idiom.
    # - CancelledError: async tasks routinely absorb cancellation in cleanup paths;
    #   flagging every one of them drowns real findings.
    "StopIteration",
    "StopAsyncIteration",
    "CancelledError",
}

#: Return statements whose payload is a constant that "looks like" a fallback.
FALLBACK_CONSTANT_NAMES: set[str] = {
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
ACTIVE_CALL_NAMES: set[str] = {"exit", "_exit"}

#: ``<logger>.<severity>(...)`` calls that record a failure worth reading.
#: A bare ``print(...)`` or ``logger.debug(...)`` does not qualify: printing
#: progress text is not failure recording.
LOG_SEVERITY_METHODS = {"error", "warning", "warn", "exception", "critical", "fatal"}
#: Exact logger base names recognised beyond the suffix heuristic in
#: :func:`is_loggerish_name`.
LOGGER_BASE_NAMES = {"logger", "logging", "log", "_logger", "_log", "sentry_sdk"}
#: ``warnings.<method>(...)`` entry points that surface a failure. The stdlib
#: warning channel is structurally visible (stderr, pytest capture, ``-W error``,
#: ``logging.captureWarnings``) and cannot be level-filtered below warning,
#: so it counts as a signal in typed and catch-all handlers alike. Only the
#: emission entry points qualify -- filter configuration (``simplefilter``...)
#: records nothing routable.
WARNINGS_SIGNAL_METHODS = frozenset({"warn", "warn_explicit"})


def is_loggerish_name(name: str) -> bool:
    """True when a name plausibly denotes a logger object.

    Real codebases name loggers ``logger``, ``LOG``, ``audit_logger``,
    ``err_log``, ``self._log``... An exact five-name whitelist misjudged all
    of those, so recording handlers were falsely reported as silent. The
    heuristic: case-insensitive match on the canonical names, plus the
    conventional suffixes ``_log`` / ``_logger`` / ``logger`` / ``logging``
    (the underscore boundary keeps ``catalog``/``dialog`` out).
    """
    lower = name.lower()
    if lower in LOGGER_BASE_NAMES:
        return True
    return lower.endswith(("_log", "_logger", "logger", "logging"))


def is_catch_all(exc_type: ast.expr | None) -> bool:
    """True when the handler catches every exception (bare except / except Exception)."""
    if exc_type is None:
        return True
    if isinstance(exc_type, ast.Attribute):
        return exc_type.attr == "Exception"
    if isinstance(exc_type, ast.Name):
        return exc_type.id == "Exception"
    return False


def constant_value(node: ast.expr | None) -> str | None:
    """Render a constant expression to its canonical token, else None.

    Canonical tokens are Python-literal renderings: ``None``/``True``/``False``
    verbatim, numbers via ``str`` (``"0"``, ``"1"``, ``"-1"``, ``"3.14"``),
    strings/bytes via ``repr`` (``"''"``, `"b''"`, ``"'N/A'"``), and the empty
    container literals. Non-constant expressions (names, calls, attributes)
    render as ``None`` — matching them is the configurable-sentinel story, not
    a hardcoded guess.
    """
    if node is None:
        return None
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return "True" if node.value else "False"
        if node.value is None:
            return "None"
        if isinstance(node.value, (int, float)):
            return str(node.value)
        if isinstance(node.value, (str, bytes)):
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
        if isinstance(v, bool):
            return None
        if isinstance(v, (int, float)):
            if v == 0:
                return "0" if isinstance(v, int) else "0.0"
            return str(-v)
    return None


def dotted_name(node: ast.expr) -> str | None:
    """Render a dotted attribute chain (``Status.UNKNOWN``) to its name.

    Bare names deliberately render as ``None``: an unqualified token would
    match ``return result``-style code, so only namespace-qualified sentinels
    are ever matchable.
    """
    parts: list[str] = []
    cur: ast.expr = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name) and parts:
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


def is_fallback_value(rendered: str | None, ctx: ScanContext) -> bool:
    """True when a rendered constant is a recognised fallback shape.

    Built-in tokens cover the shapes every codebase shares (``None``, ``0``,
    ``[]``...); project-specific sentinels (``-1``, ``"N/A"``, ``"unknown"``)
    come from ``[tool.failroute] fallback_values`` and live on the scan
    context, so the same source scans identically everywhere while each
    project can teach the scanner its own failure vocabulary.
    """
    if rendered is None:
        return False
    if rendered in FALLBACK_CONSTANT_NAMES:
        return True
    extra = getattr(ctx, "extra_fallback_values", None) or frozenset()
    return rendered in extra


def body_has_raise(statements: list[ast.stmt]) -> bool:
    """True when any statement in ``statements`` (its own scope) raises."""
    for child in walk_scope(statements):
        if isinstance(child, ast.Raise):
            return True
    return False


def walk_scope(nodes: list[ast.stmt]) -> Iterator[ast.AST]:
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


def body_has_call(statements: list[ast.stmt], names: set[str]) -> bool:
    for child in walk_scope(statements):
        if isinstance(child, ast.Raise):
            return True
        if isinstance(child, ast.Call):
            func = getattr(child, "func", None)
            if func is not None:
                name = call_name(func)
                if name in names:
                    return True
    return False


def call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def handler_logs_error(handler: ast.ExceptHandler) -> bool:
    """True when the handler records the failure somewhere routable.

    Three recognised channels:

    - ``warnings.warn(...)`` / ``warnings.warn_explicit(...)``: the stdlib
      warning channel surfaces the failure regardless of handler type (it is
      not level-filterable below warning), so it counts in typed and
      catch-all handlers alike. Deliberately aligned with the contractlens
      labeller, which treats ``warnings.warn`` as an error signal too.
    - **Catch-all handlers** (bare ``except:`` / ``except Exception:``) must
      log at a severity worth reading (``warning``+) — a ``debug`` line or a
      ``print`` is not a trace that survives production triage.
    - **Typed handlers** name an anticipated failure mode; recording it at
      *any* level (even ``logger.info``) is enough, because the exception
      type itself already documents the routing decision.
    """
    catch_all = is_catch_all(handler.type)
    for stmt in handler.body:
        # Scope-aware: a log call inside a callback *defined* in the handler
        # belongs to the callback (which may never run), not to the handler.
        for child in walk_scope([stmt]):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            if isinstance(func, ast.Attribute):
                base = func.value
                if (
                    isinstance(base, ast.Name)
                    and base.id == "warnings"
                    and func.attr in WARNINGS_SIGNAL_METHODS
                ):
                    return True
                base_is_loggerish = (isinstance(base, ast.Name) and is_loggerish_name(base.id)) or (
                    isinstance(base, ast.Attribute) and is_loggerish_name(base.attr)
                )
                if func.attr == "capture_exception":
                    if base_is_loggerish:
                        return True
                elif base_is_loggerish and (not catch_all or func.attr in LOG_SEVERITY_METHODS):
                    return True
    return False


def _handler_exc_member_names(handler: ast.ExceptHandler) -> list[str] | None:
    """Names of every exception type the handler catches; ``None`` when any
    member is not a plain name (subscripts, calls...) or the handler is bare.

    Attribute members reduce to their attribute (``asyncio.CancelledError``
    → ``CancelledError``), matching the historical single-type behaviour.
    """
    exc = handler.type
    if exc is None:
        return None
    members = exc.elts if isinstance(exc, ast.Tuple) else [exc]
    names: list[str] = []
    for member in members:
        if isinstance(member, ast.Name):
            names.append(member.id)
        elif isinstance(member, ast.Attribute):
            names.append(member.attr)
        else:
            return None
    return names


def is_ignored_handler(node: ast.ExceptHandler) -> bool:
    """True when the handler catches only ignore-listed control-flow types.

    Tuple handlers qualify only when *every* member is ignored: a mixed
    ``except (StopIteration, ValueError)`` can swallow real errors, so it
    stays reported (conservative: prefer a finding over a miss).
    """
    names = _handler_exc_member_names(node)
    if not names:
        return False
    return all(name in IGNORED_EXC_NAMES for name in names)


def render_handler(handler: ast.ExceptHandler) -> str:
    try:
        start = handler.lineno
        end = getattr(handler, "end_lineno", start)
        if end > start:
            return f"except ... (lines {start}-{end})"
    except Exception:  # pragma: no cover - defensive
        pass
    return f"except ... (line {handler.lineno})"


def make_finding(
    rule_id: str,
    file: str,
    handler: ast.ExceptHandler,
    mode: FailureMode,
    exc_name: str | None,
    *,
    message: str,
) -> Finding:
    text = render_handler(handler)
    return Finding(
        file=file,
        lineno=handler.lineno,
        end_lineno=getattr(handler, "end_lineno", handler.lineno),
        mode=mode,
        exc_name=exc_name,
        handler_text=text,
        message=message,
        rule_id=rule_id,
    )


def collect_import_bindings(tree: ast.AST) -> dict[str, str]:
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


def exc_type_name(expr: ast.expr) -> str:
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


def suppress_type_is_ignored(name: str) -> bool:
    """True when a suppress argument matches the handler-level ignore list."""
    return name in IGNORED_EXC_NAMES or name.rsplit(".", 1)[-1] in IGNORED_EXC_NAMES


def marked_off(node: ast.stmt, lines: list[str] | None) -> bool:
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


def handler_marked_off(handler: ast.ExceptHandler, lines: list[str] | None) -> bool:
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

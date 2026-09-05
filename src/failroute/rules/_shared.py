"""Shared predicates and helpers used by the detection rules.

Moved verbatim from the v0.5 analyzer monolith so the rules package has one
home for them; :mod:`failroute.analyzer` re-exports the handful the public
API and tests relied on.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from typing import cast

from failroute.ir import (
    Exit,
    FailureMode,
    Finding,
    HandlerFacts,
    Isomorphism,
    ScanContext,
    Severity,
    ValueRange,
)

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
    severity: Severity = Severity.MEDIUM,
    isomorphism: Isomorphism | None = None,
    covered_by: tuple[str, ...] = (),
    verdict: str = "",
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
        severity=severity,
        isomorphism=isomorphism,
        covered_by=tuple(covered_by),
        verdict=verdict,
    )


def facts_for(handler: ast.ExceptHandler, ctx: ScanContext) -> HandlerFacts | None:
    """The dispatcher-computed facts for ``handler``, or ``None`` if absent.

    ``None`` is possible only when a rule is called with a handler that never
    appeared in the scanned tree (a unit test constructing one by hand). Rules
    treat it as "no verdict available" rather than crashing.
    """
    return ctx.handler_facts.get(id(handler))


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


#: Exception names that mark optional-dependency probes. ModuleNotFoundError
#: is ImportError's subclass and the type raised by modern import machinery;
#: both spell the same contract.
IMPORT_EXC_NAMES = frozenset({"ImportError", "ModuleNotFoundError"})


def _is_docstring_stmt(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _try_body_is_import_probe(body: list[ast.stmt]) -> bool:
    """True when the guarded block is an import/setup block, nothing else.

    Allowed statements: imports, and bindings that derive from the import
    attempt (capability flags ``HAS_X = True``, module aliases ``mod = None``
    pre-bindings, error-class aliases). At least one import must be present.
    Anything else — calls with side effects, control flow, nested tries —
    means the ImportError handler may be masking more than an absent optional
    dependency, so it stays reportable (conservative).
    """
    stmts = [s for s in body if not _is_docstring_stmt(s)]
    if not stmts or not any(isinstance(s, (ast.Import, ast.ImportFrom)) for s in stmts):
        return False
    return all(
        isinstance(s, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign)) for s in stmts
    )


def _handler_body_is_minimal_fallback(handler: ast.ExceptHandler) -> bool:
    """True when the handler's reaction is a minimal capability fallback.

    Shapes: nothing (``pass``), a single constant return (``return False``),
    or constant/name bindings only (``HAS_X = False`` plus a fallback error
    alias). Any control flow, call, raise, or nested definition means the
    handler is doing real work on the failure path -- keep it reportable.
    """
    stmts = handler.body
    if all(isinstance(s, ast.Pass) for s in stmts):
        return True
    if len(stmts) == 1 and isinstance(stmts[0], ast.Return):
        value = stmts[0].value
        return value is None or isinstance(value, ast.Constant)
    return all(
        isinstance(s, (ast.Assign, ast.AnnAssign))
        and isinstance(getattr(s, "value", None), (ast.Constant, ast.Name, ast.Attribute))
        for s in stmts
    )


def is_import_probe_handler(try_node: ast.Try, handler: ast.ExceptHandler) -> bool:
    """True when the handler is an optional-dependency probe contract.

    Three conditions, all mandatory; the design decision and the rejected
    broader variants (with their ground-truth cost) are recorded in
    ``docs/f-batch-report.md`` ADR-0001:

    1. it catches *only* ImportError-family names (a mixed tuple could absorb
       real errors raised beside the import);
    2. the guarded block is an import/setup block (:func:`_try_body_is_import_probe`);
    3. the handler body is a minimal capability fallback
       (:func:`_handler_body_is_minimal_fallback`).
    """
    names = _handler_exc_member_names(handler)
    if not names or not all(name in IMPORT_EXC_NAMES for name in names):
        return False
    if not _try_body_is_import_probe(try_node.body):
        return False
    return _handler_body_is_minimal_fallback(handler)


def import_probe_handler_ids(tree: ast.AST) -> frozenset[int]:
    """``id()``s of every handler in ``tree`` adjudicated as an import probe."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if _is_try_node(node):
            for handler in cast(list[ast.ExceptHandler], getattr(node, "handlers", [])):
                if is_import_probe_handler(cast(ast.Try, node), handler):
                    ids.add(id(handler))
    return frozenset(ids)


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


# --------------------------------------------------------------------------------------
# V1 semantics layer
#
# The predicate this detector implements is *not* "a handler's top-level
# statement returned or assigned a generic constant". It is:
#
#     the failure was converted into a value the caller cannot tell apart from
#     success, and that conversion is not what the function was contracted to do.
#
# Three layers decide that, and each one answers a different question:
#
#   layer 1 (value range)          is the routed value inside the declared range?
#   layer 2 (isomorphism)          is the caught exception *the answer itself*?
#   layer 3 (consequence)          how far does the substituted value travel?
#
# 🔴 The load-bearing insight behind layer 2, measured on this project's own
# annotated corpus: `bare except:` stratifies the 80 labelled findings almost
# perfectly (13 bare -> 12 DEFECT / 1 CONTRACT, precision 92.3%; 64 typed ->
# 0 DEFECT). That stratification is not a coincidence — **`bare except` is a
# crude proxy for "not isomorphic"**, because you cannot claim an unknown set of
# exceptions is equivalent to your predicate's answer. It follows that every bit
# of value this tool can add over `flake8 --select E722` (134 candidates on the
# corpus, containing all 12 confirmed defects, versus failroute's 621 for the
# same recall) has to come from deciding isomorphism on *typed* handlers.
# Layer 2 exists to be measured against that bar, not to restate it.
# --------------------------------------------------------------------------------------

#: Recursion budget for :func:`enumerate_exits`. Generated files can nest
#: control flow deeply; a scanner must degrade to "fall-through" rather than
#: exhaust the interpreter's stack.
_MAX_EXIT_DEPTH = 24

#: Statements that make the guarded block *do something*: without one of these
#: the block cannot produce the value the function answers with, so whatever the
#: handler catches cannot be "the answer".
_EFFECT_NODES = (ast.Call, ast.Await, ast.Yield, ast.YieldFrom, ast.Import, ast.ImportFrom)

_MATCH_NODE = getattr(ast, "Match", None)  # 3.10+; None on 3.9
_MATCH_AS_NODE = getattr(ast, "MatchAs", None)

#: ``except*`` (PEP 654) parses to ``ast.TryStar`` on 3.11+. Its fields are
#: identical to ``ast.Try``'s, so every traversal treats the two alike; only the
#: exception group semantics differ, and nothing in this detector depends on
#: those. Before V1 the walk matched ``ast.Try`` alone, which made every
#: ``except*`` handler in a scanned tree silently invisible -- the gate that
#: caught it is the ``except*`` boundary test.
_TRY_STAR = getattr(ast, "TryStar", None)


def _is_try_node(node: ast.AST) -> bool:
    """True for ``try`` and ``try*`` statements alike."""
    if isinstance(node, ast.Try):
        return True
    return _TRY_STAR is not None and isinstance(node, _TRY_STAR)

_LOOP_NODES: tuple[type[ast.For], type[ast.AsyncFor], type[ast.While]] = (
    ast.For,
    ast.AsyncFor,
    ast.While,
)
_COMPREHENSION_NODES = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)

#: Collection mutators: writing the exception into one of these is a side
#: channel that makes the outcome distinguishable without a re-raise.
_SIDE_CHANNEL_METHODS = frozenset(
    {"append", "extend", "add", "update", "insert", "setdefault", "addHandler", "record", "report"}
)

_NONE_ANNOTATION_NAMES = frozenset({"None", "NoneType"})


def _tag(exits: list[Exit], label: str) -> list[Exit]:
    """Prefix every exit's branch label, so messages can name the path."""
    from dataclasses import replace

    return [replace(e, branch=f"{label}/{e.branch}" if e.branch else label) for e in exits]


def _exit_key(exit_: Exit) -> tuple[object, ...]:
    """Identity used to de-duplicate outcomes without depending on ``id()``.

    ``id()`` would make the output depend on CPython's allocation order, which
    is exactly what the determinism gate forbids.
    """
    value = exit_.value
    stmt = exit_.stmt
    return (
        exit_.kind,
        (value.lineno, value.col_offset) if value is not None else None,
        (stmt.lineno, stmt.col_offset) if stmt is not None else None,
        exit_.branch,
    )


def _dedup(exits: list[Exit]) -> list[Exit]:
    seen: set[tuple[object, ...]] = set()
    out: list[Exit] = []
    for e in exits:
        key = _exit_key(e)
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def enumerate_exits(
    stmts: list[ast.stmt] | tuple[ast.stmt, ...],
    cont: tuple[ast.stmt, ...] = (),
    depth: int = 0,
) -> list[Exit]:
    """Every terminal outcome of *all* paths through ``stmts`` then ``cont``.

    This replaces the ``for stmt in handler.body`` walk that only ever saw a
    handler's *direct* statements. The cost of that walk was concrete: a
    handler shaped

        except ValueError:
            if strict:
                return 0.0
            else:
                return 1.0

    reported nothing at all, because neither ``return`` is a direct statement of
    the body. On the pinned corpus the same blind spot hid 19 handlers (measured
    2026-09-04 by re-walking the corpus with a path-sensitive enumerator).

    Coverage: ``if``/``else``, ``with``, ``try``/``except``/``else``/``finally``,
    ``match``/``case`` (3.10+), loops. Loops are approximated conservatively —
    a loop may run zero times, so the fall-through after it is always reachable.
    Nested ``def``/``class``/``lambda`` bodies are never entered: a ``return
    None`` inside a callback defined in the handler belongs to the callback's
    contract, not to the handler's.

    🔴 Each block is expanded exactly once. A reference implementation of this
    idea expands the continuation once for the ``try`` body *and* once per
    handler, which emits (1 + n_handlers) duplicate outcomes; ``_dedup`` would
    hide that on simple shapes and expose it as inflated counts on the rest.
    """
    pending = list(stmts)
    tail_cont = tuple(cont)
    while True:
        if depth > _MAX_EXIT_DEPTH:
            return [Exit("fallthrough", None, None, "depth-limit")]
        if not pending:
            if tail_cont:
                pending, tail_cont = list(tail_cont), ()
                continue
            return [Exit("fallthrough", None, None, "")]

        head, rest_stmts = pending[0], tuple(pending[1:]) + tail_cont

        if isinstance(head, ast.Raise):
            return [Exit("raise", None, head, "raise")]
        if isinstance(head, ast.Return):
            return [Exit("return", head.value, head, "return")]
        if isinstance(head, ast.Continue):
            return [Exit("continue", None, head, "continue")]
        if isinstance(head, ast.Break):
            return [Exit("break", None, head, "break")]
        if isinstance(head, ast.Expr) and isinstance(head.value, ast.Call):
            if call_name(head.value.func) in ACTIVE_CALL_NAMES:
                return [Exit("exit", None, head, "process-exit")]

        if isinstance(head, ast.If):
            out = _tag(enumerate_exits(head.body, rest_stmts, depth + 1), "if")
            if head.orelse:
                out += _tag(enumerate_exits(head.orelse, rest_stmts, depth + 1), "else")
            else:
                # A bare `if` always has a path that skips the body.
                out += _tag(enumerate_exits((), rest_stmts, depth + 1), "if-no-else")
            return _dedup(out)

        if isinstance(head, _LOOP_NODES):
            out = _tag(enumerate_exits(head.body, rest_stmts, depth + 1), "loop-body")
            out += _tag(enumerate_exits(getattr(head, "orelse", []), rest_stmts, depth + 1), "loop-else")
            # Zero iterations is always possible.
            out += _tag(enumerate_exits((), rest_stmts, depth + 1), "loop-zero")
            return _dedup(out)

        if isinstance(head, (ast.With, ast.AsyncWith)):
            return _dedup(_tag(enumerate_exits(head.body, rest_stmts, depth + 1), "with"))

        if _is_try_node(head):
            finalbody = list(getattr(head, "finalbody", []) or [])
            if finalbody:
                fin = enumerate_exits(finalbody, (), depth + 1)
                if any(e.terminates for e in fin):
                    # A `finally` that returns or raises overrides every path.
                    return _dedup(_tag(fin, "finally"))
            orelse = tuple(getattr(head, "orelse", ()) or ())
            body = list(getattr(head, "body", []) or [])
            out = _tag(enumerate_exits(body, orelse + rest_stmts, depth + 1), "try")
            for index, inner in enumerate(getattr(head, "handlers", []) or []):
                out += _tag(enumerate_exits(inner.body, rest_stmts, depth + 1), f"except{index}")
            return _dedup(out)

        if (
            _MATCH_NODE is not None
            and _MATCH_AS_NODE is not None
            and isinstance(head, _MATCH_NODE)
        ):
            out = []
            wildcard = False
            # getattr rather than attribute access: ast.Match only exists on
            # 3.10+, so mypy cannot type the fields on a 3.9 floor.
            for index, case in enumerate(getattr(head, "cases", [])):
                out += _tag(
                    enumerate_exits(getattr(case, "body", []), rest_stmts, depth + 1),
                    f"case{index}",
                )
                pattern = getattr(case, "pattern", None)
                if (
                    _MATCH_AS_NODE is not None
                    and isinstance(pattern, _MATCH_AS_NODE)
                    and getattr(pattern, "pattern", None) is None
                    and getattr(case, "guard", None) is None
                ):
                    wildcard = True
            if not wildcard:
                out += _tag(enumerate_exits((), rest_stmts, depth + 1), "match-no-case")
            return _dedup(out)

        if isinstance(head, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # A definition binds a name and continues; its body is another scope.
            pending = list(rest_stmts)
            tail_cont = ()
            continue

        pending = list(rest_stmts)
        tail_cont = ()


def handler_exits(handler: ast.ExceptHandler) -> tuple[Exit, ...]:
    """Terminal outcomes of a handler body, all paths, in source order."""
    return tuple(enumerate_exits(handler.body))


def _success_path_returns(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.Return]:
    """``return`` statements reachable without going through a handler."""
    out: list[ast.Return] = []
    stack: list[ast.AST] = list(func.body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Return):
            out.append(node)
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef, ast.ExceptHandler),
        ):
            continue
        stack.extend(ast.iter_child_nodes(node))
    return out


def _annotation_is_none(ann: ast.expr) -> bool:
    if isinstance(ann, ast.Constant) and ann.value is None:
        return True
    if isinstance(ann, ast.Name) and ann.id in _NONE_ANNOTATION_NAMES:
        return True
    return isinstance(ann, ast.Attribute) and ann.attr == "NoneType"


def _annotation_admits_none(ann: ast.expr) -> bool:
    """True when ``None`` is a member of the annotated type."""
    if _annotation_is_none(ann):
        return True
    if isinstance(ann, ast.BinOp) and isinstance(ann.op, ast.BitOr):
        return _annotation_admits_none(ann.left) or _annotation_admits_none(ann.right)
    if isinstance(ann, ast.Subscript):
        base_name = dotted_name(ann.value)
        if base_name is None and isinstance(ann.value, ast.Name):
            base_name = ann.value.id
        if base_name in ("Optional", "typing.Optional"):
            return True
        if base_name in ("Union", "typing.Union"):
            slice_node = ann.slice
            elements = slice_node.elts if isinstance(slice_node, ast.Tuple) else [slice_node]
            return any(_annotation_admits_none(e) for e in elements)
    return False


def value_range_of(func: ast.FunctionDef | ast.AsyncFunctionDef | None) -> ValueRange:
    """Layer 1: what the enclosing function's return channel admits.

    🔴 Only an **explicit** annotation downgrades a finding. An unannotated
    function's contract is unknown, and unknown stays reportable — that is the
    conservative direction, and it is also what keeps module-level handlers and
    unannotated helpers visible. Where there is no annotation, the *observed*
    success-path returns decide only whether a value channel exists at all.
    """
    if func is None:
        return ValueRange(kind="absent")
    ann = func.returns
    if ann is not None:
        try:
            declared = ast.unparse(ann)
        except Exception:  # pragma: no cover - unparsing a parsed annotation does not fail
            declared = "..."
        if _annotation_is_none(ann):
            return ValueRange(
                declared=declared, kind="none", admits_none=True,
                declared_explicitly=True, procedure=True,
            )
        if _annotation_admits_none(ann):
            return ValueRange(
                declared=declared, kind="optional", admits_none=True, declared_explicitly=True
            )
        kind = "bool" if declared.replace(" ", "") == "bool" else "other"
        return ValueRange(declared=declared, kind=kind, declared_explicitly=True)

    returns = _success_path_returns(func)
    returns_value = any(
        r.value is not None and constant_value(r.value) != "None" for r in returns
    )
    if not returns_value:
        # No success path yields a value: an implicit/explicit None on the
        # failure path is the same thing the function already does.
        return ValueRange(kind="none", admits_none=True, procedure=True)
    return ValueRange(kind="other")


def guarded_block_is_inert(try_node: ast.Try) -> bool:
    """True when the guarded block produces nothing the answer can depend on.

    The motivating shape, five copies of which are confirmed defects in the
    annotated corpus::

        try:
            self.score == 1      # comparison whose result is thrown away
        except:
            self.success = False

    The block neither calls anything nor binds nor returns, so no value the
    function answers with comes out of it. Whatever the handler catches cannot
    be "the answer", and the handler is unreachable in practice.

    Nested scopes are not entered: a callback defined in the block runs later,
    on someone else's stack.
    """
    for node in walk_scope(try_node.body):
        if isinstance(node, _EFFECT_NODES):
            return False
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Return, ast.Raise)):
            return False
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            return False
    return True


def guarded_block_aggregates(try_node: ast.Try) -> bool:
    """True when the guarded block contains a loop *statement*.

    This is the structural difference between ``is_private_ip`` (one call
    decides the answer, so ``ValueError`` means "not an address" and the author
    can legitimately choose what the predicate means for it) and
    ``is_vulnerable`` (a loop accumulates over test cases, so an exception
    aborts a *partial* computation whose result is then reported as a complete,
    clean "not vulnerable").

    🔴 Comprehensions deliberately do **not** count. The first version of this
    predicate included them and it was wrong, measured on the pinned corpus:
    ``inspect_ai/scorer/_math.py:995`` guards
    ``if not all(isfinite(v) for v in (...)): return False`` inside a
    ``-> bool`` numeric-equivalence test. That generator expression is part of a
    single-shot probe, not an accumulation, and counting it as aggregation
    turned a contract into a HIGH finding. Every confirmed aggregation defect in
    the corpus uses a ``for`` statement. Restricting to loop statements keeps
    the 8:8 split on the annotated ``-> bool`` set unchanged.
    """
    for node in walk_scope(try_node.body):
        if isinstance(node, _LOOP_NODES):
            return True
    return False


def _guarded_block_is_straight_line(try_node: ast.Try) -> bool:
    """True when the guarded block is a probe: calls, bindings, returns, imports.

    Control flow other than a terminating ``if`` means the block is doing work
    whose outcome is not decided by a single operation, so the exception cannot
    be read as the answer.
    """
    allowed = (
        ast.Expr,
        ast.Assign,
        ast.AnnAssign,
        ast.AugAssign,
        ast.Return,
        ast.Import,
        ast.ImportFrom,
        ast.Pass,
        ast.With,
        ast.AsyncWith,
        ast.If,
    )
    for stmt in try_node.body:
        if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
            return False
        if _MATCH_NODE is not None and isinstance(stmt, _MATCH_NODE):
            return False
        if _is_try_node(stmt):
            return False
        if not isinstance(stmt, allowed):
            return False
        for node in walk_scope([stmt]):
            if isinstance(node, _COMPREHENSION_NODES):
                return False
    return True


def isomorphism_of(
    try_node: ast.Try, handler: ast.ExceptHandler, value_range: ValueRange
) -> tuple[Isomorphism, str, bool]:
    """Layer 2: is the caught exception *the answer* to the function's question?

    Returns ``(verdict, reason, dead_probe)``. Three structural signals decide
    it; the function's **name is never one of them** (a polarity regex over
    names was measured on this corpus: it hit 3 of 8 confirmed defects and
    judged ``is_private_ip`` — the one fail-closed positive example in the
    paper — backwards).

    S-A · catch-all-ness. A bare ``except:`` or ``except Exception:`` cannot be
        isomorphic: you cannot claim an unknown set of exceptions is equivalent
        to your predicate's answer.
    S-B · aggregation. A guarded block that loops or comprehends computes an
        answer *incrementally*; an exception aborts it part-way, so the handler
        is reporting a partial result as a complete one.
    S-D · inertness. A guarded block that produces no value at all leaves
        nothing for the exception to be the answer to.
    Otherwise, if the block is a straight-line probe behind a specific exception
    type **and the declared answer is a truth value**, the exception is the
    answer: ISOMORPHIC.

    🔴 The boolean restriction is load-bearing, not a convenience. Without it,
    ``def parse(s) -> int: try: return int(s) / except ValueError: return 0``
    would be excused — yet ``0`` is a legitimate ``int``, so the caller cannot
    tell "unparseable" from "the value is zero". An exception can *be* the
    answer only when the answer has exactly two poles. All eight CONTRACT cases
    in the annotated ``-> bool`` set declare ``-> bool``, and the eight DEFECT
    cases are caught earlier by S-A, so the restriction reproduces that 8:8
    split without letting the excuse leak into numeric or object ranges.
    """
    dead_probe = guarded_block_is_inert(try_node)
    if is_catch_all(handler.type):
        kind = "bare except:" if handler.type is None else f"except {_exc_text(handler.type)}:"
        return (
            Isomorphism.NON_ISOMORPHIC,
            f"{kind} a catch-all cannot be isomorphic with the predicate's answer "
            "— an unknown exception set is not a truth value",
            dead_probe,
        )
    if guarded_block_aggregates(try_node):
        return (
            Isomorphism.NON_ISOMORPHIC,
            "the guarded block iterates or comprehends, so an exception aborts a partial "
            "computation whose result is then reported as complete",
            dead_probe,
        )
    if dead_probe:
        return (
            Isomorphism.NON_ISOMORPHIC,
            "the guarded block calls nothing, binds nothing and returns nothing, so no "
            "value the function answers with comes out of it",
            dead_probe,
        )
    if _guarded_block_is_straight_line(try_node) and value_range.declared_explicitly and (
        value_range.kind == "bool"
    ):
        return (
            Isomorphism.ISOMORPHIC,
            f"except {_exc_text(handler.type)} guards a straight-line probe in a function "
            "declared `-> bool`, so the exception is the negative answer rather than a "
            "failure being routed",
            dead_probe,
        )
    return (
        Isomorphism.UNKNOWN,
        "the guarded block is a specific-typed handler whose structure does not decide "
        "whether the exception is the answer or a failure being substituted for one",
        dead_probe,
    )


def _exc_text(exc: ast.expr | None) -> str:
    if exc is None:
        return "..."
    try:
        return ast.unparse(exc)
    except Exception:  # pragma: no cover - defensive
        return "..."


def _bound_name_used_in(node: ast.AST, name: str) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id == name and isinstance(child.ctx, ast.Load):
            return True
    return False


def exception_escapes(handler: ast.ExceptHandler, exits: tuple[Exit, ...]) -> bool:
    """True when the exception object itself reaches the caller.

    Logging is *not* an escape: a log line does not change what the caller
    receives. What does change it is the exception travelling inside the
    returned value or into a side channel that outlives the call —
    ``return Score(value=0.0, explanation=str(e))``, ``errors.append(e)``.
    That is the only thing that makes a substituted value genuinely
    distinguishable, so it is the only downgrade that reaches INFO on its own.
    """
    name = handler.name
    if not name:
        return False
    for exit_ in exits:
        if exit_.kind == "return" and exit_.value is not None:
            if _bound_name_used_in(exit_.value, name):
                return True
    for node in walk_scope(handler.body):
        if not isinstance(node, ast.Call):
            continue
        # 🔴 Deliberately restricted to *programmatic* side channels. §V1.1
        # layer 3 names the two things that genuinely make an outcome
        # distinguishable -- the exception travelling in the return value, or
        # into a collection the caller reads -- and separately says a log line
        # is only a one-level modifier. Writing the exception to stderr is a log
        # channel, so it stays a modifier; treating it as an escape made probes
        # C2 and C3 disappear, which is exactly the behaviour §V1.0-A calls
        # wrong. (The fickling ``_has_interpretation_error`` flag that motivated
        # the broader version is handled by the answer-target gate in
        # ``silent_fallback`` instead, which is where it belongs.)
        if call_name(node.func) in _SIDE_CHANNEL_METHODS:
            if any(_bound_name_used_in(arg, name) for arg in node.args):
                return True
            if any(_bound_name_used_in(kw.value, name) for kw in node.keywords):
                return True
    return False


def amplifies(handler: ast.ExceptHandler, exits: tuple[Exit, ...]) -> bool:
    """True when the substituted value outlives the call or feeds a result.

    Two shapes raise the consequence by one level:

    * the value lands in **object state** (``self.success = False``) — the
      caller reads it long after the handler returned, and nothing marks it as
      the failure path. All four confirmed ``__init__`` defects in the
      annotated corpus are this shape;
    * the value is handed to a **result constructor or collection** rather than
      returned bare, so it is indistinguishable from a computed result.
    """
    for node in walk_scope(handler.body):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            targets = [node.target]
        if any(isinstance(t, ast.Attribute) for t in targets):
            return True
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(
            getattr(node, "value", None), ast.Call
        ):
            return True
    for exit_ in exits:
        if exit_.kind == "return" and isinstance(exit_.value, ast.Call):
            return True
    return False


#: Trivial-lint rules that flag a handler purely from its shape. Derived from
#: measurement rather than from rule documentation: ``tools/lint_mapping_probe.py``
#: generates handler-kind x body-shape probes, runs all four baselines over them,
#: attributes every hit to the case whose function span contains it, and writes the
#: matrix to ``bench/lint-rule-mapping.json``. The tables below must equal that
#: matrix; ``tools/lint_mapping_probe.py --check-encoded`` exits non-zero when they
#: diverge and ``tests/test_lint_mapping.py`` pins the same equality in CI.
#:
#: 🔴 V3: the body-shape rules are NOT handler-kind agnostic, and the V1 table did not
#: know it. It credited ``bandit:B110``/``ruff:S110`` to *every* empty-bodied handler,
#: which over-credited the linters on 145 corpus findings and drove the paper's static
#: novelty figure down to 18.3% when the measured figure is 47.7%. Two independent
#: conditions were missing, and the probe measured both:
#:
#:   * **caught type.** ``ruff:S110``/``S112`` fire when the handler is bare or catches
#:     ``Exception``/``BaseException`` (including inside a tuple). ``bandit:B110``/``B112``
#:     are narrower: bare or *exactly* ``except Exception:``. They do not fire on
#:     ``except BaseException:`` nor on ``except (Exception, ValueError):``. Gating all
#:     four rules on one "broad" predicate would have moved the over-credit rather than
#:     removed it.
#:   * **body form.** ``S110``/``B110`` are literally "try-except-**pass**": they fire on
#:     a body of ``pass`` and NOT on a body of ``...``, even for a bare handler. This
#:     module's own ``body_empty`` accepts both forms, so the distinction has to be made
#:     here rather than inherited from that flag.
#:
#: Also measured, and deliberately not credited:
#:   * ``ruff:SIM105`` fires on a ``pass`` *or* ``...`` body for **every** handler kind,
#:     narrow ones included. It is not credited because it is not in the paper's baseline
#:     rule selection, and because what it says is "rewrite this as
#:     ``contextlib.suppress``" --- the very rewrite that moves the shape out of every
#:     linter's reach (Section 1 of the paper). Counting it as coverage would claim a
#:     rule covers a handler when the rule's advice is to make it uncoverable. Note the
#:     intra-ruff inconsistency the probe found: SIM105 treats ``...`` as pass-equivalent
#:     while S110 does not.
#:   * ``contextlib.suppress(...)`` is flagged by **no** tool in the set, at any caught
#:     type, which is why ``silent-suppress`` findings always carry an empty
#:     ``covered_by``. The probe reproduces this on a synthetic case, independently of
#:     the corpus.
#:   * ``BLE001`` fires on ``except Exception:`` but **not** on a bare ``except:``; it
#:     covered 0 of the 12 confirmed defects, all of which are bare handlers.
#:   * pylint 4.x accepts ``W0703`` (the retired broad-except id the paper's RQ1 baseline
#:     enables) and reports those messages as ``W0718``. Enabling only ``W0703`` emits
#:     ``W0718`` and nothing else, so the table names ``W0718``.
_LINT_BY_BARE = ("flake8:E722", "ruff:E722", "bugbear:B001", "pylint:W0702")
_LINT_BY_CATCH_ALL_TYPED = ("ruff:BLE001", "pylint:W0718")
_LINT_BY_PASS_BODY_BROAD = ("ruff:S110",)
_LINT_BY_PASS_BODY_BARE_OR_EXCEPTION = ("bandit:B110",)
_LINT_BY_CONTINUE_BODY_BROAD = ("ruff:S112",)
_LINT_BY_CONTINUE_BODY_BARE_OR_EXCEPTION = ("bandit:B112",)
_LINT_BY_DISCARDED_COMPARISON = ("bugbear:B015", "ruff:B015")


def _handler_catches_base_exception(handler: ast.ExceptHandler) -> bool:
    """True when the caught type includes ``Exception`` or ``BaseException``.

    Walks the tuple members directly rather than delegating to
    :func:`_handler_exc_member_names`, which returns ``None`` as soon as one member is
    not statically resolvable. That bail-out is correct for the exemption gate but wrong
    here: ``except (anyio.get_cancelled_exc_class(), Exception):`` has an unresolvable
    first member and a plain ``Exception`` second, and the probe measures that
    ``BLE001``, ``W0718`` and ``S110`` all fire on it. Treating the whole handler as
    narrow would under-credit the linters and so over-state novelty --- the same
    direction of error this mapping exists to remove, with the opposite sign. Three
    ``inspect_ai`` findings in the corpus have exactly this shape.

    Still narrow, as measured: a dotted ``asyncio.CancelledError``, a caught type that
    is a bare call expression, and a ``Name`` that merely ends in ``Exception``
    (``JsonPointerException``).
    """
    exc_type = handler.type
    if exc_type is None:
        return False
    members = exc_type.elts if isinstance(exc_type, ast.Tuple) else [exc_type]
    for member in members:
        node = member.value if isinstance(member, ast.Starred) else member
        if isinstance(node, ast.Name) and node.id in ("Exception", "BaseException"):
            return True
        if isinstance(node, ast.Attribute) and node.attr in ("Exception", "BaseException"):
            return True
    return False


def _handler_is_bare_or_plain_exception(handler: ast.ExceptHandler) -> bool:
    """bandit's B110/B112 condition: bare, or the caught type is exactly ``Exception``.

    Deliberately narrower than :func:`_handler_catches_base_exception`, and the
    difference is measured rather than assumed: bandit does not fire on
    ``except BaseException:`` nor on ``except (Exception, ValueError):``, where ruff's
    S110/S112 do. Reading the type straight off the AST instead of going through
    ``_handler_exc_member_names`` keeps a dotted ``except mod.Exception:`` out, since
    that helper flattens attribute members to their last component.
    """
    if handler.type is None:
        return True
    return isinstance(handler.type, ast.Name) and handler.type.id == "Exception"


def covered_by_for(
    handler: ast.ExceptHandler,
    *,
    body_empty: bool,
    dead_probe: bool,
) -> tuple[str, ...]:
    """Lint rules that already point at this handler, inferred from its shape.

    Static inference, not a subprocess call: the shape that makes a rule fire is the
    shape we are already looking at, and spawning four linters per finding would make
    the differential unusable. What makes this trustworthy is that every condition
    below was measured against the real tools rather than read off their names --- see
    the constants above for the matrix and for the two conditions V1 got wrong.
    """
    covered: set[str] = set()
    bare = handler.type is None
    broad = bare or _handler_catches_base_exception(handler)
    if bare:
        covered.update(_LINT_BY_BARE)
    elif broad:
        covered.update(_LINT_BY_CATCH_ALL_TYPED)
    # `body_empty` accepts `pass` and `...` alike; S110/B110 accept only `pass`.
    body_all_pass = bool(handler.body) and all(isinstance(s, ast.Pass) for s in handler.body)
    if body_empty and body_all_pass:
        if broad:
            covered.update(_LINT_BY_PASS_BODY_BROAD)
        if _handler_is_bare_or_plain_exception(handler):
            covered.update(_LINT_BY_PASS_BODY_BARE_OR_EXCEPTION)
    elif all(isinstance(s, ast.Continue) or isinstance(s, ast.Pass) for s in handler.body):
        if any(isinstance(s, ast.Continue) for s in handler.body):
            if broad:
                covered.update(_LINT_BY_CONTINUE_BODY_BROAD)
            if _handler_is_bare_or_plain_exception(handler):
                covered.update(_LINT_BY_CONTINUE_BODY_BARE_OR_EXCEPTION)
    if dead_probe:
        # B015 points at the discarded comparison inside the guarded block, not
        # at the handler, but it is the same defect and the same line range.
        # Measured kind-agnostic: it fires on narrow handlers too.
        covered.update(_LINT_BY_DISCARDED_COMPARISON)
    return tuple(sorted(covered))


def handler_facts_for(
    tree: ast.AST,
) -> dict[int, HandlerFacts]:
    """Compute :class:`HandlerFacts` for every handler in ``tree``, once.

    The dispatcher calls this before any rule runs, so no rule re-derives a
    predicate and two rules cannot disagree about the same handler.
    """
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node

    facts: dict[int, HandlerFacts] = {}
    for node in ast.walk(tree):
        if not _is_try_node(node):
            continue
        for handler in cast(list[ast.ExceptHandler], getattr(node, "handlers", [])):
            func = _enclosing_function(parents, handler)
            value_range = value_range_of(func)
            exits = handler_exits(handler)
            iso, iso_reason, dead_probe = isomorphism_of(
                cast(ast.Try, node), handler, value_range
            )
            body_empty = all(
                isinstance(s, ast.Pass)
                or (
                    isinstance(s, ast.Expr)
                    and isinstance(s.value, ast.Constant)
                    and s.value.value is Ellipsis
                )
                for s in handler.body
            )
            facts[id(handler)] = HandlerFacts(
                func=func,
                value_range=value_range,
                exits=exits,
                isomorphism=iso,
                iso_reason=iso_reason,
                logs=handler_logs_error(handler),
                exception_escapes=exception_escapes(handler, exits),
                amplifies=amplifies(handler, exits),
                covered_by=covered_by_for(handler, body_empty=body_empty, dead_probe=dead_probe),
                try_node=cast(ast.Try, node),
                body_empty=body_empty,
                dead_probe=dead_probe,
                annotated_none_vars=annotated_none_vars(func),
                answer_targets=answer_targets_for(cast(ast.Try, node), func),
                is_generator=bool(func is not None and _function_is_generator(func)),
            )
    return facts


def annotated_none_vars(func: ast.FunctionDef | ast.AsyncFunctionDef | None) -> frozenset[str]:
    """Locals whose own annotation admits ``None``.

    Motivating shape, labelled CONTRACT in the pinned corpus
    (inspect_ai ``evalset.py:900``)::

        completed_at: float | None = None
        try:
            completed_at = datetime_from_iso_format_safe(s).timestamp()
        except (ValueError, TypeError):
            completed_at = None

    The handler writes ``None`` back into a name that was declared nullable and
    already held ``None``. That is the variable-level form of layer 1: the value
    is inside the declared range, so the caller is not being handed a substitute
    for a result.

    🔴 This is deliberately restricted to *annotated* locals. It must not reach
    the ``__init__`` defects in the corpus (``self.system_prompt = ""``): those
    target an attribute, not a name, and the value is not ``None``.
    """
    if func is None:
        return frozenset()
    names: set[str] = set()
    for node in walk_scope(func.body):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if _annotation_admits_none(node.annotation):
                names.add(node.target.id)
    return frozenset(names)


def _assign_target_texts(node: ast.AST) -> list[str]:
    """Dotted target texts of one assignment-ish node."""
    targets: list[ast.expr] = []
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        targets = [node.target]
    elif isinstance(node, (ast.For, ast.AsyncFor)):
        targets = [node.target]
    out: list[str] = []
    for target in targets:
        text = _target_text(target)
        if text is not None:
            out.append(text)
    return out


def _loaded_texts(node: ast.AST) -> set[str]:
    """Dotted texts of every Name/Attribute *read* inside ``node``."""
    out: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
            out.add(child.id)
        elif isinstance(child, ast.Attribute) and isinstance(child.ctx, ast.Load):
            text = _target_text(child)
            if text is not None:
                out.add(text)
    return out


def _function_is_generator(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in walk_scope(func.body):
        if isinstance(node, (ast.Yield, ast.YieldFrom)):
            return True
    return False


def answer_targets_for(
    try_node: ast.Try, func: ast.FunctionDef | ast.AsyncFunctionDef | None
) -> frozenset[str]:
    """Targets that plausibly *are* the answer the caller consumes.

    Three ways in, all structural:

    * assigned inside the guarded block — the handler overwrites a value the
      block was computing (all four confirmed ``__init__`` defects, and
      ``is_vulnerable``'s accumulator);
    * returned by the enclosing function on a success path (``is_successful``
      assigns ``self.success`` in the handler and the function returns it);
    * read after the ``try`` — the value is consumed downstream in the same call.

    Anything else is internal bookkeeping. Derived by reading every
    specific-typed HIGH finding in the pinned corpus: the false positives were
    all flags like ``self._did_stream = True`` or
    ``self._has_interpretation_error = True`` that no caller reads as a result.
    """
    targets: set[str] = set()
    for node in walk_scope(try_node.body):
        targets.update(_assign_target_texts(node))
    if func is None:
        return frozenset(targets)
    for ret in _success_path_returns(func):
        if ret.value is not None:
            targets |= _loaded_texts(ret.value)
    end = getattr(try_node, "end_lineno", try_node.lineno) or try_node.lineno
    for node in walk_scope(func.body):
        line = getattr(node, "lineno", 0)
        if line > end and isinstance(node, (ast.Name, ast.Attribute)) and isinstance(
            node.ctx, ast.Load
        ):
            text = _target_text(node)
            if text is not None:
                targets.add(text)
    return frozenset(targets)


def _enclosing_function(
    parents: dict[int, ast.AST], node: ast.AST
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    cur = parents.get(id(node))
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return cur
        cur = parents.get(id(cur))
    return None


#: ``float("nan")`` / ``math.nan`` / ``np.nan`` — a floating-point sentinel that
#: looks like a computed score to the caller. Measured at 2 occurrences in the
#: pinned corpus, so this is a convenience, not a result: it is deliberately
#: narrow (exact spellings only) and no claim is built on it.
_NAN_WORDS = frozenset({"nan", "inf", "infinity"})
_NAN_MODULES = frozenset({"math", "np", "numpy"})


def nan_shape(node: ast.expr | None) -> str | None:
    """Canonical token when ``node`` is a NaN/inf sentinel, else ``None``."""
    if node is None:
        return None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "float":
        if len(node.args) == 1 and isinstance(node.args[0], ast.Constant):
            text = node.args[0].value
            if isinstance(text, str) and text.strip().lstrip("+-").lower() in _NAN_WORDS:
                return f"float({text!r})"
    if isinstance(node, ast.Attribute) and node.attr.lower() in ("nan", "inf"):
        base = node.value
        if isinstance(base, ast.Name) and base.id in _NAN_MODULES:
            return f"{base.id}.{node.attr}"
    if isinstance(node, ast.Tuple):
        for element in node.elts:
            token = nan_shape(element)
            if token is not None:
                return token
    return None


def fallback_token(value: ast.expr | None, ctx: ScanContext) -> str | None:
    """Canonical token when ``value`` is a recognised fallback shape, else ``None``.

    One cascade for every rule: literal constant, then namespace-qualified
    sentinel (``Status.UNKNOWN``), then NaN/inf shape. A bare name never
    matches — ``return result`` is not a sentinel, it is a value the detector
    cannot see the provenance of.
    """
    if value is None:
        return None
    rendered = constant_value(value)
    if rendered is None:
        rendered = dotted_name(value)
    if rendered is not None and (
        is_fallback_value(rendered, ctx) or rendered in ctx.extra_fallback_names
    ):
        return rendered
    nan = nan_shape(value)
    return nan


@dataclass(frozen=True)
class Binding:
    """One assignment anywhere in a handler body, with the path that reaches it."""

    #: Dotted target text (``self.success``, ``result``).
    target: str
    #: True when the target is an attribute, i.e. state that outlives the call.
    to_attribute: bool
    #: The assigned expression.
    value: ast.expr | None
    #: The assignment statement.
    stmt: ast.stmt
    #: Path label from the handler entry, e.g. ``"if"`` or ``""`` for top level.
    branch: str


def handler_bindings(handler: ast.ExceptHandler) -> list[Binding]:
    """Every assignment reachable in the handler body, path-labelled.

    Replaces the top-level-only ``for stmt in handler.body`` scan, which could
    not see ``if flag: result = None`` at all. Nested ``def``/``class``/
    ``lambda`` bodies are not entered.
    """
    out: list[Binding] = []

    def visit(stmts: list[ast.stmt], branch: str) -> None:
        for stmt in stmts:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            targets: list[ast.expr] = []
            if isinstance(stmt, ast.Assign):
                targets = list(stmt.targets)
            elif isinstance(stmt, (ast.AnnAssign, ast.AugAssign)):
                targets = [stmt.target]
            for target in targets:
                text = _target_text(target)
                if text is None:
                    continue
                out.append(
                    Binding(
                        target=text,
                        to_attribute=isinstance(target, ast.Attribute),
                        value=getattr(stmt, "value", None),
                        stmt=stmt,
                        branch=branch,
                    )
                )
            if isinstance(stmt, ast.If):
                visit(stmt.body, _join(branch, "if"))
                visit(stmt.orelse, _join(branch, "else"))
            elif isinstance(stmt, _LOOP_NODES):
                visit(stmt.body, _join(branch, "loop"))
                visit(list(getattr(stmt, "orelse", []) or []), _join(branch, "loop-else"))
            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                visit(stmt.body, _join(branch, "with"))
            elif _is_try_node(stmt):
                visit(list(getattr(stmt, "body", []) or []), _join(branch, "try"))
                for index, inner in enumerate(getattr(stmt, "handlers", []) or []):
                    visit(list(inner.body), _join(branch, f"except{index}"))
                visit(list(getattr(stmt, "orelse", []) or []), _join(branch, "try-else"))
                visit(list(getattr(stmt, "finalbody", []) or []), _join(branch, "finally"))
            elif _MATCH_NODE is not None and isinstance(stmt, _MATCH_NODE):
                for index, case in enumerate(getattr(stmt, "cases", [])):
                    visit(list(getattr(case, "body", [])), _join(branch, f"case{index}"))

    visit(handler.body, "")
    return out


def _join(branch: str, label: str) -> str:
    return f"{branch}/{label}" if branch else label


def _target_text(target: ast.expr) -> str | None:
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        base = _target_text(target.value)
        return f"{base}.{target.attr}" if base is not None else target.attr
    if isinstance(target, ast.Subscript):
        base = _target_text(target.value)
        return f"{base}[...]" if base is not None else None
    if isinstance(target, (ast.Tuple, ast.List)):
        return None  # unpacking: no single name to follow
    return None


def severity_for(
    facts: HandlerFacts,
    *,
    mode_default: Severity,
    channel: str,
    routed_none: bool = False,
    target: str = "",
) -> tuple[Severity | None, str]:
    """Decide *whether* this is failure-routing, and if so how bad.

    ``channel`` says how the failure leaves the handler: ``"return"``,
    ``"assign"``, ``"fallthrough"`` or ``"silence"``. Layer 1 is about the
    **return channel**, so it can only excuse the first and third — an
    assignment to ``self.system_prompt`` in a ``-> None`` constructor still
    routes the failure into state the caller reads later, and all four
    confirmed ``__init__`` defects in the annotated corpus are exactly that.

    A returned severity of ``None`` means **suppress**: not a low-severity
    finding, but "this handler is not doing failure-routing at all".

    Order is fixed:

    1. the exception object reaches the caller → suppress (probe C7: ``return
       Score(value=0.0, explanation=str(e))`` carries the failure with it);
    2. the **declared** range admits ``None`` and the routed value is ``None``
       (or the function is declared ``-> None``, so it has no value channel at
       all) → suppress for return/fall-through, INFO for pure silence
       (probe C4);
    3. the handler is isomorphic with the predicate it serves → suppress;
    4. otherwise start from the rule's default and apply the two modifiers:
       recording the failure moves it down one level, a value that outlives the
       call moves it up one.

    🔴 Step 4 is where the old behaviour was wrong. Recording a failure used to
    be an *exemption*, which made ``logger.warning(...)`` + ``return 0.0``
    invisible (probe C2) and ``logger.info(...)`` + ``return 0.0`` invisible
    too (probe C3). A log line does not change what the caller receives, so it
    can only ever be a modifier.
    """
    if facts.exception_escapes:
        return None, "the exception object reaches the caller, so the outcome is distinguishable"

    # The assign channel has its own declared range: a local annotated
    # `float | None` and initialised to None is not being corrupted when the
    # handler writes None back into it.
    if channel == "assign" and routed_none and target in facts.annotated_none_vars:
        return None, (
            f"`{target}` is itself declared nullable, so writing None back restores the "
            "value the name already held rather than substituting one for a result"
        )

    # 🔴 In a generator the value channel is the yield protocol, not `return`:
    # a bare `return` only ends iteration. Reporting it as a substituted value
    # was a false positive found by reading the corpus (pydantic-ai
    # `realtime/google.py:1158`, an `__aiter__` whose handler reconnects or
    # re-raises). `implicit-fallback` has skipped generators for the same reason
    # since v0.6.
    if facts.is_generator and channel in ("return", "fallthrough") and routed_none:
        return None, (
            "the enclosing function is a generator, so a bare/None return ends iteration "
            "rather than substituting a value the caller reads"
        )

    vr = facts.value_range
    if vr.declared_explicitly and vr.admits_none:
        if channel in ("return", "fallthrough") and (routed_none or vr.kind == "none"):
            return None, (
                f"declared return range `{vr.declared or 'None'}` already admits None, so "
                "routing the failure there is what the contract asks for"
            )
        if channel == "silence":
            # Recorded as INFO rather than suppressed: a declared `-> None` or
            # `Optional[...]` means the caller was told to expect absence, so
            # nothing is being substituted for a result -- but the failure is
            # still unrecorded, and a reviewer may want to see that. Two corpus
            # CONTRACT labels rest on exactly this (inspect_ai `file.py:375`,
            # a capability probe that falls through to a second attempt, and
            # `http.py:156`, which falls through to an explicit `return None`).
            return Severity.INFO, (
                f"declared return range `{vr.declared}` admits None and the handler "
                "substitutes no value, so only the absence of a record remains"
            )

    if facts.isomorphism is Isomorphism.ISOMORPHIC:
        return None, facts.iso_reason

    severity = mode_default
    notes = [facts.iso_reason]
    if facts.logs:
        severity = severity.shifted(-1)
        notes.append(
            "the failure is recorded, which lowers the consequence but does not make "
            "the returned value distinguishable"
        )
    if facts.amplifies:
        severity = severity.shifted(+1)
        notes.append("the substituted value outlives the call or feeds a result object")
    return severity, "; ".join(notes)

"""``implicit-fallback`` rule: the handler falls through, so failure becomes ``None``.

The blind spot that motivated this rule: the v0.5 visitor only examined
``raise`` / ``return`` / assignment statements, and the no-action rule only
recognised ``pass`` / ``...`` bodies. A handler whose body is a bare
expression statement —

    except Exception:
        print("failed")        # or any unrecognized call / control flow

— fell through both gates, yet inside a function that returns real values on
its success path the caller observes exactly the same outcome as
``except Exception: pass``: an implicit ``return None``.

The rule reports that shape, gated for precision:

* the ``try`` must sit in **tail position** of the enclosing function (last
  statement of its block, behind non-loop blocks only) — otherwise the
  fall-through re-enters control flow (next loop iteration, a trailing
  ``return``) instead of reaching the implicit ``None``;
* the **enclosing function** must return a non-``None`` value somewhere on
  its success path (explicit ``return <expr>`` outside any handler) — in a
  procedure, or a function whose only ``return`` is bare/``None``, the
  fall-through value is the legitimate contract, not a fallback;
* generator functions are skipped (fall-through ends iteration, a different
  contract);
* handlers that record the failure at a readable severity stay exempt (the
  documented logging limitation);
* handlers already reported under another mode are skipped: empty bodies
  belong to ``no-action``, explicit fallback returns/assignments to
  ``silent-fallback``, and ``sys.exit(...)``-style terminators are treated
  like raises.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator

from failroute.ir import FailureMode, Finding, Rule, RuleSpec, ScanContext
from failroute.rules._shared import (
    ACTIVE_CALL_NAMES,
    constant_value,
    handler_logs_error,
    handler_marked_off,
    is_ignored_handler,
    walk_scope,
)

SPEC = RuleSpec(
    rule_id="implicit-fallback",
    name="ImplicitFallback",
    mode=FailureMode.IMPLICIT_FALLBACK,
    severity="error",
    short_description="Handler falls through to the function's implicit None",
    full_description=(
        "The exception handler neither re-raises, returns explicitly, nor records the "
        "failure, so execution falls through and the enclosing function returns its "
        "implicit None on this path — while the success path returns real values. "
        "Callers cannot distinguish the failure from a legitimate result. Re-raise, "
        "return an explicit failure signal, or record the failure at a severity "
        "worth reading."
    ),
)


def _scope_returns(stmts: list[ast.stmt]) -> Iterator[ast.Return]:
    """Yield ``return`` statements in the enclosing scope, skipping failure paths.

    Unlike :func:`walk_scope`, subtrees rooted at an ``ExceptHandler`` are
    skipped: a ``return`` inside a handler is a failure-path outcome, not the
    success-path value that makes an implicit ``None`` distinguishable.
    """
    stack: list[ast.AST] = list(stmts)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Return):
            yield node
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef, ast.ExceptHandler)
        ):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _is_generator(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in walk_scope(func.body):
        if isinstance(node, (ast.Yield, ast.YieldFrom)):
            return True
    return False


def _returns_real_value(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True when some success-path ``return`` yields a value other than ``None``."""
    for node in _scope_returns(func.body):
        if node.value is None:
            continue
        if constant_value(node.value) == "None":
            continue
        return True
    return False


def _has_top_level_terminal(handler: ast.ExceptHandler) -> bool:
    """True when any *direct* statement of the handler terminates control flow.

    ``raise``/``return`` end the handler; ``continue``/``break`` end it just
    as decisively inside a loop — the skip-and-continue / retry-break shapes
    are deliberate control flow, not fall-throughs to the enclosing
    function's implicit ``None``.
    """
    return any(isinstance(stmt, (ast.Raise, ast.Return, ast.Continue, ast.Break)) for stmt in handler.body)


def _has_top_level_assign(handler: ast.ExceptHandler) -> bool:
    """True when the handler binds a fresh name at top level.

    Only plain assignments count (silent-fallback's territory). An
    ``AugAssign`` counter bump (``failed += 1``) is not a fresh binding and
    reports nowhere else, so the fall-through shape stays this rule's to
    report.
    """
    return any(isinstance(stmt, (ast.Assign, ast.AnnAssign)) for stmt in handler.body)


def _has_top_level_exit(handler: ast.ExceptHandler) -> bool:
    """True when a *direct* statement terminates the process (``sys.exit(...)``).

    Only direct statements count: a process exit inside a branch still
    leaves the other branch falling through, which is exactly the shape this
    rule reports.
    """
    for stmt in handler.body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            func = stmt.value.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else (func.id if isinstance(func, ast.Name) else None)
            )
            if name in ACTIVE_CALL_NAMES:
                return True
    return False


def _body_is_effectively_empty(handler: ast.ExceptHandler) -> bool:
    for stmt in handler.body:
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


def _tail_tries(stmts: list[ast.stmt]) -> Iterator[ast.Try]:
    """Yield ``try`` statements whose handler fall-through reaches the end of
    the enclosing function body.

    The rule's premise — "the caller observes the function's implicit
    ``None`` on this path" — only holds when the ``try`` is the last
    statement of its block and every enclosing block up to the function root
    is itself in tail position. Recursion therefore descends only into
    ``if``/``with`` bodies; a ``try`` inside a loop (or followed by any other
    statement) does **not** qualify: fall-through there re-enters control
    flow (next iteration, the trailing ``return r``) instead of the implicit
    ``None``. Conservative by design — precision over recall.
    """
    if not stmts:
        return
    last = stmts[-1]
    if isinstance(last, ast.Try):
        yield last
    elif isinstance(last, (ast.If, ast.With, ast.AsyncWith)):
        yield from _tail_tries(last.body)


class ImplicitFallbackRule(Rule):
    spec = SPEC

    def check_file(self, tree: ast.AST, ctx: ScanContext) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if _is_generator(node) or not _returns_real_value(node):
                continue
            for try_node in _tail_tries(list(node.body)):
                for handler in try_node.handlers:
                    finding = self._check_handler(handler, ctx)
                    if finding is not None:
                        findings.append(finding)
        return findings

    def _check_handler(self, handler: ast.ExceptHandler, ctx: ScanContext) -> Finding | None:
        # Same dispatcher gates the per-handler rules get; a file-level rule
        # applies them itself.
        if handler_marked_off(handler, ctx.source_lines) or is_ignored_handler(handler):
            return None
        # Documented limitation: a handler that records the failure at a
        # readable severity is informational, not silent.
        if handler_logs_error(handler):
            return None
        # Empty bodies are no-action's shape; explicit fallback values are
        # silent-fallback's shape; a terminating statement (raise / return /
        # process exit) means no fall-through exists.
        if _body_is_effectively_empty(handler):
            return None
        if _has_top_level_assign(handler) or _has_top_level_terminal(handler):
            return None
        if _has_top_level_exit(handler):
            return None
        return Finding(
            file=ctx.file,
            lineno=handler.lineno,
            end_lineno=getattr(handler, "end_lineno", handler.lineno),
            mode=self.spec.mode,
            exc_name=handler.name or None,
            handler_text=f"except ... (line {handler.lineno})",
            message=(
                "exception handler neither re-raises, returns explicitly, nor records the "
                "failure; execution falls through and the enclosing function returns its "
                "implicit None on this path while the success path returns real values"
            ),
            rule_id=self.spec.rule_id,
        )

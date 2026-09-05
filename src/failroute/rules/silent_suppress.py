"""``silent-suppress`` rule: ``with contextlib.suppress(...)`` routes failure to silence.

Semantically identical to ``try`` / ``except`` + discard, but structured as a
context manager, so handler-based detection never sees it — and ruff's SIM105
actively *recommends* rewriting ``try-except-pass`` into this form. The
silence is unchanged; only the syntax learns to hide.

File-level rule: one finding per ``with`` statement even when several
suppress items share it.

🔴 V1 (2026-09-04): only **broad** suppression is reported —
``suppress(Exception)``, ``suppress(BaseException)`` and the bare
``suppress(...)`` whose arguments are not simple names. Suppressing a named,
narrow exception type is the same routing decision as ``except ValueError:
pass``, which this tool reports under ``no-action`` only when the failure is
actually discarded; on the pinned corpus the split measured 23 broad to 4
specific, so the restriction removes 4 findings and keeps every shape that
discards an unbounded exception set.

This rule is also the one place where ``covered_by`` is empty by construction
rather than by luck: ``contextlib.suppress(...)`` is flagged by **no** rule in
ruff, flake8+bugbear, bandit or pylint (verified by running all four over a
synthetic file containing every shape — command and output in the V1 result
section). Ruff's SIM105 goes the *other* way and recommends rewriting
``try/except/pass`` into this form.
"""

from __future__ import annotations

import ast

from failroute.ir import FailureMode, Finding, Rule, RuleSpec, ScanContext, Severity
from failroute.rules._shared import (
    collect_import_bindings,
    exc_type_name,
    marked_off,
    suppress_type_is_ignored,
)

SPEC = RuleSpec(
    rule_id="silent-suppress",
    name="SilentSuppress",
    mode=FailureMode.SILENT_SUPPRESS,
    severity="warning",
    short_description="contextlib.suppress routes the failure to silence",
    full_description=(
        "`with contextlib.suppress(...)` is semantically identical to wrapping the body "
        "in try/except and discarding the matched exceptions: the caller can never learn "
        "the operation failed. Register the decision explicitly (log the failure, "
        "narrow the exception types, or add a `# failroute: ignore` marker)."
    ),
)


def _is_suppress_call(func: ast.expr, bindings: dict[str, str]) -> bool:
    """True when ``func`` resolves to ``contextlib.suppress`` via the file's imports."""
    if isinstance(func, ast.Name):
        return bindings.get(func.id, func.id) == "contextlib.suppress"
    if isinstance(func, ast.Attribute) and func.attr == "suppress":
        base = func.value
        if isinstance(base, ast.Name):
            return bindings.get(base.id, base.id) == "contextlib"
    return False


def _parent_map(tree: ast.AST) -> dict[int, ast.AST]:
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    return parents


def _inside_reraising_handler(
    node: ast.AST, parents: dict[int, ast.AST]
) -> bool:
    """True when ``node`` sits inside a handler that re-raises at top level.

    Best-effort cleanup inside such a handler is not failure routing: the outer
    failure still propagates, so the suppressed error changes nothing about the
    outcome (pydantic-ai's ``except BaseException: with suppress(BaseException):
    ...`` cleanup paths are the motivating shape). Deliberately narrow --
    see ADR-0002:

    * the *nearest* enclosing handler decides; a raise further out does not
      count (an inner handler may still swallow);
    * the raise must be a **direct statement** of that handler's body -- a
      branch-conditional raise may never execute;
    * a nested function/class/lambda boundary stops the walk: a suppress
      inside a callback defined in the handler may run long after the
      handler's raise has done its work.
    """
    cur = parents.get(id(node))
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            return False
        if isinstance(cur, ast.ExceptHandler):
            return any(isinstance(stmt, ast.Raise) for stmt in cur.body)
        cur = parents.get(id(cur))
    return False


class SilentSuppressRule(Rule):
    spec = SPEC

    def check_file(self, tree: ast.AST, ctx: ScanContext) -> list[Finding]:
        bindings = ctx.bindings if ctx.bindings else collect_import_bindings(tree)
        parents = _parent_map(tree)
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
            if not hits or marked_off(node, ctx.source_lines):
                continue
            # Cleanup inside a handler that re-raises: the outer failure still
            # propagates, so the silence changes nothing (ADR-0002).
            if _inside_reraising_handler(node, parents):
                continue
            exc_names = [
                exc_type_name(arg) for arg in hits[0].args if isinstance(arg, (ast.Name, ast.Attribute))
            ]
            # Same ignore list as handlers: suppressing control-flow exception
            # types (cancellation absorption, iterator termination) is idiomatic,
            # not failure routing. Flag unless *every* argument is a simple name
            # on the ignore list -- one flaggable type means real errors are
            # being silenced too.
            if (
                exc_names
                and len(exc_names) == len(hits[0].args)
                and all(suppress_type_is_ignored(n) for n in exc_names)
            ):
                continue
            # V1: broad only. A narrow, named suppression is a documented
            # routing decision of the same kind `except T: pass` is, and
            # reporting it here just duplicated noise (4 of 27 on the corpus).
            broad = {n.rsplit(".", 1)[-1] for n in exc_names} & {"Exception", "BaseException"}
            unresolvable = len(exc_names) != len(hits[0].args)
            if not broad and not unresolvable:
                continue
            if "Exception" in exc_names:
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
                    file=ctx.file,
                    lineno=node.lineno,
                    end_lineno=getattr(node, "end_lineno", node.lineno),
                    mode=self.spec.mode,
                    exc_name=None,
                    handler_text=f"suppress({', '.join(exc_names) if exc_names else '...'})",
                    message=message,
                    rule_id=self.spec.rule_id,
                    severity=Severity.HIGH,
                    covered_by=(),
                    verdict=(
                        "no shipped linter rule flags contextlib.suppress(...): "
                        "verified against ruff, flake8+bugbear, bandit and pylint, "
                        "so this finding is novel by construction"
                    ),
                )
            )
        return findings

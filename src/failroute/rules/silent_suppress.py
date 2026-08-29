"""``silent-suppress`` rule: ``with contextlib.suppress(...)`` routes failure to silence.

Semantically identical to ``try`` / ``except`` + discard, but structured as a
context manager, so handler-based detection never sees it — and ruff's SIM105
actively *recommends* rewriting ``try-except-pass`` into this form. The
silence is unchanged; only the syntax learns to hide.

File-level rule: one finding per ``with`` statement even when several
suppress items share it.
"""

from __future__ import annotations

import ast

from failroute.ir import FailureMode, Finding, Rule, RuleSpec, ScanContext
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


class SilentSuppressRule(Rule):
    spec = SPEC

    def check_file(self, tree: ast.AST, ctx: ScanContext) -> list[Finding]:
        bindings = ctx.bindings if ctx.bindings else collect_import_bindings(tree)
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
                )
            )
        return findings

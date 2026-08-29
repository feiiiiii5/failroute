"""``silent-fallback`` rule: the handler converts the failure into a constant.

Covers both shapes the v0.5 visitor handled per statement:

* a ``return None`` / ``return 0.0`` / ``return []`` ... that never re-raises,
* an assignment of such a constant that later code mistakes for a real value
  (gated on the handler not terminating the process — ``sys.exit(...)`` means
  the fallback is never caller-observable).
"""

from __future__ import annotations

import ast

from failroute.ir import FailureMode, Finding, Rule, RuleSpec, ScanContext
from failroute.rules._shared import (
    ACTIVE_CALL_NAMES,
    body_has_call,
    constant_value,
    handler_logs_error,
    is_catch_all,
    is_fallback_value,
    make_finding,
)
from failroute.rules.masked_exception import _has_conditional_raise, _has_fallback_return

SPEC = RuleSpec(
    rule_id="silent-fallback",
    name="SilentFallback",
    mode=FailureMode.SILENT_FALLBACK,
    severity="error",
    short_description="Failure is converted to a constant fallback value",
    full_description=(
        "The handler returns or assigns a constant fallback (None/0/0.0/False/[]/{}...)"
        " without re-raising or recording the error, so the caller cannot distinguish "
        "a real failure from a legitimate value of the same shape. Route the failure "
        "to the correct outcome instead (propagate, log at error level, or return an "
        "explicit error object)."
    ),
)


def _is_masked(handler: ast.ExceptHandler, ctx: ScanContext) -> bool:
    """True when the catch-all masking gate applies (masked-exception reports it)."""
    if not is_catch_all(handler.type):
        return False
    return _has_conditional_raise(handler) and _has_fallback_return(handler, ctx)


class SilentFallbackRule(Rule):
    spec = SPEC

    def check_handler(
        self, handler: ast.ExceptHandler, exc_name: str | None, ctx: ScanContext
    ) -> list[Finding]:
        # Same gates the v0.5 visitor applied before its statement walk:
        # a masked catch-all reports once under masked-exception instead, and
        # handlers that log the failure at a readable severity are
        # informational rather than silent.
        if _is_masked(handler, ctx) or handler_logs_error(handler):
            return []
        # A handler that terminates the process never lets a caller observe
        # an assigned fallback value, so assignments are not "silent".
        exits_process = body_has_call(handler.body, ACTIVE_CALL_NAMES)

        findings: list[Finding] = []
        for stmt in handler.body:
            if isinstance(stmt, ast.Raise):
                break
            if isinstance(stmt, ast.Return):
                # Any return terminates the handler's control flow; a
                # fallback constant among them is the reportable shape.
                value = constant_value(stmt.value) if stmt.value is not None else "None"
                if is_fallback_value(value, ctx):
                    findings.append(self._fallback_finding(handler, exc_name, ctx, "return", value))
                break
            if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                # Only constant fallback values are actionable; assignments that
                # derive from the exception itself (e.g. error_msg = str(e)) are
                # part of error handling, not silent fallbacks. AugAssign is
                # excluded on purpose: its constant is an increment/accumulator
                # amount ("failed += 1"), never the assigned fallback value.
                value = constant_value(stmt.value) if stmt.value is not None else None
                if (
                    is_fallback_value(value, ctx)
                    and not exits_process
                    and not body_has_call([stmt], ACTIVE_CALL_NAMES)
                ):
                    findings.append(self._fallback_finding(handler, exc_name, ctx, "assign", value))
        return findings

    def _fallback_finding(
        self,
        handler: ast.ExceptHandler,
        exc_name: str | None,
        ctx: ScanContext,
        kind: str,
        value: str | None,
    ) -> Finding:
        if kind == "return":
            message = (
                f"exception handler returns constant {value!r} without re-raising; "
                "the caller cannot distinguish failure from a legitimate value of "
                "the same shape"
            )
        else:
            message = (
                f"exception handler assigns fallback constant {value!r} without "
                "re-raising or recording the error"
            )
        return make_finding(
            self.spec.rule_id,
            ctx.file,
            handler,
            self.spec.mode,
            exc_name,
            message=message,
        )

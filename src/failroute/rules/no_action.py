"""``no-action`` rule: the handler body does nothing, so the failure vanishes."""

from __future__ import annotations

import ast

from failroute.ir import FailureMode, Finding, Rule, RuleSpec, ScanContext
from failroute.rules._shared import make_finding

SPEC = RuleSpec(
    rule_id="no-action",
    name="NoAction",
    mode=FailureMode.NO_ACTION,
    severity="warning",
    short_description="Exception is silently discarded (pass/...)",
    full_description=(
        "The exception handler does nothing: the failure is dropped and callers "
        "can never learn the operation failed. Log the error, re-raise, or "
        "return an explicit failure signal."
    ),
)


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


class NoActionRule(Rule):
    spec = SPEC

    def check_handler(
        self, handler: ast.ExceptHandler, exc_name: str | None, ctx: ScanContext
    ) -> list[Finding]:
        if not _body_is_effectively_empty(handler):
            return []
        return [
            make_finding(
                self.spec.rule_id,
                ctx.file,
                handler,
                self.spec.mode,
                exc_name,
                message="exception handler does nothing; the failure is silently discarded",
            )
        ]

"""``no-action`` rule: the handler body does nothing, so the failure vanishes.

This is the *silence* channel, not the value channel: nothing is substituted
for a result, so layer 1 (the declared return range) can only soften it, never
excuse it. An explicitly declared ``-> None`` does downgrade the finding to
INFO — the function never promised a value, and the annotated corpus labels
best-effort cleanup in such functions as contract — but an *unannotated*
function's contract is unknown and stays reportable.
"""

from __future__ import annotations

import ast

from failroute.ir import FailureMode, Finding, Isomorphism, Rule, RuleSpec, ScanContext, Severity
from failroute.rules._shared import facts_for, make_finding, severity_for

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
        # Optional-dependency probe contract (``try: import x / except
        # ImportError: pass``) -- adjudicated centrally, see ADR-0001.
        if id(handler) in ctx.probe_handlers:
            return []
        facts = facts_for(handler, ctx)
        if facts is None:  # pragma: no cover - only when unit-tested in isolation
            return []
        # A catch-all that discards everything is the worst shape this rule
        # sees: no exception type was anticipated and nothing was recorded.
        base = (
            Severity.HIGH
            if facts.isomorphism is Isomorphism.NON_ISOMORPHIC
            else Severity.MEDIUM
        )
        severity, verdict = severity_for(facts, mode_default=base, channel="silence")
        if severity is None:
            return []
        return [
            make_finding(
                self.spec.rule_id,
                ctx.file,
                handler,
                self.spec.mode,
                exc_name,
                message="exception handler does nothing; the failure is silently discarded",
                severity=severity,
                isomorphism=facts.isomorphism,
                covered_by=facts.covered_by,
                verdict=verdict,
            )
        ]

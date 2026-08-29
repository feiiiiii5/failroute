"""``masked-exception`` rule: a catch-all handler whose outcome depends on the branch."""

from __future__ import annotations

import ast

from failroute.ir import FailureMode, Finding, Rule, RuleSpec, ScanContext
from failroute.rules._shared import (
    body_has_raise,
    constant_value,
    dotted_name,
    is_catch_all,
    is_fallback_value,
    make_finding,
    walk_scope,
)

SPEC = RuleSpec(
    rule_id="masked-exception",
    name="MaskedException",
    mode=FailureMode.MASKED_EXCEPTION,
    severity="warning",
    short_description="Branch-dependent failure outcome",
    full_description=(
        "The handler conditionally re-raises but also falls back to a constant return; "
        "whether the caller sees failure or success depends on the branch. Make the "
        "failure path unconditional or propagate explicitly."
    ),
)


#: Control-flow statements whose body can raise conditionally. ``Match`` is
#: 3.10+; on 3.9 the tuple simply omits it (match/case cannot appear there).
_CONTROL_FLOW_WITH_RAISE: tuple[type[ast.stmt], ...] = (ast.If, ast.While, ast.For)
if hasattr(ast, "Match"):  # pragma: no branch - version-gated
    _CONTROL_FLOW_WITH_RAISE = (*_CONTROL_FLOW_WITH_RAISE, ast.Match)


def _has_conditional_raise(handler: ast.ExceptHandler) -> bool:
    """True when the handler itself raises inside a branch (if/while/for/match).

    Nested function bodies are excluded: a ``raise`` inside a callback
    defined in the handler belongs to the callback, not to the handler's
    own control flow.
    """
    for stmt in handler.body:
        if isinstance(stmt, _CONTROL_FLOW_WITH_RAISE) and body_has_raise([stmt]):
            return True
    return False


def _has_fallback_return(handler: ast.ExceptHandler, ctx: ScanContext) -> bool:
    """True when the handler itself returns a fallback constant anywhere."""
    for node in walk_scope(handler.body):
        if isinstance(node, ast.Return):
            value = node.value if node.value is not None else None
            rendered = constant_value(value) if value is not None else "None"
            if rendered is None and value is not None:
                rendered = dotted_name(value)
            if is_fallback_value(rendered, ctx) or (
                rendered is not None and rendered in ctx.extra_fallback_names
            ):
                return True
    return False


class MaskedExceptionRule(Rule):
    spec = SPEC

    def check_handler(
        self, handler: ast.ExceptHandler, exc_name: str | None, ctx: ScanContext
    ) -> list[Finding]:
        # The masking contract is about *catch-all* handlers — a typed handler
        # that conditionally re-raises is usually deliberate retry logic.
        if not is_catch_all(handler.type):
            return []
        if not (_has_conditional_raise(handler) and _has_fallback_return(handler, ctx)):
            return []
        return [
            make_finding(
                self.spec.rule_id,
                ctx.file,
                handler,
                self.spec.mode,
                exc_name,
                message="catch-all conditionally re-raises but also falls back to a "
                "constant return; the failure outcome depends on the branch",
            )
        ]

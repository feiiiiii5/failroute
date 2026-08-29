"""``name-shadowing`` rule: the caught exception variable is rebound in its handler.

Python deletes the ``except E as e`` binding when the handler exits, and any
rebinding inside the body loses the original exception object mid-handler, so
later uses of the name raise ``NameError``.
"""

from __future__ import annotations

import ast

from failroute.ir import FailureMode, Finding, Rule, RuleSpec, ScanContext
from failroute.rules._shared import make_finding, walk_scope

SPEC = RuleSpec(
    rule_id="name-shadowing",
    name="NameShadowing",
    mode=FailureMode.NAME_SHADOWING,
    severity="warning",
    short_description="Caught exception variable is rebound in the handler",
    full_description=(
        "Python deletes the `except E as e` binding when the handler exits, and "
        "rebinding `e` inside the body already loses the original exception object. "
        "Later uses of that name raise NameError. Use a different name for the new "
        "value."
    ),
)


class NameShadowingRule(Rule):
    spec = SPEC

    def check_handler(
        self, handler: ast.ExceptHandler, exc_name: str | None, ctx: ScanContext
    ) -> list[Finding]:
        if not exc_name:
            return []
        for node in walk_scope(handler.body):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.For, ast.NamedExpr)):
                targets = [node.target]
            elif isinstance(node, ast.With):
                targets = [item.optional_vars for item in node.items if item.optional_vars]
            elif isinstance(node, ast.AsyncFor):
                targets = [node.target]
            if any(isinstance(t, ast.Name) and t.id == exc_name for t in targets):
                return [
                    make_finding(
                        self.spec.rule_id,
                        ctx.file,
                        handler,
                        self.spec.mode,
                        exc_name,
                        message=f"exception variable {exc_name!r} is rebound inside the "
                        "handler; Python deletes the binding when the handler exits, so any "
                        "later use of that name raises NameError",
                    )
                ]
        return []

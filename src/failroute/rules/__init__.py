"""Built-in detection rules and the registry that orders them.

Rules are plain objects with declarative metadata (:class:`failroute.ir.RuleSpec`)
and one or both check hooks. Adding a rule is: write the module, append one
line to :data:`HANDLER_RULES`/:data:`FILE_RULES` — the analyzer dispatcher,
SARIF output, and the ``[tool.failroute.rules.<id>]`` config tables all pick
it up from here.

**Registry order is emission order** for findings on the same line: the
handler rules run in list order per handler (no-action, name-shadowing,
masked-exception, silent-fallback), matching the v0.5 visitor's sequence.
"""

from __future__ import annotations

from failroute.ir import Rule
from failroute.rules.implicit_fallback import ImplicitFallbackRule
from failroute.rules.masked_exception import MaskedExceptionRule
from failroute.rules.name_shadowing import NameShadowingRule
from failroute.rules.no_action import NoActionRule
from failroute.rules.silent_fallback import SilentFallbackRule
from failroute.rules.silent_suppress import SilentSuppressRule

#: Per-handler rules, in emission order (one handler at a time).
HANDLER_RULES: list[Rule] = [
    NoActionRule(),
    NameShadowingRule(),
    MaskedExceptionRule(),
    SilentFallbackRule(),
]

#: Whole-file rules, run once per scanned module after the handler rules.
FILE_RULES: list[Rule] = [
    SilentSuppressRule(),
    ImplicitFallbackRule(),
]


def all_rules() -> list[Rule]:
    """Every registered rule in stable order (handler rules, then file rules)."""
    return [*HANDLER_RULES, *FILE_RULES]


def rule_by_id(rule_id: str) -> Rule | None:
    for rule in all_rules():
        if rule.spec.rule_id == rule_id:
            return rule
    return None

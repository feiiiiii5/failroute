"""``silent-fallback`` rule: the handler converts the failure into a constant.

The v0.5 predicate for this rule was "a handler's **top-level** statement
returns or assigns a generic constant". Two things were wrong with it, and both
were measured rather than argued:

* **It only looked at direct statements.** ``for stmt in handler.body`` cannot
  see ``if strict: return 0.0 else: return 1.0``, so a handler that routes the
  failure on *every* path reported nothing at all. The same blind spot hid
  handlers across the pinned corpus (probe C5 in 委外任务清单.md §V1.0-A). This
  rule now reads the path-sensitive exit enumeration in
  :func:`failroute.rules._shared.enumerate_exits` and the matching
  :func:`~failroute.rules._shared.handler_bindings`.
* **It treated a constant as the whole story.** Whether a substituted constant
  is failure-routing depends on the function's declared range and on whether the
  caught exception *is* the answer the function exists to give. Both questions
  are answered once by the dispatcher and read here from
  :class:`~failroute.ir.HandlerFacts`; this rule does not re-derive them.

So the reported shape is: some path through the handler hands the caller a
fallback constant (or leaves one in state the caller reads later), the failure
does not travel with it, and the function's contract does not already admit that
value.
"""

from __future__ import annotations

import ast

from failroute.ir import (
    FailureMode,
    Finding,
    HandlerFacts,
    Isomorphism,
    Rule,
    RuleSpec,
    ScanContext,
    Severity,
)
from failroute.rules._shared import (
    ACTIVE_CALL_NAMES,
    body_has_call,
    facts_for,
    fallback_token,
    handler_bindings,
    make_finding,
    severity_for,
)
from failroute.rules.masked_exception import _has_conditional_raise, _has_fallback_return

SPEC = RuleSpec(
    rule_id="silent-fallback",
    name="SilentFallback",
    mode=FailureMode.SILENT_FALLBACK,
    severity="error",
    short_description="Failure is converted to a constant fallback value",
    full_description=(
        "Some path through the handler hands the caller a constant fallback "
        "(None/0/0.0/False/[]/{}...), or leaves one in state the caller reads "
        "later, without the failure travelling with it. Whether that is a defect "
        "depends on the declared return range and on whether the caught exception "
        "is itself the answer the function exists to give; each finding carries "
        "the verdict and the reason. Route the failure to the correct outcome "
        "instead (propagate, or return an explicit error object)."
    ),
)


def _is_masked(handler: ast.ExceptHandler, ctx: ScanContext) -> bool:
    """True when the catch-all masking gate applies (masked-exception reports it)."""
    from failroute.rules._shared import is_catch_all

    if not is_catch_all(handler.type):
        return False
    return _has_conditional_raise(handler) and _has_fallback_return(handler, ctx)


def _base_severity(facts_isomorphism: Isomorphism) -> Severity:
    """NON_ISOMORPHIC is the defect class; UNKNOWN is a weaker structural read.

    🔴 This asymmetry is what makes the differential against ``flake8
    --select E722`` measurable. If every typed handler started at HIGH, the
    tool would report ~500 HIGH findings on the pinned corpus and the
    "novelty" count would be meaningless. Only handlers the structure actively
    convicts start at HIGH.
    """
    return Severity.HIGH if facts_isomorphism is Isomorphism.NON_ISOMORPHIC else Severity.MEDIUM


class SilentFallbackRule(Rule):
    spec = SPEC

    def check_handler(
        self, handler: ast.ExceptHandler, exc_name: str | None, ctx: ScanContext
    ) -> list[Finding]:
        facts = facts_for(handler, ctx)
        if facts is None:  # pragma: no cover - only when a rule is unit-tested in isolation
            return []
        # A masked catch-all reports once under masked-exception instead.
        if _is_masked(handler, ctx):
            return []
        # Optional-dependency probe contract (``try: import x / except
        # ImportError: return False`` and capability-flag bindings) --
        # adjudicated centrally, see ADR-0001.
        if id(handler) in ctx.probe_handlers:
            return []
        # Every path propagates or terminates the process: nothing is routed.
        if facts.exits and all(e.kind in ("raise", "exit") for e in facts.exits):
            return []

        base = _base_severity(facts.isomorphism)
        findings: list[Finding] = []
        findings.extend(self._return_findings(handler, exc_name, ctx, facts, base))
        findings.extend(self._assign_findings(handler, exc_name, ctx, facts, base))
        return findings

    # ------------------------------------------------------------------ return

    def _return_findings(
        self,
        handler: ast.ExceptHandler,
        exc_name: str | None,
        ctx: ScanContext,
        facts: HandlerFacts,
        base: Severity,
    ) -> list[Finding]:
        """One finding per handler for the return channel, naming every path.

        A handler shaped ``if strict: return 0.0 else: return 1.0`` routes the
        failure on both paths; that is one defect, not two, so the paths are
        folded into a single message instead of inflating the finding count.
        """
        hits: list[tuple[str, str]] = []
        for exit_ in facts.exits:
            if exit_.kind != "return":
                continue
            token = "None" if exit_.value is None else fallback_token(exit_.value, ctx)
            if token is None:
                continue
            hits.append((token, exit_.branch or "top-level"))
        if not hits:
            return []

        tokens = sorted({token for token, _ in hits})
        branches = sorted({branch for _, branch in hits})
        routed_none = tokens == ["None"]
        severity, verdict = severity_for(
            facts, mode_default=base, channel="return", routed_none=routed_none
        )
        if severity is None:
            return []
        path_note = "" if branches == ["top-level"] else f" (on path: {', '.join(branches)})"
        message = (
            f"exception handler returns fallback constant{'s' if len(tokens) > 1 else ''} "
            f"{', '.join(repr(t) for t in tokens)} without re-raising{path_note}; "
            "the caller cannot distinguish failure from a legitimate value of the same shape"
        )
        return [
            make_finding(
                self.spec.rule_id,
                ctx.file,
                handler,
                self.spec.mode,
                exc_name,
                message=message,
                severity=severity,
                isomorphism=facts.isomorphism,
                covered_by=facts.covered_by,
                verdict=verdict,
            )
        ]

    # ------------------------------------------------------------------ assign

    def _assign_findings(
        self,
        handler: ast.ExceptHandler,
        exc_name: str | None,
        ctx: ScanContext,
        facts: HandlerFacts,
        base: Severity,
    ) -> list[Finding]:
        """One finding per distinct (target, token) binding of a fallback constant.

        Assignments are collected path-sensitively, so ``if flag: result = None``
        inside the handler is visible. ``AugAssign`` is excluded on purpose: its
        constant is an increment amount (``failed += 1``), never the substituted
        value.

        🔴 Layer 1 deliberately does **not** excuse this channel. A handler in a
        ``-> None`` constructor that writes ``self.system_prompt = ""`` is not
        routing anything through the return channel — it is writing object state
        the caller reads long after the constructor returned, with nothing to
        mark it as the failure path. All four confirmed ``__init__`` defects in
        the annotated corpus are exactly this shape.
        """
        exits_process = body_has_call(handler.body, ACTIVE_CALL_NAMES)
        if exits_process:
            return []
        # 🔴 When every path that does not re-raise returns a *constructed*
        # value, the caller reads that object and never sees the bookkeeping the
        # handler did on the way out. Found by reading the corpus:
        # ``inspect_ai/scorer/_math.py:1211`` sets ``worker.started = False`` and
        # then returns ``Score.unscored(explanation="...exceeded the parsing time
        # limit.", metadata=_status_metadata("target_timeout"))`` -- the failure
        # is stated in the result, so flagging the flag is noise.
        non_raise = [e for e in facts.exits if e.kind not in ("raise", "exit")]
        if non_raise and all(
            e.kind == "return" and e.value is not None and fallback_token(e.value, ctx) is None
            for e in non_raise
        ):
            return []
        # 🔴 An assignment only routes the failure if it lands somewhere the
        # caller consumes. Derived from the same reading pass: the false
        # positives were all state flags no caller reads as a result
        # (``self._did_stream``, ``self._has_interpretation_error``,
        # ``self._result_yielded``), while every confirmed defect writes either a
        # name the function returns (``self.success``) or an attribute the
        # guarded block itself was computing (``self.system_prompt``).
        #
        # Object state in a function with no value channel is the exception that
        # keeps the four confirmed ``__init__`` defects reportable: there is no
        # return to inspect, and the attribute is exactly what later callers read.
        state_only_channel = facts.value_range.procedure and not facts.is_generator
        seen: set[tuple[str, str]] = set()
        findings: list[Finding] = []
        for binding in handler_bindings(handler):
            if isinstance(binding.stmt, ast.AugAssign):
                continue
            if binding.value is None:
                continue
            if body_has_call([binding.stmt], ACTIVE_CALL_NAMES):
                continue
            if not (
                binding.target in facts.answer_targets
                or (state_only_channel and binding.to_attribute)
            ):
                continue
            token = fallback_token(binding.value, ctx)
            if token is None:
                continue
            key = (binding.target, token)
            if key in seen:
                continue
            seen.add(key)
            severity, verdict = severity_for(
                facts,
                mode_default=base,
                channel="assign",
                routed_none=(token == "None"),
                target=binding.target,
            )
            if severity is None:
                continue
            where = f" (on path: {binding.branch})" if binding.branch else ""
            findings.append(
                make_finding(
                    self.spec.rule_id,
                    ctx.file,
                    handler,
                    self.spec.mode,
                    exc_name,
                    message=(
                        f"exception handler assigns fallback constant {token!r} to "
                        f"{binding.target}{where} without re-raising or recording the error"
                        + (
                            "; the value outlives the call as object state"
                            if binding.to_attribute
                            else ""
                        )
                    ),
                    severity=severity,
                    isomorphism=facts.isomorphism,
                    covered_by=facts.covered_by,
                    verdict=verdict,
                )
            )
        return findings

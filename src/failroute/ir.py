"""Unified finding IR, rule metadata, and the rule contract.

This module is the **single source of truth** for what a finding is and what
every rule claims about itself:

* :class:`Finding` — one anti-pattern occurrence (the IR every output format
  renders from).
* :class:`RuleSpec` — the declarative metadata a rule carries (identifier,
  failure mode, default severity, descriptions). SARIF rule definitions are
  generated from these specs, so metadata can no longer drift from the rules
  that emit findings (the structural bug behind the v0.5.0 name-shadowing
  metadata gap).
* :class:`ScanContext` — the per-file facts rules may consult (source lines
  for marker detection, import bindings for alias resolution).
* :class:`Rule` — the base class detection rules implement. Two hooks:

  - ``check_handler`` for rules that inspect a single ``except`` handler
    (called once per handler, in registry order — registry order is the
    emission order for same-line findings),
  - ``check_file`` for rules that need whole-file visibility (the
    ``contextlib.suppress`` family).

The dispatcher in :mod:`failroute.analyzer` owns everything rules should
*not* re-implement: opt-out markers, the handler-level ignore list, and
finding ordering.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FailureMode(str, Enum):
    """Aggregated finding kinds, kept coarse so consumers can group by root cause."""

    NO_ACTION = "no-action"  # pass / bare, nothing recorded
    SILENT_FALLBACK = "silent-fallback"  # returns a constant, never re-raises
    IMPLICIT_FALLBACK = "implicit-fallback"  # falls through to the function's implicit None
    MASKED_EXCEPTION = "masked-exception"  # catch-all that swallows the original error
    NAME_SHADOWING = "name-shadowing"  # except as e: ... success path uses a stale value
    SILENT_SUPPRESS = "silent-suppress"  # with contextlib.suppress(...): failure routed to silence


class Severity(str, Enum):
    """Per-finding severity — the consequence axis, distinct from the rule axis.

    A rule says *what shape* the handler has; severity says *how much it
    matters*. Two findings from the same rule can differ by two levels once
    the value range, the isomorphism verdict, and the data-flow consequences
    are taken into account, which a per-rule SARIF level cannot express.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def rank(self) -> int:
        """Position in the ascending lattice INFO < LOW < MEDIUM < HIGH."""
        return _SEVERITY_RANK[self]

    def at_least(self, other: Severity) -> bool:
        return self.rank >= other.rank

    def shifted(self, steps: int) -> Severity:
        """Move ``steps`` levels along the lattice, clamped at both ends."""
        idx = min(max(self.rank + steps, 0), len(_SEVERITY_ORDER) - 1)
        return _SEVERITY_ORDER[idx]


_SEVERITY_ORDER: tuple[Severity, ...] = (Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH)
_SEVERITY_RANK: dict[Severity, int] = {s: i for i, s in enumerate(_SEVERITY_ORDER)}

#: SARIF level for each severity. ``info`` maps to ``note``: SARIF has no
#: ``info`` level, and ``none`` would hide the result from consumers that
#: render every result regardless of level.
SEVERITY_TO_SARIF_LEVEL: dict[Severity, str] = {
    Severity.HIGH: "error",
    Severity.MEDIUM: "warning",
    Severity.LOW: "note",
    Severity.INFO: "note",
}


class Isomorphism(str, Enum):
    """Verdict of the exception/predicate isomorphism test (V1 layer 2).

    The question is not "does this handler swallow an exception" but
    **"is the caught exception the answer to the question this function
    exists to answer?"**

    * ``ISOMORPHIC`` — yes. ``_is_serializable`` guards ``json.dumps(x)`` and
      catches ``(TypeError, ValueError)``: being unserializable *is* the
      negative answer, so returning ``False`` routes nothing. Not a finding.
    * ``NON_ISOMORPHIC`` — no. ``is_vulnerable`` guards a loop that aggregates
      over test cases: an exception aborts a *partial* computation which is
      then reported as a complete, clean "not vulnerable".
    * ``UNKNOWN`` — the structure does not decide it either way.

    Derived from three structural signals only, never from the function's
    name: catch-all-ness, the shape of the guarded block, and whether the
    guarded block can raise at all.
    """

    ISOMORPHIC = "isomorphic"
    NON_ISOMORPHIC = "non-isomorphic"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Finding:
    """A single anti-pattern occurrence."""

    file: str
    lineno: int
    end_lineno: int
    mode: FailureMode
    exc_name: str | None
    handler_text: str = ""
    message: str = ""
    #: Identifier of the rule that emitted this finding (equals ``mode.value``
    #: for every rule shipped with failroute; kept separate so third-party
    #: rules can share a failure mode without losing provenance).
    rule_id: str = ""
    #: Consequence level for *this* occurrence. Distinct from the rule's
    #: declared SARIF level: two silent-fallback findings can be HIGH and INFO
    #: depending on the value range and the isomorphism verdict.
    severity: Severity = Severity.MEDIUM
    #: Verdict of the exception/predicate isomorphism test (V1 layer 2).
    #: ``None`` for findings the test does not apply to (``silent-suppress``
    #: has no handler, ``name-shadowing`` is not about routing a value).
    isomorphism: Isomorphism | None = None
    #: Trivial-lint rules that already flag this handler, inferred statically
    #: from its shape. Empty means the finding is *novel*: no shipped linter
    #: rule points at this line. Sorted, so output is byte-stable.
    covered_by: tuple[str, ...] = ()
    #: One-line justification for ``severity`` / ``isomorphism``, so a reviewer
    #: can audit the verdict without re-deriving it from the AST.
    verdict: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "lineno": self.lineno,
            "end_lineno": self.end_lineno,
            "mode": self.mode.value,
            "exc_name": self.exc_name,
            "handler_text": self.handler_text,
            "message": self.message,
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "isomorphism": self.isomorphism.value if self.isomorphism is not None else None,
            "covered_by": list(self.covered_by),
            "verdict": self.verdict,
        }


@dataclass(frozen=True)
class Exit:
    """One terminal outcome of a path through a statement block.

    Produced by :func:`failroute.rules._shared.enumerate_exits`, which walks
    every branch instead of only the block's direct statements. ``branch`` is a
    human-readable path label (``"if-body"``, ``"handler-1/else"``) used in
    finding messages so a reviewer can see *which* path routes the failure.
    """

    #: ``return`` | ``raise`` | ``fallthrough`` | ``continue`` | ``break`` | ``exit``
    kind: str
    #: Payload of a ``return`` exit; ``None`` for every other kind.
    value: ast.expr | None = None
    #: The terminating statement, when there is one.
    stmt: ast.stmt | None = None
    #: Path label from the block's entry to this outcome.
    branch: str = ""

    @property
    def terminates(self) -> bool:
        """True when control cannot leave this outcome into the following code."""
        return self.kind in ("return", "raise", "exit")


@dataclass(frozen=True)
class ValueRange:
    """What the enclosing function's return channel admits (V1 layer 1).

    ``admits_none`` is the load-bearing field: when the declared range already
    contains ``None``, routing a failure to ``None`` gives the caller a value
    the contract told them to handle, which is a different phenomenon from
    substituting an in-range constant for a real result.
    """

    #: Unparsed annotation text, or ``None`` when the function is unannotated.
    declared: str | None = None
    #: ``none`` | ``optional`` | ``bool`` | ``other`` | ``absent`` (module level).
    kind: str = "absent"
    #: True when ``None`` is inside the declared (or, lacking a declaration,
    #: the observed) return range.
    admits_none: bool = False
    #: True when the annotation is explicit. Only an *explicit* ``-> None``
    #: downgrades a finding: an unannotated function's contract is unknown,
    #: and unknown stays reportable.
    declared_explicitly: bool = False
    #: True when no success path returns a value at all.
    procedure: bool = False


@dataclass(frozen=True)
class HandlerFacts:
    """Everything the rules may need to know about one ``except`` handler.

    Computed once per handler by the dispatcher
    (:func:`failroute.rules._shared.build_handler_facts`) so that no rule
    re-derives a predicate — the failure mode behind five separate Wilson
    interval implementations in earlier batches.
    """

    #: The ``try`` statement this handler belongs to.
    try_node: ast.Try
    #: Enclosing function, or ``None`` at module level.
    func: ast.FunctionDef | ast.AsyncFunctionDef | None
    #: V1 layer 1.
    value_range: ValueRange
    #: Every terminal outcome of the handler body, all paths.
    exits: tuple[Exit, ...]
    #: V1 layer 2.
    isomorphism: Isomorphism
    #: Why the isomorphism verdict came out that way.
    iso_reason: str
    #: True when the handler records the failure through a recognised channel.
    logs: bool
    #: True when the exception object itself reaches the returned value or a
    #: side channel (``return Score(0, error=str(e))`` / ``errors.append(e)``),
    #: which is the only thing that genuinely makes the outcome distinguishable.
    exception_escapes: bool
    #: True when the routed value outlives the call (``self.attr = ...``) or
    #: feeds an aggregate/result constructor.
    amplifies: bool
    #: Trivial-lint rules that already flag this shape; empty means novel.
    covered_by: tuple[str, ...]
    #: True when the body is ``pass`` / ``...`` only.
    body_empty: bool
    #: True when the guarded block cannot raise at all, making the handler dead
    #: code (``try: self.score == 1 / except: ...``).
    dead_probe: bool
    #: Names of locals in the enclosing function whose *own* annotation admits
    #: ``None`` (``completed_at: float | None = None``). Layer 1 is usually
    #: about the function's return range, but an assignment channel has its own
    #: declared range, and writing ``None`` back into a name that was declared
    #: nullable and initialised to ``None`` restores the value it already had.
    annotated_none_vars: frozenset[str] = frozenset()
    #: Dotted targets that plausibly *are* the caller's answer: assigned inside
    #: the guarded block, returned by the enclosing function, or read after the
    #: ``try``. An assignment in a handler only routes the failure if it lands
    #: somewhere the caller actually consumes. Derived from reading the pinned
    #: corpus: ``self._has_interpretation_error = True`` beside a substituted
    #: empty AST is the handler *recording* the failure, while
    #: ``self.system_prompt = ""`` replacing the guarded block's own assignment
    #: is the handler *erasing* it.
    answer_targets: frozenset[str] = frozenset()
    #: True when the enclosing function yields, so its value channel is the
    #: generator protocol rather than ``return``.
    is_generator: bool = False


@dataclass(frozen=True)
class RuleSpec:
    """Declarative metadata for one detection rule."""

    #: Stable identifier used in ``[tool.failroute.rules.<id>]`` config tables,
    #: CLI ``--ignore``, and SARIF rule definitions.
    rule_id: str
    #: SARIF rule name (PascalCase).
    name: str
    #: Coarse failure mode the rule reports under.
    mode: FailureMode
    #: Default SARIF level: ``"error"`` or ``"warning"``.
    severity: str
    short_description: str
    full_description: str


@dataclass
class ScanContext:
    """Per-file facts shared by all rules during a scan."""

    #: Path as reported in findings.
    file: str
    #: Original source split into lines, when available (marker detection).
    source_lines: list[str] | None = None
    #: Module-level name -> dotted import origin (alias resolution).
    bindings: dict[str, str] = field(default_factory=dict)
    #: Project-configured fallback sentinels (canonical tokens from
    #: ``[tool.failroute] fallback_values``) beyond the built-in shapes.
    extra_fallback_values: frozenset[str] = frozenset()
    #: Project-configured dotted-name sentinels (``[tool.failroute]
    #: fallback_names``, e.g. ``Status.UNKNOWN``) matched on attribute chains.
    extra_fallback_names: frozenset[str] = frozenset()
    #: ``id()``s of handlers adjudicated as optional-dependency probes
    #: (``except ImportError`` guarding an import-only block with a minimal
    #: fallback body). Computed once by the dispatcher; the no-action and
    #: silent-fallback rules consult it instead of re-deriving the predicate.
    probe_handlers: frozenset[int] = frozenset()
    #: ``id(handler)`` -> :class:`HandlerFacts`. Computed once per handler by
    #: the dispatcher so that every rule reads the *same* value-range,
    #: isomorphism and coverage verdict. Deriving these per rule is how an
    #: earlier batch ended up with five disagreeing implementations of one
    #: statistic; the same failure mode applies to predicates.
    handler_facts: dict[int, HandlerFacts] = field(default_factory=dict)


class Rule:
    """Base class for failroute detection rules.

    Subclasses set :attr:`spec` and override one or both hooks. The default
    implementations return no findings, so a rule only implements the hook it
    actually needs.
    """

    spec: RuleSpec

    def check_handler(
        self, handler: ast.ExceptHandler, exc_name: str | None, ctx: ScanContext
    ) -> list[Finding]:
        """Return findings for one ``except`` handler. Called once per handler."""
        return []

    def check_file(self, tree: ast.AST, ctx: ScanContext) -> list[Finding]:
        """Return findings for a whole module. Called once per scanned file."""
        return []

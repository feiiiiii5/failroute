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
        }


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

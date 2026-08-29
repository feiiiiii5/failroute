"""SARIF 2.1.0 output for failroute.

Emits findings in the Static Analysis Results Interchange Format so the
tool can plug directly into GitHub code scanning (``upload-sarif`` action)
or any SARIF-consuming CI.

Rule definitions are **generated from the rule registry**
(:mod:`failroute.rules`) — every rule's identifier, descriptions, and default
severity live on its :class:`failroute.ir.RuleSpec`, so a rule cannot ship
findings whose metadata the SARIF output does not know about (the structural
bug behind the v0.5.0 name-shadowing metadata gap). Projects can override a
rule's level via ``[tool.failroute.rules.<id>] severity = "..."``.
"""

from __future__ import annotations

import json
from typing import Any

from failroute.ir import Finding
from failroute.rules import all_rules, rule_by_id

# Single source of truth is the installed distribution metadata; the previous
# hardcoded constant drifted out of sync on release (v0.3.0 shipped labelled 0.2.0).
try:  # pragma: no cover - exercised only when metadata is unavailable
    from importlib import metadata as _metadata

    __version__ = _metadata.version("failroute")
except Exception:  # pragma: no cover - defensive fallback
    __version__ = "0.0.0"

_RULE_ID_PREFIX = "failroute"

#: Fallback level for findings whose rule_id is not in the registry
#: (third-party rules): corruption-shaped modes default to error.
_MODE_DEFAULT_LEVELS = {"silent-fallback": "error", "implicit-fallback": "error"}


def _level(finding: Finding, severity_overrides: dict[str, str]) -> str:
    rule = rule_by_id(finding.rule_id) if finding.rule_id else None
    if rule is not None:
        return severity_overrides.get(rule.spec.rule_id, rule.spec.severity)
    return _MODE_DEFAULT_LEVELS.get(finding.mode.value, "warning")


def _rules_metadata(severity_overrides: dict[str, str]) -> list[dict[str, Any]]:
    metadata = []
    for rule in all_rules():
        spec = rule.spec
        metadata.append(
            {
                "id": f"{_RULE_ID_PREFIX}/{spec.rule_id}",
                "name": spec.name,
                "shortDescription": {"text": spec.short_description},
                "fullDescription": {"text": spec.full_description},
                "defaultConfiguration": {"level": severity_overrides.get(spec.rule_id, spec.severity)},
                "helpUri": "https://github.com/feiiiiii5/failroute#readme",
            }
        )
    return metadata


def to_sarif(
    findings: list[Finding],
    *,
    repo_uri: str | None = None,
    severity_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Render findings as a SARIF 2.1.0 run document."""
    overrides = severity_overrides or {}
    results: list[dict[str, Any]] = []

    for finding in findings:
        rule_id = f"{_RULE_ID_PREFIX}/{finding.rule_id or finding.mode.value}"
        location: dict[str, Any] = {
            "physicalLocation": {
                "artifactLocation": {"uri": finding.file},
                "region": {
                    "startLine": finding.lineno,
                    "endLine": finding.end_lineno or finding.lineno,
                },
            }
        }
        if repo_uri:
            location["logicalLocations"] = [
                {"fullyQualifiedName": f"{rule_id} in {finding.file}:{finding.lineno}"}
            ]

        results.append(
            {
                "ruleId": rule_id,
                "level": _level(finding, overrides),
                "message": {"text": finding.message},
                "locations": [location],
                "properties": {
                    "exc_name": finding.exc_name or "",
                    "mode": finding.mode.value,
                    "handler_text": finding.handler_text,
                },
            }
        )

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "failroute",
                        "version": __version__,
                        "informationUri": "https://github.com/feiiiiii5/failroute",
                        "rules": _rules_metadata(overrides),
                    }
                },
                "results": results,
            }
        ],
    }


def to_sarif_json(
    findings: list[Finding],
    *,
    repo_uri: str | None = None,
    severity_overrides: dict[str, str] | None = None,
) -> str:
    """Render findings as a JSON-encoded SARIF document."""
    return json.dumps(to_sarif(findings, repo_uri=repo_uri, severity_overrides=severity_overrides), indent=2)

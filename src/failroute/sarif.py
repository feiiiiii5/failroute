"""SARIF 2.1.0 output for failroute.

Emits findings in the Static Analysis Results Interchange Format so the
tool can plug directly into GitHub code scanning (``upload-sarif`` action)
or any SARIF-consuming CI. Severity mapping:

* ``silent-fallback``  -> error      (silent data corruption)
* ``masked-exception`` -> warning    (branch-dependent outcome)
* ``no-action``        -> warning    (dropped failure, no trace)
"""

from __future__ import annotations

from typing import Any

from failroute.analyzer import FailureMode, Finding

# Single source of truth is the installed distribution metadata; the previous
# hardcoded constant drifted out of sync on release (v0.3.0 shipped labelled 0.2.0).
try:  # pragma: no cover - exercised only when metadata is unavailable
    from importlib import metadata as _metadata

    __version__ = _metadata.version("failroute")
except Exception:  # pragma: no cover - defensive fallback
    __version__ = "0.0.0"
_RULE_ID_PREFIX = "failroute"


def _level(mode: FailureMode) -> str:
    if mode is FailureMode.SILENT_FALLBACK:
        return "error"
    return "warning"


def _rule_descriptions() -> dict[str, dict[str, str]]:
    return {
        "no-action": {
            "name": "NoAction",
            "shortDescription": "Exception is silently discarded (pass/...)",
            "fullDescription": (
                "The exception handler does nothing: the failure is dropped and callers "
                "can never learn the operation failed. Log the error, re-raise, or "
                "return an explicit failure signal."
            ),
            "defaultLevel": "warning",
        },
        "silent-fallback": {
            "name": "SilentFallback",
            "shortDescription": "Failure is converted to a constant fallback value",
            "fullDescription": (
                "The handler returns or assigns a constant fallback (None/0/0.0/False/[]/{}...)"
                " without re-raising or recording the error, so the caller cannot distinguish "
                "a real failure from a legitimate value of the same shape. Route the failure "
                "to the correct outcome instead (propagate, log at error level, or return an "
                "explicit error object)."
            ),
            "defaultLevel": "error",
        },
        "masked-exception": {
            "name": "MaskedException",
            "shortDescription": "Branch-dependent failure outcome",
            "fullDescription": (
                "The handler conditionally re-raises but also falls back to a constant return; "
                "whether the caller sees failure or success depends on the branch. Make the "
                "failure path unconditional or propagate explicitly."
            ),
            "defaultLevel": "warning",
        },
    }


def to_sarif(findings: list[Finding], *, repo_uri: str | None = None) -> dict[str, Any]:
    """Render findings as a SARIF 2.1.0 run document."""
    rules = _rule_descriptions()
    results: list[dict[str, Any]] = []

    for finding in findings:
        rule_id = f"{_RULE_ID_PREFIX}/{finding.mode.value}"
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
                "level": _level(finding.mode),
                "message": {"text": finding.message},
                "locations": [location],
                "properties": {
                    "exc_name": finding.exc_name or "",
                    "mode": finding.mode.value,
                    "handler_text": finding.handler_text,
                },
            }
        )

    rules_metadata = []
    for rule_name, meta in rules.items():
        rule_id = f"{_RULE_ID_PREFIX}/{rule_name}"
        rules_metadata.append(
            {
                "id": rule_id,
                "name": meta["name"],
                "shortDescription": {"text": meta["shortDescription"]},
                "fullDescription": {"text": meta["fullDescription"]},
                "defaultConfiguration": {"level": meta["defaultLevel"]},
                "helpUri": "https://github.com/feiiiiii5/failroute#readme",
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
                        "rules": rules_metadata,
                    }
                },
                "results": results,
            }
        ],
    }


def to_sarif_json(findings: list[Finding], *, repo_uri: str | None = None) -> str:
    """Render findings as a JSON-encoded SARIF document."""
    import json

    return json.dumps(to_sarif(findings, repo_uri=repo_uri), indent=2)

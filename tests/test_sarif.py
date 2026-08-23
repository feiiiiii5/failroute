"""Tests for SARIF output."""

from __future__ import annotations

import json

from failroute.analyzer import scan_source
from failroute.sarif import to_sarif, to_sarif_json


def test_sarif_document_shape():
    findings = scan_source(
        """
try:
    a()
except Exception:
    pass

try:
    b()
except Exception:
    return 0.0
"""
    )
    doc = to_sarif(findings)
    assert doc["version"] == "2.1.0"
    assert doc["$schema"].endswith("sarif-2.1.0.json")

    run = doc["runs"][0]
    assert run["tool"]["driver"]["name"] == "failroute"
    assert len(run["results"]) == 2
    assert len(run["tool"]["driver"]["rules"]) == 3  # no-action, silent-fallback, masked


def test_sarif_severity_mapping():
    findings = scan_source(
        """
try:
    a()
except Exception:
    pass

try:
    b()
except Exception:
    return 0.0
"""
    )
    doc = to_sarif(findings)
    results = doc["runs"][0]["results"]
    by_rule = {r["ruleId"]: r["level"] for r in results}
    assert by_rule["failroute/no-action"] == "warning"
    assert by_rule["failroute/silent-fallback"] == "error"


def test_sarif_locations_carry_lines():
    findings = scan_source("\n\ntry:\n    a()\nexcept Exception:\n    pass\n")
    doc = to_sarif(findings)
    result = doc["runs"][0]["results"][0]
    region = result["locations"][0]["physicalLocation"]["region"]
    assert region["startLine"] == 5
    assert region["endLine"] == 6


def test_sarif_rule_metadata_has_descriptions():
    findings = scan_source("try:\n    a()\nexcept Exception:\n    pass\n")
    doc = to_sarif(findings)
    rules = doc["runs"][0]["tool"]["driver"]["rules"]
    ids = {r["id"] for r in rules}
    assert {"failroute/no-action", "failroute/silent-fallback", "failroute/masked-exception"} == ids
    for rule in rules:
        assert rule["shortDescription"]["text"]
        assert rule["fullDescription"]["text"]


def test_sarif_json_roundtrip():
    findings = scan_source("try:\n    a()\nexcept Exception:\n    return None\n")
    text = to_sarif_json(findings)
    assert json.loads(text)["version"] == "2.1.0"

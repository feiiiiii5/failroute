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
    # no-action, silent-fallback, implicit-fallback, masked, name-shadowing, silent-suppress
    assert len(run["tool"]["driver"]["rules"]) == 6


def test_sarif_severity_mapping():
    # V1 (2026-09-04): the SARIF level follows the *finding's* severity, not the
    # rule's declared default. Both handlers below are catch-alls at module level
    # with nothing recorded, so both are HIGH -> "error"; `no-action` no longer
    # inherits a blanket "warning" that hid the worst shape this tool detects.
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
    assert by_rule["failroute/no-action"] == "error"
    assert by_rule["failroute/silent-fallback"] == "error"
    assert {f.severity.value for f in findings} == {"high"}


def test_sarif_level_tracks_the_severity_lattice():
    # One rule, three levels: the whole point of a per-finding severity.
    #   catch-all, nothing recorded            -> HIGH   -> error
    #   catch-all, warning logged              -> MEDIUM -> warning
    #   declared Optional, routed None         -> suppressed
    #   name-shadowing (loud failure, out of
    #     the failure-routing family)          -> INFO   -> note
    findings = scan_source(
        """
def high(x):
    try:
        return judge(x)
    except Exception:
        return 0.0

def medium(x):
    try:
        return judge(x)
    except Exception:
        logger.warning("judge failed")
        return 0.0

def suppressed(x) -> Optional[float]:
    try:
        return judge(x)
    except Exception:
        return None

def info(x):
    try:
        do()
    except ValueError as e:
        e = wrap(e)
"""
    )
    levels = {(f.mode.value, f.severity.value) for f in findings}
    assert ("silent-fallback", "high") in levels
    assert ("silent-fallback", "medium") in levels
    assert ("name-shadowing", "info") in levels
    doc = to_sarif(findings)
    by_level = {r["properties"]["mode"]: r["level"] for r in doc["runs"][0]["results"]}
    assert by_level["name-shadowing"] == "note"


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
    assert {
        "failroute/no-action",
        "failroute/silent-fallback",
        "failroute/implicit-fallback",
        "failroute/masked-exception",
        "failroute/name-shadowing",
        "failroute/silent-suppress",
    } == ids
    for rule in rules:
        assert rule["shortDescription"]["text"]
        assert rule["fullDescription"]["text"]


def test_sarif_json_roundtrip():
    findings = scan_source("try:\n    a()\nexcept Exception:\n    return None\n")
    text = to_sarif_json(findings)
    assert json.loads(text)["version"] == "2.1.0"

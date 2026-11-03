"""Regression checks for the research harness, without network or corpus scans."""
from __future__ import annotations

import ast
import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def harness(monkeypatch, stdout, returncode=0):
    # coverage_union is a historical CLI with top-level execution. Load only the
    # functions being tested, never its corpus-dependent command-line driver.
    source = ast.parse((ROOT / "tools/coverage_union.py").read_text(encoding="utf-8"))
    selected = [n for n in source.body if isinstance(n, ast.FunctionDef)
                and n.name in {"sh", "bandit", "flake8", "semgrep"}]
    namespace = {"subprocess": subprocess, "os": os, "sys": sys, "json": json,
                 "PY": sys.executable, "SG": "semgrep", "RULES": "rules.yaml"}
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: SimpleNamespace(
        returncode=returncode, stdout=stdout, stderr="analysis failed"))
    exec(compile(ast.Module(body=selected, type_ignores=[]), "coverage_union.py", "exec"), namespace)
    return namespace


def test_nonempty_error_output_is_not_a_success(monkeypatch):
    with pytest.raises(SystemExit):
        harness(monkeypatch, "[]", 2)["sh"](["ruff"])


def test_semgrep_partial_scan_is_not_empty_coverage(monkeypatch):
    with pytest.raises(SystemExit):
        harness(monkeypatch, '{"results": [], "errors": [{"message": "parse failed"}]}')["semgrep"](".")


def test_bandit_partial_scan_is_not_empty_coverage(monkeypatch):
    with pytest.raises(SystemExit):
        harness(monkeypatch, '{"results": [], "errors": ["missing file"]}')["bandit"](".")


def test_flake8_malformed_output_fails(monkeypatch):
    with pytest.raises(SystemExit):
        harness(monkeypatch, "unparseable error text")["flake8"](".")


def test_valid_empty_semgrep_result_is_accepted(monkeypatch):
    assert harness(monkeypatch, '{"results": [], "errors": []}')["semgrep"](".") == []


def test_warning_frame_counts_from_individual_rows():
    for filename, total, covered, sites in (("621", 621, 255, 617), ("v2", 476, 252, 472)):
        path = ROOT / f"bench/corpus-coverage-per-finding-{filename}.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        assert len(rows) == total
        assert sum(not r["failroute_only"] for r in rows) == covered
        assert len({(r["repo"], r["file"], r["lineno"]) for r in rows}) == sites
        assert all(r["failroute_only"] == (not r["baseline_tools_colocated"]) for r in rows)


def test_rationale_correction_targets_retained_label():
    audit = json.loads((ROOT / "paper/annotation-corrections.json").read_text())
    for correction in audit["corrections"]:
        with (ROOT / correction["source"]).open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        matched = [r for r in rows if all(r[k] == v for k, v in correction["key"].items())]
        assert len(matched) == 1
        assert matched[0]["label"] == correction["original_label"]
        assert correction["status"] == "rationale_corrected_label_unadjudicated"
        assert correction["evidence"]


def test_original_annotation_bytes_preserved():
    expected = json.loads((ROOT / "paper/annotation-corrections.json").read_text())["frozen_sha256"]
    for name, digest in expected.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest


def test_reference_audit_preserves_historical_rows():
    audit = json.loads((ROOT / "paper/reference-audit.json").read_text())
    ledger = ROOT / audit["historical_source"]
    assert hashlib.sha256(ledger.read_bytes()).hexdigest() == audit["historical_sha256"]
    with ledger.open(encoding="utf-8", newline="") as stream:
        expected = {(r["repo"], int(r["pr_number"])) for r in csv.DictReader(stream)
                    if r["belongs_to_family"] == "yes"}
    actual = {(r["repo"], r["pr"]) for r in audit["records"]}
    assert actual == expected
    assert len(audit["records"]) == len(actual) == 16
    assert all(r["status"] in audit["status_definitions"] and r["evidence"]
               for r in audit["records"])
    by_pr = {(r["repo"], r["pr"]): r for r in audit["records"]}
    assert by_pr["cvs-health/uqlm", 425]["status"] == "excluded"
    assert by_pr["truera/trulens", 2653]["status"] == "location-only"
    assert len(audit["withdrawn_claims"]) == 3


def test_reproduction_wrapper_refuses_existing_output(tmp_path):
    import runpy

    namespace = runpy.run_path(str(ROOT / "tools/reproduce_warning_coverage.py"))
    with pytest.raises(ValueError, match="already exists"):
        namespace["run"](tmp_path)


def test_reproduction_wrapper_uses_frozen_frames_and_new_paths(tmp_path, monkeypatch):
    import runpy

    namespace = runpy.run_path(str(ROOT / "tools/reproduce_warning_coverage.py"))
    function = namespace["run"]
    function.__globals__["ROOT"] = tmp_path
    (tmp_path / "paper/corpus").mkdir(parents=True)
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw)))
    output = tmp_path / "results"
    function(output)
    assert len(calls) == 2
    for (cmd, kwargs), frame, name in zip(calls, ("bench/rescan-f2", "bench/rescan-v2"),
                                        ("baseline", "refined")):
        assert cmd[cmd.index("--findings-dir") + 1] == frame
        assert cmd[cmd.index("--out") + 1] == str(output / f"{name}-coverage.json")
        assert kwargs["check"]


def test_finding_export_preserves_context_and_verdict(tmp_path):
    from failroute import main

    source = tmp_path / "scorer.py"
    source.write_text(
        "def score():\n    try:\n        return judge()\n    except Exception:\n        return 0.0\n"
    )
    output = tmp_path / "findings.jsonl"
    assert main([str(source), "--export-findings", str(output), "--repo-name", "fixture"]) == 1
    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(records) == 1
    record = records[0]
    assert record["repo"] == "fixture"
    assert record["function_signature"] == "def score()"
    assert record["rule"] == "silent-fallback"
    assert record["severity"]
    assert record["verdict"]
    assert "        return 0.0" in record["context_after"]

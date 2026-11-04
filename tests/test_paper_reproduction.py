"""Regression checks for the research harness, without network or corpus scans."""
from __future__ import annotations

import ast
import csv
import hashlib
import json
import os
import shutil
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


def test_frozen_evidence_survives_autocrlf_checkout(tmp_path):
    """Exercise Git's Windows-style checkout, without normalizing evidence hashes."""
    git = shutil.which("git")
    if git is None:
        pytest.skip("Git is required to exercise checkout conversion")
    annotations = json.loads((ROOT / "paper/annotation-corrections.json").read_text())
    audit = json.loads((ROOT / "paper/reference-audit.json").read_text())
    expected = dict(annotations["frozen_sha256"])
    expected[audit["historical_source"]] = audit["historical_sha256"]
    # Every input check_frozen_truth.py hashes must also keep its bytes.
    manifest = json.loads((ROOT / "paper/frozen-truth-sha256.json").read_text(encoding="utf-8"))
    expected.update({rel: entry["sha256"] for rel, entry in manifest["files"].items()})
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".gitattributes").write_bytes((ROOT / ".gitattributes").read_bytes())
    for name in expected:
        target = repository / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    # A control proves that checkout conversion really was active in this test.
    (repository / "control.txt").write_bytes(b"first\nsecond\n")

    def run(*args):
        return subprocess.run([git, *args], cwd=repository, check=True,
                              capture_output=True, text=True)

    run("init")
    run("-c", "core.autocrlf=false", "add", ".")
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    run("-c", "core.autocrlf=true", "-c", "core.eol=crlf", "checkout-index",
        "--all", "--force", "--prefix=" + checkout.as_posix() + "/")
    assert (checkout / "control.txt").read_bytes() == b"first\r\nsecond\r\n"
    for name, digest in expected.items():
        assert hashlib.sha256((checkout / name).read_bytes()).hexdigest() == digest


def _guard():
    import importlib.util

    spec = importlib.util.spec_from_file_location("_frozen_guard", ROOT / "tools/_frozen_guard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(shutil.which("git") is None or not (ROOT / ".git").exists(),
                    reason="needs a git checkout to know which files are tracked")
def test_frozen_guard_refuses_tracked_outputs_and_allows_scratch(tmp_path):
    guard = _guard()
    for tracked in ("bench/rq5-refactor-delta.json", "bench/corpus-coverage-union.json",
                    "bench/rescan-v2/deepteam.jsonl", "paper/corpus-lock.json"):
        assert guard.is_frozen(tracked), tracked
        with pytest.raises(SystemExit):
            guard.guard_output(tracked)
        guard.guard_output(tracked, allow=True)  # explicit regeneration stays possible
    guard.guard_output(tmp_path / "fresh.json")
    assert not guard.is_frozen(tmp_path / "fresh.json")


@pytest.mark.skipif(shutil.which("git") is None or not (ROOT / ".git").exists(),
                    reason="needs a git checkout to know which files are tracked")
def test_delta_script_refuses_default_frozen_output():
    before = (ROOT / "bench/rq5-refactor-delta.json").read_bytes()
    proc = subprocess.run([sys.executable, str(ROOT / "tools/rq5_refactor_delta.py")],
                          cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode != 0
    assert "refusing to overwrite" in proc.stderr
    assert (ROOT / "bench/rq5-refactor-delta.json").read_bytes() == before


def _frozen_truth():
    import importlib.util

    spec = importlib.util.spec_from_file_location("check_frozen_truth",
                                                  ROOT / "tools/check_frozen_truth.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_truth_detects_changed_protected_bytes(tmp_path):
    checker = _frozen_truth()
    manifest = json.loads((ROOT / checker.MANIFEST).read_text(encoding="utf-8"))
    (tmp_path / "paper").mkdir()
    shutil.copyfile(ROOT / checker.MANIFEST, tmp_path / checker.MANIFEST)
    for rel in manifest["files"]:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)
    assert checker.changed_protected(tmp_path) == []
    victim = tmp_path / "paper/annotations.csv"
    data = victim.read_bytes()
    victim.write_bytes(data.replace(b"DEFECT", b"CONTRACT", 1))  # one real label change
    assert checker.changed_protected(tmp_path) == ["paper/annotations.csv"]
    victim.write_bytes(data)
    (tmp_path / "paper/sample.jsonl").unlink()  # a missing file is a change, not a pass
    assert checker.changed_protected(tmp_path) == ["paper/sample.jsonl"]


def test_frozen_truth_intervals_ignore_only_the_timestamp(tmp_path):
    checker = _frozen_truth()
    committed = json.loads((ROOT / "paper/intervals.json").read_text(encoding="utf-8"))
    restamped = dict(committed, generated_at_utc8="2099-01-01 00:00:00")
    (tmp_path / "a.json").write_text(json.dumps(restamped))
    assert checker.same_intervals(ROOT / "paper/intervals.json", tmp_path / "a.json")
    tampered = json.loads(json.dumps(committed))
    tampered["cells"][0]["numerator"] += 1
    (tmp_path / "b.json").write_text(json.dumps(tampered))
    assert not checker.same_intervals(ROOT / "paper/intervals.json", tmp_path / "b.json")


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="needs poppler's pdftotext")
def test_frozen_truth_figure_rebuilt_from_changed_counts_differs(tmp_path):
    pytest.importorskip("matplotlib")
    checker = _frozen_truth()
    for rel in ("tools/make_figures.py", "paper/intervals.json",
                "bench/corpus-coverage-union-5tool.json", "paper/reference-audit.json"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, tmp_path / rel)
    doc = json.loads((tmp_path / "paper/intervals.json").read_text(encoding="utf-8"))
    cell = next(c for c in doc["cells"]
                if c["group"] == "overall[pass1]" and c["label"] == "defect rate")
    cell["numerator"] -= 1  # 12/80 -> 11/80: a real change to a plotted count
    (tmp_path / "paper/intervals.json").write_text(json.dumps(doc), encoding="utf-8")
    subprocess.run([sys.executable, str(tmp_path / "tools/make_figures.py"),
                    "--out-dir", str(tmp_path / "out")], check=True, capture_output=True)
    name = "fig1_llm_label_share_by_package.pdf"
    assert checker.pdf_tokens(tmp_path / "out" / name) != checker.pdf_tokens(
        ROOT / "paper/figures" / name)
    # The unchanged figure still matches, so the difference above is the count.
    other = "fig2_cross_tool_coverage.pdf"
    assert checker.pdf_tokens(tmp_path / "out" / other) == checker.pdf_tokens(
        ROOT / "paper/figures" / other)


FIG1 = "fig1_llm_label_share_by_package.pdf"
FIG2 = "fig2_cross_tool_coverage.pdf"


def _rebuild_figures(tmp_path, patch=None):
    """Rebuild the paper figures into tmp_path, optionally editing the plotting code."""
    source = (ROOT / "tools/make_figures.py").read_text(encoding="utf-8")
    if patch is not None:
        old, new = patch
        assert source.count(old) == 1, old
        source = source.replace(old, new)
    (tmp_path / "tools").mkdir(parents=True)
    (tmp_path / "tools/make_figures.py").write_text(source, encoding="utf-8")
    for rel in ("paper/intervals.json", "bench/corpus-coverage-union-5tool.json",
                "paper/reference-audit.json"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, tmp_path / rel)
    subprocess.run([sys.executable, str(tmp_path / "tools/make_figures.py"),
                    "--out-dir", str(tmp_path / "out")], check=True, capture_output=True)
    return tmp_path / "out"


_needs_render = pytest.mark.skipif(shutil.which("pdftotext") is None,
                                   reason="needs poppler's pdftotext")


@_needs_render
@pytest.mark.parametrize("label,patch,figure", [
    ("points mirrored, labels unchanged",
     ("ax.scatter(pts, y,", "ax.scatter([100.0 - p for p in pts], y,"), FIG1),
    ("one point moved by one unit, labels unchanged",
     ("ax.scatter(pts, y,",
      "ax.scatter([p + (1.0 if k == 0 else 0.0) for k, p in enumerate(pts)], y,"), FIG1),
    ("heatmap cell shading reversed per row, cell labels unchanged",
     ("image = ax.imshow(shares,", "image = ax.imshow([row[::-1] for row in shares],"), FIG2),
])
def test_geometry_check_sees_moves_the_text_check_cannot(tmp_path, label, patch, figure):
    pytest.importorskip("matplotlib")
    checker = _frozen_truth()
    before = {p.name: p.read_bytes() for p in (ROOT / "paper/figures").glob("*.pdf")}
    out = _rebuild_figures(tmp_path, patch)
    committed, tampered = ROOT / "paper/figures" / figure, out / figure
    # The blind spot: every label, count and tick is the same, so text alone passes.
    assert checker.pdf_tokens(committed) == checker.pdf_tokens(tampered), label
    text_ok, geometry_ok, detail = checker.figure_match(committed, tampered)
    assert text_ok and not geometry_ok, f"{label}: {detail}"
    # Checking never writes to the committed figures.
    assert {p.name: p.read_bytes() for p in (ROOT / "paper/figures").glob("*.pdf")} == before


@_needs_render
def test_geometry_check_passes_original_and_normal_rebuild(tmp_path):
    pytest.importorskip("matplotlib")
    checker = _frozen_truth()
    out = _rebuild_figures(tmp_path)
    for figure in (FIG1, FIG2, "fig3_reference_matches_by_family.pdf"):
        committed = ROOT / "paper/figures" / figure
        assert checker.figure_match(committed, committed)[:2] == (True, True), figure
        text_ok, geometry_ok, detail = checker.figure_match(committed, out / figure)
        assert text_ok and geometry_ok, f"{figure}: {detail}"


def test_geometry_reader_rejects_unknown_content():
    import importlib.util

    spec = importlib.util.spec_from_file_location("pdf_geometry", ROOT / "tools/pdf_geometry.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(module.GeometryError):
        module._objects(b"%PDF-1.4\nnot a pdf\n")

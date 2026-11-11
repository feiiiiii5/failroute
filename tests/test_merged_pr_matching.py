"""The revised PR driver measures location proximity, never semantic recall."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("merged_pr_recall", ROOT / "tools/merged_pr_recall.py")
assert SPEC and SPEC.loader
matching = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(matching)


def diff(body, old="a/example.py", new="b/example.py"):
    return f"diff --git {old} {new}\n--- {old}\n+++ {new}\n{body}"


@pytest.mark.parametrize(("body", "removed", "insertions"), [
    ("@@ -10,0 +11,2 @@\n+first\n+second\n", set(), {10}),
    ("@@ -0,0 +1 @@\n+first\n", set(), {1}),
    ("@@ -1 +1,2 @@\n+first\n existing\n", set(), {1}),
    ("@@ -8,2 +8,3 @@\n before\n+added\n after\n", set(), {8}),
    ("@@ -8,2 +8 @@\n before\n-removed\n", {9}, set()),
    ("@@ -8 +8 @@\n-old\n+new\n", {8}, set()),
    ("@@ -8 +8 @@\n+new\n-old\n", {8}, set()),
    ("@@ -3 +3,2 @@\n old\n+new\n\\ No newline at end of file\n", set(), {3}),
    ("@@ -3 +3,2 @@\n old\n+new\n@@ -20 +21 @@\n-old\n+new\n", {20}, {3}),
    ("@@ -3,3 +3,3 @@\n-old\n+new\n context\n+inserted\n context\n", {3}, {4}),
    ("@@ -3 +3 @@\n---text\n+++text\n", {3}, set()),
])
def test_exact_base_coordinates(body, removed, insertions):
    expected_removed = {"example.py": removed} if removed else {}
    expected_insertions = {"example.py": insertions} if insertions else {}
    assert matching.base_sites(diff(body)) == (expected_removed, expected_insertions)
    assert matching.changed_sites(diff(body)) == {"example.py": removed | insertions}
    assert matching.removed_sites(diff(body)) == expected_removed


def test_renamed_file_uses_old_path_and_deleted_file_is_retained():
    text = diff("@@ -2 +2 @@\n-old\n+new\n", "a/old.py", "b/new.py")
    text += diff("@@ -1 +0,0 @@\n-gone\n", "a/deleted.py", "/dev/null")
    assert matching.changed_sites(text) == {"old.py": {2}, "deleted.py": {1}}


def test_new_files_non_python_and_rename_without_edits_have_no_base_sites():
    text = diff("@@ -0,0 +1 @@\n+new\n", "/dev/null", "b/new.py")
    text += diff("@@ -1 +1 @@\n-old\n+new\n", "a/file.ts", "b/file.ts")
    text += "diff --git a/old.py b/new.py\nsimilarity index 100%\nrename from old.py\nrename to new.py\n"
    assert matching.changed_sites(text) == {}


def test_file_boundaries_flush_pure_addition_and_ignore_metadata():
    text = diff("@@ -5,0 +6 @@\n+new\n", "a/first.py", "b/first.py")
    text += diff("@@ -20 +20 @@\n-old\n+new\n", "a/second.py", "b/second.py")
    assert matching.changed_sites(text) == {"first.py": {5}, "second.py": {20}}


def test_quoted_path():
    text = diff("@@ -2 +2 @@\n-old\n+new\n", '"a/space name.py"', '"b/space name.py"')
    assert matching.changed_sites(text) == {"space name.py": {2}}


def test_proximity_boundary_does_not_require_semantic_mode():
    findings = [{"lineno": line, "mode": "unrelated"} for line in (6, 7, 10, 13, 14)]
    assert matching.nearby_findings(findings, {10}) == findings[1:4]
    assert matching.nearby_findings(findings, {10}, 0) == [findings[2]]
    assert matching.nearby_findings(findings, set()) == []
    with pytest.raises(ValueError, match="nonnegative"):
        matching.nearby_findings(findings, {10}, -1)


def test_default_output_is_refused_before_network():
    result = subprocess.run([sys.executable, str(ROOT / "tools/merged_pr_recall.py")],
                            capture_output=True, text=True, cwd=ROOT)
    assert result.returncode != 0
    assert "refusing to overwrite committed output" in result.stderr


def test_failed_scan_is_not_a_miss(monkeypatch, tmp_path):
    monkeypatch.setattr(matching.subprocess, "run", lambda *a, **k:
                        subprocess.CompletedProcess([], 2, "", "scan error"))
    with pytest.raises(RuntimeError, match="scan error"):
        matching.run_failroute(tmp_path / "example.py")


@pytest.mark.parametrize(("content", "findings", "expected"), [
    ("base\n", [{"lineno": 5, "mode": "test-mode"}], "yes"),
    ("base\n", [], "no"),
    (None, [], "n/a"),
])
def test_driver_uses_addition_sites_and_reports_retrieval_status(
        monkeypatch, tmp_path, content, findings, expected):
    import csv

    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    monkeypatch.setattr(matching, "OUT_DIR", tmp_path / "cache")
    monkeypatch.setattr(matching, "get_diff", lambda *a: diff("@@ -5,0 +6 @@\n+fix\n"))
    monkeypatch.setattr(matching, "pre_fix_sha", lambda *a: ("merge", "base"))
    monkeypatch.setattr(matching, "fetch_file", lambda *a: content)
    monkeypatch.setattr(matching, "run_failroute", lambda *a: findings)
    output = tmp_path / "new.csv"
    matching.main(["--out", str(output)])
    with output.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert all(row["location_match"] == expected for row in rows)
    assert all("detected" not in row for row in rows)
    if expected == "yes":
        assert all("location proximity only" in row["note"] for row in rows)
    if content is None:
        assert all("incomplete base-file retrieval" in row["note"] for row in rows)

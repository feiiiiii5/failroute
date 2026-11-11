"""Safety and comparison tests for the held-out fresh-output driver."""
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "reproduce_heldout", Path(__file__).resolve().parents[1] / "tools/reproduce_heldout.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_existing_output_refused_without_changes(tmp_path):
    marker = tmp_path / "keep.txt"
    marker.write_text("original")
    with pytest.raises(ValueError, match="already exists"):
        MODULE.run(tmp_path)
    assert list(tmp_path.iterdir()) == [marker]
    assert marker.read_text() == "original"


def test_json_compare_ignores_only_explicit_top_level_keys(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps({"time": "new", "count": 9, "nested": {"count": 1}}))
    b.write_text(json.dumps({"time": "old", "count": 8, "nested": {"count": 1}}))
    assert MODULE.compare_json(a, b, ("time",)) == ["count"]


def test_rows_compare_all_fields_and_keep_duplicates(tmp_path):
    a = tmp_path / "a.jsonl"
    a.write_text('{"a":1,"b":2}\n{"b":2,"a":1}\n\n')
    assert MODULE.json_rows(a) == ['{"a": 1, "b": 2}', '{"a": 1, "b": 2}']


def test_vendor_filter_preserves_source_and_empty_packages(tmp_path):
    source, target = tmp_path / "source", tmp_path / "filtered"
    source.mkdir()
    keep = json.dumps({"file": "paper/corpus/dspy-3.5.0/dspy/utils.py"})
    drop = json.dumps({"file": "paper/corpus/dspy-3.5.0/dspy/_vendor/x.py"})
    original = keep + "\n" + drop + "\n"
    (source / "dspy.jsonl").write_text(original)
    (source / "empty.jsonl").write_text("")
    MODULE.filter_vendor(source, target)
    assert (source / "dspy.jsonl").read_text() == original
    assert (target / "dspy.jsonl").read_text() == keep + "\n"
    assert (target / "empty.jsonl").read_text() == ""

"""Benchmark gate: scanner must match the hand-labelled corpus exactly.

Ground truth (tests/corpus/manifest.json) is labelled independently of tool
output, so precision == recall == 1.0 here is a real claim, not a tautology.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_benchmark():
    path = Path(__file__).resolve().parent.parent / "tools" / "benchmark.py"
    spec = importlib.util.spec_from_file_location("failroute_benchmark", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_corpus_precision_and_recall_are_perfect():
    report = _load_benchmark().run()
    assert report["false_positives"] == [], report["false_positives"]
    assert report["false_negatives"] == [], report["false_negatives"]
    assert report["true_negative_violations"] == [], report["true_negative_violations"]
    assert report["precision"] == 1.0
    assert report["recall"] == 1.0


@pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="match_case_cases.py is legitimately unparseable before Python 3.10; "
    "the point of this gate is that nothing else ever is",
)
def test_no_corpus_file_is_skipped_on_modern_python():
    """The skip path must never hide labels on interpreters that can parse them.

    A corpus file that fails to parse on 3.10+ means someone landed syntax the
    CI floor cannot handle without recording it -- exactly what this gate catches.
    """
    report = _load_benchmark().run()
    assert report["skipped_files"] == [], report["skipped_files"]


def test_corpus_covers_all_modes():
    import json

    manifest_path = Path(__file__).resolve().parent / "corpus" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    modes = {entry["mode"] for entry in manifest["expected"]}
    assert modes == {
        "no-action",
        "silent-fallback",
        "implicit-fallback",
        "masked-exception",
        "name-shadowing",
        "silent-suppress",
    }
    assert len(manifest["expected"]) >= 30
    assert len(manifest["labelled_true_negatives"]) >= 25

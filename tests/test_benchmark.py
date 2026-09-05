"""Regression gate over the hand-written fixture corpus.

V1 (2026-09-04): this is a **regression** gate, not a quality measurement, and
it must not be cited as one. 委外任务清单.md §V1.4 G5 downgrades it explicitly:
the fixtures in ``tests/corpus/`` and the detector were written by the same
author, and the paper's own RQ4 records the consequence -- this corpus never
caught the ``for stmt in handler.body`` blind spot that hid a whole class of
handler shapes. Passing here says "nothing changed unexpectedly", not "the
detector is good".

Quality evidence lives in ``bench/realworld/``, whose 80 labelled coordinates
come from third-party code in the SHA256-locked paper corpus.

Ground truth (``tests/corpus/manifest.json``) is labelled independently of tool
output. One label was revised in V1 and carries an inline note saying so: the
fixture at ``silent_fallback_cases.py:65`` asserted the logging exemption that
§V1.1 layer 3 removes.
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


def test_corpus_regression_is_clean():
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

"""Tests for the CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent.parent / "src")


def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    # Always invoke via the module form: it works both from an installed
    # package and straight from a source checkout (pytest's pythonpath).
    env = {**os.environ, "PYTHONPATH": _SRC}
    cmd: list[str] = [sys.executable, "-m", "failroute", *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
    )


def _sample_dir(tmp_path: Path) -> Path:
    sample = tmp_path / "sample"
    sample.mkdir()
    (sample / "bad.py").write_text(
        "def f():\n    try:\n        return fetch()\n    except Exception:\n        return None\n"
    )
    (sample / "good.py").write_text(
        "def g():\n"
        "    try:\n"
        "        return fetch()\n"
        "    except Exception as e:\n"
        "        logger.error('boom %s', e)\n"
        "        raise\n"
    )
    return sample


def test_cli_text_output(tmp_path: Path):
    sample = _sample_dir(tmp_path)
    result = _run_cli([str(sample)])
    assert result.returncode == 1  # findings above threshold 0
    assert "bad.py:4:" in result.stdout
    assert "good.py" not in result.stdout


def test_cli_json_output(tmp_path: Path):
    sample = _sample_dir(tmp_path)
    result = _run_cli([str(sample), "--format", "json"])
    lines = [line for line in result.stdout.splitlines() if line.strip().startswith("{")]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["mode"] == "silent-fallback"
    assert payload["file"].endswith("bad.py")


def test_cli_threshold_exit_codes(tmp_path: Path):
    sample = _sample_dir(tmp_path)
    assert _run_cli([str(sample), "--threshold", "0"]).returncode == 1
    assert _run_cli([str(sample), "--threshold", "5"]).returncode == 0


def test_cli_quiet_prints_summary_only(tmp_path: Path):
    sample = _sample_dir(tmp_path)
    result = _run_cli([str(sample), "--quiet"])
    assert result.stdout == ""
    assert "1 finding(s)" in result.stderr


def test_cli_missing_path_returns_2():
    result = _run_cli(["/definitely/not/a/real/path"])
    assert result.returncode == 2


def test_cli_sarif_output(tmp_path: Path):
    sample = _sample_dir(tmp_path)
    result = _run_cli([str(sample), "--format", "sarif"])
    assert result.returncode == 1
    doc = json.loads(result.stdout)
    assert doc["version"] == "2.1.0"
    assert doc["runs"][0]["tool"]["driver"]["name"] == "failroute"
    assert doc["runs"][0]["results"][0]["ruleId"] == "failroute/silent-fallback"


def test_cli_output_file(tmp_path: Path):
    sample = _sample_dir(tmp_path)
    out = tmp_path / "findings.json"
    result = _run_cli([str(sample), "--format", "json", "--output", str(out)])
    assert result.returncode == 1
    assert out.exists()
    assert '"mode": "silent-fallback"' in out.read_text()


def test_cli_legacy_json_flag(tmp_path: Path):
    sample = _sample_dir(tmp_path)
    result = _run_cli([str(sample), "--json"])
    assert result.returncode == 1
    assert '"mode": "silent-fallback"' in result.stdout

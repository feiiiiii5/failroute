"""Tests for [tool.failroute] project configuration in pyproject.toml."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent.parent / "src")

_BAD = "def f():\n    try:\n        return fetch()\n    except Exception:\n        return None\n"


def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    env_path = _SRC
    import os

    env = {**os.environ, "PYTHONPATH": env_path}
    return subprocess.run(
        [sys.executable, "-m", "failroute", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_config_exclude_and_threshold(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.failroute]\nexclude = ['skipme']\nthreshold = 5\n", encoding="utf-8"
    )
    skip = tmp_path / "skipme"
    skip.mkdir()
    (skip / "bad.py").write_text(_BAD, encoding="utf-8")
    (tmp_path / "clean.py").write_text("x = 1\n", encoding="utf-8")
    result = _run_cli([str(tmp_path)])
    assert result.returncode == 0, result.stdout + result.stderr


def test_config_threshold_applies_when_no_flag(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[tool.failroute]\nthreshold = 0\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text(_BAD, encoding="utf-8")
    assert _run_cli([str(tmp_path)]).returncode == 1
    (tmp_path / "pyproject.toml").write_text("[tool.failroute]\nthreshold = 3\n", encoding="utf-8")
    assert _run_cli([str(tmp_path)]).returncode == 0


def test_cli_flag_overrides_config(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[tool.failroute]\nthreshold = 99\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text(_BAD, encoding="utf-8")
    assert _run_cli([str(tmp_path), "--threshold", "0"]).returncode == 1


def test_malformed_config_never_crashes(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("this is not [valid toml", encoding="utf-8")
    (tmp_path / "bad.py").write_text(_BAD, encoding="utf-8")
    result = _run_cli([str(tmp_path)])
    assert result.returncode == 1  # finding still reported, no crash
    assert "Traceback" not in result.stderr

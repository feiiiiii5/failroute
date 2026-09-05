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


def test_repo_flag_with_single_file_scans_the_file(tmp_path):
    target = tmp_path / "mod.py"
    target.write_text(
        "try:\n    a()\nexcept Exception:\n    pass\n",
        encoding="utf-8",
    )
    proc = _run_cli([str(target), "--repo", "--quiet"])
    assert proc.returncode == 1


# ---------------------------------------------------------------------------
# G6⑦ exit-code contract (V1, 2026-09-04)
#
# 🔴 The old contract was "any finding at all exits 1". In CI that makes a
# healthy repository indistinguishable from a broken one, because virtually
# every codebase has at least one INFO-level finding -- 委外任务清单.md §V1.4
# G6⑦ calls this out directly ("现在「有 finding 就 1」在 CI 里等于「成功看起
# 来像失败」"). Exit 1 is now gated on severity.
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, name: str, body: str) -> Path:
    target = tmp_path / name
    target.write_text(body, encoding="utf-8")
    return target


def test_exit_zero_when_no_findings(tmp_path: Path):
    clean = _write(tmp_path, "clean.py", "def f(x):\n    return x + 1\n")
    assert _run_cli([str(clean)]).returncode == 0


def test_exit_one_on_high_finding(tmp_path: Path):
    bad = _write(
        tmp_path,
        "bad.py",
        "def f(x) -> float:\n"
        "    try:\n"
        "        return g(x)\n"
        "    except:\n"
        "        return 0.0\n",
    )
    result = _run_cli([str(bad)])
    assert result.returncode == 1
    assert "high" in result.stdout


def test_exit_zero_when_findings_are_below_fail_on(tmp_path: Path):
    # A logged catch-all fallback lands at MEDIUM: reported, but not a gate
    # failure at the default --fail-on high. This is the case the old contract
    # got wrong.
    medium = _write(
        tmp_path,
        "medium.py",
        "def f(x) -> float:\n"
        "    try:\n"
        "        return g(x)\n"
        "    except Exception:\n"
        "        logger.warning('fell back')\n"
        "        return 0.0\n",
    )
    result = _run_cli([str(medium)])
    assert result.returncode == 0
    assert "medium" in result.stdout
    assert "gate: 0 of 1 at or above high" in result.stderr


def test_fail_on_medium_promotes_the_same_scan(tmp_path: Path):
    medium = _write(
        tmp_path,
        "medium.py",
        "def f(x) -> float:\n"
        "    try:\n"
        "        return g(x)\n"
        "    except Exception:\n"
        "        logger.warning('fell back')\n"
        "        return 0.0\n",
    )
    assert _run_cli([str(medium), "--fail-on", "medium"]).returncode == 1
    assert _run_cli([str(medium), "--fail-on", "high"]).returncode == 0
    assert _run_cli([str(medium), "--fail-on", "info"]).returncode == 1


def test_exit_zero_flag_never_fails(tmp_path: Path):
    bad = _write(tmp_path, "bad.py", "try:\n    a()\nexcept Exception:\n    pass\n")
    result = _run_cli([str(bad), "--exit-zero"])
    assert result.returncode == 0
    assert "--exit-zero" in result.stderr
    assert "no-action" in result.stdout  # still reported, just not gating


def test_exit_two_on_missing_path(tmp_path: Path):
    assert _run_cli([str(tmp_path / "nope.py")]).returncode == 2


def test_exit_two_on_scan_failure(tmp_path: Path, monkeypatch):
    # An unexpected exception inside the scan is a *run* failure: it must not
    # escape as a traceback and must not be reported as exit 1, which would read
    # as "findings above threshold".
    import failroute.cli as cli

    def boom(*args, **kwargs):
        raise RuntimeError("simulated scanner failure")

    monkeypatch.setattr(cli, "scan_path", boom)
    target = _write(tmp_path, "any.py", "x = 1\n")
    assert cli.main([str(target)]) == 2


def test_only_novel_filters_to_uncovered_findings(tmp_path: Path):
    # `except:` is covered by E722/B001/W0702; `suppress(Exception)` is covered
    # by nothing. --only-novel must keep only the latter.
    target = _write(
        tmp_path,
        "mixed.py",
        "import contextlib\n"
        "\n"
        "def bare(x):\n"
        "    try:\n"
        "        return g(x)\n"
        "    except:\n"
        "        return 0.0\n"
        "\n"
        "def suppressed(x):\n"
        "    with contextlib.suppress(Exception):\n"
        "        g(x)\n",
    )
    everything = _run_cli([str(target), "--format", "json", "--exit-zero"])
    novel = _run_cli([str(target), "--format", "json", "--only-novel", "--exit-zero"])
    all_lines = [line for line in everything.stdout.splitlines() if line.startswith("{")]
    novel_lines = [line for line in novel.stdout.splitlines() if line.startswith("{")]
    assert len(all_lines) == 2
    assert len(novel_lines) == 1
    payload = json.loads(novel_lines[0])
    assert payload["rule_id"] == "silent-suppress"
    assert payload["covered_by"] == []
    assert payload["severity"] == "high"
    bare_payload = next(json.loads(x) for x in all_lines if "silent-fallback" in x)
    assert "flake8:E722" in bare_payload["covered_by"]


def test_json_output_carries_the_v1_verdict_fields(tmp_path: Path):
    target = _write(
        tmp_path,
        "bad.py",
        "def f(x) -> float:\n"
        "    try:\n"
        "        return g(x)\n"
        "    except:\n"
        "        return 0.0\n",
    )
    result = _run_cli([str(target), "--format", "json", "--exit-zero"])
    payload = json.loads([x for x in result.stdout.splitlines() if x.startswith("{")][0])
    for key in ("severity", "isomorphism", "covered_by", "verdict"):
        assert key in payload, key
    assert payload["severity"] == "high"
    assert payload["isomorphism"] == "non-isomorphic"
    assert payload["verdict"]

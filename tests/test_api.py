"""In-process tests: API-level coverage of scan_repo/scan_path/main and config.

These run the code inside the test process (not via subprocess) so coverage
sees the scanner internals, config loading, and CLI summary paths.
"""

from __future__ import annotations

from pathlib import Path

from failroute import main, scan_path, scan_repo, scan_source
from failroute.analyzer import FailureMode

_BAD = "def f():\n    try:\n        return fetch()\n    except Exception:\n        return None\n"


def test_scan_repo_exclude_inprocess(tmp_path: Path):
    (tmp_path / "bad.py").write_text(_BAD, encoding="utf-8")
    vend = tmp_path / "vend"
    vend.mkdir()
    (vend / "bad.py").write_text(_BAD, encoding="utf-8")
    findings = scan_repo(tmp_path, exclude={"vend"})
    assert len(findings) == 1
    assert "vend" not in findings[0].file


def test_scan_path_skips_directory_named_like_python_file(tmp_path: Path):
    weird = tmp_path / "weird.py"
    weird.mkdir()
    (tmp_path / "real.py").write_text(_BAD, encoding="utf-8")
    findings = scan_path(tmp_path)
    assert len(findings) == 1


def test_main_inprocess_with_config(tmp_path: Path, capsys):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.failroute]\nexclude = ['vend']\nthreshold = 5\n", encoding="utf-8"
    )
    vend = tmp_path / "vend"
    vend.mkdir()
    (vend / "bad.py").write_text(_BAD, encoding="utf-8")
    (tmp_path / "clean.py").write_text("x = 1\n", encoding="utf-8")
    rc = main([str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "0 finding(s)" in captured.err


def test_main_inprocess_malformed_config_still_scans(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("not [valid toml", encoding="utf-8")
    (tmp_path / "bad.py").write_text(_BAD, encoding="utf-8")
    assert main([str(tmp_path)]) == 1


def test_main_output_file_and_missing_path(tmp_path: Path):
    out = tmp_path / "out.json"
    (tmp_path / "bad.py").write_text(_BAD, encoding="utf-8")
    assert main([str(tmp_path / "bad.py"), "--format", "json", "--output", str(out)]) == 1
    assert out.exists()
    assert main(["/definitely/not/here"]) == 2


def test_catch_all_via_attribute_form_is_masked():
    source = (
        "def f():\n"
        "    try:\n"
        "        return g()\n"
        "    except builtins.Exception as e:\n"
        "        if isinstance(e, TimeoutError):\n"
        "            raise\n"
        "        return 0.0\n"
    )
    findings = scan_source(source)
    assert [f.mode for f in findings] == [FailureMode.MASKED_EXCEPTION]


def test_typed_conditional_raise_with_fallback_is_still_a_finding():
    # A typed handler that conditionally re-raises but also falls back to a
    # constant still routes the failure into a success-looking value on the
    # non-raising branch -- reportable as silent-fallback.
    source = (
        "def f():\n"
        "    try:\n"
        "        return g()\n"
        "    except ValueError:\n"
        "        if retryable():\n"
        "            raise\n"
        "        return None\n"
    )
    findings = scan_source(source)
    assert [f.mode for f in findings] == [FailureMode.SILENT_FALLBACK]


def test_dead_fallback_after_unconditional_raise_is_not_reported():
    source = (
        "def f():\n"
        "    try:\n"
        "        return g()\n"
        "    except ValueError:\n"
        "        raise\n"
        "        return None\n"
    )
    assert scan_source(source) == []


def test_negative_zero_constant_is_a_fallback():
    findings = scan_source(
        "def f():\n    try:\n        return g()\n    except Exception:\n        return -0.0\n"
    )
    assert [f.mode for f in findings] == [FailureMode.SILENT_FALLBACK]


def test_sys_exit_terminates_like_raise():
    findings = scan_source(
        "def f():\n    try:\n        return g()\n    except Exception:\n        sys.exit(1)\n"
    )
    assert findings == []

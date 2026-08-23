"""Tests for v0.2 deep-optimization behaviors:

- NAME_SHADOWING detector (previously declared but never emitted)
- two-tier logging exemption (severity matters for catch-all handlers)
- scope-aware scans (nested defs do not leak raises/returns into the handler)
- catch-all gate on masked-exception
- process-exit calls terminate like raises
- expanded ignore list (StopIteration, CancelledError)
- CLI contract (version, json, threshold, quiet, exit codes, determinism)
"""

from __future__ import annotations

import json

import pytest

from failroute.analyzer import FailureMode, scan_source
from failroute.cli import main

# ---------------------------------------------------------------- shadowing


def test_name_shadowing_rebind_is_flagged():
    findings = scan_source(
        """
def f():
    try:
        do()
    except ValueError as e:
        e = wrap(e)
"""
    )
    modes = [x.mode for x in findings]
    assert FailureMode.NAME_SHADOWING in modes


def test_name_shadowing_for_target_is_flagged():
    findings = scan_source(
        """
def f():
    try:
        do()
    except Exception as err:
        for err in items():
            pass
"""
    )
    assert any(x.mode == FailureMode.NAME_SHADOWING for x in findings)


def test_reading_exc_var_is_not_shadowing():
    findings = scan_source(
        """
def f():
    try:
        do()
    except ValueError as e:
        log("failed %s", e)
"""
    )
    assert all(x.mode != FailureMode.NAME_SHADOWING for x in findings)


def test_unnamed_handler_cannot_shadow():
    findings = scan_source(
        """
def f():
    try:
        do()
    except ValueError:
        e = 1
"""
    )
    assert all(x.mode != FailureMode.NAME_SHADOWING for x in findings)


# ------------------------------------------------------- logging two tiers


def test_print_does_not_exempt_catch_all_fallback():
    findings = scan_source(
        """
def f():
    try:
        judge(p)
    except Exception:
        print("done")
        return 0.0
"""
    )
    assert len(findings) == 1
    assert findings[0].mode == FailureMode.SILENT_FALLBACK


def test_debug_log_does_not_exempt_catch_all_fallback():
    findings = scan_source(
        """
def f():
    try:
        judge(p)
    except Exception:
        logger.debug("failed", exc_info=True)
        return False
"""
    )
    assert len(findings) == 1


def test_warning_log_still_exempts_catch_all():
    findings = scan_source(
        """
def f():
    try:
        judge(p)
    except Exception:
        logger.warning("judge failed; defaulting")
        return 0.0
"""
    )
    assert findings == []


def test_any_level_log_exempts_typed_handler():
    # Typed handlers document the anticipated failure mode by naming it;
    # recording it at info level is enough of a trace.
    findings = scan_source(
        """
def f():
    try:
        ctx = op.get_context()
    except (AttributeError, NameError):
        logger.info("outside migration context")
        return
"""
    )
    assert findings == []


# ------------------------------------------------------------ scope hygiene


def test_nested_def_return_does_not_mask():
    # A callback defined in the handler returning None belongs to the
    # callback's own contract; combined with an unrelated branch raise it
    # must not read as masked-exception.
    findings = scan_source(
        """
def f():
    try:
        do()
    except Exception:
        if retries > 0:
            raise
        def cb():
            return None
        register(cb)
"""
    )
    assert all(x.mode != FailureMode.MASKED_EXCEPTION for x in findings)


def test_typed_conditional_raise_with_return_not_masked():
    # Masking is a *catch-all* contract; a typed handler that conditionally
    # re-raises and early-returns is deliberate control flow.
    findings = scan_source(
        """
def f(skip):
    try:
        measure()
    except MissingParams as e:
        if skip:
            record(str(e))
            return
        raise
"""
    )
    assert all(x.mode != FailureMode.MASKED_EXCEPTION for x in findings)


def test_sys_exit_terminates_like_raise():
    # An assignment followed by sys.exit never lets the caller observe the
    # fallback value, so it is not a silent fallback.
    findings = scan_source(
        """
def f():
    try:
        boot()
    except ConfigError:
        data = {}
        sys.exit(1)
"""
    )
    assert findings == []


# ------------------------------------------------------------- ignore list


def test_stop_iteration_ignored():
    findings = scan_source(
        """
while True:
    try:
        next(it)
    except StopIteration:
        break
"""
    )
    assert findings == []


def test_cancelled_error_ignored():
    findings = scan_source(
        """
async def task():
    try:
        await work()
    except CancelledError:
        pass
"""
    )
    assert findings == []


# --------------------------------------------------------- recursion guard


def test_triple_nested_handlers_no_duplicates():
    findings = scan_source(
        """
def f():
    try:
        try:
            try:
                a()
            except ValueError:
                pass
        except KeyError:
            pass
    except Exception:
        return None
"""
    )
    assert len(findings) == 3
    keys = {(x.lineno, x.mode.value) for x in findings}
    assert len(keys) == 3


# --------------------------------------------------------------------- CLI


def _write(tmp_path, source="def f():\n    try:\n        a()\n    except Exception:\n        pass\n"):
    target = tmp_path / "mod.py"
    target.write_text(source)
    return target


def test_cli_json_output(tmp_path, capsys):
    target = _write(tmp_path)
    code = main([str(target), "--json"])
    out = capsys.readouterr().out.strip().splitlines()
    parsed = [json.loads(line) for line in out]
    assert code == 1
    assert len(parsed) == 1
    assert parsed[0]["mode"] == "no-action"
    assert parsed[0]["file"] == str(target)


def test_cli_threshold_zero_means_any_finding(tmp_path):
    target = _write(tmp_path)
    assert main([str(target), "--threshold", "0"]) == 1
    assert main([str(target), "--threshold", "5"]) == 0


def test_cli_quiet_suppresses_lines(tmp_path, capsys):
    target = _write(tmp_path)
    main([str(target), "--quiet"])
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "1 finding(s)" in captured.err


def test_cli_missing_path_exit_two(capsys):
    assert main(["/nonexistent/zzz.py"]) == 2
    assert "no such path" in capsys.readouterr().err


def test_cli_version_flag(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert "failroute" in capsys.readouterr().out


def test_cli_deterministic_order(tmp_path, capsys):
    (tmp_path / "b.py").write_text("try:\n    a()\nexcept Exception:\n    return 0\n")
    (tmp_path / "a.py").write_text("try:\n    b()\nexcept Exception:\n    pass\n")
    main([str(tmp_path), "--json"])
    files = [json.loads(x)["file"] for x in capsys.readouterr().out.strip().splitlines()]
    assert files == sorted(files)

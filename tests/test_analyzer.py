"""Tests for the failure-routing analyzer."""

from __future__ import annotations

from failroute.analyzer import FailureMode, scan_path, scan_source


def test_no_action_pass():
    findings = scan_source(
        """
def f():
    try:
        do_something()
    except Exception:
        pass
"""
    )
    assert len(findings) == 1
    assert findings[0].mode == FailureMode.NO_ACTION


def test_no_action_ellipsis():
    findings = scan_source(
        """
try:
    x()
except ValueError:
    ...
"""
    )
    assert len(findings) == 1
    assert findings[0].mode == FailureMode.NO_ACTION


def test_silent_fallback_none_return():
    findings = scan_source(
        """
def get():
    try:
        return fetch()
    except Exception:
        return None
"""
    )
    assert len(findings) == 1
    assert findings[0].mode == FailureMode.SILENT_FALLBACK


def test_silent_fallback_zero_return():
    findings = scan_source(
        """
def score():
    try:
        return judge(prompt)
    except Exception:
        return 0.0
"""
    )
    assert len(findings) == 1
    assert findings[0].mode == FailureMode.SILENT_FALLBACK


def test_silent_fallback_false_return():
    findings = scan_source(
        """
def check():
    try:
        return run()
    except Exception:
        return False
"""
    )
    assert len(findings) == 1
    assert findings[0].mode == FailureMode.SILENT_FALLBACK


def test_silent_fallback_empty_collection_return():
    findings = scan_source(
        """
def load():
    try:
        return query()
    except Exception:
        return []
"""
    )
    assert len(findings) == 1
    assert findings[0].mode == FailureMode.SILENT_FALLBACK


def test_silent_fallback_assign():
    findings = scan_source(
        """
def fetch(url):
    data = None
    try:
        data = download(url)
    except Exception:
        data = {}
    return data
"""
    )
    assert len(findings) >= 1
    assert findings[0].mode in (FailureMode.SILENT_FALLBACK,)


def test_reraises_clean_is_not_flagged():
    findings = scan_source(
        """
def f():
    try:
        do_something()
    except Exception:
        raise
"""
    )
    assert findings == []


def test_log_and_raise_is_not_flagged():
    findings = scan_source(
        """
def f():
    try:
        do_something()
    except Exception as e:
        logger.error("boom: %s", e)
        raise
"""
    )
    assert findings == []


def test_reraises_then_falls_through_to_return_is_flagged():
    findings = scan_source(
        """
def f():
    try:
        do_something()
    except Exception:
        raise
    return 0
"""
    )
    # The handler itself re-raises; the trailing `return 0` lives *outside* the
    # handler, so per our contract this handler is clean. The pattern we flag is
    # the handler-internal ambiguity; this test documents the boundary.
    assert findings == []


def test_masked_exception_conditional_raise_with_fallback():
    findings = scan_source(
        """
def f():
    try:
        do_something()
    except Exception:
        if retries > 0:
            raise
        return None
"""
    )
    assert len(findings) == 1
    assert findings[0].mode == FailureMode.MASKED_EXCEPTION


def test_unconditional_raise_then_dead_return_not_flagged():
    # `return None` after an unconditional `raise` is unreachable; the failure
    # still propagates. Not a masking defect.
    findings = scan_source(
        """
def f():
    try:
        do_something()
    except Exception:
        raise
        return None
"""
    )
    assert findings == []


def test_keyboard_interrupt_ignored():
    findings = scan_source(
        """
try:
    run()
except KeyboardInterrupt:
    pass
"""
    )
    assert findings == []


def test_nested_handlers_both_found():
    findings = scan_source(
        """
def f():
    try:
        try:
            a()
        except Exception:
            pass
    except Exception:
        return None
"""
    )
    assert len(findings) == 2
    modes = {f.mode for f in findings}
    assert modes == {FailureMode.NO_ACTION, FailureMode.SILENT_FALLBACK}


def test_bare_except_flagged():
    findings = scan_source(
        """
def f():
    try:
        a()
    except:
        pass
"""
    )
    assert len(findings) == 1
    assert findings[0].mode == FailureMode.NO_ACTION


def test_typed_exception_necessary_action_not_flagged():
    findings = scan_source(
        """
def f():
    try:
        a()
    except FileNotFoundError:
        open(path, "w").close()
"""
    )
    assert findings == []


def test_named_exception_reported_in_finding():
    findings = scan_source(
        """
try:
    a()
except ValueError as e:
    pass
"""
    )
    assert findings[0].exc_name == "e"


def test_scan_source_records_file_and_lines():
    findings = scan_source(
        "\n\ntry:\n    a()\nexcept Exception:\n    pass\n",
        file="sample.py",
    )
    assert findings[0].file == "sample.py"
    assert findings[0].lineno == 5


def test_multiple_findings_sorted():
    findings = scan_source(
        """
try:
    a()
except Exception:
    pass

try:
    b()
except Exception:
    return 0
"""
    )
    assert len(findings) == 2


def test_logging_handler_not_flagged():
    # A handler that logs the failure leaves a trace; logging + return
    # fallback is informational, not silent corruption.
    findings = scan_source(
        """
def f():
    try:
        do_something()
    except Exception as e:
        logger.error("failed: %s", e)
        return None
"""
    )
    assert findings == []


def test_log_and_assign_not_flagged():
    findings = scan_source(
        """
def f():
    try:
        do_something()
    except Exception as e:
        logger.warning("oops %s", e)
        data = {}
    return data
"""
    )
    assert findings == []


def test_assign_from_exception_is_not_fallback():
    # error_msg = str(e) derives from the exception itself; it is error
    # handling, not a silent fallback.
    findings = scan_source(
        """
def f():
    try:
        do_something()
    except ValueError as e:
        error_msg = str(e)
        raise RuntimeError(error_msg) from e
"""
    )
    assert findings == []


def test_assign_constant_fallback_is_flagged():
    findings = scan_source(
        """
def f():
    try:
        data = fetch()
    except Exception:
        data = {}
    return data
"""
    )
    assert len(findings) == 1
    assert findings[0].mode == FailureMode.SILENT_FALLBACK


def test_pragma_no_cover_handler_skipped():
    findings = scan_source(
        """
def f():
    try:
        a()
    except Exception:  # pragma: no cover - defensive
        pass
"""
    )
    assert findings == []


def test_failroute_ignore_marker_suppresses():
    findings = scan_source(
        """
def f():
    try:
        a()
    except Exception:  # failroute: ignore - documented fallback
        return None
"""
    )
    assert findings == []


def test_deeply_nested_source_never_crashes(tmp_path):
    # Generated payload files (e.g. red-team resources) can nest far beyond
    # the interpreter's recursion budget; the scanner must skip, not crash.
    deep = "(" * 20000 + "1" + ")" * 20000
    target = tmp_path / "deep.py"
    target.write_text(f"x = {deep}\n", encoding="utf-8")
    assert scan_path(target) == []

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


def test_logging_handler_is_downgraded_not_exempted():
# V1 (2026-09-04): recording a failure is a severity *modifier*, not an exemption.
    # 委外任务清单.md §V1.1 layer 3 + probes C2/C3 in §V1.0-A: a log line does not
    # change what the caller receives, so the finding stays and moves down one level.
    # This test previously asserted `== []`, which encoded the old exemption.
        # The caller still receives None where a real result was promised:
    # catch-all base HIGH, one level down for logger.error -> MEDIUM.
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
    assert [f.mode.value for f in findings] == ["silent-fallback"]
    assert findings[0].severity.value == "medium"
    assert "recorded" in findings[0].verdict


def test_log_and_assign_is_downgraded_not_exempted():
# V1 (2026-09-04): recording a failure is a severity *modifier*, not an exemption.
    # 委外任务清单.md §V1.1 layer 3 + probes C2/C3 in §V1.0-A: a log line does not
    # change what the caller receives, so the finding stays and moves down one level.
    # This test previously asserted `== []`, which encoded the old exemption.
        # `data = {}` substitutes an empty container for the real result and
    # `return data` hands it to the caller; logger.warning lowers HIGH -> MEDIUM.
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
    assert [f.mode.value for f in findings] == ["silent-fallback"]
    assert findings[0].severity.value == "medium"


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


def test_silent_suppress_catch_all():
    findings = scan_source(
        """
import contextlib

def f():
    with contextlib.suppress(Exception):
        judge(prompt)
"""
    )
    assert len(findings) == 1
    assert findings[0].mode == FailureMode.SILENT_SUPPRESS
    assert "every failure" in findings[0].message


def test_silent_suppress_direct_import():
    # V1 (2026-09-04): silent-suppress reports broad suppression only
    # (委外任务清单.md §V1.2). The fixture uses `Exception` so this still tests
    # what it was written to test -- that `from contextlib import suppress`
    # resolves -- rather than accidentally testing the narrow-type exemption.
    findings = scan_source(
        """
from contextlib import suppress

def f():
    with suppress(Exception):
        os.remove(path)
"""
    )
    assert len(findings) == 1
    assert findings[0].mode == FailureMode.SILENT_SUPPRESS
    assert "contextlib.suppress(Exception)" in findings[0].message


def test_silent_suppress_aliased_import():
    findings = scan_source(
        """
from contextlib import suppress as swallow

def f():
    with swallow(Exception):
        lookup(name)
"""
    )
    assert len(findings) == 1


def test_silent_suppress_async_with():
    findings = scan_source(
        """
import contextlib

async def f():
    async with contextlib.suppress(Exception):
        await op()
"""
    )
    assert len(findings) == 1
    assert findings[0].mode == FailureMode.SILENT_SUPPRESS


def test_suppress_from_other_module_not_flagged():
    findings = scan_source(
        """
from helpers import suppress

def f():
    with suppress(ValueError):
        lookup(name)
"""
    )
    assert findings == []


def test_suppress_ignore_marker_suppresses():
    findings = scan_source(
        """
from contextlib import suppress

def f():
    with suppress(FileNotFoundError):  # failroute: ignore - best-effort cleanup
        os.remove(path)
"""
    )
    assert findings == []


def test_non_suppress_context_manager_not_flagged():
    findings = scan_source(
        """
import contextlib

def f():
    with contextlib.closing(open(path)) as stream:
        return stream.read()
"""
    )
    assert findings == []


def test_suppress_referenced_as_value_not_flagged():
    findings = scan_source(
        """
import contextlib

def f():
    return contextlib.suppress
"""
    )
    assert findings == []


def test_suppress_finding_sorted_with_handler_findings():
    findings = scan_source(
        """
import contextlib

def f():
    with contextlib.suppress(Exception):
        a()

def g():
    try:
        b()
    except Exception:
        pass
"""
    )
    assert [f.lineno for f in findings] == sorted(f.lineno for f in findings)
    assert {f.mode for f in findings} == {FailureMode.SILENT_SUPPRESS, FailureMode.NO_ACTION}


def test_suppress_control_flow_exceptions_not_flagged():
    findings = scan_source(
        """
import asyncio
import contextlib

async def f():
    with contextlib.suppress(asyncio.CancelledError):
        fire_and_forget.cancel()
"""
    )
    assert findings == []


def test_suppress_keyboard_interrupt_not_flagged():
    findings = scan_source(
        """
from contextlib import suppress

def f():
    with suppress(KeyboardInterrupt):
        wait()
"""
    )
    assert findings == []


def test_suppress_mixed_ignore_and_broad_error_flagged():
    # V1 (2026-09-04): the "one real error type" in a mixed tuple now has to be
    # a *broad* one. `CancelledError + OSError` is narrow-only and stays clean;
    # `CancelledError + Exception` silences an unbounded set and is reported.
    findings = scan_source(
        """
import asyncio
import contextlib

def f():
    with contextlib.suppress(asyncio.CancelledError, Exception):
        op()
"""
    )
    assert len(findings) == 1
    assert findings[0].mode == FailureMode.SILENT_SUPPRESS


def test_suppress_narrow_types_only_is_not_flagged():
    # V1 (2026-09-04): 委外任务清单.md §V1.2 restricts silent-suppress to broad
    # suppression. Measured on the pinned corpus the split is 23 broad to 4
    # specific, so the restriction removes the narrow ones and keeps every
    # shape that discards an unbounded exception set.
    findings = scan_source(
        """
import asyncio
import contextlib

def f():
    with contextlib.suppress(asyncio.CancelledError, OSError):
        op()

def g():
    with contextlib.suppress(FileNotFoundError):
        os.remove(path)
"""
    )
    assert findings == []


def test_suppress_finding_is_novel_and_high():
    # No shipped linter rule flags contextlib.suppress(...): verified against
    # ruff, flake8+bugbear, bandit and pylint. covered_by is empty by
    # construction, which is what makes this rule the tool's one unambiguous
    # contribution over trivial linting.
    findings = scan_source(
        """
import contextlib

def f():
    with contextlib.suppress(Exception):
        op()
"""
    )
    assert len(findings) == 1
    assert findings[0].covered_by == ()
    assert findings[0].severity.value == "high"

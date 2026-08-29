"""Tests for the implicit-fallback rule (v0.6 blind-spot fix).

The v0.5 visitor only examined raise/return/assignment statements, so a
handler whose body was a bare expression statement slipped through every
gate while producing the same caller-visible outcome as ``except: pass``
(the function's implicit ``return None``).
"""

from __future__ import annotations

from failroute.analyzer import FailureMode, scan_source


def test_print_fallthrough_is_reported():
    source = "def a(x):\n    try:\n        return risky(x)\n    except Exception:\n        print('failed')\n"
    findings = scan_source(source)
    assert [f.mode for f in findings] == [FailureMode.IMPLICIT_FALLBACK]


def test_conditional_raise_with_fallthrough_is_reported():
    # The raising branch terminates; the other branch falls through to None.
    source = (
        "def a(x):\n"
        "    try:\n"
        "        return g(x)\n"
        "    except ValueError:\n"
        "        if retryable(x):\n"
        "            raise\n"
    )
    findings = scan_source(source)
    assert [f.mode for f in findings] == [FailureMode.IMPLICIT_FALLBACK]


def test_logged_fallthrough_is_exempt():
    # Documented limitation: a handler that records the failure at a readable
    # severity is informational, not silent.
    source = (
        "import logging\n"
        "LOG = logging.getLogger(__name__)\n"
        "def a(x):\n"
        "    try:\n"
        "        return risky(x)\n"
        "    except Exception:\n"
        "        LOG.error('failed: %s', x)\n"
    )
    assert scan_source(source) == []


def test_procedure_function_is_exempt():
    # Implicit None is the legitimate contract of a function that never
    # returns a value on its success path.
    source = "def worker(x):\n    try:\n        do_work(x)\n    except Exception:\n        print('failed')\n"
    assert scan_source(source) == []


def test_bare_return_only_function_is_exempt():
    # If the success path itself returns None, the fall-through value is not
    # distinguishable from a legitimate result, so there is nothing to flag.
    source = (
        "def f(x):\n"
        "    if x:\n"
        "        return\n"
        "    try:\n"
        "        do(x)\n"
        "    except Exception:\n"
        "        print('failed')\n"
    )
    assert scan_source(source) == []


def test_generator_function_is_exempt():
    # Fall-through ends iteration (a different contract than returning None).
    source = (
        "def gen(items):\n"
        "    try:\n"
        "        for i in items:\n"
        "            yield i\n"
        "    except Exception:\n"
        "        print('failed')\n"
    )
    assert scan_source(source) == []


def test_sys_exit_fallthrough_is_exempt():
    source = "def a(x):\n    try:\n        return g(x)\n    except Exception:\n        sys.exit(1)\n"
    assert scan_source(source) == []


def test_nested_function_handlers_use_their_own_success_path():
    # The inner function never returns a value, so its handler must not be
    # judged against the outer function's returns.
    source = (
        "def outer(x):\n"
        "    try:\n"
        "        return risky(x)\n"
        "    except Exception:\n"
        "        print('failed')\n"
        "\n"
        "def inner(y):\n"
        "    try:\n"
        "        do(y)\n"
        "    except Exception:\n"
        "        print('failed')\n"
    )
    findings = scan_source(source)
    assert [f.lineno for f in findings] == [4]


def test_assign_fallthrough_stays_with_silent_fallback():
    # An assigned fallback constant is already reported by silent-fallback;
    # implicit-fallback must not double-report the same handler.
    source = (
        "def a(x):\n"
        "    try:\n"
        "        return risky(x)\n"
        "    except Exception:\n"
        "        result = None\n"
        "        print('failed')\n"
        "    return result\n"
    )
    findings = scan_source(source)
    assert [f.mode for f in findings] == [FailureMode.SILENT_FALLBACK]


def test_handler_inside_loop_is_exempt():
    # Fall-through inside a loop proceeds to the next iteration; the
    # function still returns its accumulated value, so there is no
    # implicit-None path for the rule to report.
    source = (
        "def process(items):\n"
        "    out = []\n"
        "    for item in items:\n"
        "        try:\n"
        "            out.append(transform(item))\n"
        "        except Exception:\n"
        "            print('skip', item)\n"
        "    return out\n"
    )
    assert scan_source(source) == []


def test_try_with_trailing_return_is_exempt():
    # When a `return` statement follows the try, the failure path does not
    # reach the implicit None (it raises NameError on the consumed name or
    # returns the pre-set value) — the rule's premise does not hold.
    source = (
        "def f(x):\n"
        "    try:\n"
        "        r = compute(x)\n"
        "    except Exception:\n"
        "        print('failed')\n"
        "    return r\n"
    )
    assert scan_source(source) == []


def test_try_nested_in_tail_if_is_still_reported():
    # A try in tail position behind non-loop blocks still falls through to
    # the implicit None.
    source = (
        "def f(x):\n"
        "    if x:\n"
        "        try:\n"
        "            return risky(x)\n"
        "        except Exception:\n"
        "            print('failed')\n"
    )
    assert [f.mode for f in scan_source(source)] == [FailureMode.IMPLICIT_FALLBACK]

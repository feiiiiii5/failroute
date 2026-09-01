"""Regression tests for the F1 precision fixes (F-① / F-② / F-③).

Written red-first on 2026-09-01: every ``would-be-red`` test below failed on
the v0.7.0 tree and passes after the corresponding fix in
``failroute.rules._shared``.  The negative controls are green on both sides —
they pin the *boundary* of each fix so a later over-broadening trips.

Defects (evidence in 06-开源与项目/failroute-arXiv-工作计划.md §1.6):

* **F-①** the control-flow ignore list never matched *tuple* handler types,
  so ``except (GeneratorExit, KeyboardInterrupt): pass`` was reported even
  though every member is on the ignore list.
* **F-②** ``warnings.warn(...)`` was not recognised as an error signal
  (``LOGGER_BASE_NAMES`` has no ``warnings``), so handlers that surface the
  failure through the stdlib warning channel were reported as silent.
* **F-③** ``StopAsyncIteration`` was missing from ``IGNORED_EXC_NAMES``
  (its sync twin ``StopIteration`` and ``GeneratorExit`` were present).
"""

from __future__ import annotations

from failroute.analyzer import scan_source
from failroute.rules._shared import IGNORED_EXC_NAMES, is_ignored_handler


# ---------------------------------------------------------------------------
# F-① tuple-typed handlers honour the ignore list
# ---------------------------------------------------------------------------

def test_f1_tuple_of_ignored_names_is_not_reported():
    source = (
        "def pump():\n"
        "    while True:\n"
        "        try:\n"
        "            step()\n"
        "        except (GeneratorExit, KeyboardInterrupt):\n"
        "            pass\n"
    )
    assert scan_source(source) == []


def test_f1_tuple_of_ignored_names_returning_fallback_is_not_reported():
    source = (
        "def drain(it):\n"
        "    try:\n"
        "        return it.send(None)\n"
        "    except (GeneratorExit, SystemExit):\n"
        "        return None\n"
    )
    assert scan_source(source) == []


def test_f1_tuple_with_attribute_names_is_not_reported():
    source = (
        "import asyncio\n"
        "async def run(coro):\n"
        "    try:\n"
        "        return await coro\n"
        "    except (asyncio.CancelledError, GeneratorExit):\n"
        "        return None\n"
    )
    assert scan_source(source) == []


def test_f1_mixed_tuple_stays_reported():
    # Conservative boundary: one non-ignored member means real errors can be
    # swallowed, so the finding stands.
    source = (
        "def pump():\n"
        "    while True:\n"
        "        try:\n"
        "            step()\n"
        "        except (StopIteration, ValueError):\n"
        "            pass\n"
    )
    assert [f.rule_id for f in scan_source(source)] == ["no-action"]


def test_f1_ignored_tuple_in_tail_position_is_not_implicit_fallback():
    source = (
        "def fetch(key):\n"
        "    try:\n"
        "        return load(key)\n"
        "    except (GeneratorExit, KeyboardInterrupt):\n"
        "        cleanup()\n"
    )
    assert scan_source(source) == []


# ---------------------------------------------------------------------------
# F-② warnings.warn is an error signal
# ---------------------------------------------------------------------------

def test_f2_warnings_warn_in_typed_handler_is_not_silent():
    source = (
        "import warnings\n"
        "def probe(x):\n"
        "    try:\n"
        "        return check(x)\n"
        "    except ValueError:\n"
        "        warnings.warn('check failed, assuming absent')\n"
        "        return False\n"
    )
    assert scan_source(source) == []


def test_f2_warnings_warn_in_catch_all_handler_is_not_silent():
    source = (
        "import warnings\n"
        "def probe(x):\n"
        "    try:\n"
        "        return check(x)\n"
        "    except Exception:\n"
        "        warnings.warn('check failed, assuming absent')\n"
        "        return False\n"
    )
    assert scan_source(source) == []


def test_f2_warnings_simplefilter_is_not_a_signal():
    # Boundary: only the warn/warn_explicit entry points surface a failure;
    # configuring the filter machinery records nothing routable.
    source = (
        "import warnings\n"
        "def probe(x):\n"
        "    try:\n"
        "        return check(x)\n"
        "    except ValueError:\n"
        "        warnings.simplefilter('ignore')\n"
        "        return False\n"
    )
    assert [f.rule_id for f in scan_source(source)] == ["silent-fallback"]


# ---------------------------------------------------------------------------
# F-③ StopAsyncIteration joins the control-flow ignore list
# ---------------------------------------------------------------------------

def test_f3_stop_async_iteration_in_ignore_list():
    assert "StopAsyncIteration" in IGNORED_EXC_NAMES


def test_f3_stop_async_iteration_pass_is_not_reported():
    source = (
        "async def drain(ait):\n"
        "    while True:\n"
        "        try:\n"
        "            await ait.__anext__()\n"
        "        except StopAsyncIteration:\n"
        "            pass\n"
    )
    assert scan_source(source) == []


def test_f3_stop_async_iteration_fallback_is_not_reported():
    source = (
        "async def next_or_none(ait):\n"
        "    try:\n"
        "        return await ait.__anext__()\n"
        "    except StopAsyncIteration:\n"
        "        return None\n"
    )
    assert scan_source(source) == []


def test_f3_suppress_stop_async_iteration_is_not_reported():
    source = (
        "from contextlib import suppress\n"
        "async def close(ait):\n"
        "    with suppress(StopAsyncIteration):\n"
        "        await ait.__anext__()\n"
    )
    assert scan_source(source) == []


def test_f3_stop_iteration_still_ignored():
    # Guard: the sync twin's exemption is unchanged by the F-③ addition.
    source = (
        "def drain(it):\n"
        "    while True:\n"
        "        try:\n"
        "            next(it)\n"
        "        except StopIteration:\n"
        "            pass\n"
    )
    assert scan_source(source) == []


# ---------------------------------------------------------------------------
# is_ignored_handler unit checks (the shared predicate behind all rules)
# ---------------------------------------------------------------------------

def _handler_of(source: str):
    import ast

    tree = ast.parse(source)
    return next(n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler))


def test_f1_is_ignored_handler_tuple_all_ignored():
    h = _handler_of("try:\n    x()\nexcept (GeneratorExit, StopIteration):\n    pass\n")
    assert is_ignored_handler(h)


def test_f1_is_ignored_handler_tuple_mixed():
    h = _handler_of("try:\n    x()\nexcept (GeneratorExit, ValueError):\n    pass\n")
    assert not is_ignored_handler(h)

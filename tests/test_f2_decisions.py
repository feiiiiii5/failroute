"""Regression tests for the F2 design decisions (F-④ / F-⑤).

* **F-④ / ADR-0001** — ``except ImportError`` optional-dependency probes are
  contracts, not findings, but only under a three-part predicate: the handler
  catches ImportError-family names *only*, the guarded block is an
  import/setup block, and the handler body is a minimal capability fallback.
* **F-⑤ / ADR-0002** — ``with suppress(...)`` nested inside a handler that
  re-raises at top level is best-effort cleanup, not failure routing.

Every exemption boundary has a paired keep-reporting test: the conservative
prior is that over-broad exemptions cost more than extra findings.
"""

from __future__ import annotations

from failroute.analyzer import scan_source


# ---------------------------------------------------------------------------
# F-④ optional-dependency probes are contracts
# ---------------------------------------------------------------------------

def test_f4_single_import_probe_pass_is_contract():
    source = (
        "def setup():\n"
        "    try:\n"
        "        import rich\n"
        "    except ImportError:\n"
        "        pass\n"
    )
    assert scan_source(source) == []


def test_f4_probe_returning_constant_is_contract():
    source = (
        "def is_below(version):\n"
        "    try:\n"
        "        import importlib.metadata\n"
        "    except ModuleNotFoundError:\n"
        "        return False\n"
    )
    assert scan_source(source) == []


def test_f4_capability_flag_bindings_are_contract():
    source = (
        "try:\n"
        "    import py7zr\n"
        "    HAS_7Z = True\n"
        "except ImportError:\n"
        "    HAS_7Z = False\n"
    )
    assert scan_source(source) == []


def test_f4_probe_in_function_returning_real_value_is_contract():
    # Regression against the implicit-fallback shape: probe handler in tail
    # position of a function whose success path returns real values.
    source = (
        "def backend():\n"
        "    try:\n"
        "        import uvloop\n"
        "    except ImportError:\n"
        "        return 'default'\n"
        "    return uvloop\n"
    )
    assert [f.rule_id for f in scan_source(source)] == []


def test_f4_mixed_tuple_stays_reported():
    source = (
        "def setup():\n"
        "    try:\n"
        "        import rich\n"
        "    except (ImportError, ValueError):\n"
        "        pass\n"
    )
    assert [f.rule_id for f in scan_source(source)] == ["no-action"]


def test_f4_guarded_body_with_side_effects_stays_reported():
    # A call in the guarded block means the ImportError handler may mask more
    # than an absent dependency.
    source = (
        "def setup():\n"
        "    try:\n"
        "        import rich\n"
        "        configure(rich)\n"
        "    except ImportError:\n"
        "        pass\n"
    )
    assert [f.rule_id for f in scan_source(source)] == ["no-action"]


def test_f4_non_minimal_handler_stays_reported():
    source = (
        "def setup():\n"
        "    try:\n"
        "        import rich\n"
        "    except ImportError:\n"
        "        install_alternative()\n"
        "        return None\n"
    )
    assert [f.rule_id for f in scan_source(source)] == ["silent-fallback"]


def test_f4_no_import_in_guarded_body_stays_reported():
    source = (
        "def setup():\n"
        "    try:\n"
        "        configure()\n"
        "    except ImportError:\n"
        "        pass\n"
    )
    assert [f.rule_id for f in scan_source(source)] == ["no-action"]


# ---------------------------------------------------------------------------
# F-⑤ suppress inside a re-raising handler is cleanup
# ---------------------------------------------------------------------------

def test_f5_suppress_in_reraising_handler_is_exempt():
    source = (
        "from contextlib import suppress\n"
        "def drive(task):\n"
        "    try:\n"
        "        run(task)\n"
        "    except BaseException:\n"
        "        with suppress(BaseException):\n"
        "            task.exception()\n"
        "        raise\n"
    )
    assert scan_source(source) == []


def test_f5_suppress_in_non_reraising_handler_stays_reported():
    source = (
        "from contextlib import suppress\n"
        "def drive(task):\n"
        "    try:\n"
        "        run(task)\n"
        "    except BaseException:\n"
        "        with suppress(BaseException):\n"
        "            task.exception()\n"
    )
    assert [f.rule_id for f in scan_source(source)] == ["silent-suppress"]


def test_f5_conditional_raise_does_not_exempt():
    # A branch-conditional raise may never execute; keep reporting.
    source = (
        "from contextlib import suppress\n"
        "def drive(task, strict):\n"
        "    try:\n"
        "        run(task)\n"
        "    except BaseException:\n"
        "        with suppress(BaseException):\n"
        "            task.exception()\n"
        "        if strict:\n"
        "            raise\n"
    )
    assert [f.rule_id for f in scan_source(source)] == ["silent-suppress"]


def test_f5_suppress_in_callback_inside_reraising_handler_stays_reported():
    # The callback may run after the handler finished; the raise no longer
    # covers it.
    source = (
        "from contextlib import suppress\n"
        "def drive(task):\n"
        "    try:\n"
        "        run(task)\n"
        "    except BaseException:\n"
        "        def late():\n"
        "            with suppress(BaseException):\n"
        "                task.exception()\n"
        "        schedule(late)\n"
        "        raise\n"
    )
    assert [f.rule_id for f in scan_source(source)] == ["silent-suppress"]


def test_f5_suppress_outside_any_handler_stays_reported():
    source = (
        "from contextlib import suppress\n"
        "def close(handle):\n"
        "    with suppress(OSError):\n"
        "        handle.close()\n"
    )
    assert [f.rule_id for f in scan_source(source)] == ["silent-suppress"]

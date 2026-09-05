"""covered_by must equal what the linters actually do, not what their names suggest.

V1 credited ``bandit:B110`` and ``ruff:S110`` to every empty-bodied handler regardless
of the caught type. Both rules are broad-only, so the inference over-credited the
linters on 145 corpus findings and pushed the paper's static novelty figure down to
18.3% when the measured figure is 47.7%. V2 caught it on one witness file; V3 measured
the whole mapping (``tools/lint_mapping_probe.py``) and found a second, independent
condition that had also been missed: S110/B110 are literally "try-except-**pass**" and
do not fire on a body of ``...``, which this detector's own ``body_empty`` accepts.

These tests pin the measured conditions. They go through ``handler_facts_for`` rather
than calling ``covered_by_for`` directly, so they exercise the production path that
derives ``body_empty`` and ``dead_probe`` too -- a fix that gated the rules correctly
but read the wrong body flag would still fail here.
"""

from __future__ import annotations

import ast

import pytest

from failroute.rules._shared import handler_facts_for

BARE_ONLY = {"flake8:E722", "ruff:E722", "bugbear:B001", "pylint:W0702"}
CATCH_ALL_ONLY = {"ruff:BLE001", "pylint:W0718"}
DEAD_PROBE = {"bugbear:B015", "ruff:B015"}


def covered_by(source: str) -> set[str]:
    """The ``covered_by`` the production path computes for a source with one handler."""
    tree = ast.parse(source)
    facts = handler_facts_for(tree)
    handlers = [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)]
    assert len(handlers) == 1, "probe source must contain exactly one except handler"
    return set(facts[id(handlers[0])].covered_by)


PRELUDE = (
    "import asyncio\n"
    "import builtins\n"
    "import contextlib\n"
    "\n"
    "\n"
    "def make_exc():\n"
    "    return ValueError\n"
    "\n"
    "\n"
)


def handler(exc: str, body: str, *, loop: bool = False) -> str:
    """Build a one-handler module. ``loop`` wraps it, since ``continue`` needs one."""
    clause = f"except {exc}:" if exc else "except:"
    if loop:
        return PRELUDE + (
            "def probe():\n"
            "    for _ in range(3):\n"
            "        try:\n"
            "            f()\n"
            f"        {clause}\n"
            f"            {body}\n"
        )
    return PRELUDE + (
        "def probe():\n"
        "    out = None\n"
        "    try:\n"
        "        f()\n"
        f"    {clause}\n"
        f"        {body}\n"
        "    return out\n"
    )


# --- the caught-type axis, on a `pass` body ------------------------------------

@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        # bare: the bare-except rules plus both pass-body rules
        ("", BARE_ONLY | {"ruff:S110", "bandit:B110"}),
        # exactly `Exception`: catch-all rules plus BOTH pass-body rules
        ("Exception", CATCH_ALL_ONLY | {"ruff:S110", "bandit:B110"}),
        # 🔴 BaseException: ruff's S110 fires, bandit's B110 does NOT. Crediting both
        # from one "broad" predicate is the mistake the V3 task list would have repeated.
        ("BaseException", CATCH_ALL_ONLY | {"ruff:S110"}),
        # 🔴 mixed tuple: same split -- S110 yes, B110 no
        ("(Exception, ValueError)", CATCH_ALL_ONLY | {"ruff:S110"}),
        # narrow: nothing at all
        ("ValueError", set()),
        # the V2 witness shape, verbatim
        ("(ValueError, TypeError)", set()),
    ],
)
def test_pass_body_is_gated_on_caught_type(exc: str, expected: set[str]) -> None:
    assert covered_by(handler(exc, "pass")) == expected


@pytest.mark.parametrize("exc", ["", "Exception", "BaseException", "(Exception, ValueError)",
                                 "ValueError", "(ValueError, TypeError)"])
def test_ellipsis_body_never_gets_the_pass_rules(exc: str) -> None:
    """`except X: ...` is an empty body to this detector but not a `pass` to S110/B110."""
    got = covered_by(handler(exc, "..."))
    assert "ruff:S110" not in got
    assert "bandit:B110" not in got
    # the caught-type rules are body-agnostic and must survive
    if exc == "":
        assert BARE_ONLY <= got
    elif "Exception" in exc:
        assert CATCH_ALL_ONLY <= got
    else:
        assert got == set()


# --- the body axis, on a broad handler -----------------------------------------

@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        ("", BARE_ONLY | {"ruff:S112", "bandit:B112"}),
        ("Exception", CATCH_ALL_ONLY | {"ruff:S112", "bandit:B112"}),
        ("BaseException", CATCH_ALL_ONLY | {"ruff:S112"}),
        ("(Exception, ValueError)", CATCH_ALL_ONLY | {"ruff:S112"}),
    ],
)
def test_continue_body_is_gated_the_same_way(exc: str, expected: set[str]) -> None:
    assert covered_by(handler(exc, "continue", loop=True)) == expected


@pytest.mark.parametrize("body", ["return None", "out = None"])
@pytest.mark.parametrize("exc", ["", "Exception", "ValueError"])
def test_non_inert_bodies_get_only_the_caught_type_rules(exc: str, body: str) -> None:
    """A returned or assigned constant is not a pass/continue body, so no S1xx/B11x."""
    got = covered_by(handler(exc, body))
    assert not (got & {"ruff:S110", "bandit:B110", "ruff:S112", "bandit:B112"})
    if exc == "":
        assert got == BARE_ONLY
    elif exc == "Exception":
        assert got == CATCH_ALL_ONLY
    else:
        assert got == set()


# --- the discarded-comparison axis is kind-agnostic -----------------------------

@pytest.mark.parametrize("exc", ["", "Exception", "ValueError", "(ValueError, TypeError)"])
def test_dead_probe_credits_b015_at_every_caught_type(exc: str) -> None:
    """B015 points at the discarded comparison in the guarded block, not the handler."""
    clause = f"except {exc}:" if exc else "except:"
    src = (
        "def probe():\n"
        "    a = 1\n"
        "    out = False\n"
        "    try:\n"
        "        a == 1\n"
        f"    {clause}\n"
        "        out = False\n"
        "    return out\n"
    )
    assert DEAD_PROBE <= covered_by(src)


# --- Q2: the reverse proof ------------------------------------------------------

def test_reversing_narrow_to_broad_must_restore_the_credit() -> None:
    """The gate has to cut both ways, or it proves nothing.

    Same body, same everything else: a narrow handler gets no pass-body credit, and
    widening it to bare must bring both rules back. A fix implemented by deleting the
    credit outright would pass the narrow assertion and fail this one.
    """
    narrow = covered_by(handler("(ValueError, TypeError)", "pass"))
    bare = covered_by(handler("", "pass"))
    assert narrow == set()
    assert {"ruff:S110", "bandit:B110"} <= bare
    # and widening only as far as `Exception` restores bandit, but not further than that
    exc = covered_by(handler("Exception", "pass"))
    base = covered_by(handler("BaseException", "pass"))
    assert "bandit:B110" in exc
    assert "bandit:B110" not in base
    assert "ruff:S110" in base


# --- propagation: the facts must reach the emitted finding ----------------------

def test_finding_carries_the_gated_covered_by() -> None:
    """handler_facts_for is not the deliverable; the Finding is.

    A rule that computed the facts correctly and then dropped or widened covered_by on
    the way out would pass every test above, so check the emitted findings too: two
    handlers in one module, one bare and one narrow, both inert.
    """
    from failroute.analyzer import scan_source

    src = (
        "def bare_one():\n"
        "    try:\n"
        "        f()\n"
        "    except:\n"
        "        pass\n"
        "\n"
        "\n"
        "def narrow_one():\n"
        "    try:\n"
        "        f()\n"
        "    except (ValueError, TypeError):\n"
        "        pass\n"
    )
    findings = scan_source(src)
    by_name: dict[str, set[str]] = {"bare_one": set(), "narrow_one": set()}
    counts: dict[str, int] = {"bare_one": 0, "narrow_one": 0}
    lines = src.splitlines()
    for finding in findings:
        # attribute by which function the finding's line falls inside
        for name in by_name:
            start = lines.index(f"def {name}():") + 1
            if start <= finding.lineno <= start + 5:
                by_name[name] |= set(finding.covered_by or ())
                counts[name] += 1
    # Both handlers must actually be reported, otherwise an empty covered_by on the
    # narrow one would prove nothing: it could be an absent finding rather than an
    # absent credit.
    assert counts["bare_one"] >= 1, "the bare handler was not reported at all"
    assert counts["narrow_one"] >= 1, "the narrow handler was not reported at all"
    assert {"ruff:S110", "bandit:B110"} <= by_name["bare_one"]
    assert by_name["narrow_one"] == set()


# --- catch-all credit must survive members the resolver cannot read --------------

@pytest.mark.parametrize(
    "exc",
    [
        "(make_exc(), Exception)",                 # unresolvable member + plain Exception
        "builtins.Exception",                      # attribute-qualified
        "(Exception, asyncio.CancelledError)",     # dotted sibling
    ],
)
def test_catch_all_credit_survives_unresolvable_and_dotted_members(exc: str) -> None:
    """``except (anyio.get_cancelled_exc_class(), Exception):`` occurs 3x in the corpus.

    The member-name helper this used to delegate to returns ``None`` as soon as one
    member is not statically resolvable, which classified the whole handler as narrow
    and dropped its BLE001/W0718/S110 credit. That under-credits the linters and so
    over-states novelty -- the same direction of error as the bug being fixed, with the
    opposite sign. The probe measures that all three rules do fire on this shape.
    """
    got = covered_by(handler(exc, "pass"))
    assert got == CATCH_ALL_ONLY | {"ruff:S110"}
    # bandit is narrower still: it needs a literal `except Exception:`, so a dotted or
    # tuple-qualified Exception must not earn B110
    assert "bandit:B110" not in got


def test_continue_body_with_an_unresolvable_member() -> None:
    got = covered_by(handler("(make_exc(), Exception)", "continue", loop=True))
    assert got == CATCH_ALL_ONLY | {"ruff:S112"}
    assert "bandit:B112" not in got


@pytest.mark.parametrize(
    "exc",
    [
        "asyncio.CancelledError",   # dotted, and not Exception
        "make_exc()",               # a call expression: not statically resolvable at all
        "JsonPointerException",     # a Name that merely ends in "Exception"
    ],
)
def test_forms_that_are_genuinely_narrow_stay_narrow(exc: str) -> None:
    """The fix must not widen into a false catch-all: these three fire nothing."""
    assert covered_by(handler(exc, "pass")) == set()


# --- rules measured and deliberately NOT credited -------------------------------

def test_sim105_is_not_credited() -> None:
    """ruff SIM105 fires on every handler kind with a pass or ellipsis body.

    It is deliberately absent from the tables: it is not in the paper's baseline rule
    selection, and its advice is "rewrite this as contextlib.suppress" -- the very
    rewrite that moves the shape out of every linter's reach. Crediting it would claim
    a rule covers a handler when the rule's recommendation is to make it uncoverable.
    This test exists so that adding it is a deliberate act with a failing test to read.
    """
    for exc in ("", "Exception", "ValueError", "(ValueError, TypeError)"):
        for body in ("pass", "..."):
            assert "ruff:SIM105" not in covered_by(handler(exc, body))

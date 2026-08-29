"""Corpus fixture: v0.6 detector shapes added with the registry refactor.

Ground truth is encoded in tests/corpus/manifest.json. Every ``except`` block
and ``with suppress(...)`` statement in this file is labelled: FLAGGED
entries are expected findings, CLEAN entries must produce zero findings.
Line numbers matter -- keep manifest.json in sync when editing.
"""

from contextlib import suppress
from contextlib import suppress as ignore_errors

from myapp.errors import suppress as framework_suppress


def numeric_sentinel_unconfigured(x):
    # CLEAN: project-specific sentinels (-1) require [tool.failroute]
    # fallback_values; the built-in whitelist does not guess them
    try:
        return compute_rank(x)
    except Exception:
        return -1


def enum_member_is_not_a_constant(x):
    # CLEAN: attribute values (Status.UNKNOWN) are not constant shapes
    try:
        return check_status(x)
    except Exception:
        return Status.UNKNOWN


def int_one_is_an_ambiguous_fallback(x):
    # FLAGGED silent-fallback: 1/1.0 are documented ambiguous fallback hints
    # (the v0.5 renderer never produced these tokens, so the entries were dead)
    try:
        return score(x)
    except Exception:
        return 1


def with_item_shadowing(context):
    # FLAGGED name-shadowing: the with-item rebinds the caught name. The
    # enclosing function returns nothing, so no implicit-fallback applies.
    try:
        render(context)
    except ValueError as e:
        with open("render.log", "w") as e:
            e.write("render failed")


def match_case_masked(x):
    # FLAGGED masked-exception: match/case conditional raise plus fallback
    # return (v0.5 classified this silent-fallback)
    try:
        return g(x)
    except Exception as e:
        match e:
            case ValueError():
                raise
            case _:
                pass
        return 0.0


def multi_type_suppress():
    # FLAGGED silent-suppress: several silenced types share one statement
    with suppress(Exception, OSError):
        result = judge(prompt)


def aliased_suppress_import():
    # FLAGGED silent-suppress: the import alias resolves to contextlib.suppress
    with ignore_errors(Exception):
        result = judge(prompt)


def dotted_module_suppress():
    # FLAGGED silent-suppress: ``import contextlib as cl`` resolves through
    # the alias table
    import contextlib as cl

    with cl.suppress(Exception):
        result = judge(prompt)


def framework_suppress_is_not_contextlib():
    # CLEAN: same name, different origin -- the import resolves outside
    # contextlib, so the heuristic does not guess
    with framework_suppress(Exception):
        result = judge(prompt)


def exit_call_is_terminal(x):
    # CLEAN: os._exit terminates like a raise
    try:
        return main_op(x)
    except Exception:
        os._exit(1)


def different_name_rebind_is_fine():
    # CLEAN: rebinding a name other than the caught one is ordinary code
    try:
        return render(context)
    except ValueError as e:
        out = f"render failed: {e}"
        return out


def empty_string_fallback(x):
    # FLAGGED silent-fallback: an empty string is a built-in fallback shape
    try:
        return render_name(x)
    except Exception:
        return ""


def empty_tuple_fallback(x):
    # FLAGGED silent-fallback: an empty tuple is a built-in fallback shape
    try:
        return coordinates(x)
    except Exception:
        return ()


def named_sentinel_is_not_a_constant(x):
    # CLEAN: TIMEOUT_SENTINEL is a name, not a constant literal
    try:
        return poll_status(x)
    except TimeoutError:
        return TIMEOUT_SENTINEL


async def async_suppress():
    # FLAGGED silent-suppress: the async-with form routes to silence too
    async with suppress(Exception):
        await judge(prompt)


def bare_except_no_type():
    # FLAGGED no-action: bare except is the widest catch-all
    try:
        step()
    except:
        pass


def loop_shadow_in_procedure(items):
    # FLAGGED name-shadowing: the loop target rebinds the caught name; the
    # enclosing function returns nothing, so no implicit-fallback applies
    try:
        drain(queue)
    except Exception as e:
        for e in items:
            process(e)


def generator_exit_suppress_is_idiomatic():
    # CLEAN: suppressing GeneratorExit is control-flow, not failure routing
    with suppress(GeneratorExit):
        stream_close()

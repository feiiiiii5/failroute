"""Corpus fixture: implicit-fallback handlers (the v0.6 blind-spot detector).

Ground truth is encoded in tests/corpus/manifest.json. Every ``except`` block
in this file is labelled: FLAGGED entries are expected findings, CLEAN
entries must produce zero findings. Line numbers matter -- keep
manifest.json in sync when editing.
"""

from __future__ import annotations


def telemetry_fallthrough(x):
    # FLAGGED implicit-fallback: bare call records nothing, no re-raise
    try:
        return compute_rank(x)
    except Exception:
        print("ranking failed")


def conditional_raise_fallthrough(x):
    # FLAGGED implicit-fallback: the raise is conditional; the other branch
    # falls through to the implicit None
    try:
        return classify(x)
    except ValueError:
        if retryable(x):
            raise


def debug_only_fallthrough(x):
    # FLAGGED implicit-fallback: logger.debug does not qualify as recording
    try:
        return fetch_view(x)
    except Exception:
        logger.debug("fetch failed")


def docstring_only_handler(x):
    # FLAGGED implicit-fallback: a bare docstring records nothing
    try:
        return load_profile(x)
    except Exception:
        """TODO: handle this later."""


async def async_fallthrough(x):
    # FLAGGED implicit-fallback: async functions fall through the same way
    try:
        return await fetch_page(x)
    except Exception:
        print("page fetch failed")


def nested_try_fallthrough(x):
    # FLAGGED implicit-fallback (outer handler): the inner handler absorbs the
    # inner failure, the outer handler absorbs everything else. The inner
    # empty handler is separately flagged as no-action.
    try:
        return persist(x)
    except Exception:
        try:
            save_locally(x)
        except Exception:
            pass


def counter_bump_fallthrough(x):
    # FLAGGED implicit-fallback: an augmented-assignment counter is not a
    # fresh binding and reports nowhere else
    try:
        return resolve_status(x)
    except Exception:
        counters["failed"] += 1


def procedure_contract(x):
    # CLEAN: the function never returns a value; implicit None is the contract
    try:
        do_work(x)
    except Exception:
        print("work failed")


def generator_contract(items):
    # CLEAN: fall-through ends iteration, a different contract than None
    try:
        for item in items:
            yield item
    except Exception:
        print("iteration failed")


def logged_fallthrough_is_documented_limitation(x):
    # CLEAN (documented limitation): the failure is recorded at a readable
    # severity, so the handler is informational
    try:
        return fetch_view(x)
    except Exception:
        logger.error("fetch failed")


def typed_info_log_is_enough(x):
    # CLEAN: a typed handler records the failure at any level
    try:
        return lookup(x)
    except KeyError:
        logger.info("expected miss")


def bare_return_contract(x):
    # CLEAN: the success path itself returns None, so the fall-through is not
    # distinguishable from a legitimate result
    if x is None:
        return
    try:
        do(x)
    except Exception:
        print("failed")


def explicit_exit(x):
    # CLEAN: the handler terminates the process; no caller observes a value
    try:
        return main_op(x)
    except Exception:
        sys.exit(1)


def explicit_return_beats_fallthrough(x):
    # FLAGGED silent-fallback: an explicit fallback return is that rule's
    # shape, not implicit-fallback's
    try:
        return compute(x)
    except Exception:
        return None


def loop_skip_contract(items):
    # CLEAN: `continue` ends the handler's control flow inside the loop; the
    # skip-and-continue pattern is deliberate control flow, not a fall-through
    # to the function's implicit None
    out = []
    for item in items:
        try:
            out.append(transform(item))
        except Exception:
            continue
    return out


def retry_break_contract(cmd):
    # CLEAN: `break` leaves the retry loop deliberately and the explicit
    # trailing return owns the outcome
    for attempt in range(3):
        try:
            return run(cmd)
        except TimeoutError:
            break
    return None

"""Corpus fixture: ``contextlib.suppress`` silent-swallow forms (positives) and traps (negatives).

``with contextlib.suppress(...)`` is semantically identical to wrapping the body
in ``try`` / ``except`` and discarding the matched exceptions: the failure is
routed to silence and the caller can never learn the operation failed.
Ground truth is encoded in tests/corpus/manifest.json. Every ``with``/``async
with`` suppress statement in this file is labelled: FLAGGED entries are
expected findings, CLEAN entries must produce zero findings. Line numbers
matter -- keep manifest.json in sync when editing.
"""

from __future__ import annotations

import contextlib
from contextlib import suppress
from contextlib import suppress as swallow_errors

from helpers import suppress as impostor_suppress  # not contextlib -- must NOT be flagged


def suppress_catch_all():
    # FLAGGED silent-suppress (line of the `with` keyword)
    with contextlib.suppress(Exception):
        score = judge(prompt)
    return score


def suppress_typed():
    # FLAGGED silent-suppress: discarding a named failure is the same routing
    # decision as `except FileNotFoundError: pass`, which is already flagged
    with suppress(FileNotFoundError):
        os.remove(cache_path)


async def suppress_async():
    # FLAGGED silent-suppress
    async with contextlib.suppress(ValueError):
        await publish_result(0.0)


def suppress_aliased_import():
    # FLAGGED silent-suppress: aliasing does not change the semantics
    with swallow_errors(KeyError):
        return lookup(metric_name)


def suppress_multiline_body():
    # FLAGGED silent-suppress: body shape is irrelevant, the failure is routed
    # to silence either way
    with suppress(OSError):
        stream = open(path)
        stream.read()
        stream.close()


def suppress_with_ignore_marker():
    # CLEAN: reviewed-and-accepted via the explicit registration mechanism
    with suppress(FileNotFoundError):  # failroute: ignore - documented best-effort cleanup
        os.remove(cache_path)


def non_suppress_context_manager():
    # CLEAN: closing() does not swallow anything
    with contextlib.closing(open(path)) as stream:
        return stream.read()


def name_collides_but_not_contextlib():
    # CLEAN: this `suppress` comes from helpers, not contextlib
    with impostor_suppress(ValueError):
        return lookup(metric_name)


def suppress_used_as_value_is_untouched():
    # CLEAN: merely importing or passing around suppress routes nothing
    ctx_factory = contextlib.suppress
    return ctx_factory

"""Corpus fixture: no-action handlers (positive samples) and traps (negatives).

Ground truth is encoded in tests/corpus/manifest.json. Every ``except`` block
in this file is labelled: FLAGGED blocks are expected findings, CLEAN blocks
must produce zero findings. Line numbers matter -- keep manifest.json in sync
when editing.
"""

from __future__ import annotations


def swallow_pass():
    # FLAGGED no-action
    try:
        return fetch_metrics()
    except Exception:
        pass


def swallow_ellipsis():
    # FLAGGED no-action
    try:
        return fetch_metrics()
    except ValueError:
        ...


def swallow_comment_only():
    # FLAGGED no-action (comment-only body parses to Pass)
    try:
        return fetch_metrics()
    except KeyError:
        # TODO: handle later
        pass


def propagate_healthy():
    # CLEAN: unconditional bare re-raise, failure propagates to the caller
    try:
        return fetch_metrics()
    except Exception:
        raise


def propagate_typed_healthy():
    # CLEAN: re-raise wrapped as a domain error is still propagation
    try:
        return fetch_metrics()
    except ValueError as exc:
        raise RuntimeError("metrics unavailable") from exc


def interrupt_swallow_is_noise():
    # CLEAN: KeyboardInterrupt handlers are informational by design
    try:
        return fetch_metrics()
    except KeyboardInterrupt:
        pass

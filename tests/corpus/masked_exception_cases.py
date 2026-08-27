"""Corpus fixture: masked-exception handlers and opt-out marker handling.

Ground truth in tests/corpus/manifest.json. FLAGGED = expected finding,
CLEAN = must produce zero findings.
"""

from __future__ import annotations


def branch_dependent_outcome():
    # FLAGGED masked-exception: retryable errors propagate, everything else
    # silently becomes 0.0 -- the outcome depends on which branch ran
    try:
        return llm_judge(prompt)
    except Exception as exc:
        if isinstance(exc, TimeoutError):
            raise
        return 0.0


def reviewed_and_accepted():
    # CLEAN: explicit opt-out marker documents an accepted fallback
    try:
        return best_effort_cache(key)
    except Exception:  # failroute: ignore - documented fallback semantics
        return None


def defensive_pragma():
    # CLEAN: pragma: no cover marks explicitly defensive code
    try:
        return load_config(path)
    except Exception:  # pragma: no cover
        return {}


def loop_conditional_raise_with_fallback():
    # FLAGGED masked-exception: raise lives inside a loop in the handler,
    # constant fallback after the loop -- outcome depends on the branch
    try:
        score_batch(batch)
    except Exception:
        for attempt in retries:
            if attempt.is_fatal:
                raise
        return 0.0

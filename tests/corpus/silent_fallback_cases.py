"""Corpus fixture: silent-fallback handlers (positive samples) and traps.

Ground truth in tests/corpus/manifest.json. FLAGGED = expected finding,
CLEAN = must produce zero findings.
"""

from __future__ import annotations


def judge_score_outage():
    # FLAGGED silent-fallback: an LLM judge outage becomes a "0.0 score"
    try:
        return llm_judge(prompt)
    except Exception:
        return 0.0


def optional_metadata():
    # FLAGGED silent-fallback: parse failure indistinguishable from empty metadata
    try:
        return parse_metadata(blob)
    except ValueError:
        return None


def search_results():
    # FLAGGED silent-fallback: backend error indistinguishable from zero results
    try:
        return query_index(q)
    except Exception:
        return []


def buffered_download():
    # FLAGGED silent-fallback (assign variant): error looks like an empty buffer
    data = []
    try:
        data = download(url)
    except OSError:
        data = []
    return data


def bool_gate():
    # FLAGGED silent-fallback: outage reads as a legitimate True from the gate
    try:
        return check_policy(req)
    except Exception:
        return True


def derived_error_value():
    # CLEAN: the returned value is derived from the exception, not a constant
    try:
        return parse_metadata(blob)
    except ValueError as exc:
        return f"unparseable: {exc}"


def logged_fallback_is_documented_limitation():
    # CLEAN (documented limitation): handlers that log are treated as
    # informational even when they also fall back to a constant.
    try:
        return llm_judge(prompt)
    except Exception:
        logger.warning("judge unavailable")
        return 0.0


def dead_return_after_raise():
    # CLEAN: the fallback return is unreachable after an unconditional raise
    try:
        return llm_judge(prompt)
    except Exception:
        raise
        return 0.0


def non_empty_container_is_not_a_fallback():
    # CLEAN (current semantics): only empty/zero constants are fallback shapes
    try:
        return query_index(q)
    except Exception:
        return {"items": [], "error": True}

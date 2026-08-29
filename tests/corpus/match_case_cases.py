"""Corpus fixture: ``match``/``case`` handler shapes -- **requires Python 3.10+** (PEP 634).

On interpreters older than 3.10 this file cannot be parsed at all.
``tools/benchmark.py`` reports such a file as a *skipped* corpus file and
excludes its labels from precision/recall, instead of counting them as false
negatives. CI runs the corpus on 3.9-3.13, and a dedicated assertion checks
that nothing is skipped on 3.10+, so this file's labels are always enforced
somewhere in the matrix.
"""


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


def match_case_healthy(x):
    # CLEAN: every arm propagates or records the failure; nothing is routed to
    # a success-looking value
    try:
        return g(x)
    except Exception as e:
        match e:
            case ValueError():
                raise
            case _:
                logger.error("unmapped failure: %s", e)
                raise

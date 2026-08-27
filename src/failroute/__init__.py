"""failroute — static detection of failure-routing anti-patterns in Python.

Failure-routing is the practice of converting an underlying failure into a
*success-like* outcome at the wrong layer: swallowing an exception and
returning a default truthy/"no error" value, transforming a metric failure
into a 0.0/False score, or logging-and-continuing where the caller is
contractually entitled to know the operation failed.

This module implements an AST-based scanner that flags those patterns, so
tests / CI can treat them like the correctness bugs they are.
"""

from failroute.analyzer import FailureMode, Finding, scan_path, scan_repo, scan_source
from failroute.cli import main
from failroute.sarif import to_sarif, to_sarif_json

__all__ = [
    "FailureMode",
    "Finding",
    "scan_source",
    "scan_path",
    "scan_repo",
    "main",
    "to_sarif",
    "to_sarif_json",
]
__version__ = "0.4.0"

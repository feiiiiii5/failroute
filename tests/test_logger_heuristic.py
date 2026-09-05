"""Logger-name heuristic and match/case classification tests (v0.6 fixes).

The v0.5 whitelist matched exactly five logger base names, so conventional
names like ``LOG``/``audit_logger``/``self._log`` lost the recording
exemption and their handlers were falsely reported. ``match``/``case``
raises were not recognised as conditional raises, so those handlers were
classified ``silent-fallback`` instead of ``masked-exception``.
"""

from __future__ import annotations

import sys

import pytest

from failroute.analyzer import FailureMode, scan_source
from failroute.rules._shared import is_loggerish_name


def test_uppercase_log_name_is_recognised():
# V1 (2026-09-04): recording a failure is a severity *modifier*, not an exemption.
    # 委外任务清单.md §V1.1 layer 3 + probes C2/C3 in §V1.0-A: a log line does not
    # change what the caller receives, so the finding stays and moves down one level.
    # This test previously asserted `== []`, which encoded the old exemption.
        # Recognition is the point: LOG.error must count as a recording channel,
    # which now shows up as a one-level downgrade (HIGH -> MEDIUM).
    source = (
        "import logging\n"
        "LOG = logging.getLogger(__name__)\n"
        "def a(x):\n"
        "    try:\n"
        "        return risky(x)\n"
        "    except Exception:\n"
        "        LOG.error('failed: %s', x)\n"
        "        return None\n"
    )
    findings = scan_source(source)
    assert [f.mode.value for f in findings] == ["silent-fallback"]
    assert findings[0].severity.value == "medium"


def test_suffixed_logger_names_are_recognised():
# V1 (2026-09-04): recording a failure is a severity *modifier*, not an exemption.
    # 委外任务清单.md §V1.1 layer 3 + probes C2/C3 in §V1.0-A: a log line does not
    # change what the caller receives, so the finding stays and moves down one level.
    # This test previously asserted `== []`, which encoded the old exemption.
        # audit_logger.warning: catch-all base HIGH, one level down = MEDIUM.
    source = (
        "def a(x):\n"
        "    try:\n"
        "        return risky(x)\n"
        "    except Exception:\n"
        "        audit_logger.warning('f')\n"
        "        return None\n"
    )
    findings = scan_source(source)
    assert [f.mode.value for f in findings] == ["silent-fallback"]
    assert findings[0].severity.value == "medium"


def test_self_attr_logger_is_recognised():
# V1 (2026-09-04): recording a failure is a severity *modifier*, not an exemption.
    # 委外任务清单.md §V1.1 layer 3 + probes C2/C3 in §V1.0-A: a log line does not
    # change what the caller receives, so the finding stays and moves down one level.
    # This test previously asserted `== []`, which encoded the old exemption.
        # self._log.warning: catch-all base HIGH, one level down = MEDIUM.
    source = (
        "class C:\n"
        "    def a(self, x):\n"
        "        try:\n"
        "            return risky(x)\n"
        "        except Exception:\n"
        "            self._log.warning('f')\n"
        "            return None\n"
    )
    findings = scan_source(source)
    assert [f.mode.value for f in findings] == ["silent-fallback"]
    assert findings[0].severity.value == "medium"


def test_non_logger_names_are_not_loggerish():
    assert not is_loggerish_name("blog")
    assert not is_loggerish_name("catalog")
    assert not is_loggerish_name("dialog")
    assert is_loggerish_name("LOG")
    assert is_loggerish_name("Audit_Logger")
    assert is_loggerish_name("err_log")


@pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="match/case is PEP 634 syntax; ast.parse rejects it before Python 3.10",
)
def test_match_case_raise_classifies_as_masked():
    source = (
        "def a(x):\n"
        "    try:\n"
        "        return g(x)\n"
        "    except Exception as e:\n"
        "        match e:\n"
        "            case ValueError():\n"
        "                raise\n"
        "            case _:\n"
        "                pass\n"
        "        return 0.0\n"
    )
    findings = scan_source(source)
    assert [f.mode for f in findings] == [FailureMode.MASKED_EXCEPTION]

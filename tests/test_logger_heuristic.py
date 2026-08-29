"""Logger-name heuristic and match/case classification tests (v0.6 fixes).

The v0.5 whitelist matched exactly five logger base names, so conventional
names like ``LOG``/``audit_logger``/``self._log`` lost the recording
exemption and their handlers were falsely reported. ``match``/``case``
raises were not recognised as conditional raises, so those handlers were
classified ``silent-fallback`` instead of ``masked-exception``.
"""

from __future__ import annotations

from failroute.analyzer import FailureMode, scan_source
from failroute.rules._shared import is_loggerish_name


def test_uppercase_log_name_is_recognised():
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
    assert scan_source(source) == []


def test_suffixed_logger_names_are_recognised():
    source = (
        "def a(x):\n"
        "    try:\n"
        "        return risky(x)\n"
        "    except Exception:\n"
        "        audit_logger.warning('f')\n"
        "        return None\n"
    )
    assert scan_source(source) == []


def test_self_attr_logger_is_recognised():
    source = (
        "class C:\n"
        "    def a(self, x):\n"
        "        try:\n"
        "            return risky(x)\n"
        "        except Exception:\n"
        "            self._log.warning('f')\n"
        "            return None\n"
    )
    assert scan_source(source) == []


def test_non_logger_names_are_not_loggerish():
    assert not is_loggerish_name("blog")
    assert not is_loggerish_name("catalog")
    assert not is_loggerish_name("dialog")
    assert is_loggerish_name("LOG")
    assert is_loggerish_name("Audit_Logger")
    assert is_loggerish_name("err_log")


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

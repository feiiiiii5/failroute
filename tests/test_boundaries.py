"""Boundary regressions for the v0.6 dispatcher and scan strategies.

Covers defects and edges found while splitting the v0.5 monolith into
registry-dispatched rules:

- handlers nested two or more levels deep were visited twice and reported
  twice (the v0.5 walker re-walked its own subtree for nested handlers),
- ``--jobs`` fan-out and the mtime/size cache must produce exactly the
  serial result,
- a corrupt cache file must degrade to a cold cache, never a crash,
- the configurable sentinel vocabulary
  (``[tool.failroute] fallback_values``).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from failroute import main, scan_path, scan_repo, scan_source
from failroute.analyzer import FailureMode


def test_three_level_nested_handlers_reported_once():
    # Regression: the v0.5 walker double-visited the innermost handler
    # (no-action at line 10 appeared twice).
    source = (
        "def f():\n"
        "    try:\n"
        "        g()\n"
        "    except Exception:\n"
        "        try:\n"
        "            h()\n"
        "        except ValueError:\n"
        "            try:\n"
        "                k()\n"
        "            except TypeError:\n"
        "                pass\n"
    )
    findings = scan_source(source)
    modes = [(f.mode.value, f.lineno) for f in findings]
    # Only the innermost handler is empty-bodied; the regression is that v0.5
    # reported it twice.
    assert modes == [("no-action", 10)]


def test_int_one_fallback_is_now_reported():
    # The built-in whitelist always listed 1/1.0 as ambiguous fallback hints,
    # but the v0.5 renderer never produced those tokens, so the entries were
    # dead. The v0.6 renderer canonicalises every numeric constant.
    findings = scan_source(
        "def f():\n    try:\n        return g()\n    except Exception:\n        return 1\n"
    )
    assert [f.mode for f in findings] == [FailureMode.SILENT_FALLBACK]


def test_configured_sentinel_via_main(tmp_path: Path, capsys):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.failroute]\nfallback_values = [-1, "N/A"]\n', encoding="utf-8"
    )
    (tmp_path / "rank.py").write_text(
        "def rank(x):\n"
        "    try:\n"
        "        return compute(x)\n"
        "    except Exception:\n"
        "        return -1\n"
        "\n"
        "def label(x):\n"
        "    try:\n"
        "        return classify(x)\n"
        "    except Exception:\n"
        "        return 'N/A'\n",
        encoding="utf-8",
    )
    assert main([str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert out.count("silent-fallback") == 2


def test_configured_sentinel_default_config_stays_clean(tmp_path: Path):
    # Without fallback_values the same sources are untouched (no hardcoded
    # guesses for project-specific sentinels).
    (tmp_path / "rank.py").write_text(
        "def rank(x):\n    try:\n        return compute(x)\n    except Exception:\n        return -1\n",
        encoding="utf-8",
    )
    assert main([str(tmp_path)]) == 0


def test_cli_ignore_flag_disables_rule(tmp_path: Path, capsys):
    (tmp_path / "bad.py").write_text(
        "def f():\n    try:\n        return g()\n    except Exception:\n        pass\n",
        encoding="utf-8",
    )
    assert main([str(tmp_path), "--ignore", "no-action"]) == 0
    assert "0 finding(s)" in capsys.readouterr().err


def _write_fixture(root: Path) -> None:
    (root / "pkg").mkdir(exist_ok=True)
    (root / "pkg" / "bad.py").write_text(
        "def f():\n    try:\n        return g()\n    except Exception:\n        return None\n",
        encoding="utf-8",
    )
    (root / "pkg" / "clean.py").write_text("x = 1\n", encoding="utf-8")


def test_parallel_and_cache_match_serial(tmp_path: Path):
    _write_fixture(tmp_path)
    serial = scan_repo(tmp_path)
    parallel = scan_repo(tmp_path, jobs=0)
    cached = scan_repo(tmp_path, use_cache=True)
    cached_again = scan_repo(tmp_path, use_cache=True)
    key = lambda fs: [(f.file, f.lineno, f.mode.value, f.message) for f in fs]  # noqa: E731
    assert key(serial) == key(parallel) == key(cached) == key(cached_again)
    assert len(serial) == 1


def test_corrupt_cache_degrades_to_cold_scan(tmp_path: Path):
    import tempfile

    from failroute.analyzer import _cache_file

    _write_fixture(tmp_path)
    cache_path = _cache_file(tmp_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("not json at all", encoding="utf-8")
    findings = scan_repo(tmp_path, use_cache=True)
    assert len(findings) == 1
    # And the cache file is rebuilt in a usable state.
    assert scan_repo(tmp_path, use_cache=True) == findings
    del tempfile


def test_single_file_repo_flag_still_scans(tmp_path: Path):
    bad = tmp_path / "bad.py"
    bad.write_text(
        "def f():\n    try:\n        return g()\n    except Exception:\n        pass\n",
        encoding="utf-8",
    )
    assert len(scan_repo(bad)) == 1


def test_dotted_name_sentinel(tmp_path: Path, capsys):
    # Enum-member sentinels are matchable when the project names them
    # explicitly; the token must be a namespace-qualified dotted name.
    (tmp_path / "pyproject.toml").write_text(
        '[tool.failroute]\nfallback_names = ["Status.UNKNOWN"]\n', encoding="utf-8"
    )
    (tmp_path / "check.py").write_text(
        "def check(x):\n"
        "    try:\n"
        "        return real_check(x)\n"
        "    except Exception:\n"
        "        return Status.UNKNOWN\n",
        encoding="utf-8",
    )
    assert main([str(tmp_path)]) == 1
    assert "silent-fallback" in capsys.readouterr().out


def test_bare_name_sentinels_are_rejected(tmp_path: Path):
    # A bare (unqualified) name would match `return result`-style code; the
    # config only accepts dotted names, and anything else is ignored.
    (tmp_path / "pyproject.toml").write_text(
        '[tool.failroute]\nfallback_names = ["UNKNOWN"]\n', encoding="utf-8"
    )
    (tmp_path / "check.py").write_text(
        "def check(x):\n"
        "    try:\n"
        "        return real_check(x)\n"
        "    except Exception:\n"
        "        return UNKNOWN\n",
        encoding="utf-8",
    )
    assert main([str(tmp_path)]) == 0


def test_unconfigured_dotted_name_stays_clean(tmp_path: Path):
    (tmp_path / "check.py").write_text(
        "def check(x):\n"
        "    try:\n"
        "        return real_check(x)\n"
        "    except Exception:\n"
        "        return Status.UNKNOWN\n",
        encoding="utf-8",
    )
    assert main([str(tmp_path)]) == 0


def test_cache_does_not_leak_across_configs(tmp_path: Path):
    # Regression: the cache key ignored scan options, so findings scanned
    # under a configured sentinel vocabulary were served back to an
    # unconfigured scan.
    (tmp_path / "check.py").write_text(
        "def check(x):\n"
        "    try:\n"
        "        return real(x)\n"
        "    except Exception:\n"
        "        return Status.UNKNOWN\n",
        encoding="utf-8",
    )
    configured = scan_repo(tmp_path, use_cache=True, extra_fallback_names=frozenset({"Status.UNKNOWN"}))
    plain = scan_repo(tmp_path, use_cache=True)
    assert len(configured) == 1
    assert plain == []


def test_cache_invalidated_by_engine_version(tmp_path: Path, monkeypatch):
    # A cache written by a different engine version must not be served.
    import failroute.analyzer as ana

    (tmp_path / "bad.py").write_text(
        "def f():\n    try:\n        return g()\n    except Exception:\n        return None\n",
        encoding="utf-8",
    )
    first = scan_repo(tmp_path, use_cache=True)
    monkeypatch.setattr(ana, "_engine_version", lambda: "0.0.0-test-old")
    second = scan_repo(tmp_path, use_cache=True)
    assert first == second  # findings identical, but recomputed, not served


# ---------------------------------------------------------------------------
# G6⑥ hostile-input boundaries (V1, 2026-09-04)
#
# 委外任务清单.md §V1.4 G6⑥ names these nine shapes explicitly. The gate they
# serve is G6③/④: "a static analyser's least acceptable failure is crashing on
# someone else's code". Each test asserts *no exception escapes*, not that a
# particular finding is produced -- a skipped file is a correct outcome, a
# traceback is not.
# ---------------------------------------------------------------------------


def test_empty_file_is_clean(tmp_path: Path):
    target = tmp_path / "empty.py"
    target.write_text("", encoding="utf-8")
    assert scan_path(target) == []


def test_comment_only_file_is_clean(tmp_path: Path):
    target = tmp_path / "comments.py"
    target.write_text("# nothing but comments\n\n# still nothing\n", encoding="utf-8")
    assert scan_path(target) == []


def test_non_utf8_source_does_not_crash(tmp_path: Path):
    # latin-1 bytes that are invalid UTF-8. scan_path reads with
    # errors="replace", so the file is scanned as mojibake rather than raising.
    target = tmp_path / "latin1.py"
    target.write_bytes(
        "def g():\n    s = 'café'\n    try:\n        h()\n"
        "    except Exception:\n        pass\n".encode("latin-1")
    )
    findings = scan_path(target)
    assert [f.mode.value for f in findings] == ["no-action"]


def test_null_byte_source_is_skipped_not_raised(tmp_path: Path):
    # ast.parse raises ValueError (not SyntaxError) on a null byte; that used to
    # be an uncaught path.
    target = tmp_path / "nullbyte.py"
    target.write_bytes(b"x = 1\n\x00\n")
    assert scan_path(target) == []


def test_syntax_error_file_is_skipped_not_raised(tmp_path: Path):
    target = tmp_path / "broken.py"
    target.write_text("def f(:\n    pass\n", encoding="utf-8")
    assert scan_path(target) == []


def test_very_long_single_line_does_not_crash(tmp_path: Path):
    target = tmp_path / "longline.py"
    target.write_text(
        "x = '" + "a" * 400_000 + "'\ntry:\n    g()\nexcept Exception:\n    pass\n",
        encoding="utf-8",
    )
    assert [f.mode.value for f in scan_path(target)] == ["no-action"]


def test_deeply_nested_handler_is_still_found(tmp_path: Path):
    # 50 levels of `if` above the handler. Two things are being tested: the
    # AST walk reaches it, and enumerate_exits' depth budget does not silently
    # drop the finding.
    depth = 50
    src = "def f(x):\n"
    for i in range(1, depth + 1):
        src += "    " * i + "if x:\n"
    src += "    " * (depth + 1) + "try:\n"
    src += "    " * (depth + 2) + "g()\n"
    src += "    " * (depth + 1) + "except Exception:\n"
    src += "    " * (depth + 2) + "pass\n"
    target = tmp_path / "deep.py"
    target.write_text(src, encoding="utf-8")
    findings = scan_path(target)
    assert [f.mode.value for f in findings] == ["no-action"]
    assert findings[0].lineno == depth + 4


def test_nesting_beyond_the_parser_limit_is_skipped(tmp_path: Path):
    # CPython's tokenizer rejects more than ~100 indentation levels, so this
    # file is not valid Python. The point is that the scanner says "skipped"
    # rather than raising.
    depth = 200
    src = "def f(x):\n" + "".join("    " * i + "if x:\n" for i in range(1, depth + 1))
    src += "    " * (depth + 1) + "pass\n"
    target = tmp_path / "toodeep.py"
    target.write_text(src, encoding="utf-8")
    assert scan_path(target) == []


def test_pathologically_nested_expression_does_not_crash(tmp_path: Path):
    target = tmp_path / "extreme.py"
    target.write_text("x = " + "[" * 4000 + "]" * 4000 + "\n", encoding="utf-8")
    assert scan_path(target) == []


@pytest.mark.skipif(
    sys.version_info < (3, 10), reason="match/case is PEP 634 syntax, rejected before 3.10"
)
def test_match_statement_handler_is_found(tmp_path: Path):
    src = (
        "def f(cmd) -> float:\n"
        "    try:\n"
        "        return run(cmd)\n"
        "    except ValueError:\n"
        "        match cmd:\n"
        "            case 'a':\n"
        "                return 0.0\n"
        "            case _:\n"
        "                return 1.0\n"
    )
    target = tmp_path / "matchcase.py"
    target.write_text(src, encoding="utf-8")
    findings = scan_path(target)
    assert [f.mode.value for f in findings] == ["silent-fallback"]
    # Both arms are visible, which the top-level-only walk could never do.
    assert "0.0" in findings[0].message and "1.0" in findings[0].message


@pytest.mark.skipif(
    sys.version_info < (3, 11), reason="except* is PEP 654 syntax, rejected before 3.11"
)
def test_except_star_handler_is_found(tmp_path: Path):
    # 🔴 Before V1 the traversal matched ast.Try only, so every `except*`
    # handler in a scanned tree was invisible. PEP 654 forbids return/break/
    # continue inside an except* block, so the observable shapes are `pass`,
    # assignment and re-raise.
    src = (
        "def f():\n"
        "    try:\n"
        "        g()\n"
        "    except* ValueError:\n"
        "        pass\n"
    )
    target = tmp_path / "trystar.py"
    target.write_text(src, encoding="utf-8")
    findings = scan_path(target)
    assert [f.mode.value for f in findings] == ["no-action"]


def test_symlink_loop_terminates(tmp_path: Path):
    # A directory that contains a symlink to itself. rglob must not follow it
    # into an infinite descent.
    sub = tmp_path / "loop"
    sub.mkdir()
    (sub / "a.py").write_text("try:\n    g()\nexcept Exception:\n    pass\n", encoding="utf-8")
    (sub / "self").symlink_to(sub, target_is_directory=True)
    assert len(scan_repo(sub)) == 1


def test_symlinked_file_is_scanned(tmp_path: Path):
    real = tmp_path / "real.py"
    real.write_text("try:\n    g()\nexcept Exception:\n    pass\n", encoding="utf-8")
    link = tmp_path / "link.py"
    link.symlink_to(real)
    assert len(scan_path(link)) == 1


@pytest.mark.skipif(
    os.name != "posix" or os.geteuid() == 0,
    reason="POSIX permission bits; Windows has no geteuid and root bypasses them",
)
def test_unreadable_file_is_skipped_not_raised(tmp_path: Path):
    target = tmp_path / "noperm.py"
    target.write_text("try:\n    g()\nexcept Exception:\n    pass\n", encoding="utf-8")
    os.chmod(target, 0o000)
    try:
        assert scan_path(target) == []
    finally:
        os.chmod(target, 0o644)


def test_unreadable_file_emits_no_stderr_noise(tmp_path: Path, caplog):
    # G6③ requires "stderr 无噪音" over a whole-corpus scan. logging's
    # last-resort handler writes WARNING and above straight to stderr, so a
    # skipped file must be logged at DEBUG.
    import logging

    target = tmp_path / "broken.py"
    target.write_text("def f(:\n", encoding="utf-8")
    with caplog.at_level(logging.DEBUG):
        scan_path(target)
    assert all(record.levelno < logging.WARNING for record in caplog.records)

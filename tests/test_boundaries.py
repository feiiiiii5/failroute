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

from pathlib import Path

from failroute import main, scan_repo, scan_source
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

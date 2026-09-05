"""Replay the 36 ``covered_by`` mapping tests against the pre-V3 predicate.

A gate that only shows green now proves nothing (claims iron law 4), so this
rebuilds the buggy ``covered_by_for`` in a scratch copy of the tree and runs
``tests/test_lint_mapping.py`` against it. Expected: most of them fail.

The pre-V3 source below is a reconstruction, not a git object: §V3.2【X】 holds
the fix uncommitted, so HEAD's ``_shared.py`` is still v0.8.0 and predates the
V1 refactor that introduced ``handler_facts_for`` at all. The text is the
working-tree version as it stood immediately before the V3 edit.

    PYTHONPATH=src .venv/bin/python tools/refix_replay.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGET = Path("src/failroute/rules/_shared.py")
TESTS = Path("tests/test_lint_mapping.py")
START = "#: Trivial-lint rules"
END = "def handler_facts_for"

PRE_V3 = '''#: Trivial-lint rules that flag a handler purely from its shape. Established
#: empirically rather than from memory (V1 result section).
_LINT_BY_BARE = ("flake8:E722", "ruff:E722", "bugbear:B001", "pylint:W0702")
_LINT_BY_CATCH_ALL_TYPED = ("ruff:BLE001", "pylint:W0718")
_LINT_BY_EMPTY_BODY = ("bandit:B110", "ruff:S110")
_LINT_BY_CONTINUE_BODY = ("bandit:B112", "ruff:S112")
_LINT_BY_DISCARDED_COMPARISON = ("bugbear:B015", "ruff:B015")


def _handler_catches_base_exception(handler: ast.ExceptHandler) -> bool:
    names = _handler_exc_member_names(handler)
    if not names:
        return False
    return any(name in ("Exception", "BaseException") for name in names)


def covered_by_for(
    handler: ast.ExceptHandler,
    *,
    body_empty: bool,
    dead_probe: bool,
) -> tuple[str, ...]:
    """Lint rules that already point at this handler, inferred from its shape."""
    covered: set[str] = set()
    if handler.type is None:
        covered.update(_LINT_BY_BARE)
    elif _handler_catches_base_exception(handler):
        covered.update(_LINT_BY_CATCH_ALL_TYPED)
    if body_empty:
        covered.update(_LINT_BY_EMPTY_BODY)
    elif all(isinstance(s, ast.Continue) or isinstance(s, ast.Pass) for s in handler.body):
        if any(isinstance(s, ast.Continue) for s in handler.body):
            covered.update(_LINT_BY_CONTINUE_BODY)
    if dead_probe:
        covered.update(_LINT_BY_DISCARDED_COMPARISON)
    return tuple(sorted(covered))


'''


def build_prefix_tree(scratch: Path) -> Path:
    for name in ("src", "tests"):
        shutil.copytree(REPO / name, scratch / name)
    shutil.copy2(REPO / "pyproject.toml", scratch / "pyproject.toml")
    shared = scratch / TARGET
    lines = shared.read_text(encoding="utf-8").split("\n")
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith(START))
        end = next(i for i, line in enumerate(lines) if line.startswith(END))
    except StopIteration as exc:  # pragma: no cover - guard against drift
        raise SystemExit(f"anchor not found in {TARGET}: {exc}") from exc
    shared.write_text(
        "\n".join(lines[:start] + PRE_V3.split("\n") + lines[end:]), encoding="utf-8"
    )
    return shared


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="failroute-refix-") as tmp:
        scratch = (Path(tmp) / "tree").resolve()
        scratch.mkdir()
        build_prefix_tree(scratch)
        env = {**os.environ, "PYTHONPATH": "src"}
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "--tb=no", str(TESTS)],
            cwd=scratch,
            capture_output=True,
            text=True,
            env=env,
            timeout=300,
        )
        summary = next(
            (
                line.strip()
                for line in reversed(proc.stdout.splitlines())
                if "passed" in line or "failed" in line or "error" in line
            ),
            "",
        )
        # Guard against the scratch tree silently losing to the installed one.
        loaded = subprocess.run(
            [sys.executable, "-c", "import failroute.rules._shared as m; print(m.__file__)"],
            cwd=scratch,
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        ).stdout.strip()
        if not loaded.startswith(str(scratch)):
            print(f"REFIX_REPLAY aborted: scratch tree not imported ({loaded})")
            return 1
        print(f"REFIX_REPLAY module={loaded}")
        print(f"REFIX_REPLAY {summary}")
        return 0 if summary else 1


if __name__ == "__main__":
    raise SystemExit(main())

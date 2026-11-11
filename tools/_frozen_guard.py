"""Refuse to overwrite committed (frozen) research outputs by accident.

Several historical analysis scripts default to writing into ``bench/`` or
``paper/``, where the files that the manuscript cites are committed. Re-running
one of them with its defaults used to replace a frozen export with a fresh one,
so that a later ``git diff`` was the only record that anything had changed.

``guard_output`` stops that. A path that git tracks (or, outside a git checkout,
any existing path under ``bench/`` or ``paper/``) is refused unless the caller
passes ``allow=True``, which each script exposes as ``--allow-overwrite-frozen``.
Recomputations should write to a new directory, or run inside a disposable
``git worktree``, and be compared with the committed files afterwards.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROZEN_DIRS = ("bench", "paper")
ALLOW_FLAG = "--allow-overwrite-frozen"


def _tracked(path: Path) -> bool | None:
    """True/False when git can answer, None when this is not a usable checkout."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--error-unmatch", "--", str(path)],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode == 0:
        return True
    if "not a git repository" in (proc.stderr or "").lower():
        return None
    return False


def is_frozen(path: str | os.PathLike[str]) -> bool:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    p = p.resolve()
    try:
        rel = p.relative_to(ROOT)
    except ValueError:
        return False  # outside this checkout: a scratch location
    tracked = _tracked(p)
    if tracked is not None:
        return tracked
    return p.exists() and bool(rel.parts) and rel.parts[0] in FROZEN_DIRS


def guard_output(path: str | os.PathLike[str], allow: bool = False) -> None:
    """Exit with an explanation if ``path`` is a committed output and ``allow`` is false."""
    if allow or not is_frozen(path):
        return
    sys.exit(
        f"error: refusing to overwrite committed output {path}.\n"
        f"  Write the recomputation to a new location (for example --out /tmp/...),\n"
        f"  or run inside a disposable `git worktree`, then compare with the frozen file.\n"
        f"  Pass {ALLOW_FLAG} only when deliberately regenerating a frozen artefact."
    )


def guard_dir(directory: str | os.PathLike[str], names: list[str], allow: bool = False) -> None:
    for name in names:
        guard_output(Path(directory) / name, allow)

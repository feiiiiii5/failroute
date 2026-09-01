#!/usr/bin/env python3
"""Diff two corpus finding sets and attribute every vanished finding.

Compares a *base* findings directory (default: the frozen ``paper/scan``)
against a *new* findings directory (e.g. ``bench/rescan-v0.8``) using the
finding identity ``(file, lineno, rule, message)`` as a multiset key, then
classifies each vanished finding by re-parsing the handler in the corpus
source:

* ``F3-stopasync``    — handler catches ``StopAsyncIteration`` (alone or in an
                        all-ignored tuple)
* ``F1-ignored-tuple``— handler type is a tuple whose members are all on the
                        control-flow ignore list
* ``F2-warnings-warn``— handler body calls ``warnings.warn``/``warn_explicit``
* ``other``           — none of the above: 🔴 must be investigated by hand;
                        the script exits non-zero so it cannot be overlooked

Usage (repo root):
    PYTHONPATH=src .venv/bin/python tools/delta_findings.py \
        --base paper/scan --new bench/rescan-v0.8
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

IGNORED = {
    "KeyboardInterrupt",
    "SystemExit",
    "GeneratorExit",
    "StopIteration",
    "StopAsyncIteration",
    "CancelledError",
}


def load(dirpath: Path) -> list[dict]:
    rows: list[dict] = []
    jsonls = sorted(dirpath.glob("*.jsonl"))
    if not jsonls:
        sys.exit(f"error: no .jsonl findings under {dirpath}")
    for path in jsonls:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def key(row: dict) -> tuple:
    return (row["file"], row["lineno"], row["rule"], row["message"])


def handler_at(file: Path, lineno: int) -> ast.ExceptHandler | None:
    """The ExceptHandler starting at ``lineno``, else None (suppress findings
    have no handler; callers classify those separately)."""
    try:
        tree = ast.parse(file.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.lineno == lineno:
            return node
    return None


def suppress_at(file: Path, lineno: int) -> ast.With | None:
    """The With/AsyncWith starting at ``lineno`` whose item is contextlib.suppress."""
    try:
        tree = ast.parse(file.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.With, ast.AsyncWith))
            and node.lineno == lineno
            and any(
                isinstance(item.context_expr, ast.Call)
                and getattr(item.context_expr.func, "id", None) == "suppress"
                for item in node.items
            )
        ):
            return node
    return None


def member_names(exc: ast.expr | None) -> list[str] | None:
    if exc is None:
        return None
    members = exc.elts if isinstance(exc, ast.Tuple) else [exc]
    names: list[str] = []
    for m in members:
        if isinstance(m, ast.Name):
            names.append(m.id)
        elif isinstance(m, ast.Attribute):
            names.append(m.attr)
        else:
            return None
    return names


def body_warns(handler: ast.ExceptHandler) -> bool:
    for node in ast.walk(handler):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "warnings"
            and node.func.attr in ("warn", "warn_explicit")
        ):
            return True
    return False


def classify(row: dict) -> str:
    source_path = ROOT / row["file"]
    if not source_path.is_file():
        return "other:source-missing"
    handler = handler_at(source_path, row["lineno"])
    if handler is None:
        # with-suppress findings report at the With node's line, not a handler.
        with_node = suppress_at(source_path, row["lineno"])
        if with_node is not None:
            call = with_node.items[0].context_expr
            names = []
            for arg in call.args:
                if isinstance(arg, ast.Name):
                    names.append(arg.id)
                elif isinstance(arg, ast.Attribute):
                    names.append(arg.attr)
                else:
                    names = []
                    break
            if names and all(n in IGNORED for n in names):
                # The finding's message shows only the FIRST arg; the vanished
                # exemption comes from a later member joining the ignore list.
                return "F3-stopasync" if "StopAsyncIteration" in names else "F1-ignored-tuple"
        return "other:no-handler(suppress?)"
    names = member_names(handler.type) or []
    if "StopAsyncIteration" in names and all(n in IGNORED for n in names):
        return "F3-stopasync"
    if isinstance(handler.type, ast.Tuple) and names and all(n in IGNORED for n in names):
        return "F1-ignored-tuple"
    if body_warns(handler):
        return "F2-warnings-warn"
    return "other"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="paper/scan", help="baseline findings dir")
    parser.add_argument("--new", required=True, help="new findings dir")
    args = parser.parse_args()

    base = load(Path(args.base) if Path(args.base).is_absolute() else ROOT / args.base)
    new = load(Path(args.new) if Path(args.new).is_absolute() else ROOT / args.new)

    base_c, new_c = Counter(map(key, base)), Counter(map(key, new))
    vanished = base_c - new_c
    appeared = new_c - base_c

    print(f"base rows={sum(base_c.values())}  new rows={sum(new_c.values())}")
    print(f"vanished={sum(vanished.values())}  appeared={sum(appeared.values())}")

    by_cause: dict[str, list[tuple]] = {}
    for k, n in sorted(vanished.items()):
        cause = classify({"file": k[0], "lineno": k[1], "rule": k[2], "message": k[3]})
        by_cause.setdefault(cause, []).append((k, n))

    for cause in sorted(by_cause):
        print(f"\n== {cause} ({sum(n for _, n in by_cause[cause])}) ==")
        for (file, lineno, rule, message), n in by_cause[cause]:
            print(f"  {file}:{lineno}  {rule}  x{n}  {message[:70]}")

    if appeared:
        print("\n== APPEARED (must be explained) ==")
        for k, n in sorted(appeared.items()):
            print(f"  {k[0]}:{k[1]}  {k[2]}  x{n}  {k[3][:70]}")

    unexplained = [c for c in by_cause if c.startswith("other")] or (["appeared"] if appeared else [])
    counts = Counter()
    for cause, items in by_cause.items():
        counts[cause.split(":")[0]] += sum(n for _, n in items)
    summary = " ".join(f"{c}={counts[c]}" for c in sorted(counts))
    print(f"\nSUMMARY vanished={sum(vanished.values())} appeared={sum(appeared.values())} {summary}")
    if unexplained:
        print(f"\n🔴 UNEXPLAINED categories: {unexplained}", file=sys.stderr)
        return 1
    print("all vanished findings attributed; no findings appeared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

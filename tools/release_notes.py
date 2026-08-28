#!/usr/bin/env python3
"""Print the CHANGELOG section for the current version, for release automation.

Used by the tag-triggered release workflow to build GitHub Release notes from
the CHANGELOG (the single source of truth for release content). Exits 1 if
the section is missing, so a release never ships with empty notes silently.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "(.*?)"', pyproject, re.M)
    if not match:
        print("pyproject.toml has no version", file=sys.stderr)
        return 1
    version = match.group(1)

    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    section = re.search(
        rf"## \[{re.escape(version)}\].*?\n(.*?)(?=\n## \[|\Z)", changelog, re.S
    )
    if not section:
        print(f"no CHANGELOG section for [{version}]", file=sys.stderr)
        return 1

    body = section.group(1).strip()
    print(body)
    print()
    print(f"PyPI: https://pypi.org/project/failroute/{version}/")
    print()
    print("Install: `pip install failroute`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

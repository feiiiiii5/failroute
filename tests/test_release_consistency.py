"""Version pins across shipped artifacts must agree with the package version.

These drifted silently in the past (the composite Action kept installing an
older release, SECURITY.md advertised an unsupported version range, and the
README pre-commit rev lagged a release). A release is one commit; every
published pointer should move with it, and CI is the place that notices.
"""

from __future__ import annotations

from pathlib import Path

try:  # pragma: no cover - exercised by the version matrix
    import tomllib
except ModuleNotFoundError:  # Python < 3.11, same fallback as the CLI
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]

ROOT = Path(__file__).resolve().parent.parent


def _package_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def test_init_version_matches_pyproject():
    source = (ROOT / "src" / "failroute" / "__init__.py").read_text(encoding="utf-8")
    assert f'__version__ = "{_package_version()}"' in source


def test_composite_action_default_installs_current_release():
    source = (ROOT / "action" / "action.yml").read_text(encoding="utf-8")
    assert f'default: "{_package_version()}"' in source, (
        "action/action.yml pins an outdated failroute release; Action users would "
        "silently get the old engine"
    )


def test_readme_pre_commit_rev_matches_release():
    source = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"rev: v{_package_version()}" in source, (
        "README pre-commit example points at a tag that is not the current release"
    )


def test_security_policy_covers_current_series():
    major, minor, _ = _package_version().split(".")
    source = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert f"| {major}.{minor}.x | Yes |" in source, (
        "SECURITY.md advertises support for a version series the project no longer ships"
    )


def test_changelog_documents_current_release():
    source = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{_package_version()}]" in source

"""Project configuration: ``[tool.failroute]`` in ``pyproject.toml``.

Recognised keys (all optional; malformed values fall back to defaults — a
config problem must never turn a scan into a crash):

.. code-block:: toml

    [tool.failroute]
    exclude = ["tests/corpus"]       # repo-relative paths to skip
    threshold = 0                    # exit 1 when more findings than this
    ignore = ["name-shadowing"]      # disable rules by id
    fallback_values = [-1, "N/A"]    # project-specific fallback sentinels

    [tool.failroute.rules.implicit-fallback]
    enabled = false                  # same as adding to ``ignore``
    severity = "warning"             # override the rule's default SARIF level

Sentinel canonicalisation: a TOML int/float becomes its decimal token
(``-1`` -> ``"-1"``); a TOML string becomes its Python ``repr`` form
(``"N/A"`` -> ``"'N/A'"``). Values are matched against the same canonical
rendering the detector produces, so what you write is what gets matched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_VALID_SEVERITIES = {"error", "warning"}


@dataclass
class FailrouteConfig:
    """Resolved project configuration."""

    exclude: frozenset[str] = frozenset()
    threshold: int = 0
    #: Canonical tokens beyond the built-in fallback shapes.
    fallback_values: frozenset[str] = frozenset()
    #: Dotted-name sentinels (``Status.UNKNOWN``) matched on attribute chains.
    fallback_names: frozenset[str] = frozenset()
    #: Rule ids disabled via ``ignore`` or ``rules.<id>.enabled = false``.
    disabled_rules: frozenset[str] = frozenset()
    #: rule id -> SARIF level ("error"/"warning").
    severity_overrides: dict[str, str] = field(default_factory=dict)


def _canonical_token(value: Any) -> str | None:
    """Render a config value the same way the detector renders constants."""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return repr(value)
    return None


def _parse_rule_tables(raw: Any) -> tuple[set[str], dict[str, str]]:
    """Read ``[tool.failroute.rules.<id>]`` tables: enabled / severity."""
    disabled: set[str] = set()
    severities: dict[str, str] = {}
    if not isinstance(raw, dict):
        return disabled, severities
    for rule_id, table in raw.items():
        if not isinstance(table, dict):
            continue
        enabled = table.get("enabled")
        if enabled is False and isinstance(rule_id, str):
            disabled.add(rule_id)
        severity = table.get("severity")
        if isinstance(rule_id, str) and severity in _VALID_SEVERITIES:
            severities[rule_id] = severity
    return disabled, severities


def load_config(start: Path) -> FailrouteConfig:
    """Read ``[tool.failroute]`` from the nearest pyproject.toml at/above ``start``."""
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - py<3.11 path
        try:
            import tomli as tomllib  # type: ignore[import-not-found,no-redef,unused-ignore]
        except ModuleNotFoundError:  # failroute: ignore - no TOML parser, no project config
            return FailrouteConfig()

    for base in (start, *start.parents):
        candidate = base / "pyproject.toml"
        if not candidate.is_file():
            continue
        try:
            with candidate.open("rb") as fh:
                data = tomllib.load(fh)
        except (OSError, ValueError):  # failroute: ignore - documented: bad config = no config
            return FailrouteConfig()
        cfg = data.get("tool", {}).get("failroute", {})
        if not isinstance(cfg, dict):
            return FailrouteConfig()

        exclude_raw = cfg.get("exclude")
        exclude = (
            frozenset(e for e in exclude_raw if isinstance(e, str))
            if isinstance(exclude_raw, list)
            else frozenset()
        )

        threshold_raw = cfg.get("threshold")
        threshold = (
            threshold_raw if isinstance(threshold_raw, int) and not isinstance(threshold_raw, bool) else 0
        )

        values_raw = cfg.get("fallback_values")
        if isinstance(values_raw, list):
            fallback_values = frozenset(
                token for token in (_canonical_token(v) for v in values_raw) if token is not None
            )
        else:
            fallback_values = frozenset()

        names_raw = cfg.get("fallback_names")
        if isinstance(names_raw, list):
            # Only namespace-qualified names are accepted: a bare token would
            # match `return result`-style code, which is never a safe guess.
            fallback_names = frozenset(
                n for n in names_raw if isinstance(n, str) and "." in n and not n.isspace()
            )
        else:
            fallback_names = frozenset()

        ignore_raw = cfg.get("ignore")
        ignored = {r for r in ignore_raw if isinstance(r, str)} if isinstance(ignore_raw, list) else set()
        table_disabled, severities = _parse_rule_tables(cfg.get("rules"))

        return FailrouteConfig(
            exclude=exclude,
            threshold=threshold,
            fallback_values=fallback_values,
            fallback_names=fallback_names,
            disabled_rules=frozenset(ignored | table_disabled),
            severity_overrides=severities,
        )
    return FailrouteConfig()

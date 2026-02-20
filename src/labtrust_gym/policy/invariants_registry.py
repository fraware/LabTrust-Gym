"""
Invariant registry loader for the engine and model checker.

Invariants are safety rules (e.g. zone adjacency, token validity) checked at
runtime. This module loads policy/invariants/invariant_registry.v1.0.yaml and
returns a list of InvariantEntry objects used by the invariant runtime and
by the bounded trace checker. Each entry includes id, title, severity, scope,
signals, logic_template, and exception/enforcement hints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class InvariantEntry:
    """
    Single invariant (safety rule) from the registry.

    severity: info | low | med | high | critical.
    scope: specimen | result | device | zone | agent | system.
    """

    invariant_id: str
    title: str
    description: str
    severity: str
    scope: str
    signals: list[str]
    logic_template: dict[str, Any]  # type + parameters
    exception_hooks: dict[str, Any]  # override_token_types, allow_when
    enforcement_hint: dict[str, Any]  # recommend_action
    reason_code: str | None = None
    triggers: list[str] = field(default_factory=list)


def _normalize_entry(raw: dict[str, Any]) -> InvariantEntry:
    """Build InvariantEntry from raw YAML entry."""
    logic = raw.get("logic_template") or {}
    if isinstance(logic, str):
        logic = {"type": "state", "parameters": {}}
    exc = raw.get("exception_hooks") or {}
    if not isinstance(exc, dict):
        exc = {}
    hint = raw.get("enforcement_hint") or {}
    if not isinstance(hint, dict):
        hint = {}
    triggers = raw.get("triggers")
    if not isinstance(triggers, list):
        triggers = []
    return InvariantEntry(
        invariant_id=str(raw.get("invariant_id", "")),
        title=str(raw.get("title", "")),
        description=str(raw.get("description", "")),
        severity=str(raw.get("severity", "med")),
        scope=str(raw.get("scope", "system")),
        signals=list(raw.get("signals") or []),
        logic_template=dict(logic),
        exception_hooks={
            "override_token_types": list(exc.get("override_token_types") or []),
            "allow_when": exc.get("allow_when"),
        },
        enforcement_hint=dict(hint),
        reason_code=raw.get("reason_code"),
        triggers=list(triggers),
    )


def load_invariant_registry(path: Path | None = None) -> list[InvariantEntry]:
    """
    Load invariant registry YAML and return list of InvariantEntry.
    Path defaults to policy/invariants/invariant_registry.v1.0.yaml.
    """
    path = path or Path("policy/invariants/invariant_registry.v1.0.yaml")
    try:
        path_exists = path.exists()
    except OSError:
        path_exists = False
    if not path_exists:
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return []
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    raw_list = data.get("invariants")
    if not isinstance(raw_list, list):
        return []
    entries: list[InvariantEntry] = []
    for raw in raw_list:
        if isinstance(raw, dict) and raw.get("invariant_id"):
            entries.append(_normalize_entry(raw))
    return entries

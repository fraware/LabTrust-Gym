"""
Invariant registry loader: loads policy/invariants/invariant_registry.v1.0.yaml
and returns typed InvariantEntry objects for runtime compilation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class InvariantEntry:
    """Single invariant from the registry (machine-readable)."""

    invariant_id: str
    title: str
    description: str
    severity: str  # info | low | med | high | critical
    scope: str  # specimen | result | device | zone | agent | system
    signals: List[str]
    logic_template: Dict[str, Any]  # type + parameters
    exception_hooks: Dict[str, Any]  # override_token_types, allow_when
    enforcement_hint: Dict[str, Any]  # recommend_action
    reason_code: Optional[str] = None
    triggers: List[str] = field(default_factory=list)


def _normalize_entry(raw: Dict[str, Any]) -> InvariantEntry:
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


def load_invariant_registry(path: Optional[Path] = None) -> List[InvariantEntry]:
    """
    Load invariant registry YAML and return list of InvariantEntry.
    Path defaults to policy/invariants/invariant_registry.v1.0.yaml.
    """
    path = path or Path("policy/invariants/invariant_registry.v1.0.yaml")
    if not path.exists():
        return []
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    raw_list = data.get("invariants")
    if not isinstance(raw_list, list):
        return []
    entries: List[InvariantEntry] = []
    for raw in raw_list:
        if isinstance(raw, dict) and raw.get("invariant_id"):
            entries.append(_normalize_entry(raw))
    return entries

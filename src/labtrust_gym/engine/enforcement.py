"""
Policy-driven enforcement: throttle_agent, kill_switch, freeze_zone, forensic_freeze.

Consumes violations from invariants_runtime; matches rules by invariant_id/severity/scope;
applies actions with optional escalation (first -> throttle, repeated -> kill_switch).
Records enforcement events into audit log when audit_callback is provided.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from labtrust_gym.policy.loader import PolicyLoadError, load_yaml

EnforcementItem = Dict[str, Any]  # type, target?, duration_s?, reason_code?, rule_id?


def load_enforcement_map(path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load enforcement_map YAML. Returns dict with version, rules list.
    Path defaults to policy/enforcement/enforcement_map.v0.1.yaml.
    """
    path = path or Path("policy/enforcement/enforcement_map.v0.1.yaml")
    if not path.exists():
        return {"version": "0.1", "rules": []}
    try:
        data = load_yaml(path)
    except PolicyLoadError:
        return {"version": "0.1", "rules": []}
    rules = data.get("rules")
    if not isinstance(rules, list):
        rules = []
    return {"version": data.get("version", "0.1"), "rules": rules}


def _match_rule(rule: Dict[str, Any], violation: Dict[str, Any]) -> bool:
    """True if rule.match matches violation (invariant_id, severity, scope)."""
    match = rule.get("match") or {}
    inv_id = violation.get("invariant_id")
    mid = match.get("invariant_id")
    if mid is not None and inv_id != mid:
        return False
    # Severity/scope from registry; violation may not have them.
    severity = match.get("severity")
    if severity is not None:
        v_sev = violation.get("severity")
        if v_sev is not None and v_sev != severity:
            return False
    scope = match.get("scope")
    if scope is not None:
        v_scope = violation.get("scope")
        if v_scope is not None and v_scope != scope:
            return False
    return True


def _get_escalation_action(
    rule: Dict[str, Any],
    violation_count: int,
) -> Optional[Dict[str, Any]]:
    """
    Return action dict for violation count using rule.action or rule.escalation.
    Pick highest escalation tier where count >= violation_count_min.
    """
    escalation = rule.get("escalation")
    if isinstance(escalation, list) and escalation:
        best = None
        best_min = -1
        for tier in escalation:
            min_c = tier.get("violation_count_min", 0)
            if violation_count >= min_c and min_c >= best_min:
                best = tier.get("action")
                best_min = min_c
        if best:
            return best
    return rule.get("action")


def _apply_action(
    action: Dict[str, Any],
    agent_id: str,
    rule_id: str,
    reason_code: Optional[str],
    event: Dict[str, Any],
) -> EnforcementItem:
    """Build one enforcement item from action dict."""
    out: EnforcementItem = {
        "type": action.get("type", "throttle_agent"),
        "reason_code": reason_code,
        "rule_id": rule_id,
    }
    if action.get("type") == "throttle_agent":
        out["target"] = agent_id
        out["duration_s"] = action.get("duration_s", 60)
    elif action.get("type") == "kill_switch":
        target_type = action.get("target_type", "agent_id")
        out["target_type"] = target_type
        out["target"] = agent_id  # default; could be device_id/zone_id from context
    elif action.get("type") == "freeze_zone":
        out["zone_id"] = action.get("zone_id", "")
    elif action.get("type") == "forensic_freeze":
        pass
    return out


class EnforcementEngine:
    """
    Applies enforcement rules to violations. Tracks violation counts per
    (agent_id, rule_id) for escalation. Deterministic; optionally records to audit.
    """

    def __init__(self, map_path: Optional[Path] = None) -> None:
        self._map = load_enforcement_map(map_path)
        self._rules: List[Dict[str, Any]] = self._map.get("rules") or []
        # (agent_id, rule_id) -> violation count (for escalation)
        self._violation_counts: Dict[Tuple[str, str], int] = {}

    def reset_counts(self) -> None:
        """Clear violation counts (e.g. on env reset)."""
        self._violation_counts.clear()

    def apply(
        self,
        event: Dict[str, Any],
        violations: List[Dict[str, Any]],
        audit_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> List[EnforcementItem]:
        """
        Match violations against rules, apply escalation, return list of enforcement items.
        Only VIOLATION status is considered. Order is deterministic (rule order, then violation order).
        If audit_callback is provided, each enforcement is recorded as an audit event.
        """
        agent_id = str(event.get("agent_id", ""))
        enforcements: List[EnforcementItem] = []
        violation_list = [v for v in violations if v.get("status") == "VIOLATION"]

        for rule in self._rules:
            rule_id = rule.get("rule_id") or ""
            for v in violation_list:
                if not _match_rule(rule, v):
                    continue
                key = (agent_id, rule_id)
                count = self._violation_counts.get(key, 0) + 1
                self._violation_counts[key] = count
                action = _get_escalation_action(rule, count)
                if not action:
                    continue
                reason_code = v.get("reason_code")
                item = _apply_action(
                    action, agent_id, rule_id, reason_code, event
                )
                enforcements.append(item)
                if audit_callback:
                    audit_callback({
                        "event_type": "ENFORCEMENT",
                        "rule_id": rule_id,
                        "action_type": item.get("type"),
                        "target": item.get("target"),
                        "duration_s": item.get("duration_s"),
                        "reason_code": reason_code,
                        "violation_count": count,
                    })

        return enforcements


def apply_enforcement(
    event: Dict[str, Any],
    violations: List[Dict[str, Any]],
    engine: Optional[EnforcementEngine],
    audit_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> List[EnforcementItem]:
    """If engine is None return []; else return engine.apply(...)."""
    if engine is None:
        return []
    return engine.apply(event, violations, audit_callback)

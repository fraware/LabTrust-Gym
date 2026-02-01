"""
RBAC policy evaluator: gates actions before state mutation.

- roles: role_id -> allowed_actions, allowed_zones (optional), allowed_devices (optional)
- agents: agent_id -> role_id
- action_constraints: action_type -> required_role_id (optional)
- Given agent_id + action_type + context (zone_id, device_id), returns allow/deny + reason_code.
- Record RBAC decision in step output for receipts/forensics.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Reason codes (must match policy/reason_codes/reason_code_registry.v0.1.yaml)
RBAC_ACTION_DENY = "RBAC_ACTION_DENY"
RBAC_ZONE_DENY = "RBAC_ZONE_DENY"
RBAC_DEVICE_DENY = "RBAC_DEVICE_DENY"


def load_rbac_policy(path: Path) -> Dict[str, Any]:
    """Load rbac_policy YAML. Returns dict with rbac_policy.version, roles, agents, action_constraints."""
    from labtrust_gym.policy.loader import load_yaml
    if not path.exists():
        return {"version": "0.1", "roles": {}, "agents": {}, "action_constraints": {}}
    data = load_yaml(path)
    rbac = data.get("rbac_policy")
    if not isinstance(rbac, dict):
        return {"version": "0.1", "roles": {}, "agents": {}, "action_constraints": {}}
    roles = rbac.get("roles")
    if not isinstance(roles, dict):
        roles = {}
    agents = rbac.get("agents")
    if not isinstance(agents, dict):
        agents = {}
    constraints = rbac.get("action_constraints")
    if not isinstance(constraints, dict):
        constraints = {}
    return {
        "version": rbac.get("version", "0.1"),
        "roles": roles,
        "agents": agents,
        "action_constraints": constraints,
    }


def check(
    agent_id: str,
    action_type: str,
    context: Dict[str, Any],
    policy: Dict[str, Any],
) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """
    Decide allow/deny for agent_id + action_type + context.
    Returns (allowed, reason_code, rbac_decision).
    rbac_decision: { "allowed": bool, "reason_code": str | null, "role_id": str | null }.

    Backward compat: if policy has no agents/roles or agent_id not in agents, allow (permissive).
    """
    decision: Dict[str, Any] = {"allowed": True, "reason_code": None, "role_id": None}
    if not policy:
        return True, None, decision
    agents_map = policy.get("agents") or {}
    roles_map = policy.get("roles") or {}
    role_id = agents_map.get(agent_id) if isinstance(agents_map, dict) else None
    if role_id is None:
        # Agent not in policy: allow (backward compat)
        return True, None, decision
    decision["role_id"] = role_id
    role_def = roles_map.get(role_id) if isinstance(roles_map, dict) else None
    if not isinstance(role_def, dict):
        # Role not defined: allow (permissive)
        return True, None, decision
    allowed_actions = role_def.get("allowed_actions")
    if isinstance(allowed_actions, list) and action_type not in allowed_actions:
        decision["allowed"] = False
        decision["reason_code"] = RBAC_ACTION_DENY
        return False, RBAC_ACTION_DENY, decision
    constraints = policy.get("action_constraints") or {}
    if isinstance(constraints, dict) and action_type in constraints:
        required_role = constraints.get(action_type)
        if required_role and required_role != role_id:
            decision["allowed"] = False
            decision["reason_code"] = RBAC_ACTION_DENY
            return False, RBAC_ACTION_DENY, decision
    allowed_zones = role_def.get("allowed_zones")
    zone_id = context.get("zone_id") if isinstance(context, dict) else None
    if isinstance(allowed_zones, list) and zone_id is not None and zone_id not in allowed_zones:
        decision["allowed"] = False
        decision["reason_code"] = RBAC_ZONE_DENY
        return False, RBAC_ZONE_DENY, decision
    allowed_devices = role_def.get("allowed_devices")
    device_id = context.get("device_id") if isinstance(context, dict) else None
    if isinstance(allowed_devices, list) and device_id is not None and device_id not in allowed_devices:
        decision["allowed"] = False
        decision["reason_code"] = RBAC_DEVICE_DENY
        return False, RBAC_DEVICE_DENY, decision
    return True, None, decision


def get_agent_role(agent_id: str, policy: Dict[str, Any]) -> Optional[str]:
    """Return role_id for agent_id from policy, or None if not in policy."""
    if not policy:
        return None
    agents_map = policy.get("agents") or {}
    if not isinstance(agents_map, dict):
        return None
    return agents_map.get(agent_id)


def get_allowed_actions(agent_id: str, policy: Dict[str, Any]) -> list[str]:
    """Return list of allowed action types for agent_id (RBAC-filtered). Empty if not in policy."""
    role_id = get_agent_role(agent_id, policy)
    if role_id is None:
        return []
    roles_map = policy.get("roles") or {}
    if not isinstance(roles_map, dict):
        return []
    role_def = roles_map.get(role_id)
    if not isinstance(role_def, dict):
        return []
    allowed = role_def.get("allowed_actions")
    if not isinstance(allowed, list):
        return []
    return list(allowed)

"""
Agent capability profiles (B006): scope and rate limits beyond RBAC.

- Load policy/security/agent_capabilities.v0.1.yaml
- Check action against profile: allowed_actions (or RBAC), rate limit, override budget, high-risk reason+rationale
- Reason codes: AGENT_CAPABILITY_DENY, AGENT_RATE_LIMIT, AGENT_OVERRIDE_BUDGET_EXCEEDED
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Reason codes (must match policy/reason_codes/reason_code_registry.v0.1.yaml)
AGENT_CAPABILITY_DENY = "AGENT_CAPABILITY_DENY"
AGENT_RATE_LIMIT = "AGENT_RATE_LIMIT"
AGENT_OVERRIDE_BUDGET_EXCEEDED = "AGENT_OVERRIDE_BUDGET_EXCEEDED"


def load_agent_capabilities(repo_root: Path | None = None) -> dict[str, Any]:
    """
    Load agent_capabilities.v0.1.yaml. Returns dict with version, profiles, override_action_types.
    If repo_root is None or file missing, returns empty policy (no capability enforcement).
    """
    if repo_root is None:
        return {}
    path = Path(repo_root) / "policy" / "security" / "agent_capabilities.v0.1.yaml"
    if not path.exists():
        return {}
    try:
        from labtrust_gym.policy.loader import load_yaml

        data = load_yaml(path)
    except Exception:
        return {}
    cap = data.get("agent_capabilities") if isinstance(data, dict) else {}
    if not isinstance(cap, dict):
        return {}
    profiles = cap.get("profiles") or {}
    override_types = cap.get("override_action_types") or []
    return {
        "version": cap.get("version", "0.1"),
        "profiles": dict(profiles) if isinstance(profiles, dict) else {},
        "override_action_types": (list(override_types) if isinstance(override_types, list) else []),
    }


def get_profile_for_agent(
    agent_id: str,
    role_id: str | None,
    capabilities: dict[str, Any],
    rbac_agents: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """
    Return capability profile for agent: agent_id override first, then role_id, else None.
    rbac_agents: optional map agent_id -> role_id to resolve role when role_id not provided.
    """
    if not capabilities or not isinstance(capabilities.get("profiles"), dict):
        return None
    profiles = capabilities["profiles"]
    # Agent-specific override
    if agent_id and agent_id in profiles:
        p = profiles[agent_id]
        return p if isinstance(p, dict) else None
    # By role
    rid = role_id
    if rid is None and rbac_agents and isinstance(rbac_agents, dict):
        rid = rbac_agents.get(agent_id)
    if rid and rid in profiles:
        p = profiles[rid]
        return p if isinstance(p, dict) else None
    return None


def is_override_action(action_type: str, capabilities: dict[str, Any]) -> bool:
    """True if action_type consumes override budget."""
    types = capabilities.get("override_action_types") or []
    return action_type in types


def check_capability(
    action_type: str,
    event: dict[str, Any],
    profile: dict[str, Any] | None,
    capabilities: dict[str, Any],
    rbac_allowed_actions: list[str] | None,
    action_count: int,
    override_count: int,
) -> tuple[bool, str | None]:
    """
    Check action against capability profile. Called after RBAC.
    Returns (allowed, reason_code). reason_code is None if allowed.

    - If no profile: allow (capability layer is opt-in).
    - If profile.allowed_actions set and action_type not in it: AGENT_CAPABILITY_DENY.
    - If action_count >= max_action_rate: AGENT_RATE_LIMIT.
    - If action is override and override_count >= max_override_tokens: AGENT_OVERRIDE_BUDGET_EXCEEDED.
    - If action in high_risk_actions: require event.reason_code and event.rationale (non-empty) else AGENT_CAPABILITY_DENY.
    """
    if not profile:
        return True, None
    allowed_actions = profile.get("allowed_actions")
    if isinstance(allowed_actions, list) and len(allowed_actions) > 0:
        if action_type not in allowed_actions:
            return False, AGENT_CAPABILITY_DENY
    elif rbac_allowed_actions is not None and isinstance(rbac_allowed_actions, list) and len(rbac_allowed_actions) > 0:
        if action_type not in rbac_allowed_actions:
            return False, AGENT_CAPABILITY_DENY
    max_rate = profile.get("max_action_rate")
    if isinstance(max_rate, int | float) and action_count >= max_rate:
        return False, AGENT_RATE_LIMIT
    max_override = profile.get("max_override_tokens")
    if isinstance(max_override, int | float) and is_override_action(action_type, capabilities):
        if override_count >= max_override:
            return False, AGENT_OVERRIDE_BUDGET_EXCEEDED
    high_risk = profile.get("high_risk_actions") or []
    if action_type in high_risk:
        reason = (event.get("reason_code") or "").strip()
        rationale = (event.get("rationale") or "").strip()
        if not reason or not rationale:
            return False, AGENT_CAPABILITY_DENY
    return True, None


def get_allowed_tooling(profile: dict[str, Any] | None) -> dict[str, bool]:
    """Return { llm: bool, signing_proxy: bool } from profile; default both True if no profile."""
    if not profile:
        return {"llm": True, "signing_proxy": True}
    tooling = profile.get("allowed_tooling") or {}
    return {
        "llm": bool(tooling.get("llm", True)),
        "signing_proxy": bool(tooling.get("signing_proxy", True)),
    }

"""
Safety shield for LLM-proposed actions: RBAC, signature required, token validity.
Filters candidate action -> pass or rewrite to safe noop; records LLM_ACTION_FILTERED + reason_code.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from labtrust_gym.engine.rbac import check as rbac_check, RBAC_ACTION_DENY
from labtrust_gym.engine.signatures import is_mutating_action
from labtrust_gym.security.agent_capabilities import (
    AGENT_CAPABILITY_DENY,
    get_allowed_tooling,
)

# Emit when shield blocks (recorded in step output)
LLM_ACTION_FILTERED = "LLM_ACTION_FILTERED"

# Reason codes (must match policy)
SIG_MISSING = "SIG_MISSING"
SIG_INVALID = "SIG_INVALID"


def apply_shield(
    candidate: Dict[str, Any],
    agent_id: str,
    rbac_policy: Dict[str, Any],
    policy_summary: Dict[str, Any],
    capability_profile: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], bool, Optional[str]]:
    """
    Filter candidate action through RBAC, capability profile, and signature-required checks.
    Returns (safe_action_dict, filtered, reason_code).
    - safe_action_dict: either candidate (if pass) or {"action_type": "NOOP", "args": {}}.
    - filtered: True if shield blocked.
    - reason_code: RBAC_ACTION_DENY, AGENT_CAPABILITY_DENY, SIG_MISSING, or None.
    Token validity is left to the engine (shield does not have token store).
    """
    action_type = (candidate.get("action_type") or "NOOP").strip()
    args = candidate.get("args")
    if not isinstance(args, dict):
        args = {}
    key_id = candidate.get("key_id")
    signature = candidate.get("signature")
    strict_signatures = bool(policy_summary.get("strict_signatures", False))
    # Only block on allowed_actions list when agent is in policy (non-empty list)
    allowed_actions = policy_summary.get("allowed_actions")
    noop_base: Dict[str, Any] = {
        "action_type": "NOOP",
        "args": {},
        "reason_code": None,
        "token_refs": [],
        "rationale": (candidate.get("rationale") or "").strip(),
    }
    if (
        isinstance(allowed_actions, list)
        and len(allowed_actions) > 0
        and action_type not in allowed_actions
    ):
        return (noop_base, True, RBAC_ACTION_DENY)
    # Capability profile (B006): defense-in-depth; refuse action outside profile or signing_proxy if disabled
    if capability_profile is not None:
        profile_allowed = capability_profile.get("allowed_actions")
        if isinstance(profile_allowed, list) and len(profile_allowed) > 0:
            if action_type not in profile_allowed:
                return (noop_base, True, AGENT_CAPABILITY_DENY)
        tooling = get_allowed_tooling(capability_profile)
        if not tooling.get("signing_proxy", True) and (key_id or signature):
            return (noop_base, True, AGENT_CAPABILITY_DENY)
    # RBAC check (action_type + context)
    context: Dict[str, Any] = {}
    if args:
        context["device_id"] = args.get("device_id")
        context["zone_id"] = policy_summary.get("agent_zone")
    allowed, rbac_reason, _ = rbac_check(agent_id, action_type, context, rbac_policy)
    if not allowed and rbac_reason:
        return (noop_base, True, rbac_reason)
    if strict_signatures and is_mutating_action(action_type):
        if not key_id or not signature:
            return (noop_base, True, SIG_MISSING)
    safe: Dict[str, Any] = {
        "action_type": action_type,
        "args": args,
        "reason_code": candidate.get("reason_code"),
        "token_refs": list(candidate.get("token_refs") or []),
        "rationale": (candidate.get("rationale") or "").strip(),
    }
    if key_id is not None:
        safe["key_id"] = key_id
    if signature is not None:
        safe["signature"] = signature
    return (safe, False, None)


# Stable citation anchor prefixes for policy sections (LLM rationale must cite at least one)
CITATION_ANCHOR_RBAC_ALLOWED = "POLICY:RBAC:allowed_actions"
CITATION_ANCHOR_ZONES_RESTRICTED = "POLICY:ZONES:restricted_zones"
CITATION_ANCHOR_ZONES_AGENT = "POLICY:ZONES:agent_zone"
CITATION_ANCHOR_TOKENS = "POLICY:TOKENS:token_requirements"
CITATION_ANCHOR_CONSTRAINTS = "POLICY:CONSTRAINTS:key_constraints"
CITATION_ANCHOR_CRITICAL = "POLICY:CRITICAL:critical_ladder_summary"


def build_policy_summary(
    allowed_actions: Optional[list] = None,
    agent_zone: Optional[str] = None,
    zone_graph: Optional[Dict[str, list]] = None,
    queue_head: Optional[Dict[str, str]] = None,
    pending_criticals: Optional[list] = None,
    log_frozen: bool = False,
    strict_signatures: bool = False,
    key_constraints: Optional[list] = None,
    critical_ladder_summary: Optional[Dict[str, Any]] = None,
    restricted_zones: Optional[list] = None,
    token_requirements: Optional[Dict[str, list]] = None,
    role_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build policy_summary dict for LLM (what the agent can see). Conforms to policy_summary.schema.v0.1. Includes stable citation_anchors for rationale."""
    out: Dict[str, Any] = {
        "allowed_actions": list(allowed_actions) if allowed_actions else [],
        "agent_zone": agent_zone,
        "zone_graph": dict(zone_graph) if zone_graph else {},
        "queue_head": dict(queue_head) if queue_head else {},
        "pending_criticals": list(pending_criticals) if pending_criticals else [],
        "log_frozen": log_frozen,
        "strict_signatures": strict_signatures,
    }
    if key_constraints is not None:
        out["key_constraints"] = list(key_constraints)
    if critical_ladder_summary is not None:
        out["critical_ladder_summary"] = dict(critical_ladder_summary)
    if restricted_zones is not None:
        out["restricted_zones"] = list(restricted_zones)
    if token_requirements is not None:
        out["token_requirements"] = {k: list(v) for k, v in token_requirements.items()}

    # Stable citation anchors: at least RBAC; add section anchors for present sections
    citation_anchors: list = [CITATION_ANCHOR_RBAC_ALLOWED]
    if role_id:
        citation_anchors.append(f"POLICY:RBAC:roles.{role_id}.allowed_actions")
    if restricted_zones:
        citation_anchors.append(CITATION_ANCHOR_ZONES_RESTRICTED)
    if agent_zone is not None:
        citation_anchors.append(CITATION_ANCHOR_ZONES_AGENT)
    if token_requirements:
        citation_anchors.append(CITATION_ANCHOR_TOKENS)
    if key_constraints:
        citation_anchors.append(CITATION_ANCHOR_CONSTRAINTS)
    if critical_ladder_summary:
        citation_anchors.append(CITATION_ANCHOR_CRITICAL)
    out["citation_anchors"] = citation_anchors
    return out


def generate_policy_summary_from_policy(
    repo_root: Optional[Any] = None,
    allowed_actions: Optional[list] = None,
    agent_zone: Optional[str] = None,
    zone_graph: Optional[Dict[str, list]] = None,
    queue_head: Optional[Dict[str, str]] = None,
    pending_criticals: Optional[list] = None,
    log_frozen: bool = False,
    strict_signatures: bool = False,
    role_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build policy summary with minimal key constraints, critical ladder, restricted zones, token requirements.
    Loads from policy/ when repo_root is provided; otherwise uses stub defaults.
    Includes stable citation_anchors for rationale.
    """
    from pathlib import Path

    key_constraints: list = []
    critical_ladder_summary: Dict[str, Any] = {}
    restricted_zones: list = []
    token_requirements: Dict[str, list] = {}

    root = Path(repo_root) if repo_root else None
    if root and (root / "policy").exists():
        # Zones: restricted zones from zone_layout_policy
        zones_path = root / "policy" / "zones" / "zone_layout_policy.v0.1.yaml"
        if zones_path.exists():
            try:
                from labtrust_gym.policy.loader import load_yaml

                zones_data = load_yaml(zones_path)
                zones = zones_data.get("zone_layout") or zones_data.get("zones") or {}
                if isinstance(zones, dict):
                    for zid, zdef in zones.items():
                        if isinstance(zdef, dict) and zdef.get("restricted"):
                            restricted_zones.append(str(zid))
            except Exception:
                restricted_zones = []
        # Token requirements: OPEN_DOOR -> RESTRICTED_ENTRY for restricted doors
        token_map_path = root / "policy" / "tokens" / "token_enforcement_map.v0.1.yaml"
        if token_map_path.exists():
            try:
                from labtrust_gym.policy.loader import load_yaml

                token_data = load_yaml(token_map_path)
                enforcement = (
                    token_data.get("token_enforcement_map")
                    or token_data.get("action_tokens")
                    or {}
                )
                if isinstance(enforcement, dict):
                    for action, tokens in enforcement.items():
                        if isinstance(tokens, list):
                            token_requirements[str(action)] = [str(t) for t in tokens]
                        elif isinstance(tokens, str):
                            token_requirements[str(action)] = [str(tokens)]
            except Exception:
                token_requirements = {}
        # Key constraints (stub)
        key_constraints = [
            "Do not release results when log_frozen.",
            "Restricted zones require token for OPEN_DOOR.",
        ]
        # Critical ladder (stub)
        critical_ladder_summary = {"ack_required": True, "levels": ["CRIT_A", "CRIT_B"]}

    summary = build_policy_summary(
        allowed_actions=allowed_actions,
        agent_zone=agent_zone,
        zone_graph=zone_graph,
        queue_head=queue_head,
        pending_criticals=pending_criticals,
        log_frozen=log_frozen,
        strict_signatures=strict_signatures,
        key_constraints=key_constraints or None,
        critical_ladder_summary=critical_ladder_summary or None,
        restricted_zones=restricted_zones or None,
        token_requirements=token_requirements or None,
        role_id=role_id,
    )
    return summary

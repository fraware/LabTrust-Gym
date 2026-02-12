"""
Safety shield for LLM-proposed actions: RBAC, signature required, token validity.
Filters candidate action -> pass or rewrite to safe noop; records LLM_ACTION_FILTERED + reason_code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.engine.rbac import RBAC_ACTION_DENY
from labtrust_gym.engine.rbac import check as rbac_check
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
    candidate: dict[str, Any],
    agent_id: str,
    rbac_policy: dict[str, Any],
    policy_summary: dict[str, Any],
    capability_profile: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool, str | None]:
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
    noop_base: dict[str, Any] = {
        "action_type": "NOOP",
        "args": {},
        "reason_code": None,
        "token_refs": [],
        "rationale": (candidate.get("rationale") or "").strip(),
    }
    if isinstance(allowed_actions, list) and len(allowed_actions) > 0 and action_type not in allowed_actions:
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
    context: dict[str, Any] = {}
    if args:
        context["device_id"] = args.get("device_id")
        context["zone_id"] = policy_summary.get("agent_zone")
    allowed, rbac_reason, _ = rbac_check(agent_id, action_type, context, rbac_policy)
    if not allowed and rbac_reason:
        return (noop_base, True, rbac_reason)
    if strict_signatures and is_mutating_action(action_type):
        if not key_id or not signature:
            return (noop_base, True, SIG_MISSING)
    safe: dict[str, Any] = {
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
    allowed_actions: list[str] | None = None,
    agent_zone: str | None = None,
    zone_graph: dict[str, list[str]] | None = None,
    queue_head: dict[str, str] | None = None,
    pending_criticals: list[str] | None = None,
    log_frozen: bool = False,
    strict_signatures: bool = False,
    key_constraints: list[str] | None = None,
    critical_ladder_summary: dict[str, Any] | None = None,
    restricted_zones: list[str] | None = None,
    token_requirements: dict[str, list[str]] | None = None,
    role_id: str | None = None,
) -> dict[str, Any]:
    """Build policy_summary dict for LLM (what the agent can see). Conforms to policy_summary.schema.v0.1. Includes stable citation_anchors for rationale."""
    out: dict[str, Any] = {
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
    citation_anchors: list[str] = [CITATION_ANCHOR_RBAC_ALLOWED]
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


def _load_rbac_roles_summary(root: Path) -> dict[str, list[str]]:
    """Load RBAC policy and return role_id -> list of allowed_actions for all roles."""
    out: dict[str, list[str]] = {}
    try:
        from labtrust_gym.engine.rbac import load_rbac_policy
        path = root / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
        if not path.exists():
            return out
        policy = load_rbac_policy(path)
        for role_id, role_def in (policy.get("roles") or {}).items():
            if isinstance(role_def, dict):
                actions = role_def.get("allowed_actions")
                out[str(role_id)] = list(actions) if isinstance(actions, list) else []
    except Exception:
        pass
    return out


def _derive_zone_graph_from_policy(root: Path) -> dict[str, list[str]]:
    """Build zone adjacency from zone_layout_policy graph_edges (from -> [to, ...])."""
    graph: dict[str, list[str]] = {}
    try:
        from labtrust_gym.policy.loader import load_yaml
        path = root / "policy" / "zones" / "zone_layout_policy.v0.1.yaml"
        if not path.exists():
            return graph
        raw = load_yaml(path) or {}
        data = raw.get("zone_layout_policy") or raw
        edges = data.get("graph_edges") or []
        for e in edges:
            if not isinstance(e, dict):
                continue
            fr = e.get("from")
            to = e.get("to")
            if fr and to:
                graph.setdefault(str(fr), []).append(str(to))
        for k in graph:
            graph[k] = list(dict.fromkeys(graph[k]))
    except Exception:
        pass
    return graph


def _derive_key_constraints_full(
    root: Path,
    role_id: str | None,
    restricted_zones: list[str],
    token_requirements: dict[str, list[str]],
    critical_summary: dict[str, Any],
    log_frozen: bool,
    strict_signatures: bool,
) -> list[str]:
    """
    Derive full key_constraints list from policy: RBAC, zones, tokens, critical, audit.
    Every line is traceable to policy.
    """
    constraints: list[str] = []
    if role_id:
        constraints.append(
            f"Only propose actions from your role ({role_id}) allowed_actions list."
        )
    if log_frozen:
        constraints.append("Do not release results when log_frozen is true.")
    if restricted_zones:
        constraints.append(
            f"Restricted zones ({', '.join(sorted(restricted_zones))}) require "
            "token for OPEN_DOOR or MOVE into them."
        )
    for action, tokens in sorted((token_requirements or {}).items()):
        if tokens:
            constraints.append(
                f"Action {action} requires one of: {', '.join(sorted(tokens))}."
            )
    if critical_summary.get("ack_required"):
        constraints.append(
            "Critical results require acknowledgment per escalation ladder."
        )
    if strict_signatures:
        constraints.append(
            "Mutating actions require key_id and signature when strict_signatures."
        )
    return constraints


def _derive_critical_ladder_summary(root: Path) -> dict[str, Any]:
    """Derive critical_ladder_summary from policy/critical (thresholds + escalation_ladder)."""
    out: dict[str, Any] = {"ack_required": True, "levels": ["CRIT_A", "CRIT_B"]}
    try:
        from labtrust_gym.policy.loader import load_yaml
        # Critical levels from critical_thresholds
        ct_path = root / "policy" / "critical" / "critical_thresholds.v0.1.yaml"
        if ct_path.exists():
            ct = load_yaml(ct_path) or {}
            thresholds = ct.get("critical_thresholds") or ct
            defaults = thresholds.get("defaults_rcpath2017") or []
            levels = sorted(
                set(
                    str(d.get("class"))
                    for d in defaults
                    if isinstance(d, dict) and d.get("class")
                )
            )
            if levels:
                out["levels"] = levels
        # Escalation tiers and ack from escalation_ladder
        el_path = root / "policy" / "critical" / "escalation_ladder.v0.2.yaml"
        if el_path.exists():
            el = load_yaml(el_path) or {}
            tiers = el.get("tiers") or []
            if tiers:
                out["tiers"] = [
                    {
                        "tier_index": t.get("tier_index"),
                        "role": t.get("role"),
                        "requires_readback": t.get("requires_readback", True),
                    }
                    for t in tiers
                    if isinstance(t, dict)
                ]
                out["ack_required"] = any(
                    t.get("requires_readback", True) for t in tiers if isinstance(t, dict)
                )
    except Exception:
        pass
    return out


def generate_policy_summary_from_policy(
    repo_root: Any | None = None,
    allowed_actions: list[str] | None = None,
    agent_zone: str | None = None,
    zone_graph: dict[str, list[str]] | None = None,
    queue_head: dict[str, str] | None = None,
    pending_criticals: list[str] | None = None,
    log_frozen: bool = False,
    strict_signatures: bool = False,
    role_id: str | None = None,
) -> dict[str, Any]:
    """
    Build policy summary with minimal key constraints, critical ladder, restricted zones, token requirements.
    Loads from policy/ when repo_root is provided; otherwise uses built-in defaults.
    Includes stable citation_anchors for rationale.
    """
    from pathlib import Path

    key_constraints: list[str] = []
    critical_ladder_summary: dict[str, Any] = {}
    restricted_zones: list[str] = []
    token_requirements: dict[str, list[str]] = {}
    rbac_roles_summary: dict[str, list[str]] = {}

    root = Path(repo_root) if repo_root else None
    if root and (root / "policy").exists():
        from labtrust_gym.policy.loader import load_yaml

        # Zones: restricted from zone_layout (list or dict)
        zones_path = root / "policy" / "zones" / "zone_layout_policy.v0.1.yaml"
        if zones_path.exists():
            try:
                raw_zones = load_yaml(zones_path) or {}
                zones_data = raw_zones.get("zone_layout_policy") or raw_zones
                zones = zones_data.get("zone_layout") or zones_data.get("zones")
                if isinstance(zones, list):
                    for z in zones:
                        if isinstance(z, dict) and z.get("restricted"):
                            zid = z.get("zone_id")
                            if zid and zid not in restricted_zones:
                                restricted_zones.append(str(zid))
                elif isinstance(zones, dict):
                    for zid, zdef in zones.items():
                        if isinstance(zdef, dict) and zdef.get("restricted"):
                            restricted_zones.append(str(zid))
            except Exception:
                pass
        # Doors with requires_token: add target zone to restricted if not already
        if zones_path and zones_path.exists():
            try:
                raw_d = load_yaml(zones_path) or {}
                zones_data = raw_d.get("zone_layout_policy") or raw_d
                for d in zones_data.get("doors") or []:
                    if isinstance(d, dict) and d.get("requires_token"):
                        to_zone = d.get("to_zone")
                        if to_zone and to_zone not in restricted_zones:
                            restricted_zones.append(str(to_zone))
            except Exception:
                pass
        # Zone graph from policy when not provided
        if zone_graph is None or not zone_graph:
            zone_graph = _derive_zone_graph_from_policy(root)
        # Token requirements from token_enforcement_map (list of entries)
        token_map_path = root / "policy" / "tokens" / "token_enforcement_map.v0.1.yaml"
        if token_map_path.exists():
            try:
                token_data = load_yaml(token_map_path) or {}
                enforcement_list = token_data.get("token_enforcement_map")
                if isinstance(enforcement_list, list):
                    for entry in enforcement_list:
                        if isinstance(entry, dict):
                            action = entry.get("action_type")
                            tok = entry.get("requires_token_type")
                            if action and tok:
                                token_requirements.setdefault(
                                    str(action), []
                                ).append(str(tok))
                    token_requirements = {
                        k: list(dict.fromkeys(v))
                        for k, v in token_requirements.items()
                    }
            except Exception:
                pass
        # Critical ladder
        critical_ladder_summary = _derive_critical_ladder_summary(root)
        # Key constraints: full derivation from RBAC, zones, tokens, critical
        key_constraints = _derive_key_constraints_full(
            root,
            role_id=role_id,
            restricted_zones=restricted_zones,
            token_requirements=token_requirements,
            critical_summary=critical_ladder_summary,
            log_frozen=log_frozen,
            strict_signatures=strict_signatures,
        )
        # Dual approval: append to key_constraints
        dual_approval_path = root / "policy" / "tokens" / "dual_approval_policy.v0.1.yaml"
        if dual_approval_path.exists():
            try:
                da = load_yaml(dual_approval_path) or {}
                da_policy = da.get("dual_approval_policy") or da
                intent = da_policy.get("intent")
                if intent:
                    key_constraints.append(f"Dual approval: {intent}")
                for rule in (da_policy.get("rules") or []):
                    if isinstance(rule, dict) and rule.get("id"):
                        req = rule.get("requirements") or rule.get("requirement") or ""
                        req_str = (
                            req if isinstance(req, str)
                            else "; ".join(str(x) for x in req)
                        )
                        key_constraints.append(f"Rule {rule['id']}: {req_str}")
            except Exception:
                pass
        # RBAC roles summary for citation (optional; schema allows additionalProperties)
        rbac_roles_summary = _load_rbac_roles_summary(root)

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
    if rbac_roles_summary:
        summary["rbac_roles_summary"] = {
            k: list(v) for k, v in rbac_roles_summary.items()
        }
    return summary

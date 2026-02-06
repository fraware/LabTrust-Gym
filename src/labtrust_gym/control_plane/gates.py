"""
First gates: RBAC, capability (B006), signature verification.

Deterministic given event and context. Returns GateDecision for the engine to merge
into step output (or short-circuit return when allowed=False).
"""

from __future__ import annotations

from typing import Any

from labtrust_gym.control_plane.interface import GateDecision
from labtrust_gym.engine.rbac import (
    check as rbac_check,
)
from labtrust_gym.engine.rbac import (
    get_agent_role as rbac_get_agent_role,
)
from labtrust_gym.engine.rbac import (
    get_allowed_actions as rbac_get_allowed_actions,
)
from labtrust_gym.engine.signatures import (
    is_mutating_action,
    verify_action_signature,
)
from labtrust_gym.security.agent_capabilities import (
    check_capability,
    get_profile_for_agent,
)

SIG_ROLE_MISMATCH = "SIG_ROLE_MISMATCH"


def apply_gates(
    event: dict[str, Any],
    context: dict[str, Any],
) -> GateDecision:
    """
    Run RBAC, capability, and signature gates. Returns GateDecision.
    Context must contain: rbac_policy, zones (or zone_id getter), key_registry,
    strict_signatures, partner_id, policy_fingerprint, t_s, capability_policy (optional),
    episode_agent_action_count, episode_agent_override_count.
    """
    rbac_policy = context.get("rbac_policy") or {}
    agent_id = str(event.get("agent_id", ""))
    action_type = str(event.get("action_type", ""))
    args = event.get("args") or {}

    rbac_context: dict[str, Any] = {
        "zone_id": context.get("zone_id"),
        "device_id": args.get("device_id"),
    }
    if context.get("zones") and agent_id:
        rbac_context["zone_id"] = context["zones"].get_agent_zone(agent_id)

    allowed, rbac_reason, rbac_decision = rbac_check(agent_id, action_type, rbac_context, rbac_policy)
    if not allowed and rbac_reason:
        return GateDecision(
            allowed=False,
            step_output_fragment={
                "status": "BLOCKED",
                "emits": [],
                "blocked_reason_code": rbac_reason,
                "rbac_decision": rbac_decision,
            },
        )

    capability_policy = context.get("capability_policy")
    if capability_policy and capability_policy.get("profiles"):
        role_id = (rbac_decision or {}).get("role_id")
        profile = get_profile_for_agent(
            agent_id,
            role_id,
            capability_policy,
            rbac_policy.get("agents") if rbac_policy else None,
        )
        rbac_allowed_actions = rbac_get_allowed_actions(agent_id, rbac_policy)
        action_count = context.get("episode_agent_action_count") or {}
        override_count = context.get("episode_agent_override_count") or {}
        cap_allowed, cap_reason = check_capability(
            action_type,
            event,
            profile,
            capability_policy,
            rbac_allowed_actions,
            action_count.get(agent_id, 0),
            override_count.get(agent_id, 0),
        )
        if not cap_allowed and cap_reason:
            return GateDecision(
                allowed=False,
                step_output_fragment={
                    "status": "BLOCKED",
                    "emits": ["AGENT_SCOPE_VIOLATION"],
                    "blocked_reason_code": cap_reason,
                    "capability_decision": {
                        "allowed": False,
                        "reason_code": cap_reason,
                        "action_count": action_count.get(agent_id, 0),
                        "override_count": override_count.get(agent_id, 0),
                    },
                },
            )

    strict_signatures = context.get("strict_signatures", False)
    prev_hash = context.get("prev_hash") or ""
    t_s = context.get("t_s", 0)
    key_registry = context.get("key_registry") or {}
    partner_id = context.get("partner_id")
    policy_fingerprint = context.get("policy_fingerprint")

    sig_passed: bool | None = None
    sig_reason: str | None = None
    sig_info: dict[str, Any] | None = None
    if event.get("key_id") or event.get("signature"):
        passed, reason, info = verify_action_signature(
            event,
            prev_hash,
            partner_id,
            policy_fingerprint,
            key_registry,
            t_s,
        )
        sig_passed = passed
        sig_reason = reason
        sig_info = info or {}

    if strict_signatures and is_mutating_action(action_type):
        if not event.get("key_id") or not event.get("signature"):
            return GateDecision(
                allowed=False,
                step_output_fragment={
                    "status": "BLOCKED",
                    "emits": [],
                    "blocked_reason_code": "SIG_MISSING",
                    "signature_verification": {
                        "passed": False,
                        "reason_code": "SIG_MISSING",
                        "key_id": event.get("key_id"),
                    },
                },
            )
        if sig_passed is False and sig_reason:
            return GateDecision(
                allowed=False,
                step_output_fragment={
                    "status": "BLOCKED",
                    "emits": [],
                    "blocked_reason_code": sig_reason,
                    "signature_verification": sig_info,
                },
            )
        if sig_passed is True and sig_info:
            agent_role = rbac_get_agent_role(agent_id, rbac_policy)
            key_role = sig_info.get("key_role_id")
            if agent_role is not None and key_role is not None and agent_role != key_role:
                return GateDecision(
                    allowed=False,
                    step_output_fragment={
                        "status": "BLOCKED",
                        "emits": [],
                        "blocked_reason_code": SIG_ROLE_MISMATCH,
                        "signature_verification": sig_info,
                    },
                )

    fragment: dict[str, Any] = {
        "rbac_decision": rbac_decision,
    }
    if sig_info is not None:
        fragment["signature_verification"] = sig_info
    return GateDecision(allowed=True, step_output_fragment=fragment)

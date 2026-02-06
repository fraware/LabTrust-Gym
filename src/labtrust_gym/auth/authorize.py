"""
Policy-driven RBAC for tool invocation: is_tool_allowed, rbac_policy_fingerprint.

- is_tool_allowed(role_id, tool_id, registry, rbac_policy, context) -> (ok, reason_code)
  Uses TOOL_NOT_IN_REGISTRY and TOOL_NOT_ALLOWED_FOR_ROLE from tools.registry.
- rbac_policy_fingerprint(rbac_policy) -> SHA-256 hex for EvidenceBundle and combined_policy_fingerprint.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from labtrust_gym.baselines.llm.tool_proxy import get_tool_capabilities
from labtrust_gym.tools.registry import (
    TOOL_NOT_ALLOWED_FOR_ROLE,
    TOOL_NOT_IN_REGISTRY,
    get_tool_entry,
)


def rbac_policy_fingerprint(rbac_policy: dict[str, Any]) -> str:
    """
    Compute SHA-256 (hex) digest of the RBAC policy for reproducibility and EvidenceBundle.
    Same content => same digest. Input: loaded rbac_policy dict (roles, agents, etc.).
    """
    if not rbac_policy or not isinstance(rbac_policy, dict):
        payload = json.dumps({}, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
    payload = json.dumps(rbac_policy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def is_tool_allowed(
    role_id: str | None,
    tool_id: str,
    registry: dict[str, Any],
    rbac_policy: dict[str, Any] | None,
    context: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    """
    Check whether a tool call is allowed for the given role: tool must be in registry
    and (when rbac_policy and role_id are set) role must allow the tool via
    allowed_tool_ids and/or allowed_capabilities.

    Returns (allowed, reason_code). reason_code is TOOL_NOT_IN_REGISTRY or
    TOOL_NOT_ALLOWED_FOR_ROLE when blocked.
    """
    if not tool_id or not isinstance(tool_id, str):
        return False, TOOL_NOT_IN_REGISTRY
    tool_id = tool_id.strip()
    entry = get_tool_entry(registry, tool_id)
    if entry is None:
        return False, TOOL_NOT_IN_REGISTRY
    if not rbac_policy or not role_id:
        return True, None
    roles = rbac_policy.get("roles")
    if not isinstance(roles, dict):
        return True, None
    role_def = roles.get(role_id)
    if not isinstance(role_def, dict):
        return True, None
    allowed_tool_ids = role_def.get("allowed_tool_ids")
    allowed_caps = role_def.get("allowed_capabilities")
    has_tool_list = isinstance(allowed_tool_ids, list) and len(allowed_tool_ids) > 0
    has_cap_list = isinstance(allowed_caps, list) and len(allowed_caps) > 0
    if not has_tool_list and not has_cap_list:
        return True, None
    if has_tool_list and allowed_tool_ids is not None and tool_id in allowed_tool_ids:
        return True, None
    if has_cap_list and allowed_caps is not None:
        tool_caps = get_tool_capabilities(registry, tool_id)
        cap_set = set(allowed_caps)
        if tool_caps and any(c in cap_set for c in tool_caps):
            return True, None
    return False, TOOL_NOT_ALLOWED_FOR_ROLE

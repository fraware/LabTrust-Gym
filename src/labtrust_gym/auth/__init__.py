"""
Authorization for tool invocation (policy-driven, audited).

Checks whether a role is allowed to call a given tool using the tool registry
and RBAC (role-based access control) policy. Used by the engine when an agent
invokes a tool. Exposes is_tool_allowed and rbac_policy_fingerprint for
evidence bundles.
"""

from labtrust_gym.auth.authorize import (
    is_tool_allowed,
    rbac_policy_fingerprint,
)

__all__ = [
    "is_tool_allowed",
    "rbac_policy_fingerprint",
]

"""Auth: policy-driven RBAC for tool invocation (audited authZ)."""

from labtrust_gym.auth.authorize import (
    is_tool_allowed,
    rbac_policy_fingerprint,
)

__all__ = [
    "is_tool_allowed",
    "rbac_policy_fingerprint",
]

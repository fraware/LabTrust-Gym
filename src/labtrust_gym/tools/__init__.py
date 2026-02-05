"""Tool registry and argument validation: provably constrained, typed tool usage."""

from labtrust_gym.tools.registry import (
    load_tool_registry,
    tool_registry_fingerprint,
    check_tool_allowed,
    combined_policy_fingerprint,
    validate_registry_hashes,
    get_tool_entry,
    TOOL_NOT_IN_REGISTRY,
    TOOL_NOT_ALLOWED_FOR_ROLE,
)
from labtrust_gym.tools.arg_validation import (
    load_arg_schema,
    validate_tool_args,
    TOOL_ARG_SCHEMA_FAIL,
    TOOL_ARG_RANGE_FAIL,
)
from labtrust_gym.tools.execution import (
    execute_tool_safely,
    TOOL_EXEC_EXCEPTION,
    TOOL_TIMEOUT,
    TOOL_OUTPUT_MALFORMED,
)
from labtrust_gym.tools.capabilities import (
    load_capabilities_vocab,
    load_state_tool_capability_map,
    validate_capabilities,
    get_allowed_capabilities_for_state,
)
from labtrust_gym.tools.sandbox import (
    load_tool_boundary_policy,
    ToolSandbox,
    check_output_with_policy,
    TOOL_EGRESS_DENIED,
    TOOL_EGRESS_LIMIT_EXCEEDED,
    TOOL_DATA_CLASS_VIOLATION,
)

__all__ = [
    "load_tool_registry",
    "tool_registry_fingerprint",
    "check_tool_allowed",
    "combined_policy_fingerprint",
    "validate_registry_hashes",
    "get_tool_entry",
    "TOOL_NOT_IN_REGISTRY",
    "TOOL_NOT_ALLOWED_FOR_ROLE",
    "load_arg_schema",
    "validate_tool_args",
    "TOOL_ARG_SCHEMA_FAIL",
    "TOOL_ARG_RANGE_FAIL",
    "execute_tool_safely",
    "TOOL_EXEC_EXCEPTION",
    "TOOL_TIMEOUT",
    "TOOL_OUTPUT_MALFORMED",
    "load_capabilities_vocab",
    "load_state_tool_capability_map",
    "validate_capabilities",
    "get_allowed_capabilities_for_state",
    "load_tool_boundary_policy",
    "ToolSandbox",
    "check_output_with_policy",
    "TOOL_EGRESS_DENIED",
    "TOOL_EGRESS_LIMIT_EXCEEDED",
    "TOOL_DATA_CLASS_VIOLATION",
]

"""Tool registry and argument validation: provably constrained, typed tool usage."""

from labtrust_gym.tools.arg_validation import (
    TOOL_ARG_RANGE_FAIL,
    TOOL_ARG_SCHEMA_FAIL,
    load_arg_schema,
    validate_tool_args,
)
from labtrust_gym.tools.capabilities import (
    get_allowed_capabilities_for_state,
    load_capabilities_vocab,
    load_state_tool_capability_map,
    validate_capabilities,
)
from labtrust_gym.tools.execution import (
    TOOL_EXEC_EXCEPTION,
    TOOL_OUTPUT_MALFORMED,
    TOOL_TIMEOUT,
    ToolExecutionConfigurationError,
    execute_tool_safely,
)
from labtrust_gym.tools.registry import (
    TOOL_NOT_ALLOWED_FOR_ROLE,
    TOOL_NOT_IN_REGISTRY,
    check_tool_allowed,
    combined_policy_fingerprint,
    get_tool_entry,
    load_tool_registry,
    tool_registry_fingerprint,
    validate_registry_hashes,
)
from labtrust_gym.tools.sandbox import (
    TOOL_DATA_CLASS_VIOLATION,
    TOOL_EGRESS_DENIED,
    TOOL_EGRESS_LIMIT_EXCEEDED,
    ToolSandbox,
    check_output_with_policy,
    load_tool_boundary_policy,
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
    "ToolExecutionConfigurationError",
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

"""
Tool execution safety wrapper: non-fatal execution, canonical failure semantics.

Wraps tool execution in a single choke point with exception capture, timeout,
and output schema validation. Converts failures into structured (ok, result, error)
without propagating malformed outputs or crashing the run.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from labtrust_gym.tools.registry import get_tool_entry

# Reason codes (must exist in policy/reason_codes/reason_code_registry.v0.1.yaml)
TOOL_EXEC_EXCEPTION = "TOOL_EXEC_EXCEPTION"
TOOL_TIMEOUT = "TOOL_TIMEOUT"
TOOL_OUTPUT_MALFORMED = "TOOL_OUTPUT_MALFORMED"
# Sandbox/boundary (from tools.sandbox)
TOOL_EGRESS_DENIED = "TOOL_EGRESS_DENIED"
TOOL_EGRESS_LIMIT_EXCEEDED = "TOOL_EGRESS_LIMIT_EXCEEDED"
TOOL_DATA_CLASS_VIOLATION = "TOOL_DATA_CLASS_VIOLATION"

# Default timeout when none specified (seconds); use a small value for determinism in tests.
DEFAULT_TOOL_TIMEOUT_S = 30.0


def _default_stub_adapter(tool_id: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Stub adapter when no adapter is provided: returns empty dict (safe no-op)."""
    return {}


def _load_output_schema(ref: str, policy_root: Path) -> Dict[str, Any]:
    """Load JSON schema from policy_root/policy/ref."""
    path = Path(policy_root) / "policy" / ref
    if not path.is_file():
        raise FileNotFoundError(f"output schema not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_output_against_schema(
    result: Any, schema: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """Validate result against JSON schema. Returns (valid, error_message)."""
    try:
        import jsonschema

        jsonschema.validate(instance=result, schema=schema)
        return True, None
    except Exception as e:
        msg = getattr(e, "message", str(e))
        return False, str(msg) if msg else str(e)


def execute_tool_safely(
    tool_id: str,
    args: Dict[str, Any],
    *,
    adapter: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    registry: Optional[Dict[str, Any]] = None,
    policy_root: Optional[Path] = None,
    timeout_s: Optional[float] = None,
    output_schema_ref: Optional[str] = None,
    sandbox_ctx: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, Any, Optional[Dict[str, Any]]]:
    """
    Execute a tool in a safe wrapper: exception capture, timeout, output validation.

    Returns:
        (ok, tool_result, tool_error)
        - ok: True if execution succeeded and output passed validation.
        - tool_result: adapter return value (or {} on failure).
        - tool_error: When ok is False, dict with reason_code, message, and optional details.

    Uses a stub adapter (returns {}) when adapter is None so runs never crash.
    """
    if adapter is None:
        adapter = _default_stub_adapter
    if timeout_s is None:
        timeout_s = DEFAULT_TOOL_TIMEOUT_S
    sandbox_ctx = sandbox_ctx or {}

    result_holder: list = []
    exc_holder: list = []

    def run() -> None:
        try:
            out = adapter(tool_id, args)
            result_holder.append(out)
        except Exception as e:
            exc_holder.append(e)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=timeout_s)

    if exc_holder:
        e = exc_holder[0]
        return (
            False,
            {},
            {
                "reason_code": TOOL_EXEC_EXCEPTION,
                "message": str(e),
                "details": {"exception_type": type(e).__name__},
            },
        )

    if thread.is_alive():
        return (
            False,
            {},
            {
                "reason_code": TOOL_TIMEOUT,
                "message": f"Tool {tool_id!r} exceeded timeout {timeout_s}s",
                "details": {"timeout_s": timeout_s},
            },
        )

    if not result_holder:
        return (
            False,
            {},
            {
                "reason_code": TOOL_OUTPUT_MALFORMED,
                "message": "Tool returned no result",
                "details": None,
            },
        )

    result = result_holder[0]

    # Minimal structural check: result must be a dict (canonical tool output shape).
    if not isinstance(result, dict):
        return (
            False,
            result,
            {
                "reason_code": TOOL_OUTPUT_MALFORMED,
                "message": f"Tool output must be a dict, got {type(result).__name__}",
                "details": None,
            },
        )

    # Optional: validate against output schema from registry or explicit ref.
    schema_ref = output_schema_ref
    if schema_ref is None and registry and policy_root:
        entry = get_tool_entry(registry, tool_id)
        if entry:
            schema_ref = entry.get("output_schema_ref") or None
    if schema_ref and policy_root:
        try:
            schema = _load_output_schema(schema_ref, Path(policy_root))
            valid, err_msg = _validate_output_against_schema(result, schema)
            if not valid:
                return (
                    False,
                    result,
                    {
                        "reason_code": TOOL_OUTPUT_MALFORMED,
                        "message": err_msg or "Output schema validation failed",
                        "details": None,
                    },
                )
        except FileNotFoundError:
            pass  # Schema file missing; skip output validation
        except (json.JSONDecodeError, ValueError):
            pass  # Invalid schema; skip

    # Sandbox / boundary: deny-by-default egress, byte/record caps, data classification.
    sandbox = (sandbox_ctx or {}).get("sandbox")
    if sandbox is not None:
        allowed, boundary_reason, boundary_details = sandbox.check_output(
            result, tool_id_override=tool_id
        )
        if not allowed and boundary_reason:
            return (
                False,
                result,
                {
                    "reason_code": boundary_reason,
                    "message": (
                        boundary_details.get("message", boundary_reason)
                        if boundary_details
                        else boundary_reason
                    ),
                    "details": boundary_details,
                },
            )

    return True, result, None

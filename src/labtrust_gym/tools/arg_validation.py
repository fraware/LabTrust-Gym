"""
Tool argument validation: typed and range-checked tool calls.

Every tool entry in the registry must point to an argument schema (arg_schema_ref).
Invalid or out-of-range args are blocked deterministically before tool execution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Reason codes (must exist in policy/reason_codes/reason_code_registry.v0.1.yaml)
TOOL_ARG_SCHEMA_FAIL = "TOOL_ARG_SCHEMA_FAIL"
TOOL_ARG_RANGE_FAIL = "TOOL_ARG_RANGE_FAIL"

# JSON Schema keywords that represent range/semantic constraints (not structural)
_RANGE_KEYWORDS = frozenset(
    {
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "minProperties",
        "maxProperties",
    }
)


def load_arg_schema(ref: str, policy_root: Path) -> Dict[str, Any]:
    """
    Load the argument schema for a tool from policy.

    ref: relative path from policy dir (e.g. "tool_args/read_lims_v1.args.v0.1.schema.json").
    policy_root: repo root such that policy_root / "policy" contains policy files.

    Returns the parsed JSON schema dict.
    Raises FileNotFoundError if the file does not exist, ValueError on invalid JSON.
    """
    path = Path(policy_root) / "policy" / ref
    if not path.is_file():
        raise FileNotFoundError(f"arg schema not found: {path}")
    text = path.read_text(encoding="utf-8")
    return json.loads(text)


def _is_range_error(validation_error: Any) -> bool:
    """Return True if the ValidationError is due to a range/keyword constraint."""
    keyword = getattr(validation_error, "validator", None)
    if keyword is not None:
        return keyword in _RANGE_KEYWORDS
    # jsonschema: error.validator is the keyword that failed
    return False


def _collect_range_errors(error: Any) -> bool:
    """Return True if any error in the tree is a range error."""
    if _is_range_error(error):
        return True
    for sub in getattr(error, "context", []):
        if _collect_range_errors(sub):
            return True
    return False


def validate_tool_args(
    tool_id: str,
    args: Any,
    registry: Dict[str, Any],
    policy_root: Optional[Path],
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate tool call arguments against the tool's arg_schema_ref.

    Runs after TOOL_NOT_IN_REGISTRY / allowlist checks. Call only when the tool
    is already allowed.

    Returns:
        (ok, reason_code, details)
        - ok: True if validation passed.
        - reason_code: TOOL_ARG_SCHEMA_FAIL or TOOL_ARG_RANGE_FAIL when blocked.
        - details: short message for logging (optional).

    When the tool has no arg_schema_ref or policy_root is missing, returns
    (False, TOOL_ARG_SCHEMA_FAIL, details).
    """
    from labtrust_gym.tools.registry import get_tool_entry

    entry = get_tool_entry(registry, tool_id)
    if entry is None:
        return False, TOOL_ARG_SCHEMA_FAIL, "tool not in registry"

    ref = entry.get("arg_schema_ref")
    if not ref or (isinstance(ref, str) and not ref.strip()):
        return False, TOOL_ARG_SCHEMA_FAIL, "missing arg_schema_ref"

    if policy_root is None:
        return False, TOOL_ARG_SCHEMA_FAIL, "policy_root not set"

    try:
        schema = load_arg_schema(ref.strip(), Path(policy_root))
    except FileNotFoundError as e:
        return False, TOOL_ARG_SCHEMA_FAIL, str(e)
    except (json.JSONDecodeError, ValueError) as e:
        return False, TOOL_ARG_SCHEMA_FAIL, f"invalid schema: {e}"

    # Normalize args: must be a dict for schema validation
    if not isinstance(args, dict):
        return False, TOOL_ARG_SCHEMA_FAIL, "args must be an object"

    try:
        import jsonschema

        jsonschema.validate(instance=args, schema=schema)
        return True, None, None
    except Exception as e:
        # Classify ValidationError as range vs schema
        err_name = type(e).__name__
        if err_name == "ValidationError":
            has_range = _collect_range_errors(e)
            reason = TOOL_ARG_RANGE_FAIL if has_range else TOOL_ARG_SCHEMA_FAIL
            msg = getattr(e, "message", str(e))
            if msg is None:
                msg = str(e)
            return False, reason, str(msg)
        return False, TOOL_ARG_SCHEMA_FAIL, str(e)

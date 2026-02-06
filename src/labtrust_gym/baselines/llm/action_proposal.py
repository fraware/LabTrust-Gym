"""
ActionProposal v0.1 schema loading and validation for LLM baseline pipeline.

- load_action_proposal_schema: load policy/schemas/action_proposal.v0.1.schema.json.
- validate_action_proposal_dict: validate dict against schema; return
  (ok, normalized, error_reason). Uses jsonschema (same as policy validation).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

# Keys allowed by action_proposal.v0.1 (envelope only)
ACTION_PROPOSAL_KEYS = (
    "action_type",
    "args",
    "reason_code",
    "token_refs",
    "rationale",
    "confidence",
    "safety_notes",
)


def load_action_proposal_schema(path: Path | None = None) -> dict[str, Any]:
    """Load action_proposal.v0.1.schema.json for ActionProposal envelope."""
    if path is None:
        path = Path("policy/schemas/action_proposal.v0.1.schema.json")
    if not path.exists():
        return {}
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def validate_action_proposal_dict(
    d: dict[str, Any],
    schema: dict[str, Any] | None = None,
) -> tuple[bool, dict[str, Any] | None, str | None]:
    """
    Validate dict against ActionProposal v0.1 schema.

    Returns:
        (ok, normalized, error_reason)
        - ok: True if valid.
        - normalized: when ok, dict with only schema-defined keys; when not ok, None.
        - error_reason: when not ok, short reason (e.g. LLM_INVALID_SCHEMA); when ok, None.
    """
    if schema is None:
        schema = load_action_proposal_schema()
    if not schema:
        return (False, None, "ActionProposal schema not loaded")
    if not isinstance(d, dict):
        return (False, None, "Expected dict")
    try:
        import jsonschema

        jsonschema.validate(instance=d, schema=schema)
    except jsonschema.ValidationError as e:
        msg = getattr(e, "message", str(e))
        return (False, None, msg or "ValidationError")
    except Exception as e:
        return (False, None, str(e))
    # Normalized: only envelope keys for downstream
    normalized = {k: d[k] for k in ACTION_PROPOSAL_KEYS if k in d}
    return (True, normalized, None)

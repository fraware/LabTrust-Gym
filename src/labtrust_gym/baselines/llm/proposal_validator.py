"""
Deterministic validator for LLM proposals (2-stage: propose then validate).

- validate_proposal_deterministic: action in allowed_actions, args schema hint,
  optional pre-checks (token presence hint, device co-location hint).
- Returns (valid, structured_errors); structured_errors are short, non-sensitive
  strings for repair prompt only (no PII, no raw schema dumps).
"""

from __future__ import annotations

from typing import Any

RC_LLM_PROPOSED_INVALID = "RC_LLM_PROPOSED_INVALID"

# Required args by action_type (aligned with allowed_actions_payload)
_REQUIRED_ARGS: dict[str, set[str]] = {
    "NOOP": set(),
    "TICK": set(),
    "QUEUE_RUN": {"device_id", "work_id", "priority_class"},
    "MOVE": {"from_zone", "to_zone"},
    "OPEN_DOOR": {"door_id"},
    "START_RUN": {"device_id"},
}


def validate_proposal_deterministic(
    proposal: dict[str, Any],
    allowed_actions: list[str],
    policy_summary: dict[str, Any] | None = None,
    allowed_actions_payload: list[dict[str, Any]] | None = None,
) -> tuple[bool, list[str]]:
    """
    Deterministic validation of an LLM proposal (stage 2 after propose).

    Checks:
    1) action_type exists in allowed_actions.
    2) args schema hint: required keys for that action_type present in args.
    3) Optional pre-checks: token presence hint, device co-location hint.

    Returns (valid, structured_errors). structured_errors are short, non-sensitive
    messages only (for repair prompt); no raw schema or PII.
    """
    errors: list[str] = []
    if not isinstance(proposal, dict):
        return (False, ["proposal must be a dict"])
    action_type = (proposal.get("action_type") or "NOOP").strip()
    args = proposal.get("args")
    if not isinstance(args, dict):
        args = {}

    # 1) action in allowed_actions
    if not isinstance(allowed_actions, list) or len(allowed_actions) == 0:
        pass  # no constraint
    elif action_type not in allowed_actions:
        errors.append("action_type not in allowed_actions")

    # 2) args schema hint (required keys for action_type)
    required = _REQUIRED_ARGS.get(action_type, set())
    for key in required:
        if key not in args or args[key] is None:
            errors.append(f"args.{key} required for {action_type}")

    # 3) Optional: token presence hint (OPEN_DOOR often needs token_refs)
    if action_type == "OPEN_DOOR" and policy_summary:
        strict_tokens = policy_summary.get("token_required_for_door") or policy_summary.get(
            "restricted_door_requires_token"
        )
        if strict_tokens:
            token_refs = proposal.get("token_refs") or []
            if not isinstance(token_refs, list) or len(token_refs) == 0:
                errors.append("OPEN_DOOR requires token_refs when door is restricted")

    # 4) Optional: device co-location hint (START_RUN: device_id in queue_head)
    if action_type == "START_RUN" and policy_summary:
        queue_head = policy_summary.get("queue_head") or {}
        if isinstance(queue_head, dict) and queue_head:
            device_id = args.get("device_id")
            if device_id is not None and queue_head.get(device_id) is None:
                errors.append("args.device_id for START_RUN not in queue_head")

    valid = len(errors) == 0
    return (valid, errors)

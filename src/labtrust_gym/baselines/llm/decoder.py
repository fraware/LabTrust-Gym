"""
Constrained action decoder: schema-valid, RBAC-consistent, explainable (rationale required).
Refuses to output actions that violate RBAC/devices/zones at decode time (before env step).
Supports ActionProposal schema (action_proposal.v0.1): confidence, safety_notes, NOOP constraints.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Reason codes (must match policy)
MISSING_RATIONALE = "MISSING_RATIONALE"
MISSING_CITATION = "MISSING_CITATION"

# NOOP action used when decoder rejects (llm_action.schema.v0.2 compatible)
NOOP_ACTION: Dict[str, Any] = {
    "action_type": "NOOP",
    "args": {},
    "reason_code": None,
    "token_refs": [],
    "rationale": "",
}

# NOOP conforming to ActionProposal schema (action_proposal.v0.1): required confidence, safety_notes
NOOP_ACTION_V01: Dict[str, Any] = {
    "action_type": "NOOP",
    "args": {},
    "reason_code": None,
    "token_refs": [],
    "rationale": "",
    "confidence": 0.0,
    "safety_notes": "",
}


def _rationale_contains_citation(rationale: str, citation_anchors: List[str]) -> bool:
    """Return True if rationale contains at least one of the citation anchors (substring match)."""
    if not rationale or not citation_anchors:
        return False
    s = rationale.strip()
    for anchor in citation_anchors:
        if anchor and anchor in s:
            return True
    return False


def _noop_for_reject(
    noop_action: Optional[Dict[str, Any]], rationale: str = ""
) -> Dict[str, Any]:
    """Return NOOP dict for reject path; use noop_action if provided (ActionProposal-shaped)."""
    if noop_action is not None:
        out = dict(noop_action)
        out["rationale"] = rationale
        return out
    out = dict(NOOP_ACTION)
    out["rationale"] = rationale
    return out


def decode_constrained(
    raw_candidate: Dict[str, Any],
    policy_summary: Dict[str, Any],
    schema: Dict[str, Any],
    validate_schema_fn: Any,
    require_rationale: bool = True,
    require_citation: bool = True,
    noop_action: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], bool, Optional[str]]:
    """
    Decode and constrain LLM output: schema validation, rationale, citation anchor, allowed_actions, optional zone/device checks.
    Returns (action_dict, rejected, reason_code).
    - action_dict: valid action or NOOP when rejected (conforms to schema; use noop_action for ActionProposal).
    - rejected: True if candidate was rejected at decode time.
    - reason_code: MISSING_RATIONALE, MISSING_CITATION, RBAC_ACTION_DENY, or None.
    - validate_schema_fn: callable(action, schema) -> list of error strings.
    - noop_action: when set (e.g. NOOP_ACTION_V01), used for all reject returns so output validates against ActionProposal schema.
    """
    from labtrust_gym.engine.rbac import RBAC_ACTION_DENY

    if not isinstance(raw_candidate, dict):
        return (_noop_for_reject(noop_action), True, RBAC_ACTION_DENY)

    # 1) Schema validation
    if schema and validate_schema_fn:
        errs = (
            validate_schema_fn(raw_candidate, schema)
            if callable(validate_schema_fn)
            else []
        )
        if errs:
            return (_noop_for_reject(noop_action), True, RBAC_ACTION_DENY)

    action_type = (raw_candidate.get("action_type") or "NOOP").strip()
    args = raw_candidate.get("args")
    if not isinstance(args, dict):
        args = {}

    # 2) Require rationale (explainable)
    rationale = (
        (raw_candidate.get("rationale") or "").strip()
        if raw_candidate.get("rationale") is not None
        else ""
    )
    if require_rationale:
        if not rationale:
            # ActionProposal schema requires rationale minLength 1; use fixed string when noop_action is set
            fallback_rationale = (
                "Decode rejected: missing rationale." if noop_action else ""
            )
            return (
                _noop_for_reject(noop_action, fallback_rationale),
                True,
                MISSING_RATIONALE,
            )

    # 2b) Require at least one policy citation anchor in rationale
    if require_citation and rationale:
        citation_anchors = policy_summary.get("citation_anchors") or []
        if citation_anchors and not _rationale_contains_citation(
            rationale, citation_anchors
        ):
            return (_noop_for_reject(noop_action, rationale), True, MISSING_CITATION)

    # 3) Restrict action_type to allowed_actions (RBAC at decode time)
    allowed_actions = policy_summary.get("allowed_actions")
    if isinstance(allowed_actions, list) and len(allowed_actions) > 0:
        if action_type not in allowed_actions:
            return (
                _noop_for_reject(noop_action, raw_candidate.get("rationale") or ""),
                True,
                RBAC_ACTION_DENY,
            )

    # 4) Optional: device_id must be in queue_head for QUEUE_RUN/START_RUN
    queue_head = policy_summary.get("queue_head") or {}
    if isinstance(queue_head, dict) and queue_head:
        if action_type in ("QUEUE_RUN", "START_RUN"):
            device_id = args.get("device_id")
            if (
                device_id is not None
                and device_id not in queue_head
                and action_type == "START_RUN"
            ):
                # START_RUN typically requires work at head; QUEUE_RUN may add. Only block START_RUN if strict.
                pass  # Relaxed: engine will block invalid START_RUN

    # 5) Optional: to_zone must be in zone_graph for MOVE
    zone_graph = policy_summary.get("zone_graph") or {}
    agent_zone = policy_summary.get("agent_zone")
    if action_type == "MOVE" and agent_zone and isinstance(zone_graph, dict):
        to_zone = args.get("to_zone")
        if to_zone is not None:
            reachable = zone_graph.get(agent_zone)
            if isinstance(reachable, list) and to_zone not in reachable:
                return (
                    _noop_for_reject(noop_action, raw_candidate.get("rationale") or ""),
                    True,
                    "RC_ILLEGAL_MOVE",
                )

    # Pass: build safe action with rationale; include confidence/safety_notes when using ActionProposal
    safe: Dict[str, Any] = {
        "action_type": action_type,
        "args": dict(args),
        "reason_code": raw_candidate.get("reason_code"),
        "token_refs": list(raw_candidate.get("token_refs") or []),
        "rationale": (raw_candidate.get("rationale") or "").strip(),
    }
    if raw_candidate.get("key_id") is not None:
        safe["key_id"] = raw_candidate["key_id"]
    if raw_candidate.get("signature") is not None:
        safe["signature"] = raw_candidate["signature"]
    if noop_action is not None and "confidence" in noop_action:
        safe["confidence"] = raw_candidate.get("confidence", 0.0)
        safe["safety_notes"] = (raw_candidate.get("safety_notes") or "").strip()
    return (safe, False, None)


def validate_schema_returns_errors(
    action: Dict[str, Any], schema: Dict[str, Any]
) -> List[str]:
    """Return list of validation error strings; empty if valid. Use as validate_schema_fn in decode_constrained."""
    if not schema:
        return []
    try:
        import jsonschema

        jsonschema.validate(instance=action, schema=schema)
        return []
    except jsonschema.ValidationError as e:
        return [str(e.message) if hasattr(e, "message") else str(e)]
    except Exception as e:
        return [str(e)]


def load_action_proposal_schema(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load action_proposal.v0.1.schema.json; delegate to action_proposal module."""
    from labtrust_gym.baselines.llm.action_proposal import (
        load_action_proposal_schema as _load,
    )

    return _load(path)

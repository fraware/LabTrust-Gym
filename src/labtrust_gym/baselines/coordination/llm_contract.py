"""
Typed CoordinationProposal contract for LLM-based coordination methods.

- JSON schema validation (policy/schemas/coordination_proposal.v0.1.schema.json).
- validate_proposal(proposal_dict, ...) with optional allowed_actions and strict
  reason_code registry checks.
- canonical_json(proposal_dict) for hashing/fingerprinting.
- Dataclasses: Proposal, PerAgentAction, MessageIntent, BidIntent (mirror schema).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import jsonschema
except ImportError:
    jsonschema = None  # type: ignore[assignment]


def _load_schema(schema_path: Path | None = None) -> dict[str, Any]:
    """Load coordination_proposal.v0.1 schema from policy/schemas or given path."""
    if schema_path is not None and schema_path.is_file():
        return json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        from labtrust_gym.config import get_repo_root

        root = get_repo_root()
        path = root / "policy" / "schemas" / "coordination_proposal.v0.1.schema.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def canonical_json(proposal_dict: dict[str, Any]) -> str:
    """
    Canonical JSON string for proposal (deterministic hashing/fingerprinting).
    sort_keys=True, separators=(',', ':'), no trailing whitespace.
    """
    return json.dumps(proposal_dict, sort_keys=True, separators=(",", ":"))


def validate_proposal(
    proposal_dict: dict[str, Any],
    *,
    allowed_actions: list[str] | None = None,
    reason_code_registry: dict[str, dict[str, Any]] | None = None,
    strict_reason_codes: bool = False,
    strict_unknown_keys: bool = True,
    schema_path: Path | None = None,
) -> tuple[bool, list[str]]:
    """
    Validate proposal against coordination_proposal.v0.1 schema and optional rules.

    - Schema: required fields, types, no extra top-level keys when strict_unknown_keys.
    - If allowed_actions is provided, every per_agent.action_type must be in it.
    - If strict_reason_codes and reason_code_registry provided, every per_agent.reason_code
      must exist in the registry.
    Returns (valid, list of error messages).
    """
    errors: list[str] = []

    if jsonschema is None:
        errors.append("jsonschema required for proposal validation")
        return (False, errors)

    schema = _load_schema(schema_path)
    if not schema:
        errors.append("coordination_proposal.v0.1 schema not found")
        return (False, errors)

    # Schema validation (includes additionalProperties: false when in schema)
    try:
        jsonschema.validate(instance=proposal_dict, schema=schema)
    except jsonschema.ValidationError as e:
        errors.append(str(e))
        return (False, errors)

    # Optional: action_type in allowed set (from env / allowed_actions_payload)
    if allowed_actions is not None and len(allowed_actions) > 0:
        for i, pa in enumerate(proposal_dict.get("per_agent") or []):
            if not isinstance(pa, dict):
                continue
            action_type = (pa.get("action_type") or "").strip()
            if action_type and action_type not in allowed_actions:
                errors.append(
                    f"per_agent[{i}].action_type {action_type!r} not in allowed_actions"
                )

    # Optional: reason_code in registry when strict
    if strict_reason_codes and reason_code_registry is not None:
        for i, pa in enumerate(proposal_dict.get("per_agent") or []):
            if not isinstance(pa, dict):
                continue
            reason_code = (pa.get("reason_code") or "").strip()
            if not reason_code:
                errors.append(f"per_agent[{i}].reason_code missing (required in strict)")
            elif reason_code not in reason_code_registry:
                errors.append(
                    f"per_agent[{i}].reason_code {reason_code!r} not in "
                    "reason_code_registry"
                )

    # args must be object (schema already enforces; double-check)
    for i, pa in enumerate(proposal_dict.get("per_agent") or []):
        if not isinstance(pa, dict):
            continue
        args = pa.get("args")
        if args is not None and not isinstance(args, dict):
            errors.append(f"per_agent[{i}].args must be object")

    valid = len(errors) == 0
    return (valid, errors)


# --- Dataclasses (mirror schema for type-safe use) ---


@dataclass
class PerAgentAction:
    """One agent's proposed action in a coordination proposal."""

    agent_id: str
    action_type: str
    args: dict[str, Any]
    reason_code: str
    confidence: float | None = None
    token_refs: list[str] | None = None


@dataclass
class MessageIntent:
    """One proposed message in comms array."""

    from_agent_id: str
    channel: str
    payload_typed: dict[str, Any]
    intent: str
    ttl_steps: int
    to_agent_id: str | None = None
    broadcast: bool | None = None


@dataclass
class BidIntent:
    """One market bid entry (optional)."""

    agent_id: str
    bid: Any = None
    bundle: Any = None
    constraints: dict[str, Any] | None = None


@dataclass
class ProposalMeta:
    """Audit meta for the proposal (backend, model, tokens, latency)."""

    prompt_fingerprint: str | None = None
    policy_fingerprint: str | None = None
    backend_id: str | None = None
    model_id: str | None = None
    latency_ms: float | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None


@dataclass
class Proposal:
    """Full coordination proposal (typed view over validated dict)."""

    proposal_id: str
    step_id: int
    method_id: str
    per_agent: list[PerAgentAction]
    comms: list[MessageIntent]
    meta: ProposalMeta
    horizon_steps: int = 1
    market: list[BidIntent] = field(default_factory=list)


def proposal_from_dict(d: dict[str, Any]) -> Proposal:
    """Build Proposal dataclass from validated proposal dict."""
    per_agent: list[PerAgentAction] = []
    for pa in d.get("per_agent") or []:
        if not isinstance(pa, dict):
            continue
        per_agent.append(
            PerAgentAction(
                agent_id=str(pa.get("agent_id", "")),
                action_type=str(pa.get("action_type", "")),
                args=dict(pa.get("args") or {}),
                reason_code=str(pa.get("reason_code", "")),
                confidence=pa.get("confidence"),
                token_refs=pa.get("token_refs"),
            )
        )
    comms: list[MessageIntent] = []
    for c in d.get("comms") or []:
        if not isinstance(c, dict):
            continue
        comms.append(
            MessageIntent(
                from_agent_id=str(c.get("from_agent_id", "")),
                channel=str(c.get("channel", "")),
                payload_typed=dict(c.get("payload_typed") or {}),
                intent=str(c.get("intent", "")),
                ttl_steps=int(c.get("ttl_steps", 0)),
                to_agent_id=c.get("to_agent_id"),
                broadcast=c.get("broadcast"),
            )
        )
    market: list[BidIntent] = []
    for m in d.get("market") or []:
        if not isinstance(m, dict):
            continue
        market.append(
            BidIntent(
                agent_id=str(m.get("agent_id", "")),
                bid=m.get("bid"),
                bundle=m.get("bundle"),
                constraints=m.get("constraints"),
            )
        )
    meta_d = d.get("meta") or {}
    meta = ProposalMeta(
        prompt_fingerprint=meta_d.get("prompt_fingerprint"),
        policy_fingerprint=meta_d.get("policy_fingerprint"),
        backend_id=meta_d.get("backend_id"),
        model_id=meta_d.get("model_id"),
        latency_ms=meta_d.get("latency_ms"),
        tokens_in=meta_d.get("tokens_in"),
        tokens_out=meta_d.get("tokens_out"),
    )
    return Proposal(
        proposal_id=str(d.get("proposal_id", "")),
        step_id=int(d.get("step_id", 0)),
        method_id=str(d.get("method_id", "")),
        per_agent=per_agent,
        comms=comms,
        meta=meta,
        horizon_steps=int(d.get("horizon_steps", 1)),
        market=market,
    )

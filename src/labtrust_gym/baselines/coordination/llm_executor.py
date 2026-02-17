"""
Generic executor for CoordinationProposal: runs proposal through deterministic
shield and env.step; produces ExecutionReport. Supports repair loop with
RepairRequest. All outcomes reason-coded and auditable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from labtrust_gym.baselines.coordination.interface import (
    ACTION_NOOP,
    ACTION_MOVE,
    ACTION_OPEN_DOOR,
    ACTION_QUEUE_RUN,
    ACTION_START_RUN,
    ACTION_TICK,
)
from labtrust_gym.baselines.coordination.llm_contract import canonical_json

# Action type string -> action index (align with pz_parallel and interface)
ACTION_TYPE_TO_INDEX: dict[str, int] = {
    "NOOP": ACTION_NOOP,
    "TICK": ACTION_TICK,
    "QUEUE_RUN": ACTION_QUEUE_RUN,
    "MOVE": ACTION_MOVE,
    "OPEN_DOOR": ACTION_OPEN_DOOR,
    "START_RUN": ACTION_START_RUN,
}


def _proposal_hash(proposal_dict: dict[str, Any]) -> str:
    """Deterministic hash of canonical proposal JSON."""
    raw = canonical_json(proposal_dict)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _repair_request_hash(repair_request: dict[str, Any]) -> str:
    """Deterministic hash of canonical repair request JSON."""
    raw = json.dumps(repair_request, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _shield_outcome_hash(executed: list[dict], blocked: list[dict]) -> str:
    """Deterministic hash of shield outcome (executed + blocked lists)."""
    payload = {"executed": executed, "blocked": blocked}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def shield_outcome_hash_from_step_results(
    step_results: list[dict[str, Any]],
    agent_ids: list[str],
) -> str:
    """
    Build (executed, blocked) from step_results and agent list, return shield outcome hash.
    step_results is aligned with agent_ids: first len(agent_ids) entries are one per agent.
    Used by the runner after env.step to set shield_outcome_hash on LLM_COORD_PROPOSAL and audit.
    """
    executed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    n = min(len(step_results), len(agent_ids))
    for i in range(n):
        result = step_results[i]
        agent_id = agent_ids[i]
        status = result.get("status", "")
        blocked_rc = result.get("blocked_reason_code")
        action_type = result.get("action_type") or "NOOP"
        args = result.get("args") if isinstance(result.get("args"), dict) else {}
        if status == "BLOCKED" or blocked_rc:
            blocked.append({
                "agent_id": agent_id,
                "action_type": action_type,
                "blocked_reason_code": str(blocked_rc) if blocked_rc else "",
            })
        else:
            executed.append({
                "agent_id": agent_id,
                "action_type": action_type,
                "args": args,
            })
    return _shield_outcome_hash(executed, blocked)


@dataclass
class ExecutionReport:
    """Outcome of execute_proposal: executed, blocked, violations, comms."""

    executed_actions: list[dict[str, Any]] = field(default_factory=list)
    blocked_actions: list[dict[str, Any]] = field(default_factory=list)
    invariant_violations_delta: list[dict[str, Any]] = field(
        default_factory=list
    )
    enforcement_actions_triggered: list[dict[str, Any]] = field(
        default_factory=list
    )
    comms_delivered_count: int = 0
    comms_dropped_count: int = 0
    per_agent_outcome: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )
    proposal_hash: str = ""
    shield_outcome_hash: str = ""
    step_results: list[dict[str, Any]] = field(default_factory=list)
    proposal_meta: dict[str, Any] = field(default_factory=dict)


def _per_agent_list_to_dict(
    per_agent: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Index per_agent by agent_id for lookup."""
    out: dict[str, dict[str, Any]] = {}
    for pa in per_agent or []:
        if not isinstance(pa, dict):
            continue
        aid = pa.get("agent_id")
        if aid is not None and isinstance(aid, str):
            out[aid] = dict(pa)
    return out


def _proposal_to_actions_and_infos(
    proposal_dict: dict[str, Any],
    env_agents: list[str],
    shield: Callable[..., tuple[dict[str, Any], bool, str | None]],
    rbac_policy: dict[str, Any],
    policy_summary: dict[str, Any],
    capability_profile: dict[str, Any] | None,
) -> tuple[dict[str, int], dict[str, dict[str, Any]], list[dict], list[dict]]:
    """
    Convert proposal per_agent through shield to (actions, action_infos).
    Returns (actions, action_infos, executed_list, blocked_list).
    """
    per_agent_by_id = _per_agent_list_to_dict(proposal_dict.get("per_agent") or [])
    actions: dict[str, int] = {}
    action_infos: dict[str, dict[str, Any]] = {}
    executed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for agent_id in env_agents:
        pa = per_agent_by_id.get(agent_id)
        if not pa:
            action_type = "NOOP"
            args: dict[str, Any] = {}
            reason_code = None
            token_refs: list[str] = []
        else:
            action_type = (pa.get("action_type") or "NOOP").strip()
            args = dict(pa.get("args") or {})
            reason_code = pa.get("reason_code")
            token_refs = list(pa.get("token_refs") or [])

        candidate: dict[str, Any] = {
            "action_type": action_type,
            "args": args,
            "reason_code": reason_code,
            "token_refs": token_refs,
        }
        safe_action, filtered, block_reason = shield(
            candidate,
            agent_id,
            rbac_policy,
            policy_summary,
            capability_profile,
        )
        at_key = (safe_action.get("action_type") or "NOOP").strip()
        action_index = ACTION_TYPE_TO_INDEX.get(at_key, ACTION_NOOP)
        actions[agent_id] = action_index
        info: dict[str, Any] = {
            "action_type": safe_action.get("action_type", "NOOP"),
            "args": safe_action.get("args") or {},
            "reason_code": safe_action.get("reason_code"),
        }
        if safe_action.get("token_refs"):
            info["token_refs"] = safe_action["token_refs"]
        if filtered and block_reason:
            info["_shield_filtered"] = True
            info["_shield_reason_code"] = block_reason
            blocked.append(
                {
                    "agent_id": agent_id,
                    "action_type": action_type,
                    "blocked_reason_code": block_reason,
                }
            )
        else:
            executed.append(
                {
                    "agent_id": agent_id,
                    "action_type": safe_action.get("action_type", "NOOP"),
                    "args": info.get("args"),
                }
            )
        action_infos[agent_id] = info

    return actions, action_infos, executed, blocked


def execute_proposal(
    env: Any,
    proposal_dict: dict[str, Any],
    shield: Callable[..., tuple[dict[str, Any], bool, str | None]],
    rbac_policy: dict[str, Any],
    policy_summary: dict[str, Any],
    *,
    capability_profile: dict[str, Any] | None = None,
    strict: bool = True,
) -> ExecutionReport:
    """
    Execute a CoordinationProposal through the deterministic shield and env.step.

    Converts proposal per_agent to actions; runs each through shield;
    env.step(actions, action_infos); collects step_results and builds
    ExecutionReport. Does not mutate proposal_dict. Comms in proposal
    are not delivered by the core env; comms_delivered and comms_dropped
    are default counts unless integrated.
    """
    agents = getattr(env, "agents", None) or getattr(env, "possible_agents", [])
    if hasattr(agents, "__iter__") and not isinstance(agents, list):
        agents = list(agents)

    actions, action_infos, executed, blocked = _proposal_to_actions_and_infos(
        proposal_dict,
        agents,
        shield,
        rbac_policy,
        policy_summary,
        capability_profile,
    )
    obs, rewards, term, trunc, infos = env.step(actions, action_infos=action_infos)

    first_agent = agents[0] if agents else None
    step_results = list(
        (infos.get(first_agent) or {}).get("_benchmark_step_results", [])
        if first_agent
        else []
    )

    violations_delta: list[dict[str, Any]] = []
    enforcements: list[dict[str, Any]] = []
    per_agent_outcome: dict[str, dict[str, Any]] = {}
    for i, res in enumerate(step_results):
        agent_id = agents[i] if i < len(agents) else f"agent_{i}"
        status = res.get("status", "")
        blocked_rc = res.get("blocked_reason_code")
        vlist = res.get("violations") or []
        elist = res.get("enforcements") or []
        for v in vlist:
            violations_delta.append({**v, "agent_id": agent_id})
        for e in elist:
            enforcements.append({**e} if isinstance(e, dict) else {"raw": e})
        per_agent_outcome[agent_id] = {
            "status": status,
            "blocked_reason_code": blocked_rc,
            "violation_count": len(vlist),
        }

    comms = proposal_dict.get("comms") or []
    comms_attempted = len(comms)
    comms_delivered = 0
    comms_dropped = comms_attempted

    proposal_hash_val = _proposal_hash(proposal_dict)
    shield_outcome_hash_val = _shield_outcome_hash(executed, blocked)
    proposal_meta = {}
    for key in ("intent_confidence", "assumptions", "risk_flags"):
        if key in proposal_dict:
            proposal_meta[key] = proposal_dict[key]

    return ExecutionReport(
        executed_actions=executed,
        blocked_actions=blocked,
        invariant_violations_delta=violations_delta,
        enforcement_actions_triggered=enforcements,
        comms_delivered_count=comms_delivered,
        comms_dropped_count=comms_dropped,
        per_agent_outcome=per_agent_outcome,
        proposal_hash=proposal_hash_val,
        shield_outcome_hash=shield_outcome_hash_val,
        step_results=step_results,
        proposal_meta=proposal_meta,
    )


def execute_proposal_shield_only(
    env: Any,
    proposal_dict: dict[str, Any],
    shield: Callable[..., tuple[dict[str, Any], bool, str | None]],
    rbac_policy: dict[str, Any],
    policy_summary: dict[str, Any],
    *,
    capability_profile: dict[str, Any] | None = None,
) -> ExecutionReport:
    """
    Run proposal through the shield only; do not call env.step.
    Returns ExecutionReport with executed_actions, blocked_actions,
    shield_outcome_hash, proposal_hash. step_results and violations_delta
    are empty. Used by the repair loop when the runner will perform
    a single env.step after the loop.
    """
    agents = getattr(env, "agents", None) or getattr(env, "possible_agents", [])
    if hasattr(agents, "__iter__") and not isinstance(agents, list):
        agents = list(agents)

    actions, action_infos, executed, blocked = _proposal_to_actions_and_infos(
        proposal_dict,
        agents,
        shield,
        rbac_policy,
        policy_summary,
        capability_profile,
    )
    proposal_hash_val = _proposal_hash(proposal_dict)
    shield_outcome_hash_val = _shield_outcome_hash(executed, blocked)
    proposal_meta = {}
    for key in ("intent_confidence", "assumptions", "risk_flags"):
        if key in proposal_dict:
            proposal_meta[key] = proposal_dict[key]

    comms = proposal_dict.get("comms") or []
    comms_attempted = len(comms)

    return ExecutionReport(
        executed_actions=executed,
        blocked_actions=blocked,
        invariant_violations_delta=[],
        enforcement_actions_triggered=[],
        comms_delivered_count=0,
        comms_dropped_count=comms_attempted,
        per_agent_outcome={},
        proposal_hash=proposal_hash_val,
        shield_outcome_hash=shield_outcome_hash_val,
        step_results=[],
        proposal_meta=proposal_meta,
    )


# --- RepairRequest and repair loop ---


def build_repair_request(
    blocked_reason_codes: list[str],
    failed_validation_fields: list[str],
    state_digest: dict[str, Any],
) -> dict[str, Any]:
    """Build typed RepairRequest payload for coordinator retry."""
    return {
        "blocked_reason_codes": list(blocked_reason_codes),
        "failed_validation_fields": list(failed_validation_fields),
        "state_digest": dict(state_digest),
    }


def get_actions_from_proposal(
    env: Any,
    proposal_dict: dict[str, Any],
    shield: Callable[..., tuple[dict[str, Any], bool, str | None]],
    rbac_policy: dict[str, Any],
    policy_summary: dict[str, Any],
    capability_profile: dict[str, Any] | None = None,
) -> tuple[dict[str, int], dict[str, dict[str, Any]]]:
    """
    Convert proposal to (actions, action_infos) for env.step.
    Uses _proposal_to_actions_and_infos; returns only actions and action_infos.
    """
    agents = getattr(env, "agents", None) or getattr(env, "possible_agents", [])
    if hasattr(agents, "__iter__") and not isinstance(agents, list):
        agents = list(agents)
    actions, action_infos, _e, _b = _proposal_to_actions_and_infos(
        proposal_dict,
        agents,
        shield,
        rbac_policy,
        policy_summary,
        capability_profile,
    )
    return actions, action_infos


def run_proposal_with_repair(
    propose_fn: Callable[..., dict[str, Any]],
    env: Any,
    shield: Callable[..., tuple[dict[str, Any], bool, str | None]],
    rbac_policy: dict[str, Any],
    policy_summary: dict[str, Any],
    obs: dict[str, Any],
    infos: dict[str, dict[str, Any]],
    t: int,
    *,
    validate_fn: Callable[
        [dict[str, Any]], tuple[bool, list[str]]
    ] | None = None,
    capability_profile: dict[str, Any] | None = None,
    max_repairs: int = 1,
    blocked_threshold: int = 0,
    log_attempt_fn: Callable[[dict[str, Any]], None] | None = None,
    execute_fn: Callable[..., ExecutionReport] | None = None,
) -> tuple[dict[str, Any] | None, ExecutionReport | None, int]:
    """
    Get proposal from propose_fn, validate, execute; on failure build
    RepairRequest and retry up to max_repairs.
    Returns (final_proposal, report, attempt_count).

    propose_fn(obs, infos, t, repair_request=None) -> proposal_dict.
    validate_fn(proposal_dict) -> (valid, errors). If None, no validation.
    log_attempt_fn(record) called each attempt with attempt_index, hashes.
    execute_fn(env, proposal_dict, shield, rbac_policy, policy_summary, capability_profile=...)
    -> ExecutionReport. If None, uses execute_proposal (which calls env.step).
    Use execute_proposal_shield_only when the runner will perform env.step once after the loop.
    """
    repair_request: dict[str, Any] | None = None
    last_report: ExecutionReport | None = None
    attempt = 0
    max_attempts = 1 + max_repairs

    while attempt < max_attempts:
        proposal = propose_fn(obs, infos, t, repair_request=repair_request)
        if not proposal:
            return (None, last_report, attempt)

        attempt += 1
        proposal_hash_val = _proposal_hash(proposal)
        repair_request_hash_val = _repair_request_hash(repair_request) if repair_request else ""

        if validate_fn:
            valid, errors = validate_fn(proposal)
            if not valid:
                if log_attempt_fn:
                    log_attempt_fn(
                        {
                            "log_type": "LLM_COORD_PROPOSAL_ATTEMPT",
                            "attempt_index": attempt,
                            "proposal_id": proposal.get("proposal_id", ""),
                            "step_id": proposal.get("step_id", 0),
                            "proposal_hash": proposal_hash_val,
                            "repair_request_hash": repair_request_hash_val,
                            "shield_outcome_hash": "",
                            "validation_failed": True,
                            "failed_validation_fields": errors,
                        }
                    )
                repair_request = build_repair_request(
                    [],
                    errors,
                    {"step": t, "attempt": attempt},
                )
                continue

        if execute_fn is not None:
            report = execute_fn(
                env,
                proposal,
                shield,
                rbac_policy,
                policy_summary,
                capability_profile=capability_profile,
            )
        else:
            report = execute_proposal(
                env,
                proposal,
                shield,
                rbac_policy,
                policy_summary,
                capability_profile=capability_profile,
                strict=True,
            )
        last_report = report

        if log_attempt_fn:
            log_attempt_fn(
                {
                    "log_type": "LLM_COORD_PROPOSAL_ATTEMPT",
                    "attempt_index": attempt,
                    "proposal_id": proposal.get("proposal_id", ""),
                    "step_id": proposal.get("step_id", 0),
                    "proposal_hash": proposal_hash_val,
                    "repair_request_hash": repair_request_hash_val,
                    "shield_outcome_hash": report.shield_outcome_hash,
                    "validation_failed": False,
                    "blocked_count": len(report.blocked_actions),
                }
            )

        if len(report.blocked_actions) <= blocked_threshold:
            return (proposal, report, attempt)

        blocked_codes = [
            b.get("blocked_reason_code")
            for b in report.blocked_actions
            if b.get("blocked_reason_code")
        ]
        repair_request = build_repair_request(
            blocked_codes,
            [],
            {
                "step": t,
                "attempt": attempt,
                "blocked_count": len(report.blocked_actions),
            },
        )

    return (None, last_report, attempt)

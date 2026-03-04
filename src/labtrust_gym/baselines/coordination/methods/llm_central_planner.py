"""
Centralized LLM coordinator: receives global state digest, returns a
CoordinationProposal for all agents for the next step.

Uses state_digest.build_state_digest, a proposal backend (deterministic or live),
coordination_proposal schema validation, and converts proposal to actions_dict
for the runner. Supports metrics: tokens, latency, proposal validity rate,
blocked rate, repair rate. Repair loop (invalid proposal -> retry with repair
backend) is implemented in the executor/runner; max_repairs limits retries.
When detector is used (wrap_with_detector_advisor), probability_threshold and
cooldown_steps should be calibrated per deployment.

Envelope (SOTA audit):
  - Typical steps per episode: N/A; horizon-driven.
  - LLM calls per step: 1 (single proposal per step).
  - Fallback on timeout/refusal: NOOP for all agents.
  - max_latency_ms: N/A for live; bounded in llm_offline by deterministic backend.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

_LOG = logging.getLogger(__name__)

from labtrust_gym.baselines.coordination.interface import (
    ACTION_NOOP,
    CoordinationMethod,
)
from labtrust_gym.baselines.coordination.llm_contract import validate_proposal
from labtrust_gym.baselines.coordination.llm_executor import ACTION_TYPE_TO_INDEX
from labtrust_gym.baselines.coordination.state_digest import build_state_digest

COMMITTEE_ROLES = ("Allocator", "Scheduler", "Router", "Safety reviewer")


def _merge_committee_outputs(
    role_outputs: dict[str, dict[str, Any]],
    agent_ids: list[str],
) -> dict[str, Any]:
    """
    Merge per-role outputs into one proposal. Allocator provides primary per_agent;
    Scheduler/Router/Safety may override or veto. Deterministic merge order.
    """
    allocator = role_outputs.get("Allocator") or {}
    scheduler = role_outputs.get("Scheduler") or {}
    router = role_outputs.get("Router") or {}
    safety = role_outputs.get("Safety reviewer") or {}
    per_agent_alloc = allocator.get("per_agent") or []
    per_agent_sched = scheduler.get("per_agent") or []
    per_agent_router = router.get("per_agent") or []
    safety_veto = safety.get("veto_agent_ids") or []
    merged: list[dict[str, Any]] = []
    by_agent: dict[str, dict[str, Any]] = {a: {} for a in agent_ids}
    for pa in per_agent_alloc:
        if isinstance(pa, dict) and pa.get("agent_id") in agent_ids:
            by_agent[pa["agent_id"]] = dict(pa)
    for pa in per_agent_sched:
        if isinstance(pa, dict) and pa.get("agent_id") in by_agent:
            by_agent[pa["agent_id"]].update(pa)
    for pa in per_agent_router:
        if isinstance(pa, dict) and pa.get("agent_id") in by_agent:
            by_agent[pa["agent_id"]].update(pa)
    for aid in agent_ids:
        if aid in safety_veto:
            by_agent[aid] = {"agent_id": aid, "action_type": "NOOP", "args": {}}
        if by_agent[aid]:
            merged.append(by_agent[aid])
    return {
        "per_agent": merged,
        "proposal_id": allocator.get("proposal_id") or "committee",
        "step_id": allocator.get("step_id", 0),
        "method_id": allocator.get("method_id") or "llm_central_planner",
        "horizon_steps": allocator.get("horizon_steps", 1),
        "comms": [],
    }


def _arbiter_validate_committee(
    proposal_dict: dict[str, Any],
    allowed_actions: list[str],
) -> tuple[bool, list[str]]:
    """
    Deterministic arbiter: validate merged committee proposal.
    Returns (valid, list of reason codes). Used when backend provides role outputs.
    """
    valid, errors = validate_proposal(
        proposal_dict,
        allowed_actions=allowed_actions,
        strict_reason_codes=False,
    )
    return valid, errors


def _proposal_to_actions_dict(
    proposal_dict: dict[str, Any],
    agent_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Convert validated proposal per_agent to runner action_dict by agent_id."""
    out: dict[str, dict[str, Any]] = {a: {"action_index": ACTION_NOOP} for a in agent_ids}
    per_agent = proposal_dict.get("per_agent") or []
    for pa in per_agent:
        if not isinstance(pa, dict):
            continue
        agent_id = pa.get("agent_id")
        if agent_id not in out:
            continue
        action_type = (pa.get("action_type") or "NOOP").strip()
        args = pa.get("args")
        if not isinstance(args, dict):
            args = {}
        action_index = ACTION_TYPE_TO_INDEX.get(action_type, ACTION_NOOP)
        out[agent_id] = {
            "action_index": action_index,
            "action_type": action_type,
            "args": args,
            "reason_code": pa.get("reason_code"),
        }
        if pa.get("token_refs"):
            out[agent_id]["token_refs"] = pa["token_refs"]
        if pa.get("intent_confidence") is not None:
            out[agent_id]["intent_confidence"] = pa["intent_confidence"]
        if pa.get("assumptions") is not None:
            out[agent_id]["assumptions"] = list(pa["assumptions"])
        if pa.get("risk_flags") is not None:
            out[agent_id]["risk_flags"] = list(pa["risk_flags"])
    return out


class DeterministicCommitteeBackend:
    """
    Multi-role committee backend: produces Allocator, Scheduler, Router, Safety reviewer
    outputs and merges them. For testing: golden committee trace and fault injection.
    Same seed and step_id -> same merged proposal. Optional corrupt_role for fault-injection tests.
    """

    def __init__(
        self,
        seed: int = 0,
        corrupt_role: str | None = None,
    ) -> None:
        self._seed = seed
        self._step_counter = 0
        self._corrupt_role = corrupt_role

    def reset(self, seed: int) -> None:
        self._seed = seed
        self._step_counter = 0

    def generate_proposal(
        self,
        state_digest: dict[str, Any],
        allowed_actions: list[str],
        step_id: int,
        method_id: str,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        agent_ids = [p.get("agent_id") for p in state_digest.get("per_agent") or []]
        if not agent_ids:
            agent_ids = ["ops_0"]
        at = "NOOP" if "NOOP" in allowed_actions else (allowed_actions[0] if allowed_actions else "NOOP")
        _rng = (self._seed + step_id) % (2**31)
        per_agent_base = [
            {"agent_id": aid, "action_type": at, "args": {}, "reason_code": "COORD_COMMITTEE"} for aid in agent_ids
        ]
        if self._corrupt_role == "Allocator":
            per_agent_base = [{"agent_id": aid, "action_type": "INVALID_ACTION", "args": {}} for aid in agent_ids]
        allocator = {
            "per_agent": per_agent_base,
            "proposal_id": f"committee-{self._seed}-{step_id}",
            "step_id": step_id,
            "method_id": method_id,
            "horizon_steps": 1,
        }
        scheduler = {"per_agent": per_agent_base}
        router = {"per_agent": per_agent_base}
        safety = {"veto_agent_ids": []}
        role_outputs = {"Allocator": allocator, "Scheduler": scheduler, "Router": router, "Safety reviewer": safety}
        merged = _merge_committee_outputs(role_outputs, agent_ids)
        merged["comms"] = []
        meta = {
            "backend_id": "deterministic_committee",
            "model_id": "n/a",
            "latency_ms": 0.0,
            "tokens_in": 0,
            "tokens_out": 0,
        }
        merged["meta"] = meta
        return merged, meta


class DeterministicProposalBackend:
    """
    Deterministic backend that returns a valid CoordinationProposal from
    state digest. Uses seed for reproducible proposal_id; all agents get
    NOOP or TICK by default.
    """

    DEFAULT_BACKEND_ID = "deterministic"

    def __init__(
        self,
        seed: int = 0,
        default_action_type: str = "NOOP",
        backend_id: str | None = None,
    ) -> None:
        self._seed = seed
        self._default_action_type = default_action_type
        self._step_counter = 0
        self._backend_id = (backend_id or self.DEFAULT_BACKEND_ID).strip() or self.DEFAULT_BACKEND_ID

    def reset(self, seed: int) -> None:
        """Reset step counter and seed for new episode."""
        self._seed = seed
        self._step_counter = 0

    def generate_proposal(
        self,
        state_digest: dict[str, Any],
        allowed_actions: list[str],
        step_id: int,
        method_id: str,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Return (proposal_dict, meta). Proposal conforms to coordination_proposal schema.
        Deterministic for same digest and step_id. Accepts optional conversation_history
        for interface compatibility; ignored.
        """
        agent_ids = [p.get("agent_id") for p in state_digest.get("per_agent") or []]
        if not agent_ids:
            agent_ids = ["ops_0"]
        at = self._default_action_type
        if at not in allowed_actions and allowed_actions:
            at = allowed_actions[0]
        proposal_id = f"det-{self._seed}-{step_id}"
        per_agent = [
            {
                "agent_id": aid,
                "action_type": at,
                "args": {},
                "reason_code": "COORD_STALE_VIEW",
                "intent_confidence": 1.0,
                "assumptions": [],
                "risk_flags": [],
            }
            for aid in agent_ids
        ]
        meta = {
            "backend_id": self._backend_id,
            "model_id": "n/a",
            "latency_ms": 0.0,
            "tokens_in": 0,
            "tokens_out": 0,
        }
        try:
            from labtrust_gym.baselines.llm.llm_tracer import record_deterministic_coord_span

            record_deterministic_coord_span("coord_proposal", self._backend_id)
        except Exception as e:
            _LOG.debug("Tracing coord_proposal span failed: %s", e)
        proposal = {
            "proposal_id": proposal_id,
            "step_id": step_id,
            "method_id": method_id,
            "horizon_steps": 1,
            "per_agent": per_agent,
            "comms": [],
            "meta": meta,
            "intent_confidence": 1.0,
            "assumptions": [],
            "risk_flags": [],
        }
        return proposal, meta


class LLMCentralPlanner(CoordinationMethod):
    """
    Centralized LLM coordinator: build state digest from obs, call proposal
    backend, validate proposal, return actions_dict for all agents.
    """

    def __init__(
        self,
        proposal_backend: Any,
        rbac_policy: dict[str, Any],
        allowed_actions: list[str] | None = None,
        *,
        policy_summary: dict[str, Any] | None = None,
        get_allowed_actions_fn: Callable[[str], list[str]] | None = None,
        max_repairs: int = 1,
        blocked_threshold: int = 0,
        method_id_override: str | None = None,
        defense_profile: str | None = None,
    ) -> None:
        self._backend = proposal_backend
        self._rbac_policy = rbac_policy
        self._allowed_actions = allowed_actions or []
        self._policy_summary = policy_summary or {}
        self._get_allowed_actions_fn = get_allowed_actions_fn
        self._max_repairs = max(0, int(max_repairs))
        self._blocked_threshold = max(0, int(blocked_threshold))
        self._method_id_override = method_id_override
        self._defense_profile = defense_profile or ""
        self._conversation_history: list[dict[str, Any]] = []
        self._last_proposal: dict[str, Any] | None = None
        self._last_meta: dict[str, Any] | None = None
        self._last_valid = False
        self._latency_ms_list: list[float] = []
        self._proposal_valid_count = 0
        self._proposal_total_count = 0

    @property
    def method_id(self) -> str:
        return self._method_id_override or "llm_central_planner"

    def reset(
        self,
        seed: int,
        policy: dict[str, Any],
        scale_config: dict[str, Any],
    ) -> None:
        self._policy_summary = (policy or {}).get("policy_summary") or policy or {}
        if isinstance(scale_config, dict):
            if "max_repairs" in scale_config:
                self._max_repairs = max(0, int(scale_config["max_repairs"]))
            if "blocked_threshold" in scale_config:
                self._blocked_threshold = max(0, int(scale_config["blocked_threshold"]))
        allowed = self._policy_summary.get("allowed_actions")
        if isinstance(allowed, list):
            self._allowed_actions = list(allowed)
        elif self._get_allowed_actions_fn and policy.get("pz_to_engine"):
            agents = list((policy.get("pz_to_engine") or {}).keys())
            if agents:
                self._allowed_actions = self._get_allowed_actions_fn(
                    (policy["pz_to_engine"] or {}).get(agents[0], agents[0])
                )
        self._latency_ms_list = []
        self._conversation_history = []
        reset_fn = getattr(self._backend, "reset", None)
        if callable(reset_fn):
            reset_fn(seed)

    def propose_actions(
        self,
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        agent_ids = sorted(obs.keys())
        digest = build_state_digest(obs, infos, t, self._policy_summary)
        allowed = self._allowed_actions or ["NOOP", "TICK"]
        generate = getattr(
            self._backend,
            "generate_proposal",
            None,
        )
        if not callable(generate):
            return {a: {"action_index": ACTION_NOOP} for a in agent_ids}

        safe_fallback = self._defense_profile == "safe_fallback"
        try:
            proposal, meta = generate(
                digest,
                allowed,
                step_id=t,
                method_id=self.method_id,
                conversation_history=self._conversation_history or None,
            )
        except Exception as e:
            _LOG.warning("Proposal generation failed, using fallback: %s", e)
            if safe_fallback:
                return {a: {"action_index": ACTION_NOOP} for a in agent_ids}
            raise
        self._last_proposal = proposal
        self._last_meta = meta
        if meta.get("conversation_history_updated") is not None:
            self._conversation_history = meta["conversation_history_updated"]
        self._proposal_total_count += 1
        lat = meta.get("latency_ms")
        if lat is not None and isinstance(lat, (int, float)):
            self._latency_ms_list.append(float(lat))

        strict_reason = self._defense_profile == "shielded"
        valid, errors = validate_proposal(
            proposal,
            allowed_actions=allowed,
            strict_reason_codes=strict_reason,
        )
        if not valid:
            return {a: {"action_index": ACTION_NOOP} for a in agent_ids}
        self._last_valid = True
        self._proposal_valid_count += 1

        return _proposal_to_actions_dict(proposal, agent_ids)

    def get_llm_metrics(self) -> dict[str, Any]:
        """Return metrics for coordination+LLM: tokens, latency, validity/blocked/repair."""
        meta = self._last_meta or {}
        total = max(1, self._proposal_total_count)
        valid_rate = self._proposal_valid_count / total
        out: dict[str, Any] = {
            "tokens_in": meta.get("tokens_in", 0),
            "tokens_out": meta.get("tokens_out", 0),
            "latency_ms": meta.get("latency_ms"),
            "estimated_cost_usd": meta.get("estimated_cost_usd"),
            "backend_id": meta.get("backend_id"),
            "model_id": meta.get("model_id"),
            "proposal_validity_rate": round(valid_rate, 4),
            "proposal_total_count": self._proposal_total_count,
            "proposal_valid_count": self._proposal_valid_count,
        }
        if self._latency_ms_list:
            out["latency_ms_list"] = list(self._latency_ms_list)
        return out

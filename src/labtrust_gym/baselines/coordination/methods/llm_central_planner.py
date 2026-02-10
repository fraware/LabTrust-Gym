"""
Centralized LLM coordinator: receives global state digest, returns a
CoordinationProposal for all agents for the next step.

Uses state_digest.build_state_digest, a proposal backend (deterministic or live),
coordination_proposal schema validation, and converts proposal to actions_dict
for the runner. Supports metrics: tokens, latency, proposal validity rate,
blocked rate, repair rate.
"""

from __future__ import annotations

from typing import Any, Callable

from labtrust_gym.baselines.coordination.interface import (
    ACTION_NOOP,
    CoordinationMethod,
)
from labtrust_gym.baselines.coordination.llm_contract import validate_proposal
from labtrust_gym.baselines.coordination.llm_executor import ACTION_TYPE_TO_INDEX
from labtrust_gym.baselines.coordination.state_digest import build_state_digest


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
    return out


class DeterministicProposalBackend:
    """
    Deterministic backend that returns a valid CoordinationProposal from
    state digest. Uses seed for reproducible proposal_id; all agents get
    NOOP or TICK by default.
    """

    def __init__(self, seed: int = 0, default_action_type: str = "NOOP") -> None:
        self._seed = seed
        self._default_action_type = default_action_type
        self._step_counter = 0

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
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Return (proposal_dict, meta). Proposal conforms to coordination_proposal schema.
        Deterministic for same digest and step_id.
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
            }
            for aid in agent_ids
        ]
        meta = {
            "backend_id": "deterministic",
            "model_id": "n/a",
            "latency_ms": 0.0,
            "tokens_in": 0,
            "tokens_out": 0,
        }
        proposal = {
            "proposal_id": proposal_id,
            "step_id": step_id,
            "method_id": method_id,
            "horizon_steps": 1,
            "per_agent": per_agent,
            "comms": [],
            "meta": meta,
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
            )
        except Exception:
            if safe_fallback:
                return {a: {"action_index": ACTION_NOOP} for a in agent_ids}
            raise
        self._last_proposal = proposal
        self._last_meta = meta
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

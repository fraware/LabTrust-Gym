"""
LLM constrained coordination: reuses existing baselines/llm/agent (LLMAgentWithShield)
as a CoordinationMethod. Logs LLM_DECISION via meta passed into action_infos.

Envelope (SOTA audit):
  - Typical steps per episode: N/A; horizon-driven.
  - LLM calls per step: 1 per agent (act per agent).
  - Fallback on timeout/refusal: NOOP from shield.
  - max_latency_ms: N/A for live; bounded in llm_offline by deterministic backend.
"""

from __future__ import annotations

import os
from typing import Any

from labtrust_gym.baselines.coordination.interface import CoordinationMethod


class LLMConstrained(CoordinationMethod):
    """
    Wraps LLMAgentWithShield to implement CoordinationMethod.
    One LLM agent instance; propose_actions calls act(obs[agent_id], agent_id) per agent.
    Constraints (RBAC, zone, device) are enforced by the wrapped LLMAgentWithShield via
    rbac_policy and capability_policy: only actions allowed for the agent's role and
    capability set are proposed; shield rejects others.
    """

    def __init__(
        self,
        llm_agent: Any,
        pz_to_engine: dict[str, str] | None = None,
    ) -> None:
        self._llm_agent = llm_agent
        self._pz_to_engine = pz_to_engine or {}
        self._max_agents_per_step: int | None = None

    @property
    def method_id(self) -> str:
        return "llm_constrained"

    def reset(self, seed: int, policy: dict[str, Any], scale_config: dict[str, Any]) -> None:
        policy_summary = (policy or {}).get("policy_summary") or policy
        partner_id = (scale_config or {}).get("partner_id") or (policy or {}).get("partner_id")
        timing_mode = (scale_config or {}).get("timing_mode") or "explicit"
        reset_fn = getattr(self._llm_agent, "reset", None)
        if callable(reset_fn):
            reset_fn(seed, policy_summary, partner_id, timing_mode)
        max_agents_raw = (scale_config or {}).get("llm_constrained_max_agents_per_step")
        if max_agents_raw is None:
            max_agents_raw = os.environ.get("LABTRUST_LLM_CONSTRAINED_MAX_AGENTS_PER_STEP")
        try:
            max_agents = int(max_agents_raw) if max_agents_raw is not None else 0
        except (TypeError, ValueError):
            max_agents = 0
        self._max_agents_per_step = max_agents if max_agents > 0 else None

    def propose_actions(
        self,
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        agent_ids = sorted(obs.keys())
        if self._max_agents_per_step is not None and len(agent_ids) > self._max_agents_per_step:
            # Bounded per-step LLM fan-out for large swarms; rotate the active slice by
            # time-step so every agent is periodically evaluated by the LLM.
            n = len(agent_ids)
            k = self._max_agents_per_step
            start = (t * k) % n
            active_ids = [agent_ids[(start + i) % n] for i in range(k)]
        else:
            active_ids = agent_ids

        out: dict[str, dict[str, Any]] = {aid: {"action_index": 0} for aid in agent_ids}
        for agent_id in active_ids:
            o = obs.get(agent_id) or {}
            ret = self._llm_agent.act(o, agent_id)
            action_index = int(ret[0])
            action_info = ret[1] if len(ret) > 1 else {}
            meta = ret[2] if len(ret) > 2 else {}
            action_dict: dict[str, Any] = {
                "action_index": action_index,
                **(action_info or {}),
            }
            if meta and meta.get("_llm_decision") is not None:
                action_dict["_llm_decision"] = meta["_llm_decision"]
            out[agent_id] = action_dict
        return out

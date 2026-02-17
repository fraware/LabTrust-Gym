"""
LLM constrained coordination: reuses existing baselines/llm/agent (LLMAgentWithShield)
as a CoordinationMethod. Logs LLM_DECISION via meta passed into action_infos.
"""

from __future__ import annotations

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

    def propose_actions(
        self,
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for agent_id in sorted(obs.keys()):
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

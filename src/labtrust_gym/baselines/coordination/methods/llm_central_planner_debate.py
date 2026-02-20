"""
Debate/consensus coordination: N proposer backends each produce a proposal;
a deterministic rule (e.g. majority vote per agent on action_type) or an
aggregator backend produces the final proposal. Same propose_actions interface.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Callable

from labtrust_gym.baselines.coordination.interface import (
    ACTION_NOOP,
    CoordinationMethod,
)
from labtrust_gym.baselines.coordination.llm_contract import validate_proposal
from labtrust_gym.baselines.coordination.llm_executor import ACTION_TYPE_TO_INDEX
from labtrust_gym.baselines.coordination.state_digest import build_state_digest


def _majority_merge_proposals(
    proposals: list[dict[str, Any]],
    agent_ids: list[str],
    allowed_actions: list[str],
    step_id: int,
    method_id: str,
) -> dict[str, Any]:
    """
    Merge N proposals by majority vote per agent on action_type.
    Tie-break: prefer first in allowed_actions, then NOOP.
    """
    allowed_set = set(allowed_actions or ["NOOP", "TICK"])
    per_agent: list[dict[str, Any]] = []
    for aid in agent_ids:
        votes: list[str] = []
        for prop in proposals:
            for pa in prop.get("per_agent") or []:
                if isinstance(pa, dict) and pa.get("agent_id") == aid:
                    at = (pa.get("action_type") or "NOOP").strip()
                    if at in allowed_set:
                        votes.append(at)
                    else:
                        votes.append("NOOP")
                    break
        if not votes:
            action_type = "NOOP"
        else:
            counts = Counter(votes)
            best = counts.most_common(1)[0][0]
            action_type = best
        per_agent.append({
            "agent_id": aid,
            "action_type": action_type,
            "args": {},
            "reason_code": "DEBATE_MAJORITY",
        })
    return {
        "proposal_id": f"debate_majority_{step_id}",
        "step_id": step_id,
        "method_id": method_id,
        "per_agent": per_agent,
        "comms": [],
        "meta": {"backend_id": "debate_majority"},
    }


def _proposal_to_actions_dict(
    proposal_dict: dict[str, Any],
    agent_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Convert proposal per_agent to runner action_dict by agent_id."""
    out: dict[str, dict[str, Any]] = {a: {"action_index": ACTION_NOOP} for a in agent_ids}
    for pa in proposal_dict.get("per_agent") or []:
        if not isinstance(pa, dict):
            continue
        agent_id = pa.get("agent_id")
        if agent_id not in out:
            continue
        action_type = (pa.get("action_type") or "NOOP").strip()
        args = pa.get("args") if isinstance(pa.get("args"), dict) else {}
        action_index = ACTION_TYPE_TO_INDEX.get(action_type, ACTION_NOOP)
        out[agent_id] = {
            "action_index": action_index,
            "action_type": action_type,
            "args": args,
            "reason_code": pa.get("reason_code"),
        }
    return out


class LLMCentralPlannerDebate(CoordinationMethod):
    """
    Debate/consensus: N proposer backends; aggregate by majority or aggregator backend.
    Same propose_actions interface as LLMCentralPlanner.
    """

    def __init__(
        self,
        proposal_backend: Any,
        rbac_policy: dict[str, Any],
        allowed_actions: list[str] | None = None,
        *,
        policy_summary: dict[str, Any] | None = None,
        get_allowed_actions_fn: Callable[[str], list[str]] | None = None,
        aggregator: str = "majority",
        method_id_override: str | None = None,
    ) -> None:
        if isinstance(proposal_backend, list):
            self._proposers = list(proposal_backend)
        else:
            self._proposers = [proposal_backend]
        self._rbac_policy = rbac_policy
        self._allowed_actions = allowed_actions or []
        self._policy_summary = policy_summary or {}
        self._get_allowed_actions_fn = get_allowed_actions_fn
        self._aggregator = (aggregator or "majority").lower()
        self._method_id_override = method_id_override
        self._last_proposal: dict[str, Any] | None = None
        self._last_meta: dict[str, Any] | None = None

    @property
    def method_id(self) -> str:
        return self._method_id_override or "llm_central_planner_debate"

    def reset(
        self,
        seed: int,
        policy: dict[str, Any],
        scale_config: dict[str, Any],
    ) -> None:
        self._policy_summary = (policy or {}).get("policy_summary") or policy or {}
        if isinstance(scale_config, dict) and scale_config.get("coord_debate_aggregator"):
            self._aggregator = str(scale_config["coord_debate_aggregator"]).lower()
        if self._get_allowed_actions_fn and policy.get("pz_to_engine"):
            agents = list((policy.get("pz_to_engine") or {}).keys())
            if agents:
                first = (policy.get("pz_to_engine") or {}).get(agents[0], agents[0])
                self._allowed_actions = self._get_allowed_actions_fn(first)
        for backend in self._proposers:
            reset_fn = getattr(backend, "reset", None)
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

        proposals: list[dict[str, Any]] = []
        for backend in self._proposers:
            gen = getattr(backend, "generate_proposal", None)
            if not callable(gen):
                continue
            try:
                out = gen(
                    digest,
                    allowed,
                    step_id=t,
                    method_id=self.method_id,
                )
            except Exception:
                continue
            if isinstance(out, tuple):
                prop, _ = out[0], out[1]
            else:
                prop = out
            if isinstance(prop, dict) and prop.get("per_agent"):
                proposals.append(prop)

        if not proposals:
            return {a: {"action_index": ACTION_NOOP} for a in agent_ids}

        if self._aggregator == "majority":
            merged = _majority_merge_proposals(
                proposals, agent_ids, allowed, t, self.method_id
            )
        else:
            merged = proposals[0]

        self._last_proposal = merged
        self._last_meta = {"backend_id": "debate_majority"}

        valid, _ = validate_proposal(
            merged,
            allowed_actions=allowed,
            strict_reason_codes=False,
        )
        if not valid:
            return {a: {"action_index": ACTION_NOOP} for a in agent_ids}

        return _proposal_to_actions_dict(merged, agent_ids)

    def get_llm_metrics(self) -> dict[str, Any]:
        meta = self._last_meta or {}
        return {
            "backend_id": meta.get("backend_id", "debate"),
            "proposal_count": len(self._proposers),
        }

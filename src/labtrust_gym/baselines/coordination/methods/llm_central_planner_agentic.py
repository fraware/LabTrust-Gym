"""
Coordinator agentic loop: bounded tool rounds per env step.

The coordinator backend is called in a loop. If it returns tool_calls in meta,
we execute tools and call again with tool_results appended to context until
final proposal or max_rounds. Same propose_actions interface.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from labtrust_gym.baselines.coordination.interface import (
    ACTION_NOOP,
    CoordinationMethod,
)
from labtrust_gym.baselines.coordination.llm_contract import validate_proposal
from labtrust_gym.baselines.coordination.llm_executor import ACTION_TYPE_TO_INDEX
from labtrust_gym.baselines.coordination.methods.coord_agentic_tools import (
    DEFAULT_COORD_TOOL_REGISTRY,
    run_tools,
)
from labtrust_gym.baselines.coordination.state_digest import build_state_digest


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


class DeterministicAgenticProposalBackend:
    """
    Deterministic backend for testing agentic loop: first call returns tool_calls in meta,
    second call returns a normal proposal.
    """

    def __init__(self, seed: int = 0) -> None:
        self._seed = seed
        self._call_count = 0

    def reset(self, seed: int) -> None:
        self._seed = seed
        self._call_count = 0

    def generate_proposal(
        self,
        state_digest: dict[str, Any],
        allowed_actions: list[str],
        step_id: int,
        method_id: str,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        self._call_count += 1
        agent_ids = [p.get("agent_id") for p in state_digest.get("per_agent") or []]
        if not agent_ids:
            agent_ids = ["ops_0"]
        if self._call_count == 1:
            return (
                {"per_agent": [], "proposal_id": "tool_round"},
                {"tool_calls": [{"name": "query_queue_state", "args": {}}]},
            )
        per_agent = [{"agent_id": aid, "action_type": "NOOP", "args": {}, "reason_code": "OK"} for aid in agent_ids]
        return (
            {
                "proposal_id": f"agentic-{self._seed}-{step_id}",
                "step_id": step_id,
                "method_id": method_id,
                "per_agent": per_agent,
                "comms": [],
                "meta": {},
            },
            {"backend_id": "deterministic_agentic"},
        )


class LLMCentralPlannerAgentic(CoordinationMethod):
    """
    Agentic coordinator: loop over proposal backend with tool execution.
    Backend returns (proposal, meta); if meta["tool_calls"] is set, run tools
    and call again with tool_results in kwargs until proposal or max_rounds.
    """

    def __init__(
        self,
        proposal_backend: Any,
        rbac_policy: dict[str, Any],
        allowed_actions: list[str] | None = None,
        *,
        policy_summary: dict[str, Any] | None = None,
        get_allowed_actions_fn: Callable[[str], list[str]] | None = None,
        max_tool_rounds: int = 5,
        tool_registry: dict[str, Any] | None = None,
        method_id_override: str | None = None,
    ) -> None:
        self._backend = proposal_backend
        self._rbac_policy = rbac_policy
        self._allowed_actions = allowed_actions or []
        self._policy_summary = policy_summary or {}
        self._get_allowed_actions_fn = get_allowed_actions_fn
        self._max_tool_rounds = max(1, min(max_tool_rounds, 10))
        self._tool_registry = tool_registry or DEFAULT_COORD_TOOL_REGISTRY
        self._method_id_override = method_id_override
        self._method_state: dict[str, Any] = {}
        self._last_proposal: dict[str, Any] | None = None
        self._last_meta: dict[str, Any] | None = None

    @property
    def method_id(self) -> str:
        return self._method_id_override or "llm_central_planner_agentic"

    def reset(
        self,
        seed: int,
        policy: dict[str, Any],
        scale_config: dict[str, Any],
    ) -> None:
        self._policy_summary = (policy or {}).get("policy_summary") or policy or {}
        self._method_state = {"seed": seed}
        if isinstance(scale_config, dict):
            r = int(scale_config.get("coord_agentic_max_rounds", self._max_tool_rounds))
            self._max_tool_rounds = max(1, min(r, 10))
        if self._get_allowed_actions_fn and policy.get("pz_to_engine"):
            agents = list((policy.get("pz_to_engine") or {}).keys())
            if agents:
                first = (policy.get("pz_to_engine") or {}).get(agents[0], agents[0])
                self._allowed_actions = self._get_allowed_actions_fn(first)
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
        gen = getattr(self._backend, "generate_proposal", None)
        if not callable(gen):
            return {a: {"action_index": ACTION_NOOP} for a in agent_ids}

        tool_results: list[dict[str, Any]] = []
        proposal: dict[str, Any] | None = None
        meta: dict[str, Any] = {}

        for _ in range(self._max_tool_rounds):
            try:
                out = gen(
                    digest,
                    allowed,
                    step_id=t,
                    method_id=self.method_id,
                    tool_results=tool_results,
                )
            except Exception:
                break
            if isinstance(out, tuple):
                proposal, meta = out[0], out[1]
            else:
                proposal, meta = out, {}
            tool_calls = meta.get("tool_calls") if isinstance(meta.get("tool_calls"), list) else None
            if not tool_calls:
                break
            results = run_tools(
                tool_calls,
                obs,
                infos,
                t,
                self._method_state,
                registry=self._tool_registry,
            )
            tool_results.extend(results)

        if not proposal or not proposal.get("per_agent"):
            return {a: {"action_index": ACTION_NOOP} for a in agent_ids}

        self._last_proposal = proposal
        self._last_meta = meta
        valid, _ = validate_proposal(
            proposal,
            allowed_actions=allowed,
            strict_reason_codes=False,
        )
        if not valid:
            return {a: {"action_index": ACTION_NOOP} for a in agent_ids}
        return _proposal_to_actions_dict(proposal, agent_ids)

    def get_llm_metrics(self) -> dict[str, Any]:
        m = self._last_meta or {}
        return {"backend_id": m.get("backend_id", "agentic"), "tool_rounds": len(m.get("tool_calls") or [])}

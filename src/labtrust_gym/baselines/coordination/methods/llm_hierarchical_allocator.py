"""
Hierarchical coordination: LLM allocates high-level assignments (agent_id -> job_id,
optional priority weights); deterministic local controller translates SET_INTENT
into concrete actions (greedy, EDF, WHCA).

Security: LLM cannot directly issue privileged ops; shield still blocks unsafe
concrete actions. Proposals wrapped in CoordinationProposal with per-agent
action_type SET_INTENT (non-mutating); local controller produces NOOP, TICK,
MOVE, QUEUE_RUN, START_RUN, OPEN_DOOR.
"""

from __future__ import annotations

from typing import Any, Callable

from labtrust_gym.baselines.coordination.interface import (
    ACTION_NOOP,
    CoordinationMethod,
)
from labtrust_gym.baselines.coordination.llm_contract import validate_proposal
from labtrust_gym.baselines.coordination.local_controller import (
    intent_to_actions,
    _job_id,
)
from labtrust_gym.baselines.coordination.obs_utils import extract_zone_and_device_ids
from labtrust_gym.baselines.coordination.state_digest import build_state_digest

# Allowed action for hierarchical proposal validation (LLM outputs SET_INTENT only)
SET_INTENT = "SET_INTENT"


class DeterministicAssignmentsBackend:
    """
    Deterministic backend: CoordinationProposal with per-agent SET_INTENT and
    args {job_id, priority_weight}. Builds available jobs from state digest
    (per_device + device_zone); assigns greedily by priority. Same digest and
    step_id yield same proposal (stable for benchmarking).
    """

    def __init__(self, seed: int = 0) -> None:
        self._seed = seed

    def reset(self, seed: int) -> None:
        self._seed = seed

    def generate_proposal(
        self,
        state_digest: dict[str, Any],
        allowed_actions: list[str],
        step_id: int,
        method_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Return (proposal_dict, meta). per_agent entries have action_type
        SET_INTENT and args {job_id, priority_weight}. Deterministic for same
        digest and step_id.
        """
        device_zone = state_digest.get("device_zone") or {}
        per_agent_digest = state_digest.get("per_agent") or []
        per_device = state_digest.get("per_device") or []

        available_jobs: list[tuple[str, str, str, str, int]] = []
        for d in per_device:
            if not isinstance(d, dict):
                continue
            dev_id = str(d.get("device_id") or "")
            queue_head = str(d.get("queue_head") or "").strip()
            if not dev_id or not queue_head:
                continue
            zone_id = device_zone.get(dev_id, "")
            prio = 2 if "STAT" in queue_head.upper() else (
                1 if "URGENT" in queue_head.upper() else 0
            )
            jid = _job_id(dev_id, queue_head)
            available_jobs.append((jid, dev_id, queue_head, zone_id, prio))
        available_jobs.sort(key=lambda x: (-x[4], x[1], x[2]))

        agent_list = [
            (p.get("agent_id"), (p.get("zone") or ""))
            for p in per_agent_digest
            if isinstance(p, dict) and p.get("agent_id")
        ]
        used_jobs: set[str] = set()
        used_agents: set[str] = set()
        assignments: list[tuple[str, str, int]] = []

        for job_id, _dev_id, work_id, zone_id, prio in available_jobs:
            if job_id in used_jobs:
                continue
            for agent_id, agent_zone in agent_list:
                if agent_id in used_agents:
                    continue
                if zone_id and agent_zone and zone_id != agent_zone:
                    continue
                used_agents.add(agent_id)
                used_jobs.add(job_id)
                assignments.append((agent_id, job_id, prio))
                break

        proposal_id = f"hier-det-{self._seed}-{step_id}"
        per_agent = [
            {
                "agent_id": aid,
                "action_type": SET_INTENT,
                "args": {"job_id": jid, "priority_weight": pw},
                "reason_code": "COORD_HIER_ASSIGN",
            }
            for aid, jid, pw in assignments
        ]
        meta = {
            "backend_id": "deterministic_assignments",
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


class LLMHierarchicalAllocator(CoordinationMethod):
    """
    Hierarchical method: allocator backend produces CoordinationProposal with
    SET_INTENT per agent; local controller (greedy/edf/whca) translates to
    concrete actions. Shield applies to final actions.
    """

    def __init__(
        self,
        allocator_backend: Any,
        rbac_policy: dict[str, Any],
        allowed_actions: list[str] | None = None,
        *,
        policy_summary: dict[str, Any] | None = None,
        get_allowed_actions_fn: Callable[[str], list[str]] | None = None,
        local_strategy: str = "edf",
        use_whca: bool = False,
        whca_horizon: int = 10,
    ) -> None:
        self._backend = allocator_backend
        self._rbac_policy = rbac_policy
        self._allowed_actions = list(allowed_actions or [])
        if SET_INTENT not in self._allowed_actions:
            self._allowed_actions.append(SET_INTENT)
        self._policy_summary = policy_summary or {}
        self._get_allowed_actions_fn = get_allowed_actions_fn
        ok = local_strategy in ("greedy", "edf", "whca")
        self._local_strategy = local_strategy if ok else "edf"
        self._use_whca = use_whca
        self._whca_horizon = whca_horizon
        self._seed = 0
        self._last_proposal: dict[str, Any] | None = None
        self._last_meta: dict[str, Any] | None = None

    @property
    def method_id(self) -> str:
        return "llm_hierarchical_allocator"

    def reset(
        self,
        seed: int,
        policy: dict[str, Any],
        scale_config: dict[str, Any],
    ) -> None:
        self._policy_summary = (policy or {}).get("policy_summary") or policy or {}
        if self._get_allowed_actions_fn and policy.get("pz_to_engine"):
            agents = list((policy.get("pz_to_engine") or {}).keys())
            if agents:
                p2e = policy.get("pz_to_engine") or {}
                first = p2e.get(agents[0], agents[0])
                self._allowed_actions = list(
                    self._get_allowed_actions_fn(first) or []
                )
                if SET_INTENT not in self._allowed_actions:
                    self._allowed_actions.append(SET_INTENT)
        self._seed = seed
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
        policy = self._policy_summary
        obs_sample = next(iter(obs.values())) if obs else None
        zone_ids, device_ids, device_zone = extract_zone_and_device_ids(
            policy, obs_sample=obs_sample
        )
        if not zone_ids and obs:
            zone_ids = ["Z_SORTING_LANES"]
        digest = build_state_digest(obs, infos, t, policy)
        digest["device_zone"] = device_zone

        generate = getattr(self._backend, "generate_proposal", None)
        if not callable(generate):
            return {a: {"action_index": ACTION_NOOP} for a in agent_ids}

        proposal, meta = generate(
            digest,
            self._allowed_actions,
            step_id=t,
            method_id=self.method_id,
        )
        self._last_proposal = proposal
        self._last_meta = meta
        valid, errors = validate_proposal(
            proposal,
            allowed_actions=self._allowed_actions,
            strict_reason_codes=False,
        )
        if not valid:
            return {a: {"action_index": ACTION_NOOP} for a in agent_ids}

        return intent_to_actions(
            proposal,
            obs,
            agent_ids,
            zone_ids,
            device_ids,
            device_zone,
            policy,
            t,
            self._seed,
            strategy=self._local_strategy,
            use_whca=self._use_whca,
            whca_horizon=self._whca_horizon,
        )

    def get_llm_metrics(self) -> dict[str, Any]:
        """Return metrics for coordination+LLM: tokens, latency, backend_id, model_id, estimated_cost_usd."""
        meta = self._last_meta or {}
        return {
            "tokens_in": meta.get("tokens_in", 0),
            "tokens_out": meta.get("tokens_out", 0),
            "latency_ms": meta.get("latency_ms"),
            "estimated_cost_usd": meta.get("estimated_cost_usd"),
            "backend_id": meta.get("backend_id"),
            "model_id": meta.get("model_id"),
        }

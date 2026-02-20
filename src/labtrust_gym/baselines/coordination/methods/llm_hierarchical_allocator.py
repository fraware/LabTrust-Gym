"""
Hierarchical coordination: LLM allocates high-level assignments (agent_id -> job_id,
optional priority weights); deterministic local controller translates SET_INTENT
into concrete actions (greedy, EDF, WHCA).

Security: LLM cannot directly issue privileged ops; shield still blocks unsafe
concrete actions. Proposals wrapped in CoordinationProposal with per-agent
action_type SET_INTENT (non-mutating); local controller produces NOOP, TICK,
MOVE, QUEUE_RUN, START_RUN, OPEN_DOOR.

Envelope (SOTA audit):
  - Typical steps per episode: N/A; horizon-driven.
  - LLM calls per step: 1 (single assignment proposal per step).
  - Fallback on timeout/refusal: NOOP or local controller default.
  - max_latency_ms: N/A for live; bounded in llm_offline by deterministic backend.
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

# Default below which controller falls back to kernel (no LLM assignments)
DEFAULT_CONFIDENCE_THRESHOLD = 0.3


def _check_assumptions_match(
    proposal: dict[str, Any],
    obs: dict[str, Any],
) -> bool:
    """
    Return True if stated assumptions are consistent with current obs.
    Assumption strings: "agent:<agent_id>:<zone_id>" meaning agent must be in that zone.
    Mismatch -> reject proposal (controller will fall back to NOOP).
    """
    per_agent = proposal.get("per_agent") or []
    for pa in per_agent:
        if not isinstance(pa, dict):
            continue
        assumptions = pa.get("assumptions")
        if not isinstance(assumptions, list):
            continue
        agent_id = pa.get("agent_id")
        if not agent_id or agent_id not in obs:
            continue
        agent_obs = obs[agent_id] if isinstance(obs[agent_id], dict) else {}
        current_zone = (agent_obs.get("zone_id") or "").strip()
        for raw in assumptions:
            s = (raw if isinstance(raw, str) else str(raw)).strip()
            if s.startswith("agent:") and ":" in s[6:]:
                parts = s.split(":", 2)
                if len(parts) >= 3 and parts[1] == agent_id and parts[2] != current_zone:
                    return False
    top = proposal.get("assumptions") or []
    if isinstance(top, list):
        for raw in top:
            s = (raw if isinstance(raw, str) else str(raw)).strip()
            if s.startswith("agent:") and ":" in s[6:]:
                parts = s.split(":", 2)
                if len(parts) >= 3:
                    aid, z = parts[1], parts[2]
                    if aid in obs and isinstance(obs[aid], dict):
                        if (obs[aid].get("zone_id") or "").strip() != z:
                            return False
    return True


class DeterministicAssignmentsBackend:
    """
    Deterministic backend: CoordinationProposal with per-agent SET_INTENT and
    args {job_id, priority_weight}. Builds available jobs from state digest
    (per_device + device_zone); assigns greedily by priority. Same digest and
    step_id yield same proposal (stable for benchmarking).
    Optional low_confidence / wrong_assumptions for tests (fallback and reject paths).
    """

    def __init__(
        self,
        seed: int = 0,
        *,
        low_confidence: bool = False,
        wrong_assumptions: bool = False,
    ) -> None:
        self._seed = seed
        self._low_confidence = low_confidence
        self._wrong_assumptions = wrong_assumptions

    def reset(self, seed: int) -> None:
        self._seed = seed

    def generate_proposal(
        self,
        state_digest: dict[str, Any],
        allowed_actions: list[str],
        step_id: int,
        method_id: str,
        **kwargs: Any,
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
        conf = 0.1 if self._low_confidence else 1.0
        assump: list[str] = []
        if self._wrong_assumptions and agent_list:
            first_agent = agent_list[0][0]
            assump = [f"agent:{first_agent}:Z_WRONG"]
        per_agent = [
            {
                "agent_id": aid,
                "action_type": SET_INTENT,
                "args": {"job_id": jid, "priority_weight": pw},
                "reason_code": "COORD_HIER_ASSIGN",
                "intent_confidence": conf,
                "assumptions": assump if assump and aid == (agent_list[0][0] if agent_list else "") else [],
                "risk_flags": [],
            }
            for aid, jid, pw in assignments
        ]
        if self._wrong_assumptions and not per_agent and agent_list:
            first_agent = agent_list[0][0]
            per_agent = [
                {
                    "agent_id": first_agent,
                    "action_type": SET_INTENT,
                    "args": {},
                    "reason_code": "COORD_HIER_ASSIGN",
                    "intent_confidence": 1.0,
                    "assumptions": [f"agent:{first_agent}:Z_WRONG"],
                    "risk_flags": [],
                }
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
            "intent_confidence": conf,
            "assumptions": list(assump) if assump else [],
            "risk_flags": [],
        }
        return proposal, meta


class LLMHierarchicalAllocator(CoordinationMethod):
    """
    Hierarchical method: allocator backend produces CoordinationProposal with
    SET_INTENT per agent; local controller (greedy/edf/whca) translates to
    concrete actions. Shield applies to final actions.

    Compute envelope: one proposal generation per step (cost depends on backend);
    local controller is O(agents + devices) per step.
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
        method_id_override: str | None = None,
        defense_profile: str | None = None,
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
        self._method_id_override = method_id_override
        self._defense_profile = defense_profile or ""
        self._seed = 0
        self._confidence_threshold = DEFAULT_CONFIDENCE_THRESHOLD
        self._last_proposal: dict[str, Any] | None = None
        self._last_meta: dict[str, Any] | None = None
        self._allowed_by_agent: dict[str, list[str]] = {}

    @property
    def method_id(self) -> str:
        return self._method_id_override or "llm_hierarchical_allocator"

    def reset(
        self,
        seed: int,
        policy: dict[str, Any],
        scale_config: dict[str, Any],
    ) -> None:
        self._policy_summary = (policy or {}).get("policy_summary") or policy or {}
        self._allowed_by_agent = {}
        if self._get_allowed_actions_fn and policy.get("pz_to_engine"):
            for aid in (policy.get("pz_to_engine") or {}):
                allowed = list(self._get_allowed_actions_fn(aid) or [])
                if SET_INTENT not in allowed:
                    allowed.append(SET_INTENT)
                self._allowed_by_agent[aid] = allowed
            agents = list((policy.get("pz_to_engine") or {}).keys())
            if agents:
                first = agents[0]
                self._allowed_actions = list(self._allowed_by_agent.get(first, self._allowed_actions))
                if SET_INTENT not in self._allowed_actions:
                    self._allowed_actions.append(SET_INTENT)
        self._seed = seed
        if isinstance(scale_config, dict) and "confidence_threshold" in scale_config:
            try:
                self._confidence_threshold = float(scale_config["confidence_threshold"])
            except (TypeError, ValueError):
                pass
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

        safe_fallback = self._defense_profile == "safe_fallback"
        try:
            proposal, meta = generate(
                digest,
                self._allowed_actions,
                step_id=t,
                method_id=self.method_id,
            )
        except Exception:
            if safe_fallback:
                return {a: {"action_index": ACTION_NOOP} for a in agent_ids}
            raise
        self._last_proposal = proposal
        self._last_meta = meta
        strict_reason = self._defense_profile == "shielded"
        valid, errors = validate_proposal(
            proposal,
            allowed_actions=self._allowed_actions,
            strict_reason_codes=strict_reason,
        )
        if not valid:
            return {a: {"action_index": ACTION_NOOP} for a in agent_ids}

        confidence = proposal.get("intent_confidence")
        if confidence is None:
            per = proposal.get("per_agent") or []
            confs = [p.get("intent_confidence") for p in per if isinstance(p, dict) and p.get("intent_confidence") is not None]
            confidence = min(confs) if confs else 1.0
        if isinstance(confidence, (int, float)) and float(confidence) < self._confidence_threshold:
            proposal = {**proposal, "per_agent": []}
        elif not _check_assumptions_match(proposal, obs):
            return {a: {"action_index": ACTION_NOOP} for a in agent_ids}

        actions = intent_to_actions(
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
        # RBAC: only allow actions that are in this agent's allowed set
        for aid in actions:
            allowed = self._allowed_by_agent.get(aid, self._allowed_actions)
            rec = actions.get(aid) or {}
            action_type = (rec.get("action_type") or "NOOP").strip()
            if allowed and action_type not in allowed:
                actions[aid] = {"action_index": ACTION_NOOP, "action_type": "NOOP"}
        return actions

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

"""
LLM repair over kernel WHCA: base plan from deterministic kernel (WHCA),
shield-only execute; when shield rejects or security/staleness flags, call LLM
repair then re-shield and execute. Deterministic in llm_offline via seeded backend.
"""

from __future__ import annotations

from typing import Any

from labtrust_gym.baselines.coordination.assurance.simplex import (
    validate_plan,
)
from labtrust_gym.baselines.coordination.compose import (
    _route_to_action_dict,
    build_kernel_context,
)
from labtrust_gym.baselines.coordination.decision_types import RouteDecision
from labtrust_gym.baselines.coordination.interface import (
    ACTION_NOOP,
    CoordinationMethod,
)
from labtrust_gym.baselines.coordination.repair_input import (
    build_repair_input,
    repair_input_hash,
)


def _per_agent_to_route_decision(
    per_agent: list[tuple[str, str, dict[str, Any]]],
) -> RouteDecision:
    """Convert list of (agent_id, action_type, args_dict) to RouteDecision."""
    tupled = []
    for agent_id, action_type, args in per_agent:
        args_tuple = tuple(
            sorted((k, v) for k, v in (args or {}).items())
        )
        tupled.append((agent_id, action_type, args_tuple))
    return RouteDecision(per_agent=tuple(tupled), explain="llm_repair")


class DeterministicRepairBackend:
    """
    Deterministic repair backend: same repair_input + seed -> same repaired plan.
    Returns all NOOP (safe fallback); optional TICK when seed+hash even.
    """

    def __init__(self, seed: int = 0) -> None:
        self._seed = seed

    def reset(self, seed: int) -> None:
        self._seed = seed

    def repair(
        self,
        repair_input: dict[str, Any],
        agent_ids: list[str],
    ) -> tuple[list[tuple[str, str, dict[str, Any]]], dict[str, Any]]:
        """
        Return (per_agent, meta). per_agent = [(agent_id, action_type, args), ...].
        Deterministic: same input and seed -> same output.
        """
        h = repair_input_hash(repair_input)
        rng = (self._seed + int(h[:8], 16)) % (2**31)
        # Deterministic: hash-derived value -> safe action (NOOP or TICK)
        use_tick = (rng % 2) == 0 and len(agent_ids) > 0
        action_type = "TICK" if use_tick else "NOOP"
        per_agent = [(aid, action_type, {}) for aid in sorted(agent_ids)]
        meta = {
            "backend_id": "deterministic_repair",
            "latency_ms": 0.0,
            "tokens_in": 0,
            "tokens_out": 0,
        }
        return per_agent, meta


class LLMRepairOverKernelWHCA(CoordinationMethod):
    """
    Compose: kernel (WHCA) -> shield -> if blocked/flagged -> LLM repair
    -> re-shield -> execute (or NOOP). Emits coordination.llm_repair metrics.
    """

    def __init__(
        self,
        kernel: CoordinationMethod,
        repair_backend: Any,
        allowed_actions: list[str] | None = None,
    ) -> None:
        self._kernel = kernel
        self._repair_backend = repair_backend
        self._allowed_actions = allowed_actions or [
            "NOOP",
            "TICK",
            "MOVE",
            "START_RUN",
            "QUEUE_RUN",
            "OPEN_DOOR",
        ]
        self._policy: dict[str, Any] = {}
        self._scale_config: dict[str, Any] = {}
        self._seed = 0
        self._repair_call_count = 0
        self._repair_success_count = 0
        self._repair_fallback_noop_count = 0
        self._repair_latency_ms_list: list[float] = []
        self._repair_tokens_total = 0

    @property
    def method_id(self) -> str:
        return "llm_repair_over_kernel_whca"

    def reset(
        self,
        seed: int,
        policy: dict[str, Any],
        scale_config: dict[str, Any],
    ) -> None:
        self._policy = policy or {}
        self._scale_config = dict(scale_config or {})
        self._seed = (
            int(scale_config.get("seed", seed)) if scale_config else seed
        )
        self._repair_call_count = 0
        self._repair_success_count = 0
        self._repair_fallback_noop_count = 0
        self._repair_latency_ms_list = []
        self._repair_tokens_total = 0
        if hasattr(self._kernel, "reset"):
            self._kernel.reset(seed, policy, scale_config)
        if hasattr(self._repair_backend, "reset"):
            self._repair_backend.reset(self._seed)

    def propose_actions(
        self,
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        agent_ids = sorted(obs.keys())
        if not agent_ids:
            return {}

        context = build_kernel_context(
            obs,
            infos,
            t,
            self._policy,
            self._scale_config,
            self._seed,
            blackboard_harness=None,
        )

        if not hasattr(self._kernel, "step"):
            noop = {a: {"action_index": ACTION_NOOP} for a in agent_ids}
            return noop

        actions, decision = self._kernel.step(context)
        result = validate_plan(decision.route, context)

        repair_triggers = infos.get("_coord_repair_triggers") or []
        trigger_repair = not result.ok or len(repair_triggers) > 0

        if not trigger_repair:
            out: dict[str, dict[str, Any]] = {
                a: {"action_index": ACTION_NOOP} for a in agent_ids
            }
            for agent_id, action_type, args_tuple in decision.route.per_agent:
                if agent_id in out:
                    out[agent_id] = _route_to_action_dict(
                        agent_id, action_type, args_tuple
                    )
            return out

        self._repair_call_count += 1
        blocked_actions = []
        if not result.ok and decision.route.per_agent:
            reason = result.reasons[0] if result.reasons else "COORD_SHIELD_REJECT"
            for agent_id, action_type, args_tuple in decision.route.per_agent:
                blocked_actions.append(
                    {
                        "agent_id": agent_id,
                        "action_type": action_type,
                        "reason_code": reason,
                    }
                )

        scale_snapshot = {k: v for k, v in self._scale_config.items() if k != "seed"}
        plan_summary = {
            "route_hash": getattr(decision, "route_hash", ""),
            "step_idx": getattr(decision, "step_idx", t),
        }
        constraint_summary = {
            "allowed_actions": list(self._allowed_actions),
            "invariants": ["INV-ROUTE-001", "INV-ROUTE-002"],
        }
        repair_input = build_repair_input(
            scale_config_snapshot=scale_snapshot,
            last_accepted_plan_summary=plan_summary,
            blocked_actions=blocked_actions,
            constraint_summary=constraint_summary,
            red_team_flags=(
                repair_triggers if isinstance(repair_triggers, list) else []
            ),
        )

        repaired_per_agent, meta = self._repair_backend.repair(repair_input, agent_ids)
        lat = meta.get("latency_ms")
        if lat is not None:
            self._repair_latency_ms_list.append(float(lat))
        ti = int(meta.get("tokens_in", 0) or 0)
        to = int(meta.get("tokens_out", 0) or 0)
        self._repair_tokens_total += ti + to

        repaired_route = _per_agent_to_route_decision(repaired_per_agent)
        result2 = validate_plan(repaired_route, context)

        if result2.ok:
            self._repair_success_count += 1
            out = {a: {"action_index": ACTION_NOOP} for a in agent_ids}
            for agent_id, action_type, args_tuple in repaired_route.per_agent:
                if agent_id in out:
                    out[agent_id] = _route_to_action_dict(
                        agent_id, action_type, args_tuple
                    )
            return out

        self._repair_fallback_noop_count += 1
        return {a: {"action_index": ACTION_NOOP} for a in agent_ids}

    def get_llm_repair_metrics(self) -> dict[str, Any]:
        """Return coordination.llm_repair block for results v0.2."""
        calls = max(0, self._repair_call_count)
        success_rate = (
            self._repair_success_count / calls if calls > 0 else 0.0
        )
        lat_list = self._repair_latency_ms_list
        mean_latency = (
            sum(lat_list) / len(lat_list) if lat_list else None
        )
        mean_latency_round = (
            round(mean_latency, 2) if mean_latency is not None else None
        )
        out = {
            "repair_call_count": calls,
            "repair_success_rate": round(success_rate, 4),
            "repair_fallback_noop_count": self._repair_fallback_noop_count,
            "mean_repair_latency_ms": mean_latency_round,
            "total_repair_tokens": self._repair_tokens_total,
        }
        fault_metrics = getattr(
            self._repair_backend, "get_fault_metrics", lambda: None
        )()
        if fault_metrics:
            fi = int(fault_metrics.get("fault_injected_count", 0))
            fb = int(fault_metrics.get("fallback_count", 0))
            out["fault_injected_count"] = fi
            out["fallback_count"] = fb
            out["fault_injected_rate"] = (
                round(fi / calls, 4) if calls > 0 else 0.0
            )
            out["fallback_rate"] = round(fb / calls, 4) if calls > 0 else 0.0
        return out

    def get_route_metrics(self) -> dict[str, Any] | None:
        fn = getattr(self._kernel, "get_route_metrics", lambda: None)
        return fn()

    def get_alloc_metrics(self) -> dict[str, Any] | None:
        fn = getattr(self._kernel, "get_alloc_metrics", lambda: None)
        return fn()

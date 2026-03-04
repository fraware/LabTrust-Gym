"""
LLM repair over kernel WHCA: base plan from deterministic kernel (WHCA),
shield-only execute; when shield rejects or security/staleness flags, call LLM
repair then re-shield and execute. Deterministic in llm_offline via seeded backend.

Envelope (SOTA audit):
  - Typical steps per episode: N/A; horizon-driven (scale_config.horizon_steps).
  - LLM calls per step: 0 when kernel plan accepted; 1--3 when repair path used.
  - Fallback on timeout/refusal: kernel plan (all NOOP) or repair fallback NOOP.
  - max_latency_ms: N/A for live; bounded in llm_offline by deterministic backend.
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
        args_tuple = tuple(sorted((k, v) for k, v in (args or {}).items()))
        tupled.append((agent_id, action_type, args_tuple))
    return RouteDecision(per_agent=tuple(tupled), explain="llm_repair")


def _score_repair_candidate(
    route: RouteDecision,
    context: Any,
    result_ok: bool,
) -> float:
    """
    Score a repair candidate: 0 if invalid; else 1.0 plus fairness bonus.
    Used to select best among 3–10 candidates (collision-free, SLA, fairness).
    """
    if not result_ok:
        return -1.0
    work_per_agent: dict[str, int] = {}
    for agent_id, action_type, _ in route.per_agent:
        work_per_agent[agent_id] = work_per_agent.get(agent_id, 0) + (1 if action_type == "START_RUN" else 0)
    if not work_per_agent:
        return 1.0
    counts = list(work_per_agent.values())
    n = len(counts)
    total = sum(counts)
    if total == 0:
        return 1.0
    counts_sorted = sorted(counts)
    cumul = sum((2 * (i + 1) - n - 1) * v for i, v in enumerate(counts_sorted))
    gini = float(cumul) / (n * total) if n and total else 0.0
    return 1.0 - min(1.0, max(0.0, gini))


class DeterministicRepairBackend:
    """
    Deterministic repair backend: returns 3–10 candidate repairs (list of
    per_agent lists). Same repair_input + seed -> same candidate list.
    At least one candidate is valid (all NOOP); others may be NOOP/TICK mix.
    """

    def __init__(self, seed: int = 0) -> None:
        self._seed = seed

    def reset(self, seed: int) -> None:
        self._seed = seed

    def repair(
        self,
        repair_input: dict[str, Any],
        agent_ids: list[str],
    ) -> tuple[list[list[tuple[str, str, dict[str, Any]]]], dict[str, Any]]:
        """
        Return (candidates, meta). candidates = list of 3–10 per_agent lists.
        Deterministic: same input and seed -> same output.
        """
        h = repair_input_hash(repair_input)
        rng = (self._seed + int(h[:8], 16)) % (2**31)
        sorted_agents = sorted(agent_ids)
        candidates: list[list[tuple[str, str, dict[str, Any]]]] = []
        for i in range(5):
            use_tick = (rng + i) % 2 == 0 and len(sorted_agents) > 0
            action_type = "TICK" if use_tick else "NOOP"
            candidates.append([(aid, action_type, {}) for aid in sorted_agents])
        meta = {
            "backend_id": "deterministic_repair",
            "latency_ms": 0.0,
            "tokens_in": 0,
            "tokens_out": 0,
        }
        return candidates, meta


def _noop_repair_result(
    agent_ids: list[str],
) -> tuple[list[tuple[str, str, dict[str, Any]]], dict[str, Any]]:
    """Fallback (all NOOP) and meta for live repair on error."""
    per_agent = [(aid, "NOOP", {}) for aid in sorted(agent_ids)]
    meta = {
        "backend_id": "live_repair_fallback",
        "latency_ms": 0.0,
        "tokens_in": 0,
        "tokens_out": 0,
    }
    return per_agent, meta


class LiveRepairBackend:
    """
    Live repair backend: uses an LLM backend (generate(messages) -> str) to produce
    a repaired plan. Builds prompt from repair_input and agent_ids; parses response
    to per_agent list. On parse/API error returns all NOOP.
    """

    def __init__(self, llm_backend: Any) -> None:
        self._backend = llm_backend
        self._seed = 0

    def reset(self, seed: int) -> None:
        self._seed = seed

    def repair(
        self,
        repair_input: dict[str, Any],
        agent_ids: list[str],
    ) -> tuple[list[tuple[str, str, dict[str, Any]]], dict[str, Any]]:
        import json
        import time

        allowed = (repair_input.get("constraint_summary") or {}).get(
            "allowed_actions", ["NOOP", "TICK", "MOVE", "START_RUN"]
        )
        if not isinstance(allowed, list):
            allowed = ["NOOP", "TICK", "MOVE", "START_RUN"]
        blocked = repair_input.get("blocked_actions", [])
        constraint = repair_input.get("constraint_summary", {})
        user_content = (
            "Repair the blocked plan. Return a single JSON array of objects, "
            "each with agent_id, action_type, args. Allowed action_type values: "
            + json.dumps(allowed)
            + ". agent_ids: "
            + json.dumps(agent_ids)
            + ". repair_input (blocked_actions, constraint_summary): "
            + json.dumps(
                {"blocked_actions": blocked, "constraint_summary": constraint},
                sort_keys=True,
            )
            + ". Return only the JSON array, no markdown."
        )
        messages = [
            {
                "role": "system",
                "content": "Return only a JSON array of {agent_id, action_type, args}.",
            },
            {"role": "user", "content": user_content},
        ]
        tracer = None
        try:
            from labtrust_gym.baselines.llm.llm_tracer import get_llm_tracer

            tracer = get_llm_tracer()
        except Exception:
            pass
        if tracer is not None:
            tracer.start_span("coord_repair")
            tracer.set_attribute("backend_id", "live_repair")
            tracer.set_attribute("model_id", "unknown")
        start = time.perf_counter()
        try:
            raw = self._backend.generate(messages)
        except Exception as e:
            if tracer is not None:
                tracer.set_attribute("latency_ms", 0)
                tracer.end_span("error", str(e)[:200])
            return _noop_repair_result(agent_ids)
        latency_ms = (time.perf_counter() - start) * 1000
        if tracer is not None:
            tracer.set_attribute("latency_ms", round(latency_ms, 2))
        raw = (raw or "").strip()
        if "```" in raw:
            for part in raw.split("```"):
                part = part.strip()
                if part.startswith("json") or part.startswith("["):
                    raw = part.replace("json", "", 1).strip()
                    break
        try:
            from labtrust_gym.baselines.llm.parse_utils import (
                extract_first_json_object,
            )

            extracted = extract_first_json_object(raw)
            if not extracted or not extracted.strip().startswith("["):
                if tracer is not None:
                    tracer.end_span("error", "no JSON array")
                return _noop_repair_result(agent_ids)
            arr = json.loads(extracted)
        except (json.JSONDecodeError, TypeError):
            if tracer is not None:
                tracer.end_span("error", "parse error")
            return _noop_repair_result(agent_ids)
        if not isinstance(arr, list):
            if tracer is not None:
                tracer.end_span("error", "not list")
            return _noop_repair_result(agent_ids)
        per_agent: list[tuple[str, str, dict[str, Any]]] = []
        allowed_set = set(allowed)
        for item in arr:
            if not isinstance(item, dict):
                continue
            aid = str(item.get("agent_id", ""))
            if aid not in agent_ids:
                continue
            atype = str(item.get("action_type", "NOOP")).strip()
            if atype not in allowed_set:
                atype = "NOOP"
            args = item.get("args")
            if not isinstance(args, dict):
                args = {}
            per_agent.append((aid, atype, args))
        for aid in sorted(agent_ids):
            if not any(aid == p[0] for p in per_agent):
                per_agent.append((aid, "NOOP", {}))
        per_agent.sort(key=lambda x: (x[0], x[1]))
        _lm = getattr(self._backend, "last_metrics", lambda: {})
        usage = _lm() if callable(_lm) else (_lm if isinstance(_lm, dict) else {})
        if tracer is not None:
            tracer.set_attribute("prompt_tokens", usage.get("tokens_in", 0))
            tracer.set_attribute("completion_tokens", usage.get("tokens_out", 0))
            if usage.get("estimated_cost_usd") is not None:
                tracer.set_attribute("estimated_cost_usd", usage["estimated_cost_usd"])
            tracer.end_span()
        meta = {
            "backend_id": "live_repair",
            "latency_ms": round(latency_ms, 2),
            "tokens_in": int(usage.get("prompt_tokens", 0) or 0),
            "tokens_out": int(usage.get("completion_tokens", 0) or 0),
        }
        return per_agent, meta


class LLMRepairOverKernelWHCA(CoordinationMethod):
    """
    Compose: kernel (WHCA) -> shield -> if blocked/flagged -> LLM repair
    -> re-shield -> execute (or NOOP). Emits coordination.llm_repair metrics.
    Repair input includes constraint_summary with invariants INV-ROUTE-001, INV-ROUTE-002.
    Backend may return multiple candidate repairs (list of per_agent lists); first that
    passes shield is used (up to 3--10 candidates).
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
        self._seed = int(scale_config.get("seed", seed)) if scale_config else seed
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
            out: dict[str, dict[str, Any]] = {a: {"action_index": ACTION_NOOP} for a in agent_ids}
            for agent_id, action_type, args_tuple in decision.route.per_agent:
                if agent_id in out:
                    out[agent_id] = _route_to_action_dict(agent_id, action_type, args_tuple)
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
            red_team_flags=(repair_triggers if isinstance(repair_triggers, list) else []),
        )

        repair_result = self._repair_backend.repair(repair_input, agent_ids)
        repaired_per_agent, meta = (
            repair_result[0],
            repair_result[1] if len(repair_result) > 1 else {},
        )
        lat = meta.get("latency_ms")
        if lat is not None:
            self._repair_latency_ms_list.append(float(lat))
        ti = int(meta.get("tokens_in", 0) or 0)
        to = int(meta.get("tokens_out", 0) or 0)
        self._repair_tokens_total += ti + to

        candidates: list[list[tuple[str, str, dict[str, Any]]]] = []
        if isinstance(repaired_per_agent, list) and len(repaired_per_agent) > 0:
            first = repaired_per_agent[0]
            if isinstance(first, list):
                for cand in repaired_per_agent[:10]:
                    if isinstance(cand, (list, tuple)) and cand:
                        candidates.append(list(cand))
            else:
                candidates = [list(repaired_per_agent)]

        repaired_route = None
        best_score = -1.0
        for cand in candidates[:10]:
            route = _per_agent_to_route_decision(cand)
            result = validate_plan(route, context)
            score = _score_repair_candidate(route, context, result.ok)
            if score > best_score:
                best_score = score
                if result.ok:
                    repaired_route = route

        if repaired_route is not None:
            self._repair_success_count += 1
            out = {a: {"action_index": ACTION_NOOP} for a in agent_ids}
            for agent_id, action_type, args_tuple in repaired_route.per_agent:
                if agent_id in out:
                    out[agent_id] = _route_to_action_dict(agent_id, action_type, args_tuple)
            return out

        self._repair_fallback_noop_count += 1
        return {a: {"action_index": ACTION_NOOP} for a in agent_ids}

    def get_llm_repair_metrics(self) -> dict[str, Any]:
        """Return coordination.llm_repair block for results v0.2."""
        calls = max(0, self._repair_call_count)
        success_rate = self._repair_success_count / calls if calls > 0 else 0.0
        lat_list = self._repair_latency_ms_list
        mean_latency = sum(lat_list) / len(lat_list) if lat_list else None
        mean_latency_round = round(mean_latency, 2) if mean_latency is not None else None
        out = {
            "repair_call_count": calls,
            "repair_success_rate": round(success_rate, 4),
            "repair_fallback_noop_count": self._repair_fallback_noop_count,
            "mean_repair_latency_ms": mean_latency_round,
            "total_repair_tokens": self._repair_tokens_total,
        }
        fault_metrics = getattr(self._repair_backend, "get_fault_metrics", lambda: None)()
        if fault_metrics:
            fi = int(fault_metrics.get("fault_injected_count", 0))
            fb = int(fault_metrics.get("fallback_count", 0))
            out["fault_injected_count"] = fi
            out["fallback_count"] = fb
            out["fault_injected_rate"] = round(fi / calls, 4) if calls > 0 else 0.0
            out["fallback_rate"] = round(fb / calls, 4) if calls > 0 else 0.0
        return out

    def get_last_planned_path(
        self,
    ) -> (
        tuple[
            list[tuple[str, int, str]],
            list[tuple[str, int, str, str]],
            set[tuple[str, str]],
            dict[str, bool],
        ]
        | None
    ):
        """Delegate to kernel so safety_invariants conformance can run on planned path."""
        fn = getattr(self._kernel, "get_last_planned_path", None)
        return fn() if callable(fn) else None

    def get_route_metrics(self) -> dict[str, Any] | None:
        fn = getattr(self._kernel, "get_route_metrics", lambda: None)
        return fn()

    def get_alloc_metrics(self) -> dict[str, Any] | None:
        fn = getattr(self._kernel, "get_alloc_metrics", lambda: None)
        return fn()

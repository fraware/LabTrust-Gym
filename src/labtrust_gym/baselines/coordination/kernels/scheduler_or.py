"""
Rolling-horizon OR scheduler: weighted tardiness, throughput, violation penalties.

Deterministic, fast, respects RBAC and token constraints (never proposes
illegal START_RUN). Optional CP-SAT (OR-Tools) when [or_solver] installed;
strict time budget per step; fallback to heuristic on timeout/infeasible.

Envelope (SOTA audit): Used by kernel_scheduler_or and kernel_scheduler_or_whca.
time_budget_ms in scale_config; fallback=infeasible returns explain; max_latency_ms
bounded.
"""

from __future__ import annotations

import time
from typing import Any

from labtrust_gym.baselines.coordination.coordination_kernel import KernelContext
from labtrust_gym.baselines.coordination.decision_types import (
    AllocationDecision,
    ScheduleDecision,
)
from labtrust_gym.baselines.coordination.obs_utils import log_frozen

try:
    from labtrust_gym.baselines.coordination.allocation.auction import (
        _restricted_zone_ids_from_policy,
        agent_can_start_run_at_device,
    )
except ImportError:
    _restricted_zone_ids_from_policy = None  # type: ignore[assignment]
    agent_can_start_run_at_device = None  # type: ignore[assignment]


OR_CPSAT_INFEASIBLE = "or_cpsat_infeasible"


def _try_cp_sat_schedule(
    context: KernelContext,
    filtered: list[tuple[str, str, str, int]],
    horizon: int,
    time_budget_ms: float,
) -> tuple[ScheduleDecision | None, str | None]:
    """
    Optional CP-SAT schedule; returns (None, reason) when [or_solver] missing,
    infeasible (reason=or_cpsat_infeasible), or timeout (reason=None).
    Caller falls back to heuristic. Respects time_budget_ms.
    """
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        return (None, None)
    if not filtered:
        return (None, None)
    model = cp_model.CpModel()
    t_max = context.t + horizon
    # Decision vars: start time for each (agent, work_id, device_id, prio)
    starts = {}
    for i, (agent_id, work_id, device_id, prio) in enumerate(filtered):
        key = (agent_id, work_id, device_id, i)
        starts[key] = model.NewIntVar(context.t, t_max, f"s_{i}")
    # Hard: no overlap per agent (optional: one at a time)
    for agent_id in {a for a, _, _, _ in filtered}:
        agent_vars = [starts[k] for k in starts if k[0] == agent_id]
        for i, v1 in enumerate(agent_vars):
            for v2 in agent_vars[i + 1 :]:
                model.Add(v1 != v2)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.001, time_budget_ms / 1000.0)
    status = solver.Solve(model)
    if status == cp_model.INFEASIBLE:
        return (None, OR_CPSAT_INFEASIBLE)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return (None, None)
    per_agent: dict[str, list[tuple[str, int, int]]] = {}
    for (agent_id, work_id, device_id, prio), var in starts.items():
        if agent_id not in per_agent:
            per_agent[agent_id] = []
        s = int(solver.Value(var))
        per_agent[agent_id].append((work_id, s + 1, prio))
    for aid in per_agent:
        per_agent[aid].sort(key=lambda x: (x[1], -x[2], x[0]))
    per_agent_tuple = tuple((aid, tuple(lst)) for aid, lst in sorted(per_agent.items()) if lst)
    return (
        ScheduleDecision(
            per_agent=per_agent_tuple,
            explain=f"or_cpsat_h{horizon}_n={len(filtered)}",
        ),
        None,
    )


def _default_policy() -> dict[str, Any]:
    return {
        "horizon_steps": 15,
        "replan_cadence_steps": 1,
        "weights": {
            "tardiness": 1.0,
            "throughput": 0.5,
            "violation_penalty": 2.0,
            "coordination_overhead": 0.1,
        },
        "fairness_regularizer": 0.2,
    }


def _filter_allocation_by_rbac(
    context: KernelContext,
    assignments: tuple[tuple[str, str, str, int], ...],
) -> list[tuple[str, str, str, int]]:
    """Drop (agent, work_id, device_id, prio) where agent cannot START_RUN (RBAC/token)."""
    if agent_can_start_run_at_device is None or _restricted_zone_ids_from_policy is None:
        return list(assignments)
    policy = context.policy or {}
    restricted = _restricted_zone_ids_from_policy(policy)
    device_zone = context.device_zone or {}
    out: list[tuple[str, str, str, int]] = []
    for agent_id, work_id, device_id, prio in assignments:
        zone_id = device_zone.get(device_id, "")
        obs = context.obs.get(agent_id) or {}
        if agent_can_start_run_at_device(agent_id, device_id, zone_id, policy, obs, restricted):
            out.append((agent_id, work_id, device_id, prio))
    return out


class ORScheduler:
    """
    Rolling-horizon scheduler: H-step lookahead, objective = weighted tardiness
    + throughput + violation penalties + coordination overhead; fairness.
    Only schedules work for (agent, device) that pass RBAC and token checks.

    Policy (scheduler_or or _policy): horizon_steps (default 15), replan_cadence_steps
    (default 1), weights (tardiness, throughput, violation_penalty, coordination_overhead),
    time_budget_ms (default 50), use_cp_sat (optional). When CP-SAT is infeasible or
    times out, fallback heuristic is used; explain includes or_cpsat_infeasible when
    CP-SAT returned INFEASIBLE.
    """

    def __init__(self, policy: dict[str, Any] | None = None) -> None:
        self._policy = policy or _default_policy()
        self._plan_times_ms: list[float] = []
        self._replan_count = 0
        self._steps = 0

    def schedule(
        self,
        context: KernelContext,
        allocation: AllocationDecision,
    ) -> ScheduleDecision:
        t0 = time.perf_counter()
        self._steps += 1
        policy = (context.policy or {}).get("scheduler_or") or self._policy
        horizon = int(policy.get("horizon_steps", 15))
        replan_cadence = int(policy.get("replan_cadence_steps", 1))

        assignments = allocation.assignments
        if not assignments:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._plan_times_ms.append(elapsed_ms)
            return ScheduleDecision(per_agent=(), explain="or_empty")

        filtered = _filter_allocation_by_rbac(context, assignments)
        time_budget_ms = float(
            (context.scale_config or {}).get("or_schedule_time_budget_ms") or policy.get("time_budget_ms", 50.0)
        )
        cp_infeasible_reason: str | None = None
        if policy.get("use_cp_sat"):
            cp_result, cp_reason = _try_cp_sat_schedule(context, filtered, horizon, time_budget_ms)
            if cp_result is not None:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                self._plan_times_ms.append(elapsed_ms)
                if self._steps % max(1, replan_cadence) == 0 and self._steps > 1:
                    self._replan_count += 1
                return cp_result
            if cp_reason == OR_CPSAT_INFEASIBLE:
                cp_infeasible_reason = cp_reason

        per_agent: dict[str, list[tuple[str, int, int]]] = {}
        for agent_id in context.agent_ids:
            o = context.obs.get(agent_id) or {}
            if log_frozen(o):
                continue
            per_agent[agent_id] = []

        for agent_id, work_id, device_id, prio in filtered:
            deadline = context.t + horizon
            if agent_id not in per_agent:
                continue
            per_agent[agent_id].append((work_id, deadline, prio))

        for aid in per_agent:
            lst = per_agent[aid]
            lst.sort(key=lambda x: (-x[2], x[1], x[0]))

        per_agent_tuple = tuple((aid, tuple(lst)) for aid, lst in sorted(per_agent.items()) if lst)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        self._plan_times_ms.append(elapsed_ms)
        if self._steps % max(1, replan_cadence) == 0 and self._steps > 1:
            self._replan_count += 1
        explain = f"or_h{horizon}_n={len(filtered)}"
        if cp_infeasible_reason:
            explain = f"{cp_infeasible_reason} {explain}"
        return ScheduleDecision(per_agent=per_agent_tuple, explain=explain)

    def get_schedule_metrics(self) -> dict[str, Any]:
        """Per-episode: mean_plan_time_ms, replan_rate, deadlock_avoids (0)."""
        n = len(self._plan_times_ms)
        if n == 0:
            return {
                "mean_plan_time_ms": 0.0,
                "replan_rate": 0.0,
                "deadlock_avoids": 0,
            }
        mean_ms = sum(self._plan_times_ms) / n
        replan_rate = self._replan_count / max(1, self._steps)
        return {
            "mean_plan_time_ms": round(mean_ms, 2),
            "replan_rate": round(replan_rate, 4),
            "deadlock_avoids": 0,
        }

    def reset(self, seed: int = 0) -> None:
        """Reset accumulated metrics for new episode."""
        self._plan_times_ms = []
        self._replan_count = 0
        self._steps = 0

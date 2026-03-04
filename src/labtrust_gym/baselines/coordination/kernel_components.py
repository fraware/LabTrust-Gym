"""
Concrete kernel components: allocator, scheduler, router.

CentralizedAllocator: greedy assign by priority and colocation (like centralized_planner).
EDFScheduler: earliest-deadline-first per agent; deterministic tie-break.
TrivialRouter: BFS move or START_RUN from schedule; deterministic.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from labtrust_gym.baselines.coordination.coordination_kernel import KernelContext
from labtrust_gym.baselines.coordination.decision_types import (
    AllocationDecision,
    RouteDecision,
    ScheduleDecision,
)
from labtrust_gym.baselines.coordination.obs_utils import (
    get_queue_by_device,
    get_zone_from_obs,
    log_frozen,
    queue_has_head,
)
from labtrust_gym.engine.zones import build_adjacency_set

try:
    from labtrust_gym.baselines.coordination.allocation.auction import (
        gini_coefficient,
    )
except ImportError:
    gini_coefficient = None  # type: ignore[assignment]


def _bfs_next_zone(
    start: str,
    goal: str,
    adjacency: set[tuple[str, str]],
) -> str | None:
    """Next zone from start toward goal. Deterministic."""
    if start == goal:
        return None
    seen: set[str] = {start}
    queue: deque[tuple[str, list[str]]] = deque([(start, [])])
    while queue:
        node, path = queue.popleft()
        neighbors = sorted([b for (a, b) in adjacency if a == node and b not in seen])
        for n in neighbors:
            seen.add(n)
            new_path = path + [n]
            if n == goal:
                return new_path[0] if new_path else None
            queue.append((n, new_path))
    return None


class CentralizedAllocator:
    """
    Greedy allocation: STAT > URGENT > ROUTINE, colocation, compute_budget.
    When fairness=True, assigns to the agent with fewest current assignments first
    (load balancing; improves Gini work distribution).
    """

    def __init__(
        self,
        compute_budget: int | None = None,
        fairness: bool = False,
    ) -> None:
        self._compute_budget = compute_budget
        self._fairness = bool(fairness)
        self._last_assignments: list[tuple[str, str, str, int]] = []

    def get_alloc_metrics(self) -> dict[str, Any] | None:
        """Alloc metrics: gini_work_distribution from last allocation."""
        if not self._last_assignments or gini_coefficient is None:
            return None
        work_per_agent: dict[str, int] = {}
        for agent_id, _work_id, _device_id, _prio in self._last_assignments:
            work_per_agent[agent_id] = work_per_agent.get(agent_id, 0) + 1
        return {"gini_work_distribution": round(gini_coefficient(work_per_agent), 4)}

    def allocate(self, context: KernelContext) -> AllocationDecision:
        agents = context.agent_ids
        zone_ids = context.zone_ids or []
        device_ids = context.device_ids or []
        device_zone = context.device_zone or {}
        budget = self._compute_budget if self._compute_budget is not None else len(agents) * 2
        if not device_ids:
            return AllocationDecision(explain="no_devices")

        worklist: list[tuple[int, str, str, str]] = []
        for agent_id in agents:
            o = context.obs.get(agent_id) or {}
            if log_frozen(o):
                continue
            my_zone = get_zone_from_obs(o, zone_ids) or o.get("zone_id") or ""
            qbd = get_queue_by_device(o)
            for idx, dev_id in enumerate(device_ids):
                if not queue_has_head(o, idx):
                    continue
                dev_zone = device_zone.get(dev_id, "")
                if my_zone != dev_zone:
                    continue
                head = (qbd[idx] if idx < len(qbd) else {}).get("queue_head", "W")
                prio = 2 if "STAT" in str(head).upper() else (1 if "URGENT" in str(head).upper() else 0)
                worklist.append((prio, dev_id, head or "W", dev_zone))

        worklist.sort(key=lambda x: (-x[0], x[1], x[2]))
        assigned: set[str] = set()
        used_work: set[tuple[str, str]] = set()
        assignments: list[tuple[str, str, str, int]] = []

        work_count = {a: 0 for a in agents}
        for prio, device_id, work_id, zone_id in worklist:
            if len(assigned) >= budget:
                break
            if (device_id, work_id) in used_work:
                continue
            candidates = [
                a
                for a in agents
                if a not in assigned
                and (
                    get_zone_from_obs(context.obs.get(a) or {}, zone_ids)
                    or (context.obs.get(a) or {}).get("zone_id")
                    or ""
                )
                == zone_id
            ]
            if not candidates:
                continue
            if self._fairness:
                candidates.sort(key=lambda a: (work_count[a], a))
            else:
                candidates.sort(key=lambda a: a)
            agent_id = candidates[0]
            assigned.add(agent_id)
            used_work.add((device_id, work_id))
            assignments.append((agent_id, work_id, device_id, prio))
            work_count[agent_id] = work_count.get(agent_id, 0) + 1

        self._last_assignments = list(assignments)
        explain = f"n={len(assignments)}"
        return AllocationDecision(assignments=tuple(assignments), explain=explain)


# Reason code when schedule deadlines are infeasible (plan 1.3)
RC_SCHED_INFEASIBLE = "RC_SCHED_INFEASIBLE"


class EDFScheduler:
    """
    Earliest-deadline-first: order by (deadline_step, priority). Deterministic.
    Preemption: STAT can interrupt ROUTINE when STAT slack <= preemption_sla_threshold.
    Aging: ROUTINE effective priority increases with wait_steps (from scale_config or infos)
    to prevent starvation. Feasibility: if any deadline < t, explain includes RC_SCHED_INFEASIBLE.
    """

    def __init__(
        self,
        deadline_slack_steps: int = 20,
        criticality_slack_steps: dict[int, int] | None = None,
        preemption_sla_threshold: int | None = None,
        aging_steps_per_boost: int = 10,
    ) -> None:
        self._deadline_slack = max(1, min(200, deadline_slack_steps))
        self._criticality_slack = dict(criticality_slack_steps) if criticality_slack_steps else {}
        self._preemption_sla = max(0, preemption_sla_threshold) if preemption_sla_threshold is not None else None
        self._aging_steps_per_boost = max(1, min(200, aging_steps_per_boost))

    def _slack_for_priority(self, prio: int) -> int:
        """Slack steps for this priority (criticality-aware)."""
        if self._criticality_slack and prio in self._criticality_slack:
            return max(1, min(200, self._criticality_slack[prio]))
        return self._deadline_slack

    def _work_wait_steps(self, context: KernelContext, work_id: str) -> int:
        """Optional wait steps for aging (scale_config or infos)."""
        cfg = (context.scale_config or {}).get("work_wait_steps")
        if isinstance(cfg, dict) and work_id in cfg:
            return int(cfg[work_id])
        for info in (context.infos or {}).values():
            if isinstance(info, dict) and "work_wait_steps" in info and work_id in info.get("work_wait_steps", {}):
                return int(info["work_wait_steps"][work_id])
        return 0

    def schedule(
        self,
        context: KernelContext,
        allocation: AllocationDecision,
    ) -> ScheduleDecision:
        per_agent: dict[str, list[tuple[str, int, int]]] = {}
        for agent_id, work_id, device_id, prio in allocation.assignments:
            slack = self._slack_for_priority(prio)
            deadline = context.t + slack
            wait = self._work_wait_steps(context, work_id)
            boost = min(2, wait // self._aging_steps_per_boost) if self._aging_steps_per_boost else 0
            effective_prio = prio + boost
            if agent_id not in per_agent:
                per_agent[agent_id] = []
            per_agent[agent_id].append((work_id, deadline, effective_prio))
        infeasible = False
        for aid in per_agent:
            lst = per_agent[aid]
            if self._preemption_sla is not None:
                t = context.t
                lst.sort(
                    key=lambda x: (
                        0 if (x[1] - t <= self._preemption_sla and x[2] >= 2) else 1,
                        x[1],
                        -x[2],
                        x[0],
                    ),
                )
            else:
                lst.sort(key=lambda x: (x[1], -x[2], x[0]))
            if any(d < context.t for (_, d, _) in lst):
                infeasible = True
        if (context.scale_config or {}).get("edf_force_infeasible"):
            infeasible = True
        per_agent_tuple = tuple((aid, tuple(lst)) for aid, lst in sorted(per_agent.items()))
        explain = "edf"
        if infeasible:
            explain = f"edf {RC_SCHED_INFEASIBLE}"
        return ScheduleDecision(per_agent=per_agent_tuple, explain=explain)


class TrivialRouter:
    """BFS move to goal zone or START_RUN for first scheduled work. Deterministic."""

    def __init__(self) -> None:
        self._adjacency: set[tuple[str, str]] = set()

    def route(
        self,
        context: KernelContext,
        allocation: AllocationDecision,
        schedule: ScheduleDecision,
    ) -> RouteDecision:
        layout = (context.policy or {}).get("zone_layout") or {}
        edges = layout.get("graph_edges") or []
        adjacency = build_adjacency_set(edges)
        zone_ids = context.zone_ids or []
        device_ids = context.device_ids or []
        device_zone = context.device_zone or {}
        per_agent: list[tuple[str, str, tuple[tuple[str, Any], ...]]] = []

        assignment_by_agent: dict[str, tuple[str, str, int]] = {}
        for agent_id, work_id, device_id, prio in allocation.assignments:
            assignment_by_agent[agent_id] = (work_id, device_id, prio)

        schedule_first: dict[str, tuple[str, str, int]] = {}
        for agent_id, seq in schedule.per_agent:
            if seq:
                work_id, deadline, prio = seq[0]
                if agent_id in assignment_by_agent:
                    _, device_id, _ = assignment_by_agent[agent_id]
                    schedule_first[agent_id] = (work_id, device_id, prio)

        for agent_id in context.agent_ids:
            o = context.obs.get(agent_id) or {}
            if log_frozen(o):
                per_agent.append((agent_id, "NOOP", ()))
                continue
            my_zone = get_zone_from_obs(o, zone_ids) or o.get("zone_id") or ""

            if agent_id in schedule_first:
                work_id, device_id, _ = schedule_first[agent_id]
                dev_zone = device_zone.get(device_id, "")
                if my_zone == dev_zone:
                    per_agent.append(
                        (
                            agent_id,
                            "START_RUN",
                            (("device_id", device_id), ("work_id", work_id)),
                        )
                    )
                    continue

            goal = zone_ids[0] if zone_ids else "Z_SORTING_LANES"
            for dev_id in device_ids:
                z = device_zone.get(dev_id)
                if not z:
                    continue
                qbd = get_queue_by_device(o)
                for idx, d in enumerate(device_ids):
                    if d != dev_id:
                        continue
                    if idx < len(qbd) and (qbd[idx].get("queue_len") or 0) > 0:
                        goal = z
                        break
            if my_zone == goal:
                per_agent.append((agent_id, "NOOP", ()))
                continue
            next_z = _bfs_next_zone(my_zone, goal, adjacency)
            if next_z:
                per_agent.append(
                    (
                        agent_id,
                        "MOVE",
                        (("from_zone", my_zone), ("to_zone", next_z)),
                    )
                )
            else:
                per_agent.append((agent_id, "NOOP", ()))

        return RouteDecision(per_agent=tuple(per_agent), explain="trivial")


class WHCARouter:
    """
    Windowed Cooperative A* over zone graph with reservation table.
    Plans collision-free moves for horizon H; deadlock-safe fallback (wait-in-place).
    Deterministic: agent order sorted, tie-break via context.rng.

    Horizon and reservation table:
    - Planning window is horizon steps (1--64). Search is bounded by t in [t0, t0+horizon];
      no separate timeout or iteration cap beyond this.
    - Reservation table: at most one agent per (t, node) (INV-ROUTE-001). When no path
      is found within the window, fallback is safe_wait (wait-in-place / NOOP) and the
      (t, current_zone) is reserved to avoid swap collisions.

    Tuning (state-of-the-art):
    - horizon: planning window (1--64). Can be overridden per step via
      context.scale_config["whca_horizon"] for dynamic tuning.
    - Larger horizon improves path quality but increases reservation density;
      smaller horizon reduces conflicts but may increase deadlock-avoid steps.
    """

    def __init__(self, horizon: int = 10) -> None:
        self._horizon_default = max(1, min(64, horizon))
        self._route_metrics: dict[str, Any] = {}
        self._accumulated: dict[str, Any] = {
            "replan_rate_sum": 0.0,
            "steps": 0,
            "deadlock_avoids": 0,
        }
        self._last_planned_nodes: list[tuple[str, int, str]] = []
        self._last_planned_moves: list[tuple[str, int, str, str]] = []
        self._last_restricted_edges: set[tuple[str, str]] = set()
        self._last_agent_has_token: dict[str, bool] = {}

    def _effective_horizon(self, context: KernelContext) -> int:
        """Horizon for this step: scale_config.whca_horizon or constructor default."""
        cfg = (context.scale_config or {}).get("whca_horizon")
        if cfg is not None:
            try:
                h = int(cfg)
                return max(1, min(64, h))
            except (TypeError, ValueError):
                pass
        return self._horizon_default

    def reset(self, seed: int = 0) -> None:
        """Reset accumulated metrics for new episode."""
        self._accumulated = {
            "replan_rate_sum": 0.0,
            "steps": 0,
            "deadlock_avoids": 0,
        }

    def get_route_metrics(self) -> dict[str, Any]:
        """Aggregated route metrics for results coordination block."""
        s = self._accumulated["steps"]
        if s == 0:
            return {
                "replan_rate": 0.0,
                "mean_plan_time_ms": 0.0,
                "deadlock_avoids": 0,
            }
        return {
            "replan_rate": self._accumulated["replan_rate_sum"] / s,
            "mean_plan_time_ms": 0.0,
            "deadlock_avoids": self._accumulated["deadlock_avoids"],
        }

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
        """
        Return (planned_nodes, planned_moves, restricted_edges, agent_has_token)
        from the last route() call when expose_planned_path was True; else None.
        """
        if not self._last_planned_nodes and not self._last_planned_moves:
            return None
        return (
            list(self._last_planned_nodes),
            list(self._last_planned_moves),
            set(self._last_restricted_edges),
            dict(self._last_agent_has_token),
        )

    def route(
        self,
        context: KernelContext,
        allocation: AllocationDecision,
        schedule: ScheduleDecision,
    ) -> RouteDecision:
        from labtrust_gym.baselines.coordination.routing.fallback import (
            safe_wait_policy,
        )
        from labtrust_gym.baselines.coordination.routing.graph import (
            build_routing_graph,
        )
        from labtrust_gym.baselines.coordination.routing.reservations import (
            ReservationTable,
        )
        from labtrust_gym.baselines.coordination.routing.whca_router import (
            whca_route_and_reserve,
        )

        layout = (context.policy or {}).get("zone_layout") or (context.policy or {}).get("zone_layout_policy") or {}
        zone_ids = context.zone_ids or []
        device_zone = context.device_zone or {}
        rng = context.rng

        try:
            graph = build_routing_graph(layout)
        except Exception:
            graph = None
        if graph is None or not graph.nodes():
            per_agent_no_graph: list[tuple[str, str, tuple[tuple[str, Any], ...]]] = []
            for agent_id in context.agent_ids:
                per_agent_no_graph.append((agent_id, "NOOP", ()))
            self._route_metrics = {
                "replan_rate": 0.0,
                "mean_plan_time_ms": 0.0,
                "deadlock_avoids": 0,
            }
            return RouteDecision(per_agent=tuple(per_agent_no_graph), explain="whca_no_graph")

        horizon = self._effective_horizon(context)
        max_t = context.t + horizon + 1
        reservations = ReservationTable(max_t=max_t)

        assignment_by_agent: dict[str, tuple[str, str, int]] = {}
        for agent_id, work_id, device_id, prio in allocation.assignments:
            assignment_by_agent[agent_id] = (work_id, device_id, prio)
        schedule_first: dict[str, tuple[str, str, int]] = {}
        for agent_id, seq in schedule.per_agent:
            if seq and agent_id in assignment_by_agent:
                work_id, deadline, _ = seq[0]
                _, device_id, _ = assignment_by_agent[agent_id]
                schedule_first[agent_id] = (work_id, device_id, deadline)

        no_path_count = 0
        deadlock_avoids = 0
        per_agent: list[tuple[str, str, tuple[tuple[str, Any], ...]]] = []
        expose_path = (context.scale_config or {}).get("expose_planned_path") is True
        paths_by_agent: dict[str, list[tuple[int, str]]] = {}
        agent_has_token_map: dict[str, bool] = {}

        for agent_id in sorted(context.agent_ids):
            o = context.obs.get(agent_id) or {}
            if log_frozen(o):
                per_agent.append((agent_id, "NOOP", ()))
                continue
            my_zone = get_zone_from_obs(o, zone_ids) or o.get("zone_id") or ""

            if agent_id in schedule_first:
                work_id, device_id, _ = schedule_first[agent_id]
                dev_zone = device_zone.get(device_id, "")
                if my_zone == dev_zone:
                    per_agent.append(
                        (
                            agent_id,
                            "START_RUN",
                            (("device_id", device_id), ("work_id", work_id)),
                        ),
                    )
                    reservations.reserve(context.t, my_zone, agent_id)
                    reservations.reserve(context.t + 1, my_zone, agent_id)
                    if expose_path:
                        paths_by_agent[agent_id] = [
                            (context.t, my_zone),
                            (context.t + 1, my_zone),
                        ]
                        agent_has_token_map[agent_id] = bool(
                            (o.get("token_active") or {}).get("TOKEN_RESTRICTED_ENTRY")
                        )
                    continue
                goal = dev_zone
            else:
                goal = my_zone

            has_token = bool((o.get("token_active") or {}).get("TOKEN_RESTRICTED_ENTRY"))
            agent_has_token_map[agent_id] = has_token
            path = whca_route_and_reserve(
                agent_id,
                my_zone,
                goal,
                context.t,
                horizon,
                graph,
                reservations,
                rng,
                has_restricted_token=has_token,
                zone_order=zone_ids,
            )
            if expose_path and path:
                paths_by_agent[agent_id] = list(path)
            if path and len(path) >= 2:
                next_zone = path[1][1]
                per_agent.append(
                    (
                        agent_id,
                        "MOVE",
                        (("from_zone", my_zone), ("to_zone", next_zone)),
                    ),
                )
            else:
                per_agent.append((agent_id, safe_wait_policy(), ()))
                reservations.reserve(context.t, my_zone, agent_id)
                reservations.reserve(context.t + 1, my_zone, agent_id)
                no_path_count += 1
                deadlock_avoids += 1
                if expose_path and agent_id not in paths_by_agent:
                    paths_by_agent[agent_id] = [(context.t, my_zone), (context.t + 1, my_zone)]

        if expose_path and paths_by_agent:
            planned_nodes = []
            planned_moves = []
            for aid, path_list in paths_by_agent.items():
                for t, node in path_list:
                    planned_nodes.append((aid, t, node))
                for i in range(len(path_list) - 1):
                    t1, n1 = path_list[i]
                    t2, n2 = path_list[i + 1]
                    if t2 == t1 + 1:
                        planned_moves.append((aid, t1, n1, n2))
            self._last_planned_nodes = planned_nodes
            self._last_planned_moves = planned_moves
            re_set = getattr(graph, "restricted_edges_set", None)
            self._last_restricted_edges = set(re_set) if re_set is not None else set()
            self._last_agent_has_token = dict(agent_has_token_map)
        else:
            self._last_planned_nodes = []
            self._last_planned_moves = []
            self._last_restricted_edges = set()
            self._last_agent_has_token = {}

        n_agents = len(context.agent_ids) or 1
        self._route_metrics = {
            "replan_rate": no_path_count / n_agents,
            "mean_plan_time_ms": 0.0,
            "deadlock_avoids": deadlock_avoids,
        }
        self._accumulated["steps"] += 1
        self._accumulated["replan_rate_sum"] += no_path_count / n_agents
        self._accumulated["deadlock_avoids"] += deadlock_avoids
        return RouteDecision(per_agent=tuple(per_agent), explain="whca")

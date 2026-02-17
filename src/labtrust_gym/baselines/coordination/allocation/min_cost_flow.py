"""
Min-cost flow allocator: bipartite agents x tasks, optional [or_solver].
Falls back to greedy (CentralizedAllocator-like) when solver unavailable.
"""

from __future__ import annotations

from typing import Any

from labtrust_gym.baselines.coordination.coordination_kernel import KernelContext
from labtrust_gym.baselines.coordination.decision_types import AllocationDecision
from labtrust_gym.baselines.coordination.obs_utils import (
    get_queue_by_device,
    get_zone_from_obs,
    log_frozen,
    queue_has_head,
)


def _build_task_list(context: KernelContext) -> list[tuple[int, str, str, str]]:
    """(prio, device_id, work_id, zone_id) for each visible task, deduped by (device_id, work_id)."""
    zone_ids = context.zone_ids or []
    device_ids = context.device_ids or []
    device_zone = context.device_zone or {}
    seen: set[tuple[str, str]] = set()
    worklist: list[tuple[int, str, str, str]] = []
    for agent_id in context.agent_ids:
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
            prio = (
                2
                if "STAT" in str(head).upper()
                else (1 if "URGENT" in str(head).upper() else 0)
            )
            key = (dev_id, head or "W")
            if key not in seen:
                seen.add(key)
                worklist.append((prio, dev_id, head or "W", dev_zone))
    return worklist


def _agent_zone(context: KernelContext, agent_id: str) -> str:
    o = context.obs.get(agent_id) or {}
    zone_ids = context.zone_ids or []
    return get_zone_from_obs(o, zone_ids) or o.get("zone_id") or ""


def min_cost_flow_allocate(
    context: KernelContext,
    tasks_per_agent_cap: int = 2,
    fairness_weight: float = 0.1,
    forbidden_edges: Any = None,
) -> AllocationDecision:
    """
    Allocate via min-cost flow on bipartite (agents x tasks).
    Edge cost = -priority + fairness_penalty; forbidden_edges omit edges (RBAC/token).
    Uses networkx max_flow_min_cost when available; else greedy fallback.
    """
    agents = context.agent_ids
    device_ids = context.device_ids or []
    if not device_ids:
        return AllocationDecision(explain="no_devices")

    worklist = _build_task_list(context)
    if not worklist:
        return AllocationDecision(explain="no_tasks")

    try:
        import networkx as nx

        G = nx.DiGraph()
        source, sink = "_source", "_sink"
        # source -> agent: capacity tasks_per_agent_cap, cost 0
        for a in agents:
            G.add_edge(source, a, capacity=tasks_per_agent_cap, weight=0)
        # task nodes: (device_id, work_id) as id
        task_nodes: list[tuple[str, int, str, str, str]] = []
        for i, (prio, dev_id, work_id, zone_id) in enumerate(worklist):
            tid = f"T_{dev_id}_{work_id}_{i}"
            task_nodes.append((tid, prio, dev_id, work_id, zone_id))
            G.add_edge(tid, sink, capacity=1, weight=0)
        # agent -> task: only if same zone; cost = (2 - prio)*1000 + fairness
        forbidden = set(forbidden_edges or [])
        work_count: dict[str, int] = {a: 0 for a in agents}
        for tid, prio, dev_id, work_id, zone_id in task_nodes:
            for a in agents:
                if _agent_zone(context, a) != zone_id:
                    continue
                if (a, tid) in forbidden or (a, (dev_id, work_id)) in forbidden:
                    continue
                # minimize cost: prefer high prio (low 2-prio), low work_count
                cost = (2 - prio) * 1000 + fairness_weight * (work_count[a] or 0)
                G.add_edge(a, tid, capacity=1, weight=cost)
            # after adding edges we don't update work_count here; flow solves it

        flow_dict = nx.max_flow_min_cost(G, source, sink)
        assignments: list[tuple[str, str, str, int]] = []
        for a in agents:
            for tid, flow in (flow_dict.get(a) or {}).items():
                if flow <= 0 or not tid.startswith("T_"):
                    continue
                for tn in task_nodes:
                    if tn[0] == tid:
                        _, prio, dev_id, work_id, _ = tn
                        assignments.append((a, work_id, dev_id, prio))
                        break
        if not assignments:
            return AllocationDecision(explain="mcf_zero_flow")
        return AllocationDecision(
            assignments=tuple(assignments),
            explain=f"mcf_n={len(assignments)}",
        )
    except ImportError:
        pass
    # Fallback: greedy (same logic as CentralizedAllocator)
    worklist.sort(key=lambda x: (-x[0], x[1], x[2]))
    assigned: set[str] = set()
    used_work: set[tuple[str, str]] = set()
    assignments = []
    work_count = {a: 0 for a in agents}
    budget = tasks_per_agent_cap * len(agents)
    for prio, device_id, work_id, zone_id in worklist:
        if len(assignments) >= budget:
            break
        if (device_id, work_id) in used_work:
            continue
        candidates = [
            a
            for a in agents
            if a not in assigned
            and _agent_zone(context, a) == zone_id
            and ((a, (device_id, work_id)) not in (forbidden_edges or set()))
        ]
        if not candidates:
            continue
        candidates.sort(key=lambda a: (work_count[a], a))
        agent_id = candidates[0]
        assigned.add(agent_id)
        used_work.add((device_id, work_id))
        assignments.append((agent_id, work_id, device_id, prio))
        work_count[agent_id] = work_count.get(agent_id, 0) + 1
    return AllocationDecision(
        assignments=tuple(assignments),
        explain=f"greedy_n={len(assignments)}",
    )


class MinCostFlowAllocator:
    """
    Allocator using min-cost flow on agents x tasks.
    Same interface as CentralizedAllocator.allocate(context) -> AllocationDecision.
    """

    def __init__(
        self,
        compute_budget: int | None = None,
        tasks_per_agent_cap: int = 2,
        fairness_weight: float = 0.1,
    ) -> None:
        self._compute_budget = compute_budget
        self._tasks_per_agent_cap = max(1, min(32, tasks_per_agent_cap))
        self._fairness_weight = max(0.0, min(1.0, fairness_weight))
        self._last_assignments: list[tuple[str, str, str, int]] = []

    def allocate(self, context: KernelContext) -> AllocationDecision:
        cap = self._tasks_per_agent_cap
        if self._compute_budget is not None:
            cap = min(cap, max(1, self._compute_budget // max(1, len(context.agent_ids))))
        decision = min_cost_flow_allocate(
            context,
            tasks_per_agent_cap=cap,
            fairness_weight=self._fairness_weight,
        )
        self._last_assignments = list(decision.assignments)
        return decision

    def get_alloc_metrics(self) -> dict[str, Any] | None:
        """Alloc metrics from last allocation."""
        if not self._last_assignments:
            return None
        try:
            from labtrust_gym.baselines.coordination.allocation.auction import (
                gini_coefficient,
            )
        except ImportError:
            return None
        work_per_agent: dict[str, int] = {}
        for agent_id, _w, _d, _p in self._last_assignments:
            work_per_agent[agent_id] = work_per_agent.get(agent_id, 0) + 1
        return {"gini_work_distribution": round(gini_coefficient(work_per_agent), 4)}

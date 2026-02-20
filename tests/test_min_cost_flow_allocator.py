"""
Tests for min-cost flow allocator (bipartite agents x tasks).
"""

from __future__ import annotations

import random

import pytest

from labtrust_gym.baselines.coordination.allocation.min_cost_flow import (
    MinCostFlowAllocator,
    min_cost_flow_allocate,
    _build_task_list,
    _agent_zone,
)
from labtrust_gym.baselines.coordination.coordination_kernel import KernelContext
from labtrust_gym.baselines.coordination.decision_types import AllocationDecision


def _brute_force_optimal_cost(
    context: KernelContext,
    tasks_per_agent_cap: int,
    fairness_weight: float = 0.0,
) -> float:
    """
    Enumerate all valid assignments for N agents x M tasks (N, M <= 6); return minimum total cost
    among assignments that assign the maximum possible number of tasks (same as MCF).
    Cost per (agent, task) = (2 - prio) * 1000 + fairness_weight * (current work count of agent).
    Same zone only; each task at most once; each agent at most tasks_per_agent_cap.
    """
    worklist = _build_task_list(context)
    agents = list(context.agent_ids)
    if not worklist or not agents:
        return 0.0
    n_tasks = len(worklist)
    max_assignable = min(n_tasks, len(agents) * tasks_per_agent_cap)
    if max_assignable == 0:
        return 0.0
    agent_zone_map = {a: _agent_zone(context, a) for a in agents}

    def recurse(
        task_i: int,
        agent_counts: dict[str, int],
        current_cost: float,
        remaining_to_assign: int,
    ) -> float:
        if remaining_to_assign == 0:
            return current_cost
        if task_i >= n_tasks:
            return float("inf")
        prio, _dev_id, _work_id, zone_id = worklist[task_i]
        best = float("inf")
        if n_tasks - task_i > remaining_to_assign:
            best = recurse(
                task_i + 1, dict(agent_counts), current_cost, remaining_to_assign
            )
        for a_idx, a in enumerate(agents):
            if agent_zone_map[a] != zone_id:
                continue
            if agent_counts.get(a, 0) >= tasks_per_agent_cap:
                continue
            new_counts = dict(agent_counts)
            new_counts[a] = new_counts.get(a, 0) + 1
            edge_cost = (2 - prio) * 1000 + fairness_weight * (agent_counts.get(a, 0))
            best = min(
                best,
                recurse(
                    task_i + 1,
                    new_counts,
                    current_cost + edge_cost,
                    remaining_to_assign - 1,
                ),
            )
        return best

    return recurse(0, {}, 0.0, max_assignable)


def _minimal_context(
    agent_ids: list[str],
    zone_ids: list[str],
    device_ids: list[str],
    device_zone: dict[str, str],
    obs_with_tasks: dict[str, dict],
) -> KernelContext:
    """Build KernelContext for allocator tests."""
    zones = [{"zone_id": z} for z in zone_ids]
    placement = [{"device_id": d, "zone_id": device_zone.get(d, "")} for d in device_ids]
    policy = {
        "zone_layout": {"zones": zones, "device_placement": placement},
    }
    return KernelContext(
        obs=obs_with_tasks,
        infos={},
        t=0,
        policy=policy,
        scale_config={"seed": 42},
        seed=42,
        rng=random.Random(42),
    )


def test_min_cost_flow_no_devices() -> None:
    """No devices -> AllocationDecision with explain no_devices."""
    ctx = _minimal_context(
        agent_ids=["a1"],
        zone_ids=["Z_A"],
        device_ids=[],
        device_zone={},
        obs_with_tasks={"a1": {"zone_id": "Z_A", "queue_by_device": []}},
    )
    decision = min_cost_flow_allocate(ctx)
    assert decision.explain == "no_devices"
    assert len(decision.assignments) == 0


def test_min_cost_flow_no_tasks() -> None:
    """No queue heads -> no assignments."""
    ctx = _minimal_context(
        agent_ids=["a1"],
        zone_ids=["Z_A"],
        device_ids=["DEV_1"],
        device_zone={"DEV_1": "Z_A"},
        obs_with_tasks={
            "a1": {
                "zone_id": "Z_A",
                "queue_by_device": [{"queue_head": "", "queue_len": 0}],
                "queue_has_head": [0],
            },
        },
    )
    decision = min_cost_flow_allocate(ctx)
    assert len(decision.assignments) == 0


def test_min_cost_flow_one_agent_one_task() -> None:
    """One agent in zone, one device with queue head -> one assignment."""
    ctx = _minimal_context(
        agent_ids=["a1"],
        zone_ids=["Z_A"],
        device_ids=["DEV_1"],
        device_zone={"DEV_1": "Z_A"},
        obs_with_tasks={
            "a1": {
                "zone_id": "Z_A",
                "queue_by_device": [{"queue_head": "W1", "queue_len": 1}],
                "queue_has_head": [1],
            },
        },
    )
    decision = min_cost_flow_allocate(ctx, tasks_per_agent_cap=2)
    assert len(decision.assignments) >= 1
    (agent_id, work_id, device_id, prio) = decision.assignments[0]
    assert agent_id == "a1"
    assert work_id == "W1"
    assert device_id == "DEV_1"
    assert prio in (0, 1, 2)


def test_min_cost_flow_allocator_interface() -> None:
    """MinCostFlowAllocator.allocate returns AllocationDecision."""
    alloc = MinCostFlowAllocator(tasks_per_agent_cap=2, fairness_weight=0.1)
    ctx = _minimal_context(
        agent_ids=["a1", "a2"],
        zone_ids=["Z_A"],
        device_ids=["DEV_1"],
        device_zone={"DEV_1": "Z_A"},
        obs_with_tasks={
            "a1": {
                "zone_id": "Z_A",
                "queue_by_device": [{"queue_head": "W1", "queue_len": 1}],
                "queue_has_head": [1],
            },
            "a2": {
                "zone_id": "Z_A",
                "queue_by_device": [{"queue_head": "", "queue_len": 0}],
                "queue_has_head": [0],
            },
        },
    )
    decision = alloc.allocate(ctx)
    assert isinstance(decision, AllocationDecision)
    assert len(decision.assignments) >= 1
    metrics = alloc.get_alloc_metrics()
    assert metrics is None or "gini_work_distribution" in metrics


def test_min_cost_flow_brute_force_vs_mcf() -> None:
    """Small N (<=6) agents and tasks: MCF total cost equals brute-force optimum."""
    pytest.importorskip("networkx")
    agent_ids = ["a1", "a2", "a3"]
    zone_ids = ["Z_A"]
    device_ids = ["D1", "D2"]
    device_zone = {"D1": "Z_A", "D2": "Z_A"}
    obs = {
        "a1": {
            "zone_id": "Z_A",
            "queue_by_device": [
                {"queue_head": "W1", "queue_len": 1},
                {"queue_head": "W2", "queue_len": 1},
            ],
            "queue_has_head": [1, 1],
        },
        "a2": {
            "zone_id": "Z_A",
            "queue_by_device": [
                {"queue_head": "W1", "queue_len": 1},
                {"queue_head": "W2", "queue_len": 1},
            ],
            "queue_has_head": [1, 1],
        },
        "a3": {
            "zone_id": "Z_A",
            "queue_by_device": [
                {"queue_head": "W1", "queue_len": 1},
                {"queue_head": "W2", "queue_len": 1},
            ],
            "queue_has_head": [1, 1],
        },
    }
    ctx = _minimal_context(
        agent_ids=agent_ids,
        zone_ids=zone_ids,
        device_ids=device_ids,
        device_zone=device_zone,
        obs_with_tasks=obs,
    )
    brute_opt = _brute_force_optimal_cost(ctx, tasks_per_agent_cap=2, fairness_weight=0.0)
    decision = min_cost_flow_allocate(
        ctx, tasks_per_agent_cap=2, fairness_weight=0.0
    )
    if not decision.assignments or "greedy" in (decision.explain or ""):
        pytest.skip("networkx not used or zero flow")
    mcf_cost = sum(
        (2 - p) * 1000 for _a, _w, _d, p in decision.assignments
    )
    assert mcf_cost == brute_opt, (
        f"MCF cost {mcf_cost} should equal brute-force optimum {brute_opt}"
    )
    for agent_id, work_id, device_id, _ in decision.assignments:
        assert agent_id in agent_ids
        assert (device_id, work_id) in {("D1", "W1"), ("D2", "W2")}


def test_min_cost_flow_forbidden_edges() -> None:
    """forbidden_edges (agent_x, (dev_id, work_id)) -> assignment never contains that pair."""
    pytest.importorskip("networkx")
    agent_ids = ["a1", "a2"]
    device_ids = ["DEV_1", "DEV_2"]
    device_zone = {"DEV_1": "Z_A", "DEV_2": "Z_A"}
    obs = {
        "a1": {
            "zone_id": "Z_A",
            "queue_by_device": [
                {"queue_head": "W1", "queue_len": 1},
                {"queue_head": "W2", "queue_len": 1},
            ],
            "queue_has_head": [1, 1],
        },
        "a2": {
            "zone_id": "Z_A",
            "queue_by_device": [
                {"queue_head": "W1", "queue_len": 1},
                {"queue_head": "W2", "queue_len": 1},
            ],
            "queue_has_head": [1, 1],
        },
    }
    ctx = _minimal_context(
        agent_ids=agent_ids,
        zone_ids=["Z_A"],
        device_ids=device_ids,
        device_zone=device_zone,
        obs_with_tasks=obs,
    )
    forbidden_edges = [("a1", ("DEV_1", "W1"))]
    decision = min_cost_flow_allocate(
        ctx, tasks_per_agent_cap=2, forbidden_edges=forbidden_edges
    )
    for agent_id, work_id, device_id, _ in decision.assignments:
        assert (agent_id, (device_id, work_id)) not in forbidden_edges
    assert not any(
        a == "a1" and (d, w) == ("DEV_1", "W1")
        for a, w, d, _ in decision.assignments
    )


def test_min_cost_flow_gini_fairness() -> None:
    """fairness_weight=0.2 yields Gini <= fairness_weight=0 (or stable)."""
    pytest.importorskip("networkx")
    try:
        from labtrust_gym.baselines.coordination.allocation.auction import (
            gini_coefficient,
        )
    except ImportError:
        pytest.skip("gini_coefficient not available")
    agent_ids = ["a1", "a2", "a3"]
    device_ids = ["D1", "D2", "D3"]
    device_zone = {d: "Z_A" for d in device_ids}
    obs = {
        aid: {
            "zone_id": "Z_A",
            "queue_by_device": [
                {"queue_head": f"W{d}", "queue_len": 1} for d in device_ids
            ],
            "queue_has_head": [1, 1, 1],
        }
        for aid in agent_ids
    }
    ctx = _minimal_context(
        agent_ids=agent_ids,
        zone_ids=["Z_A"],
        device_ids=device_ids,
        device_zone=device_zone,
        obs_with_tasks=obs,
    )
    decision_zero = min_cost_flow_allocate(
        ctx, tasks_per_agent_cap=3, fairness_weight=0.0
    )
    decision_fair = min_cost_flow_allocate(
        ctx, tasks_per_agent_cap=3, fairness_weight=0.2
    )
    def gini(decision: AllocationDecision) -> float:
        work_per_agent: dict[str, int] = {a: 0 for a in agent_ids}
        for a, _w, _d, _ in decision.assignments:
            work_per_agent[a] = work_per_agent.get(a, 0) + 1
        return gini_coefficient(work_per_agent)
    g0 = gini(decision_zero)
    gf = gini(decision_fair)
    assert gf <= g0 + 1e-6

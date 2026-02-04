"""
Composition: swapping only the router changes route_hash but not allocation_hash/schedule_hash.
"""

from __future__ import annotations

from labtrust_gym.baselines.coordination.coordination_kernel import (
    KernelContext,
    RouteDecision,
)
from labtrust_gym.baselines.coordination.decision_types import (
    AllocationDecision,
    ScheduleDecision,
)
from labtrust_gym.baselines.coordination.kernel_components import (
    CentralizedAllocator,
    EDFScheduler,
    TrivialRouter,
)
from labtrust_gym.baselines.coordination.compose import (
    build_kernel_context,
    compose_kernel,
)


def _minimal_policy() -> dict:
    from pathlib import Path
    from labtrust_gym.policy.loader import load_yaml

    root = Path(__file__).resolve().parent.parent
    zone_path = root / "policy" / "zones" / "zone_layout_policy.v0.1.yaml"
    if not zone_path.exists():
        return {"zone_layout": {"zones": [], "graph_edges": [], "device_placement": []}}
    data = load_yaml(zone_path)
    layout = data.get("zone_layout") or data
    return {"zone_layout": layout}


class AlternateRouter:
    """Router that returns different per-agent actions to change route_hash."""

    def route(
        self,
        context: KernelContext,
        allocation: AllocationDecision,
        schedule: ScheduleDecision,
    ) -> RouteDecision:
        # Return TICK for first agent so payload differs from TrivialRouter (NOOP/MOVE/START_RUN).
        per_agent = []
        for i, aid in enumerate(context.agent_ids):
            if i == 0:
                per_agent.append((aid, "TICK", ()))
            else:
                per_agent.append((aid, "NOOP", ()))
        return RouteDecision(per_agent=tuple(per_agent), explain="alternate_tick")


def test_swap_router_changes_route_hash_only() -> None:
    """Same allocator + scheduler; different router => same allocation_hash, schedule_hash; different route_hash."""
    policy = _minimal_policy()
    scale_config = {"num_agents_total": 2, "horizon_steps": 10}
    agent_ids = ["worker_0", "worker_1"]
    obs = {}
    for i, aid in enumerate(agent_ids):
        obs[aid] = {
            "my_zone_idx": 1 + i,
            "zone_id": "Z_SORTING_LANES" if i == 0 else "Z_ANALYZER_HALL_A",
            "queue_has_head": [0, 0],
            "queue_by_device": [
                {"queue_head": "", "queue_len": 0},
                {"queue_head": "", "queue_len": 0},
            ],
            "log_frozen": 0,
        }
    infos = {}
    seed = 7
    ctx = build_kernel_context(obs, infos, 0, policy, scale_config, seed)

    method_a = compose_kernel(
        CentralizedAllocator(2),
        EDFScheduler(),
        TrivialRouter(),
        "kernel_centralized_edf",
    )
    method_a.reset(seed, policy, scale_config)
    actions_a, decision_a = method_a.step(ctx)

    method_b = compose_kernel(
        CentralizedAllocator(2),
        EDFScheduler(),
        AlternateRouter(),
        "kernel_centralized_edf",
    )
    method_b.reset(seed, policy, scale_config)
    actions_b, decision_b = method_b.step(ctx)

    assert decision_a is not None
    assert decision_b is not None
    assert decision_a.allocation_hash == decision_b.allocation_hash
    assert decision_a.schedule_hash == decision_b.schedule_hash
    assert decision_a.route_hash != decision_b.route_hash

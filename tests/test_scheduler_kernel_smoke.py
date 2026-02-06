"""
Kernel OR scheduler smoke: small-scale config, few steps, no crash, decision shape.
"""

from __future__ import annotations

from pathlib import Path

from labtrust_gym.baselines.coordination.compose import (
    build_kernel_context,
)
from labtrust_gym.baselines.coordination.decision_types import CoordinationDecision
from labtrust_gym.baselines.coordination.kernels.scheduler_or import ORScheduler
from labtrust_gym.baselines.coordination.registry import make_coordination_method


def _minimal_obs(agent_ids: list, zone_id: str = "Z_SORTING_LANES") -> dict:
    obs = {}
    for i, aid in enumerate(agent_ids):
        obs[aid] = {
            "my_zone_idx": 1,
            "zone_id": zone_id,
            "queue_has_head": [1, 0],
            "queue_by_device": [
                {"device_id": "D1", "queue_head": "W1", "queue_len": 1},
                {"device_id": "D2", "queue_head": "", "queue_len": 0},
            ],
            "log_frozen": 0,
        }
    return obs


def test_kernel_scheduler_or_step_returns_actions_and_decision() -> None:
    """Composed kernel_scheduler_or step() returns (actions, CoordinationDecision)."""
    repo = Path(__file__).resolve().parent.parent
    method = make_coordination_method(
        "kernel_scheduler_or",
        policy={},
        repo_root=repo,
        scale_config={"num_agents_total": 2, "horizon_steps": 20},
    )
    method.reset(seed=42, policy={}, scale_config={})
    agent_ids = ["worker_0", "worker_1"]
    obs = _minimal_obs(agent_ids)
    infos: dict = {}
    ctx = build_kernel_context(obs, infos, 0, {}, {}, 42)
    actions, decision = method.step(ctx)
    assert isinstance(actions, dict)
    assert set(actions.keys()) == set(agent_ids)
    assert isinstance(decision, CoordinationDecision)
    assert decision.method_id == "kernel_scheduler_or"
    assert hasattr(decision, "allocation_hash")
    assert hasattr(decision, "schedule_hash")
    assert hasattr(decision, "route_hash")
    for aid in agent_ids:
        assert "action_index" in actions[aid]


def test_kernel_scheduler_or_metrics_exposed() -> None:
    """get_schedule_metrics and get_alloc_metrics return expected keys."""
    repo = Path(__file__).resolve().parent.parent
    policy = {
        "zone_layout": {
            "zones": [{"zone_id": "Z_A"}],
            "device_placement": [{"device_id": "D1", "zone_id": "Z_A"}],
        },
    }
    method = make_coordination_method(
        "kernel_scheduler_or",
        policy=policy,
        repo_root=repo,
        scale_config={"num_agents_total": 2},
    )
    method.reset(seed=0, policy=policy, scale_config={})
    agent_ids = ["worker_0", "worker_1"]
    obs = _minimal_obs(agent_ids, zone_id="Z_A")
    infos: dict = {}
    for t in range(3):
        ctx = build_kernel_context(obs, infos, t, policy, {}, 0)
        method.step(ctx)
    sched = method.get_schedule_metrics()
    assert sched is not None
    assert "mean_plan_time_ms" in sched
    assert "replan_rate" in sched
    assert "deadlock_avoids" in sched
    alloc = method.get_alloc_metrics()
    assert alloc is not None
    assert "gini_work_distribution" in alloc


def test_orscheduler_standalone_produces_schedule_decision() -> None:
    """ORScheduler.schedule(context, allocation) returns ScheduleDecision."""
    from labtrust_gym.baselines.coordination.decision_types import (
        AllocationDecision,
        ScheduleDecision,
    )

    sched = ORScheduler(policy={"horizon_steps": 10})
    policy = {"scheduler_or": {"horizon_steps": 10}}
    obs = _minimal_obs(["a", "b"])
    import random

    rng = random.Random(0)
    ctx = build_kernel_context(obs, {}, 0, policy, {}, 0)
    ctx.rng = rng
    alloc = AllocationDecision(
        assignments=(("a", "W1", "D1", 1), ("b", "W2", "D2", 0)),
        explain="test",
    )
    out = sched.schedule(ctx, alloc)
    assert isinstance(out, ScheduleDecision)
    assert hasattr(out, "per_agent")
    assert hasattr(out, "explain")
    m = sched.get_schedule_metrics()
    assert m["mean_plan_time_ms"] >= 0
    assert m["replan_rate"] >= 0

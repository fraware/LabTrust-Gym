"""
Tests for EDFScheduler: preemption, aging, RC_SCHED_INFEASIBLE.
"""

from __future__ import annotations

import random

from labtrust_gym.baselines.coordination.coordination_kernel import KernelContext
from labtrust_gym.baselines.coordination.decision_types import (
    AllocationDecision,
)
from labtrust_gym.baselines.coordination.kernel_components import (
    RC_SCHED_INFEASIBLE,
    EDFScheduler,
)


def _context(t: int, scale_config: dict | None = None) -> KernelContext:
    obs = {"a1": {"zone_id": "Z_A", "queue_by_device": []}}
    return KernelContext(
        obs=obs,
        infos={},
        t=t,
        policy={},
        scale_config=scale_config or {},
        seed=42,
        rng=random.Random(42 + t),
    )


def test_edf_basic_schedule() -> None:
    """EDF orders by deadline then priority."""
    sched = EDFScheduler(deadline_slack_steps=10)
    ctx = _context(0)
    alloc = AllocationDecision(
        assignments=(("a1", "W1", "D1", 2), ("a1", "W2", "D2", 0)),
        explain="",
    )
    out = sched.schedule(ctx, alloc)
    assert out.per_agent
    (aid, seq) = out.per_agent[0]
    assert aid == "a1"
    assert len(seq) == 2
    assert out.explain == "edf"


def test_edf_rc_sched_infeasible() -> None:
    """When infeasible (deadline < t or edf_force_infeasible), explain has RC_SCHED_INFEASIBLE."""
    sched = EDFScheduler(deadline_slack_steps=2)
    ctx = _context(0, scale_config={"edf_force_infeasible": True})
    alloc = AllocationDecision(
        assignments=(("a1", "W1", "D1", 0),),
        explain="",
    )
    out = sched.schedule(ctx, alloc)
    assert RC_SCHED_INFEASIBLE in out.explain


def test_edf_stat_preemption() -> None:
    """STAT (prio 2) with slack 3 is scheduled before ROUTINE (prio 0) with slack 20 when preemption_sla_threshold=5."""
    sched = EDFScheduler(
        deadline_slack_steps=20,
        criticality_slack_steps={2: 3, 0: 20},
        preemption_sla_threshold=5,
    )
    ctx = _context(0)
    alloc = AllocationDecision(
        assignments=(
            ("a1", "W_ROUTINE", "D2", 0),
            ("a1", "W_STAT", "D1", 2),
        ),
        explain="",
    )
    out = sched.schedule(ctx, alloc)
    (aid, seq) = out.per_agent[0]
    assert aid == "a1"
    assert len(seq) >= 2
    first_work_id = seq[0][0]
    assert first_work_id == "W_STAT"


def test_edf_aging_starvation() -> None:
    """ROUTINE task with work_wait_steps boosted gets higher effective priority and is scheduled first."""
    sched = EDFScheduler(deadline_slack_steps=20, aging_steps_per_boost=10)
    ctx = _context(0, scale_config={"work_wait_steps": {"W_WAITED": 25}})
    alloc = AllocationDecision(
        assignments=(
            ("a1", "W_FRESH", "D1", 0),
            ("a1", "W_WAITED", "D2", 0),
        ),
        explain="",
    )
    out = sched.schedule(ctx, alloc)
    (aid, seq) = out.per_agent[0]
    assert aid == "a1"
    assert len(seq) >= 2
    first_work_id = seq[0][0]
    assert first_work_id == "W_WAITED"


def test_kernel_centralized_edf_stat_before_routine() -> None:
    """Composed kernel_centralized_edf: STAT is scheduled before ROUTINE (same agent, two devices in one zone)."""
    from pathlib import Path

    from labtrust_gym.baselines.coordination.registry import make_coordination_method

    repo_root = Path(__file__).resolve().parent.parent
    policy = {
        "zone_layout": {
            "zones": [{"zone_id": "Z_A"}],
            "device_placement": [
                {"device_id": "D1", "zone_id": "Z_A"},
                {"device_id": "D2", "zone_id": "Z_A"},
            ],
            "graph_edges": [],
        },
        "pz_to_engine": {"a1": "ops_0"},
    }
    obs = {
        "a1": {
            "zone_id": "Z_A",
            "queue_by_device": [
                {"queue_len": 1, "queue_head": "W_STAT"},
                {"queue_len": 1, "queue_head": "W_ROUTINE"},
            ],
            "queue_has_head": [1, 1],
            "log_frozen": 0,
        },
    }
    scale_config = {"seed": 42}
    coord = make_coordination_method(
        "kernel_centralized_edf",
        policy,
        repo_root=repo_root,
        scale_config=scale_config,
    )
    coord.reset(seed=42, policy=policy, scale_config=scale_config)
    actions = coord.propose_actions(obs, {}, 0)
    rec = actions.get("a1", {})
    assert rec.get("action_type") == "START_RUN"
    assert rec.get("args", {}).get("work_id") == "W_STAT"

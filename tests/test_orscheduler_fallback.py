"""
Tests for ORScheduler: heuristic fallback when use_cp_sat false or ortools missing;
time budget respected when CP-SAT used.
"""

from __future__ import annotations

import random

import pytest

from labtrust_gym.baselines.coordination.coordination_kernel import KernelContext
from labtrust_gym.baselines.coordination.decision_types import (
    AllocationDecision,
    ScheduleDecision,
)
from labtrust_gym.baselines.coordination.kernels.scheduler_or import ORScheduler


def _context_with_policy(t: int, use_cp_sat: bool = False) -> KernelContext:
    obs = {
        "a1": {"zone_id": "Z_A", "queue_by_device": [], "log_frozen": 0},
        "a2": {"zone_id": "Z_A", "queue_by_device": [], "log_frozen": 0},
    }
    policy = {
        "zone_layout": {"zones": [{"zone_id": "Z_A"}], "device_placement": [{"device_id": "D1", "zone_id": "Z_A"}]},
        "scheduler_or": {"horizon_steps": 5, "use_cp_sat": use_cp_sat, "time_budget_ms": 20.0},
    }
    return KernelContext(
        obs=obs,
        infos={},
        t=t,
        policy=policy,
        scale_config={"seed": 42},
        seed=42,
        rng=random.Random(42),
    )


def test_orscheduler_heuristic_returns_schedule() -> None:
    """Without use_cp_sat, ORScheduler returns valid ScheduleDecision."""
    sched = ORScheduler()
    ctx = _context_with_policy(0, use_cp_sat=False)
    alloc = AllocationDecision(
        assignments=(("a1", "W1", "D1", 1),),
        explain="",
    )
    out = sched.schedule(ctx, alloc)
    assert isinstance(out, ScheduleDecision)
    assert "or_" in out.explain.lower() or "or_h" in out.explain


def test_orscheduler_empty_allocation() -> None:
    """Empty allocation -> or_empty."""
    sched = ORScheduler()
    ctx = _context_with_policy(0)
    out = sched.schedule(ctx, AllocationDecision(assignments=(), explain=""))
    assert out.explain == "or_empty"
    assert out.per_agent == ()


def test_orscheduler_cp_sat_infeasible_returns_fallback_with_reason() -> None:
    """Impossible constraints (e.g. horizon=0 with two tasks same agent) -> fallback and explain mentions infeasibility."""
    pytest.importorskip("ortools")
    sched = ORScheduler()
    obs = {
        "a1": {"zone_id": "Z_A", "queue_by_device": [], "log_frozen": 0},
    }
    policy = {
        "zone_layout": {"zones": [{"zone_id": "Z_A"}], "device_placement": [{"device_id": "D1", "zone_id": "Z_A"}]},
        "scheduler_or": {
            "horizon_steps": 0,
            "use_cp_sat": True,
            "time_budget_ms": 50.0,
        },
    }
    ctx = KernelContext(
        obs=obs,
        infos={},
        t=10,
        policy=policy,
        scale_config={"seed": 42},
        seed=42,
        rng=random.Random(42),
    )
    alloc = AllocationDecision(
        assignments=(
            ("a1", "W1", "D1", 0),
            ("a1", "W2", "D1", 0),
        ),
        explain="",
    )
    out = sched.schedule(ctx, alloc)
    assert isinstance(out, ScheduleDecision)
    assert out.per_agent
    assert "or_cpsat_infeasible" in out.explain


def test_orscheduler_timeout_returns_fallback_no_hang() -> None:
    """Very low time_budget_ms -> fallback or solution; no hard hang."""
    pytest.importorskip("ortools")
    import time as time_module

    sched = ORScheduler()
    policy = {
        "zone_layout": {"zones": [{"zone_id": "Z_A"}], "device_placement": [{"device_id": "D1", "zone_id": "Z_A"}]},
        "scheduler_or": {
            "horizon_steps": 5,
            "use_cp_sat": True,
            "time_budget_ms": 0.1,
        },
    }
    ctx = KernelContext(
        obs={"a1": {"zone_id": "Z_A", "queue_by_device": [], "log_frozen": 0}},
        infos={},
        t=0,
        policy=policy,
        scale_config={"seed": 42},
        seed=42,
        rng=random.Random(42),
    )
    alloc = AllocationDecision(
        assignments=(("a1", "W1", "D1", 0),),
        explain="",
    )
    t0 = time_module.perf_counter()
    out = sched.schedule(ctx, alloc)
    elapsed = (time_module.perf_counter() - t0) * 1000.0
    assert isinstance(out, ScheduleDecision)
    assert out.per_agent is not None
    assert elapsed < 5000

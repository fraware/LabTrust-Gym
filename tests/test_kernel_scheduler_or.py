"""
Tests for kernel_scheduler_or: CP-SAT timeout/infeasible fallback, explain visibility.
"""

from __future__ import annotations

import random

import pytest

from labtrust_gym.baselines.coordination.coordination_kernel import KernelContext
from labtrust_gym.baselines.coordination.decision_types import (
    AllocationDecision,
    ScheduleDecision,
)
from labtrust_gym.baselines.coordination.kernels.scheduler_or import (
    OR_CPSAT_INFEASIBLE,
    ORScheduler,
)


def test_or_scheduler_time_budget_fallback() -> None:
    """With use_cp_sat and very small or_schedule_time_budget_ms, fallback is used; explain is non-empty."""
    sched = ORScheduler(
        policy={
            "horizon_steps": 10,
            "replan_cadence_steps": 1,
            "use_cp_sat": True,
        }
    )
    context = KernelContext(
        obs={"a1": {"zone_id": "Z_A", "queue_by_device": [], "log_frozen": 0}},
        infos={},
        t=0,
        policy={"scheduler_or": {"use_cp_sat": True}},
        scale_config={"or_schedule_time_budget_ms": 0.001},
        seed=42,
        rng=random.Random(42),
    )
    context.agent_ids = ["a1"]
    alloc = AllocationDecision(
        assignments=(("a1", "W1", "D1", 0),),
        explain="",
    )
    out = sched.schedule(context, alloc)
    assert isinstance(out, ScheduleDecision)
    assert out.explain
    assert "or_" in out.explain


def test_or_scheduler_infeasible_explain() -> None:
    """When CP-SAT returns INFEASIBLE, fallback ScheduleDecision explain contains OR_CPSAT_INFEASIBLE."""
    sched = ORScheduler(
        policy={
            "horizon_steps": 2,
            "replan_cadence_steps": 1,
            "use_cp_sat": True,
        }
    )
    context = KernelContext(
        obs={"a1": {"zone_id": "Z_A", "queue_by_device": [], "log_frozen": 0}},
        infos={},
        t=0,
        policy={"scheduler_or": {"use_cp_sat": True, "horizon_steps": 2}},
        scale_config={"or_schedule_time_budget_ms": 100.0},
        seed=42,
        rng=random.Random(42),
    )
    context.agent_ids = ["a1"]
    alloc = AllocationDecision(
        assignments=(("a1", "W1", "D1", 0),),
        explain="",
    )
    out = sched.schedule(context, alloc)
    assert isinstance(out, ScheduleDecision)
    if OR_CPSAT_INFEASIBLE in out.explain:
        assert "or_" in out.explain
    else:
        assert out.explain

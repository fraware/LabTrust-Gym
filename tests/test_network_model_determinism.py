"""
NetworkModel determinism: same seed and policy => same deliveries and metrics.

Network randomness is seeded solely from the RNG passed at init/reset.
"""

from __future__ import annotations

import random

from labtrust_gym.coordination.blackboard import BlackboardEvent
from labtrust_gym.coordination.network import NetworkModel


def _event(eid: int, t: int = 0) -> BlackboardEvent:
    return BlackboardEvent(
        id=eid,
        t_event=t,
        t_emit=t,
        type="QUEUE_HEAD",
        payload_hash="a1b2",
        payload_small={"device_id": "D1", "queue_head_work_id": None},
    )


def test_network_model_perfect_delivers_all_immediately() -> None:
    """With perfect=True, all events delivered to all agents at now_t."""
    rng = random.Random(42)
    policy = {"version": "0.1", "perfect": True}
    model = NetworkModel(agent_ids=["a", "b"], policy=policy, rng=rng)
    events = [_event(0), _event(1)]
    out = model.apply(events, 10)
    assert out["a"] == events
    assert out["b"] == events
    m = model.get_metrics()
    assert m["msg_count"] == 4
    assert m["p95_latency_ms"] == 0.0
    assert m["drop_rate"] == 0.0
    assert m.get("partition_events", 0) == 0


def test_network_model_same_seed_same_metrics() -> None:
    """Same seed and policy yields identical metrics (deterministic)."""
    agent_ids = ["a", "b", "c"]
    policy = {
        "version": "0.1",
        "perfect": False,
        "delay": {"p50_ms": 5, "p95_ms": 20},
        "drop_rate": 0.1,
        "reorder_window": 2,
        "partition_schedule": [],
    }
    events = [_event(i, i) for i in range(5)]

    def run(seed: int):
        rng = random.Random(seed)
        model = NetworkModel(agent_ids=agent_ids, policy=policy, rng=rng)
        model.apply(events, 0)
        for t in range(1, 20):
            model.apply([], t)
        return model.get_metrics()

    m1 = run(99)
    m2 = run(99)
    assert m1["msg_count"] == m2["msg_count"]
    assert m1["drop_rate"] == m2["drop_rate"]
    assert m1["p95_latency_ms"] == m2["p95_latency_ms"]


def test_network_model_reset_same_seed_reproducible() -> None:
    """Reset(seed) then apply yields same metrics as fresh model with same seed."""
    agent_ids = ["x", "y"]
    policy = {
        "version": "0.1",
        "perfect": False,
        "delay": {"p50_ms": 10, "p95_ms": 40},
        "drop_rate": 0.2,
        "partition_schedule": [],
    }
    events = [_event(0), _event(1)]

    rng_a = random.Random(123)
    model_a = NetworkModel(agent_ids=agent_ids, policy=policy, rng=rng_a)
    model_a.apply(events, 0)
    for t in range(1, 20):
        model_a.apply([], t)
    m_a = model_a.get_metrics()

    rng_b = random.Random(123)
    model_b = NetworkModel(agent_ids=agent_ids, policy=policy, rng=rng_b)
    model_b.reset(rng_b)
    model_b.apply(events, 0)
    for t in range(1, 20):
        model_b.apply([], t)
    m_b = model_b.get_metrics()

    assert m_a["msg_count"] == m_b["msg_count"]
    assert m_a["drop_rate"] == m_b["drop_rate"]
    assert m_a["partition_events"] == m_b["partition_events"]


def test_network_model_partition_events_in_metrics() -> None:
    """Partition schedule causes partition_events to appear in metrics."""
    agent_ids = ["a", "b"]
    policy = {
        "version": "0.1",
        "perfect": False,
        "delay": {"p50_ms": 0, "p95_ms": 0},
        "drop_rate": 0.0,
        "partition_schedule": [
            {"start_t": 0, "end_t": 5, "affected_agents": ["a"]},
        ],
    }
    rng = random.Random(0)
    model = NetworkModel(agent_ids=agent_ids, policy=policy, rng=rng)
    events = [_event(i) for i in range(3)]
    for t in range(6):
        model.apply(events if t < 3 else [], t)
    m = model.get_metrics()
    assert "partition_events" in m
    assert m.get("partition_events", 0) >= 0

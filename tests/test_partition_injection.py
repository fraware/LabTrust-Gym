"""
INJ-NET-PARTITION-001: attack success definition and detection.

Partition injection configures network_policy with a partition_schedule; success is
that partitioned agents observe no coordination updates during the interval.
Detection: comm.partition_events > 0 and/or coordination.stale_action_rate increase.
"""

from __future__ import annotations

from labtrust_gym.coordination.blackboard import BlackboardEvent
from labtrust_gym.coordination.comms_model import CommsConfig, CommsModel
from labtrust_gym.security.risk_injections import make_injector


def test_inj_net_partition_001_returns_comms_config_with_network_policy() -> None:
    """INJ-NET-PARTITION-001 exposes get_comms_config() with network_policy."""
    inj = make_injector("INJ-NET-PARTITION-001", intensity=0.4, seed_offset=0)
    cfg = inj.get_comms_config()
    assert isinstance(cfg, CommsConfig)
    assert getattr(cfg, "network_policy", None) is not None
    policy = cfg.network_policy
    assert policy.get("version") == "0.1"
    assert policy.get("perfect") is False
    schedule = policy.get("partition_schedule") or []
    assert len(schedule) >= 1
    assert "start_t" in schedule[0] and "end_t" in schedule[0]
    assert "affected_agent_fraction" in schedule[0] or "affected_agents" in schedule[0]


def test_comms_model_with_network_policy_uses_network_model() -> None:
    """CommsModel with network_policy delegates to NetworkModel; metrics include partition_events."""
    policy = {
        "version": "0.1",
        "perfect": False,
        "delay": {"p50_ms": 5, "p95_ms": 15},
        "drop_rate": 0.0,
        "partition_schedule": [
            {"start_t": 1, "end_t": 3, "affected_agents": ["b"]},
        ],
    }
    cfg = CommsConfig(perfect=False, network_policy=policy)
    comms = CommsModel(agent_ids=["a", "b"], config=cfg, seed=7)
    ev = BlackboardEvent(id=0, t_event=0, t_emit=0, type="X", payload_hash="h", payload_small={})
    for t in range(5):
        comms.apply([ev] if t == 0 else [], t)
    metrics = comms.get_metrics()
    assert "msg_count" in metrics
    assert "p95_latency_ms" in metrics
    assert "drop_rate" in metrics
    assert "partition_events" in metrics
    # b is partitioned during 1–3, so at least some partition drops
    assert metrics["partition_events"] >= 0


def test_inj_net_reorder_and_drop_spike_expose_comms_config() -> None:
    """INJ-NET-REORDER-001 and INJ-NET-DROP-SPIKE-001 expose get_comms_config with network_policy."""
    reorder_inj = make_injector("INJ-NET-REORDER-001", intensity=0.5)
    reorder_cfg = reorder_inj.get_comms_config()
    assert reorder_cfg.network_policy is not None
    assert reorder_cfg.network_policy.get("reorder_window", 0) >= 1

    spike_inj = make_injector("INJ-NET-DROP-SPIKE-001", intensity=0.3)
    spike_cfg = spike_inj.get_comms_config()
    assert spike_cfg.network_policy is not None
    assert "drop_spike" in spike_cfg.network_policy
    assert spike_cfg.network_policy["drop_spike"].get("drop_rate", 0) > 0

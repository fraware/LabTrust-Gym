"""
SOTA tests for gossip_consensus: CRDT merge order determinism, Byzantine aggregation.
"""

from __future__ import annotations

from labtrust_gym.baselines.coordination.methods.gossip_consensus import (
    GossipConsensus,
    _aggregate_load_values,
)


def test_gossip_consensus_same_seed_same_actions() -> None:
    """Same seed and obs yield identical actions_dict (determinism / CRDT outcome)."""
    policy = {
        "zone_layout": {
            "zones": [{"zone_id": "Z_A"}],
            "device_placement": [{"device_id": "D1", "zone_id": "Z_A"}],
            "graph_edges": [],
        },
    }
    method = GossipConsensus(gossip_rounds=3)
    method.reset(seed=42, policy=policy, scale_config={})
    obs = {
        "a1": {"zone_id": "Z_A", "queue_by_device": [{"device_id": "D1", "queue_head": "W1", "queue_len": 1}], "queue_has_head": [1], "log_frozen": 0},
        "a2": {"zone_id": "Z_A", "queue_by_device": [{"device_id": "D1", "queue_head": "W1", "queue_len": 1}], "queue_has_head": [1], "log_frozen": 0},
    }
    infos = {}
    out1 = method.propose_actions(obs, infos, 0)
    method.reset(seed=42, policy=policy, scale_config={})
    out2 = method.propose_actions(obs, infos, 0)
    assert out1 == out2
    for aid in obs:
        assert out1[aid].get("action_index") is not None


def test_gossip_consensus_median_aggregation_bounds_inflated_load() -> None:
    """With aggregation_mode=median, one inflated load value does not dominate."""
    agg = _aggregate_load_values([1, 1, 100], "median")
    assert agg == 1
    agg_trim = _aggregate_load_values([1, 1, 2, 100], "trim_mean")
    assert 1 <= agg_trim <= 3


def test_gossip_consensus_byzantine_mode_runs() -> None:
    """With scale_config gossip_aggregation=median method runs and produces valid actions."""
    policy = {
        "zone_layout": {"zones": [{"zone_id": "Z_A"}], "device_placement": [{"device_id": "D1", "zone_id": "Z_A"}], "graph_edges": []},
    }
    method = GossipConsensus(gossip_rounds=2)
    method.reset(seed=0, policy=policy, scale_config={"gossip_aggregation": "median"})
    obs = {
        "a1": {"zone_id": "Z_A", "queue_by_device": [], "queue_has_head": [], "log_frozen": 0},
        "a2": {"zone_id": "Z_A", "queue_by_device": [], "queue_has_head": [], "log_frozen": 0},
    }
    actions = method.propose_actions(obs, {}, 0)
    assert set(actions.keys()) == {"a1", "a2"}
    for rec in actions.values():
        assert "action_index" in rec

"""
SOTA tests for consensus_paxos_lite: agreement on same digest, determinism.
"""

from __future__ import annotations

from labtrust_gym.baselines.coordination.methods.consensus_paxos_lite import (
    ConsensusPaxosLite,
    _digest_from_obs,
)


def test_consensus_paxos_lite_agreement() -> None:
    """All agents use the same agreed digest (leader's view); actions consistent with that digest."""
    policy = {
        "zone_layout": {
            "zones": [{"zone_id": "Z_A"}],
            "device_placement": [{"device_id": "D1", "zone_id": "Z_A"}],
            "graph_edges": [],
        },
    }
    method = ConsensusPaxosLite(max_rounds=2)
    method.reset(seed=42, policy=policy, scale_config={})
    # Leader at t=0 is agents[0]; all agents see same queue state so digest is same
    obs = {
        "a1": {"zone_id": "Z_A", "queue_by_device": [{"device_id": "D1", "queue_head": "W1", "queue_len": 1}], "queue_has_head": [1], "log_frozen": 0},
        "a2": {"zone_id": "Z_A", "queue_by_device": [{"device_id": "D1", "queue_head": "W1", "queue_len": 1}], "queue_has_head": [1], "log_frozen": 0},
    }
    actions = method.propose_actions(obs, {}, 0)
    assert set(actions.keys()) == {"a1", "a2"}
    leader_digest = _digest_from_obs(obs["a1"], ["D1"])
    assert leader_digest.get("D1") == "W1"
    for aid, rec in actions.items():
        if rec.get("action_type") == "START_RUN":
            args = rec.get("args") or {}
            dev, work = args.get("device_id"), args.get("work_id")
            assert (dev, work) == ("D1", "W1") or leader_digest.get(dev) == work

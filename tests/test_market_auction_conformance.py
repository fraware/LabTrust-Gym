"""
Conformance and SOTA tests for market_auction: RBAC, forbidden_edges, determinism.
"""

from __future__ import annotations

from labtrust_gym.baselines.coordination.methods.market_auction import MarketAuction


def test_market_auction_forbidden_edges_excluded() -> None:
    """With scale_config forbidden_edges=(agent, (device_id, work_id)), that pair never wins."""
    policy = {
        "pz_to_engine": {"a1": "a1", "a2": "a2"},
        "zone_layout": {
            "zones": [{"zone_id": "Z_A"}],
            "device_placement": [{"device_id": "D1", "zone_id": "Z_A"}, {"device_id": "D2", "zone_id": "Z_A"}],
            "graph_edges": [],
        },
    }
    forbidden_edges = [("a1", ("D1", "W1"))]
    scale_config = {"forbidden_edges": forbidden_edges}
    method = MarketAuction(collusion=False)
    method.reset(seed=42, policy=policy, scale_config=scale_config)
    obs = {
        "a1": {
            "zone_id": "Z_A",
            "queue_by_device": [
                {"device_id": "D1", "queue_head": "W1", "queue_len": 1},
                {"device_id": "D2", "queue_head": "W2", "queue_len": 1},
            ],
            "queue_has_head": [1, 1],
            "log_frozen": 0,
        },
        "a2": {
            "zone_id": "Z_A",
            "queue_by_device": [
                {"device_id": "D1", "queue_head": "W1", "queue_len": 1},
                {"device_id": "D2", "queue_head": "W2", "queue_len": 1},
            ],
            "queue_has_head": [1, 1],
            "log_frozen": 0,
        },
    }
    actions = method.propose_actions(obs, {}, 0)
    for aid, rec in actions.items():
        if rec.get("action_type") == "START_RUN":
            args = rec.get("args") or {}
            dev, work = args.get("device_id"), args.get("work_id")
            assert (aid, (dev, work)) not in forbidden_edges
    a1_rec = actions.get("a1") or {}
    if a1_rec.get("action_type") == "START_RUN":
        args = a1_rec.get("args") or {}
        assert (args.get("device_id"), args.get("work_id")) != ("D1", "W1"), "forbidden (a1, (D1, W1)) must not win"

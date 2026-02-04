"""
Hierarchical coordination determinism: same seed and obs yield same partition, same actions.
"""

from __future__ import annotations

import random

from labtrust_gym.baselines.coordination.hierarchical.region_partition import (
    partition_zones_into_regions,
    zone_to_region_map,
)
from labtrust_gym.baselines.coordination.hierarchical.hub_planner import HubPlanner
from labtrust_gym.baselines.coordination.hierarchical import HierarchicalHubLocal


def test_region_partition_deterministic() -> None:
    zone_ids = ["Z_A", "Z_B", "Z_C", "Z_D", "Z_E"]
    scale_config = {"num_sites": 2}
    m1 = zone_to_region_map(zone_ids, scale_config=scale_config)
    m2 = zone_to_region_map(zone_ids, scale_config=scale_config)
    assert m1 == m2
    assert set(m1.values()) <= {"R_0", "R_1"}
    assert len(set(m1.keys())) == 5


def test_region_partition_same_zones_same_regions() -> None:
    zone_ids = ["Z_X", "Z_Y"]
    m = zone_to_region_map(zone_ids, num_regions=2)
    assert m["Z_X"] in ("R_0", "R_1")
    assert m["Z_Y"] in ("R_0", "R_1")
    m2 = zone_to_region_map(sorted(zone_ids), num_regions=2)
    assert m == m2


def test_hierarchical_hub_local_same_seed_same_actions() -> None:
    policy = {
        "zone_layout": {
            "zones": [{"zone_id": "Z_A"}, {"zone_id": "Z_B"}],
            "device_placement": [
                {"device_id": "D1", "zone_id": "Z_A"},
                {"device_id": "D2", "zone_id": "Z_B"},
            ],
            "graph_edges": [{"from": "Z_A", "to": "Z_B"}],
        },
    }
    scale_config = {"num_sites": 2}
    obs = {
        "A1": {
            "zone_id": "Z_A",
            "queue_has_head": [1, 0],
            "queue_by_device": [
                {"device_id": "D1", "queue_head": "W1", "queue_len": 1},
                {"device_id": "D2", "queue_head": "", "queue_len": 0},
            ],
            "log_frozen": 0,
        },
        "A2": {
            "zone_id": "Z_B",
            "queue_has_head": [0, 1],
            "queue_by_device": [
                {"device_id": "D1", "queue_head": "", "queue_len": 0},
                {"device_id": "D2", "queue_head": "W2", "queue_len": 1},
            ],
            "log_frozen": 0,
        },
    }
    method = HierarchicalHubLocal(ack_deadline_steps=10, sla_horizon=20)
    method.reset(seed=42, policy=policy, scale_config=scale_config)
    infos: dict = {}
    actions1 = method.propose_actions(obs, infos, 0)
    method.reset(seed=42, policy=policy, scale_config=scale_config)
    actions2 = method.propose_actions(obs, infos, 0)
    assert actions1 == actions2


def test_hub_planner_deterministic() -> None:
    hub = HubPlanner(sla_horizon=20)
    zone_to_region = {"Z_A": "R_0", "Z_B": "R_0", "Z_C": "R_1"}
    device_zone = {"D1": "Z_A", "D2": "Z_B", "D3": "Z_C"}
    device_ids = ["D1", "D2", "D3"]
    obs = {
        "A1": {
            "queue_by_device": [
                {"device_id": "D1", "queue_head": "W1"},
                {"device_id": "D2", "queue_head": ""},
                {"device_id": "D3", "queue_head": ""},
            ],
            "log_frozen": 0,
        },
    }
    rng = random.Random(99)
    m1 = hub.assign(obs, zone_to_region, device_zone, device_ids, t=0, rng=rng)
    rng2 = random.Random(99)
    m2 = hub.assign(obs, zone_to_region, device_zone, device_ids, t=0, rng=rng2)
    assert m1 == m2

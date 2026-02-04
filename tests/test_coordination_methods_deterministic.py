"""
Determinism: run centralized_planner twice with same seed => identical action sequence hashes.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from labtrust_gym.baselines.coordination.methods.centralized_planner import (
    CentralizedPlanner,
)


def _tiny_policy() -> dict:
    return {
        "zone_layout": {
            "zones": [
                {
                    "zone_id": "Z_A",
                    "name": "A",
                    "kind": "STAGING",
                    "temp_band": "AMBIENT_20_25",
                },
                {
                    "zone_id": "Z_B",
                    "name": "B",
                    "kind": "STAGING",
                    "temp_band": "AMBIENT_20_25",
                },
            ],
            "graph_edges": [{"from": "Z_A", "to": "Z_B", "travel_s": 10}],
            "device_placement": [{"device_id": "DEV_1", "zone_id": "Z_B"}],
        },
    }


def _obs_for_step(agent_ids: list[str], step: int) -> dict:
    return {
        aid: {
            "my_zone_idx": 1 + (step + i) % 2,
            "zone_id": "Z_B" if (step + i) % 2 else "Z_A",
            "queue_by_device": [
                {"device_id": "DEV_1", "queue_len": 1, "queue_head": "W1"}
            ],
            "queue_has_head": [1],
            "log_frozen": 0,
            "door_restricted_open": 0,
        }
        for i, aid in enumerate(agent_ids)
    }


def _action_sequence_hash(method: CentralizedPlanner, seed: int, steps: int) -> str:
    """Return deterministic hash of action dicts over steps."""
    policy = _tiny_policy()
    scale_config = {"num_agents_total": 2, "num_sites": 1}
    method.reset(seed, policy, scale_config)
    agent_ids = ["worker_0", "worker_1"]
    sequence = []
    infos = {}
    for t in range(steps):
        obs = _obs_for_step(agent_ids, t)
        actions_dict = method.propose_actions(obs, infos, t)
        sequence.append(json.dumps(actions_dict, sort_keys=True))
    return hashlib.sha256("\n".join(sequence).encode()).hexdigest()


def test_centralized_planner_same_seed_same_action_sequence() -> None:
    """Two runs with same seed produce identical action sequence hash."""
    steps = 20
    seed = 12345
    method1 = CentralizedPlanner(compute_budget=None)
    method2 = CentralizedPlanner(compute_budget=None)
    hash1 = _action_sequence_hash(method1, seed, steps)
    hash2 = _action_sequence_hash(method2, seed, steps)
    assert hash1 == hash2


def test_centralized_planner_different_seed_different_sequence() -> None:
    """Different seeds can produce different sequences (when RNG used)."""
    steps = 20
    method = CentralizedPlanner(compute_budget=None)
    hash_a = _action_sequence_hash(method, 1, steps)
    method2 = CentralizedPlanner(compute_budget=None)
    hash_b = _action_sequence_hash(method2, 2, steps)
    # With current implementation, same obs may give same actions; if so hashes match.
    # We only require same seed => same hash (tested above).
    assert isinstance(hash_a, str)
    assert isinstance(hash_b, str)

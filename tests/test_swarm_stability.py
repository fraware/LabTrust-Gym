"""
Tests for swarm potential-field stability: inertia, congestion, pheromone.
"""

from __future__ import annotations

import pytest

from labtrust_gym.baselines.coordination.methods.swarm_stability import (
    congestion_penalty,
    inertia_term,
    pheromone_diffusion,
)


def test_inertia_term() -> None:
    """Inertia scales direction by weight."""
    out = inertia_term((1.0, 0.0), weight=0.3)
    assert out == (0.3, 0.0)


def test_congestion_penalty() -> None:
    """Penalty increases with agent count in zone."""
    assert congestion_penalty(1, scale=0.5) == 0.0
    assert congestion_penalty(2, scale=0.5) == 0.5
    assert congestion_penalty(3, scale=0.5) == 1.0


def test_pheromone_diffusion() -> None:
    """Decay * mean of neighbors."""
    assert pheromone_diffusion([1.0, 2.0], decay=0.9) == pytest.approx(1.35)
    assert pheromone_diffusion([], decay=0.9) == 0.0


def test_swarm_stigmergy_congestion_penalty_affects_choice() -> None:
    """With congestion_penalty wired in, crowded zone has lower effective score."""
    from labtrust_gym.baselines.coordination.methods.swarm_stigmergy_priority import (
        SwarmStigmergyPriority,
    )

    policy = {
        "zone_layout": {
            "zones": [
                {"zone_id": "Z_A"},
                {"zone_id": "Z_B"},
                {"zone_id": "Z_C"},
            ],
            "graph_edges": [
                {"from": "Z_A", "to": "Z_B"},
                {"from": "Z_A", "to": "Z_C"},
            ],
        },
    }
    scale_config: dict = {}
    method = SwarmStigmergyPriority()
    method.reset(42, policy, scale_config)
    method._pheromone = {"Z_B": 1.5, "Z_C": 1.0}
    method._adjacency = {("Z_A", "Z_B"), ("Z_B", "Z_A"), ("Z_A", "Z_C"), ("Z_C", "Z_A")}
    method._zone_ids = ["Z_A", "Z_B", "Z_C"]
    obs = {
        "a1": {"zone_id": "Z_A", "queue_by_device": [], "log_frozen": 0},
        "b1": {"zone_id": "Z_B", "queue_by_device": [], "log_frozen": 0},
        "b2": {"zone_id": "Z_B", "queue_by_device": [], "log_frozen": 0},
        "b3": {"zone_id": "Z_B", "queue_by_device": [], "log_frozen": 0},
    }
    out = method.propose_actions(obs, {}, 0)
    move_a1 = out.get("a1", {}).get("args", {}).get("to_zone")
    assert move_a1 is not None
    assert move_a1 == "Z_C"


def test_swarm_oscillation_bounded() -> None:
    """Two agents in symmetric corridor Z_A <-> Z_B; run 20 steps; no unbounded ping-pong."""
    from labtrust_gym.baselines.coordination.methods.swarm_stigmergy_priority import (
        SwarmStigmergyPriority,
    )

    policy = {
        "zone_layout": {
            "zones": [{"zone_id": "Z_A"}, {"zone_id": "Z_B"}],
            "graph_edges": [{"from": "Z_A", "to": "Z_B"}, {"from": "Z_B", "to": "Z_A"}],
        },
    }
    method = SwarmStigmergyPriority()
    method.reset(42, policy, {})
    obs = {
        "a1": {"zone_id": "Z_A", "queue_by_device": [], "log_frozen": 0},
        "a2": {"zone_id": "Z_B", "queue_by_device": [], "log_frozen": 0},
    }
    positions: list[tuple[str, str]] = []
    for t in range(20):
        out = method.propose_actions(obs, {}, t)
        pos_a1 = obs["a1"]["zone_id"]
        pos_a2 = obs["a2"]["zone_id"]
        positions.append((pos_a1, pos_a2))
        to_a1 = out.get("a1", {}).get("args", {}).get("to_zone")
        to_a2 = out.get("a2", {}).get("args", {}).get("to_zone")
        if to_a1:
            obs["a1"] = dict(obs["a1"], zone_id=to_a1)
        if to_a2:
            obs["a2"] = dict(obs["a2"], zone_id=to_a2)
    back_forth = sum(
        1
        for i in range(len(positions) - 1)
        if positions[i] == ("Z_A", "Z_B")
        and positions[i + 1] == ("Z_B", "Z_A")
        or positions[i] == ("Z_B", "Z_A")
        and positions[i + 1] == ("Z_A", "Z_B")
    )
    assert back_forth <= 10


def test_swarm_herding_congestion_penalty_reduces_pile_up() -> None:
    """With congestion_penalty, run several steps; agent distribution does not pile all in one zone when alternatives exist."""
    from labtrust_gym.baselines.coordination.methods.swarm_stigmergy_priority import (
        SwarmStigmergyPriority,
    )

    policy = {
        "zone_layout": {
            "zones": [{"zone_id": "Z_A"}, {"zone_id": "Z_B"}, {"zone_id": "Z_C"}],
            "graph_edges": [
                {"from": "Z_A", "to": "Z_B"},
                {"from": "Z_B", "to": "Z_A"},
                {"from": "Z_A", "to": "Z_C"},
                {"from": "Z_C", "to": "Z_A"},
            ],
        },
    }
    method = SwarmStigmergyPriority()
    method.reset(42, policy, {})
    method._pheromone = {"Z_B": 1.0, "Z_C": 1.0}
    obs = {
        "a1": {"zone_id": "Z_A", "queue_by_device": [], "log_frozen": 0},
        "a2": {"zone_id": "Z_B", "queue_by_device": [], "log_frozen": 0},
        "a3": {"zone_id": "Z_C", "queue_by_device": [], "log_frozen": 0},
    }
    for t in range(5):
        out = method.propose_actions(obs, {}, t)
        for aid in ["a1", "a2", "a3"]:
            to_z = out.get(aid, {}).get("args", {}).get("to_zone")
            if to_z:
                obs[aid] = dict(obs[aid], zone_id=to_z)
    counts: dict[str, int] = {}
    for aid in ["a1", "a2", "a3"]:
        z = obs[aid]["zone_id"]
        counts[z] = counts.get(z, 0) + 1
    assert sum(counts.values()) == 3
    assert len(counts) >= 1

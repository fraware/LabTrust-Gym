"""
SOTA tests for swarm methods: oscillation (no infinite A/B ping-pong),
herding (congestion_penalty reduces pile-ups), and stability parameters.
Parametrized for swarm_reactive and swarm_stigmergy_priority where applicable.
"""

from __future__ import annotations

import pytest

from labtrust_gym.baselines.coordination.interface import CoordinationMethod
from labtrust_gym.baselines.coordination.methods.swarm_reactive import SwarmReactive
from labtrust_gym.baselines.coordination.methods.swarm_stigmergy_priority import (
    SwarmStigmergyPriority,
)


def _make_reactive() -> CoordinationMethod:
    return SwarmReactive()


def _make_stigmergy() -> CoordinationMethod:
    return SwarmStigmergyPriority()


@pytest.mark.parametrize(
    "method_factory", [_make_reactive, _make_stigmergy], ids=["swarm_reactive", "swarm_stigmergy_priority"]
)
def test_swarm_symmetric_corridor_no_infinite_pingpong(method_factory) -> None:
    """Symmetric corridor Z_A - Z_B: two agents; stability terms damp flip-flop; no unbounded oscillation."""
    policy = {
        "zone_layout": {
            "zones": [{"zone_id": "Z_A"}, {"zone_id": "Z_B"}],
            "device_placement": [],
            "graph_edges": [{"from": "Z_A", "to": "Z_B"}, {"from": "Z_B", "to": "Z_A"}],
        },
    }
    method = method_factory()
    method.reset(seed=42, policy=policy, scale_config={"inertia_weight": 0.5, "congestion_penalty_scale": 0.5})
    state = {"a1": "Z_A", "a2": "Z_B"}
    max_steps = 25
    pingpong_count = 0
    prev_pair = None
    for t in range(max_steps):
        obs = {
            aid: {"zone_id": z, "queue_by_device": [], "queue_has_head": [], "log_frozen": 0}
            for aid, z in state.items()
        }
        actions = method.propose_actions(obs, {}, t)
        assert set(actions.keys()) == {"a1", "a2"}
        for rec in actions.values():
            assert rec.get("action_type") in ("NOOP", "MOVE", "QUEUE_RUN", "START_RUN", "TICK", None)
        for aid, rec in actions.items():
            if (rec.get("action_type") or "") == "MOVE":
                to_z = (rec.get("args") or {}).get("to_zone")
                if to_z:
                    state[aid] = to_z
        pair = (state["a1"], state["a2"])
        if prev_pair is not None and prev_pair == ("Z_B", "Z_A") and pair == ("Z_A", "Z_B"):
            pingpong_count += 1
        prev_pair = pair
    assert pingpong_count <= 5, "Oscillation (A/B ping-pong) should be bounded by stability terms"


@pytest.mark.parametrize(
    "method_factory", [_make_reactive, _make_stigmergy], ids=["swarm_reactive", "swarm_stigmergy_priority"]
)
def test_swarm_herding_congestion_reduces_pileup(method_factory) -> None:
    """Multiple agents in same zone; with congestion_penalty at least one can move away."""
    policy = {
        "zone_layout": {
            "zones": [{"zone_id": "Z_A"}, {"zone_id": "Z_B"}],
            "device_placement": [{"device_id": "D1", "zone_id": "Z_B"}],
            "graph_edges": [{"from": "Z_A", "to": "Z_B"}, {"from": "Z_B", "to": "Z_A"}],
        },
    }
    method = method_factory()
    method.reset(seed=0, policy=policy, scale_config={"congestion_penalty_scale": 0.8})
    obs = {
        "a1": {
            "zone_id": "Z_A",
            "queue_by_device": [{"queue_len": 1, "queue_head": ""}],
            "queue_has_head": [0],
            "log_frozen": 0,
        },
        "a2": {
            "zone_id": "Z_A",
            "queue_by_device": [{"queue_len": 1, "queue_head": ""}],
            "queue_has_head": [0],
            "log_frozen": 0,
        },
        "a3": {
            "zone_id": "Z_A",
            "queue_by_device": [{"queue_len": 1, "queue_head": ""}],
            "queue_has_head": [0],
            "log_frozen": 0,
        },
    }
    actions = method.propose_actions(obs, {}, 0)
    move_count = sum(1 for r in actions.values() if (r.get("action_type") or "") == "MOVE")
    assert move_count >= 1
    for rec in actions.values():
        assert rec.get("action_type") in ("NOOP", "MOVE", "QUEUE_RUN", "START_RUN", "TICK", None)


def test_swarm_stigmergy_beats_reactive_throughput() -> None:
    """Same seed and layout: 3 agents, 2 zones, device in Z_B; stigmergy >= reactive throughput."""
    policy = {
        "zone_layout": {
            "zones": [{"zone_id": "Z_A"}, {"zone_id": "Z_B"}],
            "device_placement": [{"device_id": "D1", "zone_id": "Z_B"}],
            "graph_edges": [{"from": "Z_A", "to": "Z_B"}, {"from": "Z_B", "to": "Z_A"}],
        },
    }
    scale = {"inertia_weight": 0.3, "congestion_penalty_scale": 0.5}

    def run_start_run_count(method: CoordinationMethod, steps: int, seed: int) -> int:
        method.reset(seed=seed, policy=policy, scale_config=scale)
        state: dict[str, str] = {"a1": "Z_A", "a2": "Z_A", "a3": "Z_B"}
        start_run_count = 0
        for t in range(steps):
            obs = {}
            for aid, z in state.items():
                in_z_b = z == "Z_B"
                obs[aid] = {
                    "zone_id": z,
                    "queue_by_device": [{"queue_len": 1, "queue_head": "W1"}] if in_z_b else [],
                    "queue_has_head": [1] if in_z_b else [0],
                    "log_frozen": 0,
                }
            actions = method.propose_actions(obs, {}, t)
            for aid, rec in actions.items():
                if (rec.get("action_type") or "") == "START_RUN":
                    start_run_count += 1
                atype = rec.get("action_type")
                args = rec.get("args") or {}
                if atype == "MOVE" and "to_zone" in args:
                    state[aid] = args["to_zone"]
        return start_run_count

    reactive = SwarmReactive()
    stigmergy = SwarmStigmergyPriority()
    n_steps = 15
    seed = 77
    count_reactive = run_start_run_count(reactive, n_steps, seed)
    count_stigmergy = run_start_run_count(stigmergy, n_steps, seed)
    assert count_stigmergy >= count_reactive
